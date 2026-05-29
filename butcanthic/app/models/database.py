import hashlib
import os
from datetime import datetime, date
from typing import Generator, List, Optional

from sqlalchemy import Column, Integer, String, Text, DateTime, Date, Float, ForeignKey, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    documents = relationship("DocumentMeta", back_populates="owner")
    flashcards = relationship("Flashcard", back_populates="owner")


class DocumentMeta(Base):
    __tablename__ = "document_meta"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), index=True, nullable=False)
    filename = Column(String(500), nullable=False)
    file_type = Column(String(20), nullable=False)
    file_size = Column(Integer, default=0)
    page_count = Column(Integer, default=0)
    content_length = Column(Integer, default=0)
    upload_time = Column(DateTime, default=datetime.utcnow)
    status = Column(String(20), default="processing")
    tags = Column(Text, default="")
    description = Column(Text, default="")
    chunk_count = Column(Integer, default=0)
    collection_name = Column(String(200), default="default")
    task_id = Column(String(100), default="")
    owner_id = Column(String(200), default="")

    owner = relationship("User", back_populates="documents")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "filename": self.filename,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "page_count": self.page_count,
            "content_length": self.content_length,
            "upload_time": self.upload_time.isoformat() if self.upload_time else None,
            "status": self.status,
            "tags": self.tags.split(",") if self.tags else [],
            "description": self.description,
            "chunk_count": self.chunk_count,
            "collection_name": self.collection_name,
            "task_id": self.task_id,
            "owner_id": self.owner_id,
        }


class Flashcard(Base):
    __tablename__ = "flashcards"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), index=True, nullable=False)
    document_name = Column(String(500), nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    next_review_date = Column(Date, default=date.today)
    interval = Column(Integer, default=0)
    ease_factor = Column(Float, default=2.5)
    repetitions = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="flashcards")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "document_name": self.document_name,
            "question": self.question,
            "answer": self.answer,
            "next_review_date": self.next_review_date.isoformat() if self.next_review_date else None,
            "interval": self.interval,
            "ease_factor": self.ease_factor,
            "repetitions": self.repetitions,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


def chunk_text_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


class ChunkExposureHistory(Base):
    __tablename__ = "chunk_exposure_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), index=True, nullable=False)
    chunk_text_hash = Column(String(32), index=True, nullable=False)
    last_exposed_at = Column(DateTime, default=datetime.utcnow)
    exposure_count = Column(Integer, default=1)
    consecutive_correct = Column(Integer, default=0)

    __table_args__ = (
        {"sqlite_autoincrement": True},
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "chunk_text_hash": self.chunk_text_hash,
            "last_exposed_at": self.last_exposed_at.isoformat() if self.last_exposed_at else None,
            "exposure_count": self.exposure_count,
            "consecutive_correct": self.consecutive_correct,
        }


DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "metadata.db")
ENGINE = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=ENGINE)


def init_db():
    Base.metadata.create_all(ENGINE)


def get_session():
    return SessionLocal()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
