"""
任务执行引擎 - 双模式 (Celery / 本地轻量模式)

核心业务逻辑抽离层:
  - run_document_pipeline: 纯异步函数，执行 LangGraph 工作流
  - ProgressStore: 进度存储抽象层 (Redis / 内存)
  - update_doc_status: 更新 SQLite 文档状态

Celery 模式: 进度写入 Redis → SSE 通过 Redis Pub/Sub 推送
本地模式:   进度写入内存 dict → SSE 通过轮询内存 / SQLite 推送
"""

import asyncio
import json
import logging
import os
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(BASE_DIR, "ai_models_config.json")

NODE_PROGRESS_MAP = {
    "gateway": (5, "正在路由分析文件类型..."),
    "extract_context": (15, "正在提取文档内容与图片..."),
    "retrieve_knowledge": (25, "正在检索知识库..."),
    "reason_and_fill": (45, "正在AI推理填充..."),
    "critic_review": (55, "正在审查校验..."),
    "increment_retry": (60, "正在重试优化..."),
    "process_excel": (40, "正在分析Excel数据..."),
    "process_ppt": (40, "正在分析PPT结构..."),
    "supervisor": (20, "正在智能调度任务..."),
    "web_researcher": (30, "正在联网检索资料..."),
    "knowledge_librarian": (25, "正在检索知识库..."),
    "generate_ppt": (65, "正在生成PPT..."),
    "generate_summary": (65, "正在生成深度总结..."),
    "generate_ppt_entry": (20, "正在路由至PPT生成..."),
}


class ProgressStore:
    _instance = None
    _store: Dict[str, dict] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def set(self, task_id: str, payload: dict):
        self._store[task_id] = payload

    def get(self, task_id: str) -> Optional[dict]:
        return self._store.get(task_id)

    def delete(self, task_id: str):
        self._store.pop(task_id, None)

    def all_keys(self):
        return list(self._store.keys())


progress_store = ProgressStore()


def push_progress(task_id: str, progress: int, action: str, extra: dict = None, use_redis: bool = True):
    payload = {
        "task_id": task_id,
        "progress": progress,
        "action": action,
        "timestamp": time.time(),
    }
    if extra:
        payload.update(extra)

    progress_store.set(task_id, payload)

    if use_redis:
        try:
            import redis as redis_lib
            from app.core.celery_app import REDIS_PASSWORD, REDIS_HOST, REDIS_PORT
            if REDIS_PASSWORD:
                url = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/0"
            else:
                url = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"
            r = redis_lib.from_url(url, decode_responses=True)
            r.set(f"task_progress:{task_id}", json.dumps(payload, ensure_ascii=False), ex=3600)
            r.publish(f"task_channel:{task_id}", json.dumps(payload, ensure_ascii=False))
            r.close()
        except Exception as e:
            logger.debug(f"Redis push skipped (local mode): {e}")


def update_doc_status(doc_ids: list, status: str):
    if not doc_ids:
        return
    try:
        from app.models.database import DocumentMeta, get_session
        session = get_session()
        try:
            for doc_id in doc_ids:
                doc = session.query(DocumentMeta).filter(DocumentMeta.id == doc_id).first()
                if doc:
                    doc.status = status
            session.commit()
        except Exception as e:
            logger.warning(f"Failed to update doc status: {e}")
            session.rollback()
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"Failed to update doc status (outer): {e}")


