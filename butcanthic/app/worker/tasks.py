import asyncio
import json
import logging
import os
import re

from app.core.celery_app import celery_app
from app.core.task_runner import run_document_pipeline
from app.services.kb_processor import process_kb_files_sync

logger = logging.getLogger(__name__)

FLASHCARD_SYSTEM_PROMPT = """你是一个严苛的考试出题专家。请从以下文本中提取出最核心的 5-10 个概念，生成 Q&A 形式的闪卡。

要求：
- 问题要求简明扼要，直击核心
- 答案要求一语中的，不超过 50 字
- 优先提取定义、原理、公式、关键区别等高价值考点
- 你必须严格输出 JSON 格式，结构为：{"cards": [{"q": "问题", "a": "答案"}]}
- 不要输出任何其他文字，只输出 JSON"""


def _extract_flashcard_json(raw_text: str) -> list:
    cleaned = re.sub(r'<think[^>]*>.*?</think\s*>', '', raw_text, flags=re.DOTALL)
    code_block = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', cleaned, re.DOTALL)
    if code_block:
        cleaned = code_block.group(1).strip()
    brace_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if brace_match:
        cleaned = brace_match.group(0)
    try:
        parsed = json.loads(cleaned)
        return parsed.get("cards", [])
    except json.JSONDecodeError:
        pass
    fixed = re.sub(r"'", '"', cleaned)
    fixed = re.sub(r',\s*}', '}', fixed)
    fixed = re.sub(r',\s*]', ']', fixed)
    try:
        parsed = json.loads(fixed)
        return parsed.get("cards", [])
    except json.JSONDecodeError:
        pass
    pairs = re.findall(r'"q"\s*:\s*"(.+?)"\s*,\s*"a"\s*:\s*"(.+?)"', cleaned)
    if not pairs:
        pairs = re.findall(r'"q"\s*:\s*"(.+?)"\s*,\s*"a"\s*:\s*"(.+?)"', fixed)
    return [{"q": q, "a": a} for q, a in pairs]


@celery_app.task(bind=True, name="process_document_task")
def process_document_task(
    self,
    task_id: str,
    uploaded_files: list,
    user_instruction: str = "",
    max_retries: int = 3,
    thread_id: str = "",
    user_id: str = "",
    doc_ids: list = None,
):
    return asyncio.run(run_document_pipeline(
        task_id=task_id,
        uploaded_files=uploaded_files,
        user_instruction=user_instruction,
        max_retries=max_retries,
        thread_id=thread_id,
        user_id=user_id,
        doc_ids=doc_ids,
        use_redis=True,
    ))


@celery_app.task(bind=True, name="process_kb_document")
def process_kb_document(
    self,
    user_id: str,
    files: list,
):
    try:
        result = asyncio.run(process_kb_files_sync(user_id, files))

        for f in files:
            saved_path = f.get("saved_path", "")
            filename = f.get("filename", "")
            ext = f.get("ext", "")
            if saved_path and os.path.exists(saved_path) and ext in (".pdf", ".docx", ".txt", ".md"):
                try:
                    extract_flashcards_task.delay(
                        user_id=user_id,
                        file_path=saved_path,
                        document_name=filename,
                    )
                    logger.info(f"🃏 process_kb_document: dispatched flashcard extraction for {filename}")
                except Exception as dispatch_err:
                    logger.warning(f"🃏 process_kb_document: failed to dispatch flashcard task for {filename}: {dispatch_err}")

        return result
    except Exception as e:
        logger.error(f"process_kb_document CRASHED for user={user_id}: {e}", exc_info=True)
        try:
            from app.models.database import DocumentMeta, get_session
            session = get_session()
            try:
                doc_ids = [f.get("doc_id") for f in files if f.get("doc_id")]
                for doc_id in doc_ids:
                    doc = session.query(DocumentMeta).filter(DocumentMeta.id == doc_id).first()
                    if doc and doc.status == "processing":
                        doc.status = "failed"
                        doc.description = str(e)[:500]
                        session.add(doc)
                session.commit()
                logger.info(f"process_kb_document: marked {len(doc_ids)} docs as 'failed' after crash")
            except Exception as db_err:
                session.rollback()
                logger.error(f"process_kb_document: failed to mark docs as failed: {db_err}")
            finally:
                session.close()
        except Exception as fallback_err:
            logger.error(f"process_kb_document: fallback DB update also failed: {fallback_err}")
        return {"status": "error", "message": str(e)}


