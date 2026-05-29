import json
import logging
import os
from typing import Any, Dict, List, Optional

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

_worker_rag_engine = None


def _get_rag_engine():
    global _worker_rag_engine
    if _worker_rag_engine is not None:
        return _worker_rag_engine

    from app.core.app_state import app_state
    if app_state.rag_engine is not None:
        _worker_rag_engine = app_state.rag_engine
        return _worker_rag_engine

    logger.info("KB Processor: initializing standalone RAG engine for Celery worker...")
    try:
        from app.services.rag_engine import RAGEngine

        config_path = "ai_models_config.json"
        ai_config = {}
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                ai_config = json.load(f)

        embedding_config = ai_config.get("embedding", {})
        embedding_api_key = (
            embedding_config.get("api_key")
            or os.getenv("EMBEDDING_API_KEY")
            or os.getenv("DASHSCOPE_API_KEY")
        )
        embedding_base_url = embedding_config.get("base_url", "https://api.siliconflow.cn/v1")
        embedding_model = embedding_config.get("model", "BAAI/bge-m3")
        embedding_dimension = embedding_config.get("dimension", 1024)

        _worker_rag_engine = RAGEngine(
            embedding_api_key=embedding_api_key,
            embedding_base_url=embedding_base_url,
            embedding_model=embedding_model,
            embedding_dimension=embedding_dimension,
        )
        logger.info(f"KB Processor: standalone RAG engine initialized | model={embedding_model}")
    except Exception as e:
        logger.error(f"KB Processor: standalone RAG engine init failed: {e}")
        _worker_rag_engine = None

    return _worker_rag_engine


async def process_kb_files_sync(user_id: str, files: List[Dict[str, Any]]) -> Dict[str, Any]:
    rag_engine = _get_rag_engine()
    if rag_engine is None:
        logger.error("KB Processor: RAG engine not initialized (both app_state and standalone)")
        return {"status": "error", "message": "RAG引擎未初始化"}

    try:
        return await _process_kb_files_inner(user_id, files, rag_engine)
    except Exception as e:
        logger.error(f"KB Processor: unhandled exception for user={user_id}: {e}", exc_info=True)
        _mark_files_failed(files, str(e))
        return {"status": "error", "message": str(e), "files": files}


async def _process_kb_files_inner(user_id: str, files: List[Dict[str, Any]], rag_engine) -> Dict[str, Any]:

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100,
        separators=["\n\n", "\n", "。", "！", "？", "；", " ", ""],
    )

    all_chunks: List[Document] = []
    file_results = []

    for file_info in files:
        filename = file_info.get("filename", "unknown")
        saved_path = file_info.get("saved_path", "")
        ext = file_info.get("ext", "")
        doc_id = file_info.get("doc_id")

        if not saved_path or not os.path.exists(saved_path):
            file_results.append({"filename": filename, "status": "error", "reason": "文件不存在", "doc_id": doc_id})
            continue

        try:
            documents = _extract_documents(saved_path, filename, ext, rag_engine)

            if not documents:
                file_results.append({"filename": filename, "status": "empty", "chunks": 0, "doc_id": doc_id})
                continue

            chunks = text_splitter.split_documents(documents)
            for i, chunk in enumerate(chunks):
                chunk.metadata["source"] = filename
                chunk.metadata["chunk_index"] = i

            all_chunks.extend(chunks)
            file_results.append({"filename": filename, "status": "success", "chunks": len(chunks), "doc_id": doc_id})
            logger.info(f"KB Processor: {filename} → {len(chunks)} chunks")

        except Exception as e:
            logger.error(f"KB Processor: failed to process {filename}: {e}")
            file_results.append({"filename": filename, "status": "error", "reason": str(e)})

    total_chunks = 0
    effective_collection = ""
    ingest_error = None
    if all_chunks:
        try:
            result = await rag_engine.ingest_documents_batch(all_chunks, "default", user_id=user_id)
            total_chunks = result["ingested_count"]
            effective_collection = result["collection"]
            logger.info(f"KB Processor: {len(all_chunks)} chunks → [{effective_collection}], ingested={total_chunks}")
        except Exception as e:
            logger.error(f"KB Processor: batch ingest failed: {e}")
            ingest_error = str(e)
            for fr in file_results:
                if fr.get("status") == "success":
                    fr["status"] = "error"
                    fr["reason"] = f"向量化入库失败: {ingest_error}"

    try:
        from app.models.database import DocumentMeta, get_session
        session = get_session()
        for fr in file_results:
            doc_id = fr.get("doc_id")
            if doc_id:
                doc_meta = session.query(DocumentMeta).filter(DocumentMeta.id == doc_id).first()
                if doc_meta:
                    if fr.get("status") == "success":
                        doc_meta.status = "completed"
                        doc_meta.chunk_count = fr.get("chunks", 0)
                        doc_meta.collection_name = effective_collection
                    else:
                        doc_meta.status = "failed"
                    session.add(doc_meta)
            elif fr.get("status") == "success":
                doc_meta = DocumentMeta(
                    filename=fr["filename"],
                    file_type=os.path.splitext(fr["filename"])[1].lower().lstrip("."),
                    chunk_count=fr.get("chunks", 0),
                    status="completed",
                    collection_name=effective_collection,
                    owner_id=user_id,
                    user_id=user_id,
                )
                session.add(doc_meta)
        session.commit()
    except Exception as e:
        logger.warning(f"KB Processor: failed to update document metadata: {e}")
    finally:
        try:
            session.close()
        except Exception:
            pass

    _trigger_flashcard_extraction(user_id, files)

    if ingest_error:
        return {
            "status": "error",
            "collection_name": effective_collection,
            "total_chunks": total_chunks,
            "files": file_results,
            "message": f"向量化入库失败: {ingest_error}",
        }

    return {
        "status": "success",
        "collection_name": effective_collection,
        "total_chunks": total_chunks,
        "files": file_results,
    }