def _init_services():
    from app.services.ai_client import UnifiedAIClient

    llm_client = None
    rag_engine = None

    try:
        llm_client = UnifiedAIClient(config_path=CONFIG_PATH)
        if not llm_client.langchain_initialized:
            logger.error(f"LLM Client init failed | config_path={CONFIG_PATH}")
            llm_client = None
        else:
            logger.info(f"LLM Client initialized | model={llm_client.selected_model}")
    except Exception as e:
        logger.error(f"LLM Client init exception: {e}", exc_info=True)
        llm_client = None

    try:
        from app.services.rag_engine import RAGEngine

        ai_config = {}
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                ai_config = json.load(f)

        embedding_config = ai_config.get("embedding", {})
        embedding_api_key = embedding_config.get("api_key") or os.getenv("EMBEDDING_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
        embedding_base_url = embedding_config.get("base_url", "https://api.siliconflow.cn/v1")
        embedding_model = embedding_config.get("model", "BAAI/bge-m3")
        embedding_dimension = embedding_config.get("dimension", 1024)

        rag_engine = RAGEngine(
            embedding_api_key=embedding_api_key,
            embedding_base_url=embedding_base_url,
            embedding_model=embedding_model,
            embedding_dimension=embedding_dimension,
            ai_client=llm_client,
        )
        logger.info(f"RAG Engine initialized | model={embedding_model}")
    except Exception as e:
        logger.warning(f"RAG Engine init failed (non-fatal): {e}")
        rag_engine = None

    return llm_client, rag_engine


def _try_use_app_state_services():
    try:
        from app.core.app_state import app_state
        llm = getattr(app_state, "llm_client", None)
        rag = getattr(app_state, "rag_engine", None)
        if llm and getattr(llm, "langchain_initialized", False):
            return llm, rag
    except Exception:
        pass
    return None, None


async def run_document_pipeline(
    task_id: str,
    uploaded_files: list,
    user_instruction: str = "",
    max_retries: int = 3,
    thread_id: str = "",
    user_id: str = "",
    doc_ids: list = None,
    use_redis: bool = True,
) -> dict:
    """
    核心文档处理管道 (纯异步函数，与调度引擎解耦)

    可被以下两种方式调用:
      - Celery Worker: asyncio.run(run_document_pipeline(..., use_redis=True))
      - FastAPI BackgroundTasks: await run_document_pipeline(..., use_redis=False)
    """
    push_progress(task_id, 0, "任务已接收，正在初始化...", use_redis=use_redis)

    try:
        result = await _run_workflow(
            task_id, uploaded_files, user_instruction, max_retries, thread_id, user_id, use_redis
        )
        push_progress(task_id, 100, "处理完成！", extra={"status": "success", "result": result}, use_redis=use_redis)
        update_doc_status(doc_ids, "completed")
        return result
    except Exception as e:
        logger.error(f"Pipeline {task_id} failed: {e}", exc_info=True)
        push_progress(task_id, -1, f"处理失败: {str(e)}", extra={"status": "error", "error": str(e)}, use_redis=use_redis)
        update_doc_status(doc_ids, "failed")
        raise


async def _run_workflow(
    task_id: str,
    uploaded_files: list,
    user_instruction: str,
    max_retries: int,
    thread_id: str,
    user_id: str = "",
    use_redis: bool = True,
) -> dict:
    import json as _json

    from app.agent_workflow.graph import build_workflow_graph, NODE_DISPLAY_NAMES

    push_progress(task_id, 1, "正在初始化 AI 服务...", use_redis=use_redis)

    llm_client, rag_engine = _try_use_app_state_services()
    if not llm_client:
        llm_client, rag_engine = _init_services()

    if not llm_client:
        raise RuntimeError(
            f"AI 服务未初始化，请检查配置或 API_KEY 是否有效 | "
            f"config_path={CONFIG_PATH} | exists={os.path.exists(CONFIG_PATH)}"
        )

    if not rag_engine:
        logger.warning("RAG Engine not available, proceeding without knowledge retrieval")

    graph = build_workflow_graph(rag_engine, llm_client, max_retries)

    file_path = ""
    file_type = ""
    if uploaded_files:
        file_path = uploaded_files[0].get("path", "")
        file_type = uploaded_files[0].get("type", "")

    update_state = {
        "user_instruction": user_instruction,
        "max_retries": max_retries,
        "uploaded_files": uploaded_files,
        "user_id": user_id,
    }
    if file_path:
        update_state["file_path"] = file_path
    if file_type:
        update_state["file_type"] = file_type

    config = {"configurable": {"thread_id": thread_id}} if thread_id else None

    push_progress(task_id, 2, "正在启动工作流引擎...", use_redis=use_redis)

    final_output_path = ""
    final_file_type = ""
    final_filled_html = ""
    final_image_store = {}
    final_structured_data = {}
    final_ppt_data = {}

    async for event in graph.astream(update_state, config=config):
        for node_name, node_state in event.items():
            if not isinstance(node_state, dict):
                continue

            progress_info = NODE_PROGRESS_MAP.get(node_name)
            if progress_info:
                progress_val, action_text = progress_info
                state_progress = node_state.get("current_progress", 0)
                state_action = node_state.get("current_action", "")
                if state_progress > 0:
                    progress_val = state_progress
                if state_action:
                    action_text = state_action
                push_progress(task_id, progress_val, action_text, extra={
                    "node": node_name,
                    "agent": NODE_DISPLAY_NAMES.get(node_name, node_name),
                }, use_redis=use_redis)

            ft = node_state.get("file_type", "")
            if ft:
                final_file_type = ft

            filled = node_state.get("filled_html", "")
            if filled:
                final_filled_html = filled

            img_store = node_state.get("image_store", {})
            if img_store:
                final_image_store = img_store

            sd = node_state.get("structured_data", {})
            if sd:
                final_structured_data = sd

            pd = node_state.get("ppt_data", {})
            if pd:
                final_ppt_data = pd

            output = node_state.get("output_path", "")
            if output:
                final_output_path = output

    push_progress(task_id, 90, "正在整理最终结果...", use_redis=use_redis)

    download_url = ""
    if final_output_path and os.path.exists(final_output_path):
        filename = os.path.basename(final_output_path)
        download_url = f"/api/v1/files/output/{filename}"

    preview_html = ""
    if final_filled_html:
        try:
            from app.services.document_service import restore_images_to_html
            preview_html = restore_images_to_html(final_filled_html, final_image_store)
        except Exception as e:
            logger.warning(f"restore_images_to_html failed: {e}")
            preview_html = final_filled_html

    result = {
        "file_type": final_file_type,
        "filled_html": preview_html,
        "structured_data": _json_safe(final_structured_data),
        "ppt_data": _json_safe(final_ppt_data),
        "download_url": download_url,
        "output_path": final_output_path,
    }

    return result


def _json_safe(obj):
    try:
        return json.loads(json.dumps(obj, ensure_ascii=False, default=str))
    except Exception:
        return {}


def run_document_pipeline_sync(
    task_id: str,
    uploaded_files: list,
    user_instruction: str = "",
    max_retries: int = 3,
    thread_id: str = "",
    user_id: str = "",
    doc_ids: list = None,
    use_redis: bool = True,
):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                asyncio.run,
                run_document_pipeline(
                    task_id, uploaded_files, user_instruction, max_retries,
                    thread_id, user_id, doc_ids, use_redis,
                ),
            )
            return future.result()
    else:
        return asyncio.run(
            run_document_pipeline(
                task_id, uploaded_files, user_instruction, max_retries,
                thread_id, user_id, doc_ids, use_redis,
            ),
        )
