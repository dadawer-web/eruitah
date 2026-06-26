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


def update_doc_status(doc_ids: list, status: str, filled_html: str = ""):
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
                    if filled_html:
                        doc.filled_html = filled_html
            session.commit()
        except Exception as e:
            logger.warning(f"Failed to update doc status: {e}")
            session.rollback()
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"Failed to update doc status (outer): {e}")


# 追问报告的分隔线：将新报告与旧报告优雅隔开
_FOLLOWUP_DIVIDER = (
    "<div style='margin: 40px 0; border-bottom: 2px dashed #cbd5e1;'>"
    "<span style='background: white; padding: 0 10px; color: #6b7280;'>"
    "👇 追加分析结果</span></div>"
)


def persist_task_result(
    task_id: str,
    user_id: str,
    filled_html: str,
    user_instruction: str = "",
    status: str = "completed",
):
    """单会话流统一持久化：按 task_id 查 DocumentMeta，已有内容则追加（追问），否则覆盖（首轮）。

    追问绝不新建记录！只更新原始任务的 filled_html + history：
      - 已有 filled_html → 追问追加（旧 + 分隔线 + 新），history 追加本轮对话
      - filled_html 为空 → 首轮覆盖写入，history 初始化

    Args:
        task_id: 业务任务 ID（首轮=新uuid；追问=原任务ID，复用同一记录）
        user_id: 当前用户 id
        filled_html: 本轮生成的 HTML 报告
        user_instruction: 本轮用户指令（追问时含【追问】标记，会清洗后写入 history）
        status: 目标状态（completed / failed）；failed 时只改状态不动内容
    """
    if not task_id:
        return
    try:
        from app.models.database import DocumentMeta, get_session

        session = get_session()
        try:
            doc = session.query(DocumentMeta).filter(
                DocumentMeta.task_id == task_id,
                DocumentMeta.user_id == user_id,
            ).first()
            if not doc:
                logger.warning(f"persist_task_result: task {task_id} not found, skip")
                return

            # 失败路径：只回滚状态，不动已有内容/历史（追问失败时保留首轮报告可见）
            if status == "failed":
                doc.status = "failed"
                session.add(doc)
                session.commit()
                logger.info(f"persist_task_result: task {task_id} marked failed (content untouched)")
                return

            # 清洗出本轮用户的真实问句（剥离多轮 history 前缀）
            clean_query = (user_instruction or "").strip()
            if "【追问】" in clean_query:
                clean_query = clean_query.split("【追问】")[-1].strip()
            if len(clean_query) > 200:
                clean_query = clean_query[:200] + "…"

            existing_html = doc.filled_html or ""
            if existing_html:
                # 已有首轮报告 → 追问追加（绝不覆盖）
                # 解析已有 history 以计算本轮是第几次追问
                current_history = []
                if doc.history:
                    try:
                        current_history = json.loads(doc.history)
                        if not isinstance(current_history, list):
                            current_history = []
                    except Exception:
                        current_history = []
                # 轮次索引：首轮占 history[0]，追问从 history[1] 起成对存在
                # len//2+1：len=1→1, len=3→2, len=5→3
                turn_index = len(current_history) // 2 + 1

                # 结构化追问块：带唯一 id + data-* 便于后端定点清除
                block_start = (
                    f"<div class='followup-block' id='followup-block-{turn_index}' "
                    f"data-turn-index='{turn_index}'>"
                )
                divider = (
                    f"<div style='margin: 40px 0; border-bottom: 2px dashed #cbd5e1; text-align:center;'>"
                    f"<span style='background: white; padding: 0 10px; color: #6b7280;'>"
                    f"👇 第 {turn_index} 次追问结果</span></div>"
                )
                # 删除按钮用 span（非 button，因 DOMPurify ADD_TAGS 不含 button），
                # 配合前端事件委托（class + data-*，DOMPurify 允许）触发删除
                delete_btn = (
                    f"<div style='text-align: right; margin-bottom: 10px;'>"
                    f"<span class='followup-delete-btn' data-task-id='{task_id}' "
                    f"data-turn-index='{turn_index}' "
                    f"style='display:inline-block; color:#ef4444; background:#fef2f2; "
                    f"border:1px solid #fca5a5; padding:4px 10px; border-radius:4px; "
                    f"cursor:pointer; font-size:12px;'>🗑️ 撤销本次追问</span></div>"
                )
                block_end = "</div>"
                doc.filled_html = (
                    existing_html + block_start + divider + delete_btn
                    + (filled_html or "") + block_end
                )

                current_history.append({"role": "user", "content": clean_query})
                current_history.append({"role": "ai", "content": "已为您生成追加分析，请查看报告。"})
                doc.history = json.dumps(current_history, ensure_ascii=False)
                mode = f"append(turn={turn_index})"
            else:
                # 首轮 → 覆盖写入
                doc.filled_html = filled_html or ""
                doc.history = json.dumps(
                    [{"role": "user", "content": clean_query}],
                    ensure_ascii=False,
                )
                mode = "overwrite"

            doc.status = "completed"
            session.add(doc)
            session.commit()
            session.refresh(doc)
            logger.info(f"persist_task_result: task {task_id}, mode={mode}")
        except Exception as e:
            logger.error(f"persist_task_result failed: {e}", exc_info=True)
            session.rollback()
        finally:
            session.close()
    except Exception as e:
        logger.error(f"persist_task_result (outer) failed: {e}")


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

    单会话流持久化策略：
      - doc_ids 非空（首轮上传）→ update_doc_status 按 id 覆盖写入
      - doc_ids 为空（追问）→ persist_task_result 按 task_id 查原记录，
        已有 filled_html 则追加（旧+分隔线+新），否则覆盖
    """
    push_progress(task_id, 0, "任务已接收，正在初始化...", use_redis=use_redis)

    try:
        result = await _run_workflow(
            task_id, uploaded_files, user_instruction, max_retries, thread_id, user_id, use_redis
        )
        push_progress(task_id, 100, "处理完成！", extra={"status": "success", "result": result}, use_redis=use_redis)
        if doc_ids:
            # 首轮上传：按 DocumentMeta.id 覆盖写入
            update_doc_status(doc_ids, "completed", filled_html=result.get("filled_html", ""))
        else:
            # 追问：复用原任务记录，按 filled_html 判断追加/覆盖
            persist_task_result(
                task_id=task_id,
                user_id=user_id,
                filled_html=result.get("filled_html", ""),
                user_instruction=user_instruction,
            )
        return result
    except Exception as e:
        logger.error(f"Pipeline {task_id} failed: {e}", exc_info=True)
        push_progress(task_id, -1, f"处理失败: {str(e)}", extra={"status": "error", "error": str(e)}, use_redis=use_redis)
        if doc_ids:
            update_doc_status(doc_ids, "failed")
        else:
            # 追问失败：保留首轮报告可见，仅记录失败状态
            persist_task_result(
                task_id=task_id, user_id=user_id, filled_html="",
                user_instruction=user_instruction, status="failed",
            )
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

    # 始终使用 task_id 作为 thread_id，确保 LangGraph Checkpointer 正常工作
    config = {"configurable": {"thread_id": str(thread_id or task_id)}}

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