@celery_app.task(bind=True, name="extract_flashcards_task")
def extract_flashcards_task(
    self,
    user_id: str,
    file_path: str,
    document_name: str,
):
    logger.info(f"🃏 开始为文档 {document_name} 提取闪卡... (user={user_id}, path={file_path})")

    try:
        text = _read_file_text(file_path)
        if not text or len(text.strip()) < 50:
            logger.warning(f"🃏 文档内容过短，跳过闪卡提取: {document_name} (len={len(text.strip()) if text else 0})")
            return {"status": "skipped", "reason": "文件内容过短", "document_name": document_name}

        logger.info(f"🃏 文档读取成功: {document_name} (chars={len(text)})")

        max_chars = 8000
        if len(text) > max_chars:
            text = text[:max_chars]
            logger.info(f"🃏 文本截断至 {max_chars} 字符")

        llm_client = _get_llm_client()
        if llm_client is None:
            logger.error("🃏 LLM 客户端未初始化，无法提取闪卡")
            return {"status": "error", "reason": "LLM客户端未初始化"}

        messages = [
            {"role": "system", "content": FLASHCARD_SYSTEM_PROMPT},
            {"role": "user", "content": f"请从以下文本中提取闪卡：\n\n{text}"},
        ]

        logger.info(f"🃏 正在调用大模型提取闪卡: {document_name} ...")
        response = asyncio.run(llm_client.acall_api(messages, max_tokens=2048))

        if not response or not response.strip():
            logger.warning(f"🃏 大模型返回为空: {document_name}")
            return {"status": "error", "reason": "LLM返回为空", "document_name": document_name}

        logger.info(f"🤖 大模型原始返回内容: {response[:500]}")

        try:
            cards = _extract_flashcard_json(response)
        except Exception as parse_err:
            logger.error(f"❌ 闪卡JSON解析异常: {parse_err}", exc_info=True)
            return {"status": "error", "reason": f"JSON解析异常: {parse_err}", "document_name": document_name}

        if not cards:
            logger.warning(f"🃏 未能从大模型返回中解析出闪卡: {document_name}")
            return {"status": "error", "reason": "无法解析闪卡JSON", "document_name": document_name, "raw": response[:200]}

        logger.info(f"🃏 成功解析 {len(cards)} 张闪卡，准备入库: {document_name}")

        try:
            from datetime import date as date_type
            from app.models.database import Flashcard, get_session

            session = get_session()
            try:
                saved_count = 0
                for card in cards:
                    q = card.get("q", "").strip()
                    a = card.get("a", "").strip()
                    if not q or not a:
                        continue
                    flashcard = Flashcard(
                        user_id=user_id,
                        document_name=document_name,
                        question=q,
                        answer=a,
                        next_review_date=date_type.today(),
                        interval=0,
                        ease_factor=2.5,
                        repetitions=0,
                    )
                    session.add(flashcard)
                    saved_count += 1
                session.commit()
                logger.info(f"✅ 成功为文档 {document_name} 存入数据库 {saved_count} 张闪卡！")
                return {"status": "success", "cards_extracted": saved_count, "document_name": document_name}
            except Exception as db_err:
                session.rollback()
                logger.error(f"❌ 闪卡入库失败(DB): {db_err}", exc_info=True)
                return {"status": "error", "reason": str(db_err), "document_name": document_name}
            finally:
                session.close()
        except Exception as e:
            logger.error(f"❌ 闪卡解析或入库失败: {e}", exc_info=True)
            return {"status": "error", "reason": str(e), "document_name": document_name}

    except Exception as e:
        logger.error(f"❌ extract_flashcards_task CRASHED for user={user_id}, doc={document_name}: {e}", exc_info=True)
        return {"status": "error", "reason": str(e), "document_name": document_name}


def _read_file_text(file_path: str) -> str:
    if not os.path.exists(file_path):
        return ""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(file_path)
            pages = []
            for page in reader.pages:
                t = page.extract_text() or ""
                if t.strip():
                    pages.append(t)
            return "\n\n".join(pages)
        except Exception as e:
            logger.warning(f"_read_file_text: pypdf failed for {file_path}: {e}")
            return ""
    elif ext == ".docx":
        try:
            from langchain_community.document_loaders import Docx2txtLoader
            loader = Docx2txtLoader(file_path)
            docs = loader.load()
            return "\n\n".join(d.page_content for d in docs if d.page_content.strip())
        except Exception:
            try:
                from docx import Document as DocxDoc
                doc = DocxDoc(file_path)
                return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
            except Exception as e:
                logger.warning(f"_read_file_text: docx failed for {file_path}: {e}")
                return ""
    else:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError:
            with open(file_path, "r", encoding="gbk", errors="ignore") as f:
                return f.read()


_worker_llm_client = None


def _get_llm_client():
    global _worker_llm_client
    if _worker_llm_client is not None:
        return _worker_llm_client

    try:
        from app.core.app_state import app_state
        if app_state.llm_client is not None:
            _worker_llm_client = app_state.llm_client
            return _worker_llm_client
    except Exception:
        pass

    try:
        from app.services.ai_client import UnifiedAIClient
        _worker_llm_client = UnifiedAIClient()
        logger.info("extract_flashcards: initialized standalone UnifiedAIClient for Celery worker")
        return _worker_llm_client
    except Exception as e:
        logger.error(f"extract_flashcards: failed to init LLM client: {e}")
        return None