def _trigger_flashcard_extraction(user_id: str, files: List[Dict[str, Any]]):
    try:
        from app.core.config import settings
        if not settings.USE_CELERY:
            logger.info("KB Processor: skipping flashcard extraction (Celery disabled)")
            return

        from app.worker.tasks import extract_flashcards_task
        for f in files:
            saved_path = f.get("saved_path", "")
            filename = f.get("filename", "")
            ext = f.get("ext", "")
            if saved_path and os.path.exists(saved_path) and ext in (".pdf", ".docx", ".txt", ".md"):
                extract_flashcards_task.delay(
                    user_id=user_id,
                    file_path=saved_path,
                    document_name=filename,
                )
                logger.info(f"KB Processor: dispatched flashcard extraction for {filename}")
    except Exception as e:
        logger.warning(f"KB Processor: failed to trigger flashcard extraction: {e}")


def _mark_files_failed(files: List[Dict[str, Any]], error_msg: str):
    try:
        from app.models.database import DocumentMeta, get_session
        session = get_session()
        try:
            for f in files:
                doc_id = f.get("doc_id")
                if doc_id:
                    doc = session.query(DocumentMeta).filter(DocumentMeta.id == doc_id).first()
                    if doc and doc.status == "processing":
                        doc.status = "failed"
                        doc.description = error_msg[:500]
                        session.add(doc)
            session.commit()
            logger.info(f"KB Processor: marked docs as 'failed' after exception")
        except Exception as e:
            session.rollback()
            logger.error(f"KB Processor: _mark_files_failed DB error: {e}")
        finally:
            session.close()
    except Exception as e:
        logger.error(f"KB Processor: _mark_files_failed total failure: {e}")


def _extract_documents(file_path: str, filename: str, ext: str, rag_engine) -> List[Document]:
    documents = []

    if ext == ".pdf":
        try:
            from langchain_community.document_loaders import PyPDFLoader
            loader = PyPDFLoader(file_path)
            documents = loader.load()
        except Exception as e:
            logger.warning(f"KB Processor: PyPDFLoader failed for {filename}: {e}")
            try:
                import pypdf
                reader = pypdf.PdfReader(file_path)
                for page_num, page in enumerate(reader.pages):
                    text = page.extract_text() or ""
                    if text.strip():
                        documents.append(Document(
                            page_content=text,
                            metadata={"source": filename, "page": page_num + 1},
                        ))
            except Exception as e2:
                logger.error(f"KB Processor: pypdf fallback also failed for {filename}: {e2}")

    elif ext == ".docx":
        try:
            from app.services.docx_parser import DocxParser
            import asyncio
            parser = DocxParser()
            loop = asyncio.new_event_loop()
            try:
                html = loop.run_until_complete(parser.convert_docx_to_html(file_path))
            finally:
                loop.close()
            if html:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")
                text = soup.get_text(separator="\n", strip=True)
                if text.strip():
                    documents.append(Document(page_content=text, metadata={"source": filename}))
        except Exception:
            try:
                from langchain_community.document_loaders import Docx2txtLoader
                loader = Docx2txtLoader(file_path)
                documents = loader.load()
            except Exception as e:
                logger.error(f"KB Processor: DOCX parse failed for {filename}: {e}")

    elif ext == ".jsonl":
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        except UnicodeDecodeError:
            with open(file_path, "r", encoding="gbk", errors="ignore") as f:
                text = f.read()

        for line_idx, line in enumerate(text.strip().split("\n")):
            line = line.strip()
            if line:
                try:
                    record = json.loads(line)
                    field_parts = [f"{k}: {v}" for k, v in record.items() if v is not None and str(v).strip()]
                    page_content = " | ".join(field_parts)
                    documents.append(Document(page_content=page_content, metadata={"source": filename, "record_index": line_idx}))
                except json.JSONDecodeError:
                    continue

    elif ext in (".txt", ".md"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        except UnicodeDecodeError:
            with open(file_path, "r", encoding="gbk", errors="ignore") as f:
                text = f.read()
        if text.strip():
            documents.append(Document(page_content=text, metadata={"source": filename}))

    return documents
