from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    PROJECT_NAME: str = "Enterprise Document Copilot"
    VERSION: str = "1.0.0"
    DESCRIPTION: str = "Enterprise-grade intelligent document processing SaaS engine"
    API_V1_PREFIX: str = "/api/v1"

    ALLOWED_ORIGINS: List[str] = ["http://127.0.0.1:5174", "http://localhost:5174", "http://127.0.0.1:8002"]

    UPLOAD_DIR: str = "uploads"
    OUTPUT_DIR: str = "output"

    AI_CONFIG_PATH: str = "ai_models_config.json"

    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "knowledge_base"

    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    EMBEDDING_DIMENSION: int = 1024

    MAX_UPLOAD_SIZE_MB: int = 50

    USE_CELERY: bool = True

    UNSPLASH_ACCESS_KEY: str = ""


settings = Settings()
