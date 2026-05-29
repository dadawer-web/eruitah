import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

logger = logging.getLogger(__name__)


def _load_ai_config() -> dict:
    config_path = "ai_models_config.json"
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Enterprise Document Copilot starting up...")

    from app.core.file_manager import file_manager
    file_manager.init_workspace()

    _init_services()

    try:
        from app.models.database import init_db
        init_db()
        logger.info("Database initialized (metadata.db)")
    except Exception as e:
        logger.warning(f"Database init failed: {e}")

    yield

    logger.info("Enterprise Document Copilot shutting down...")


def _init_services():
    from app.core.app_state import app_state

    ai_config = _load_ai_config()
    embedding_config = ai_config.get("embedding", {})

    try:
        from app.services.ai_client import UnifiedAIClient
        config_path = "ai_models_config.json"
        if not os.path.exists(config_path):
            config_path = "ai_models_config.json"
        app_state.llm_client = UnifiedAIClient(config_path)
        logger.info("LLM Client initialized")
    except Exception as e:
        logger.warning(f"LLM Client init failed: {e}")
        app_state.llm_client = None

    try:
        from app.services.rag_engine import RAGEngine

        embedding_api_key = embedding_config.get("api_key") or os.getenv("EMBEDDING_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
        embedding_base_url = embedding_config.get("base_url", "https://api.siliconflow.cn/v1")
        embedding_model = embedding_config.get("model", "BAAI/bge-m3")
        embedding_dimension = embedding_config.get("dimension", 1024)

        app_state.rag_engine = RAGEngine(
            embedding_api_key=embedding_api_key,
            embedding_base_url=embedding_base_url,
            embedding_model=embedding_model,
            embedding_dimension=embedding_dimension,
            ai_client=app_state.llm_client,
        )
        logger.info(f"RAG Engine initialized | model={embedding_model} | graph=ON")
    except Exception as e:
        logger.warning(f"RAG Engine init failed: {e}")
        app_state.rag_engine = None

    if app_state.rag_engine and app_state.llm_client:
        try:
            from app.services.document_service import DocumentService
            app_state.document_service = DocumentService(
                rag_engine=app_state.rag_engine,
                llm_client=app_state.llm_client,
            )
            logger.info("Document Service initialized")
        except Exception as e:
            logger.warning(f"Document Service init failed: {e}")
            app_state.document_service = None
    else:
        logger.warning("Document Service skipped (missing RAG or LLM)")
        app_state.document_service = None
