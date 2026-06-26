from datetime import datetime, date
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    FAILED = "failed"


class SupportedFileType(str, Enum):
    DOCX = "docx"
    XLSX = "xlsx"
    CSV = "csv"
    PPTX = "pptx"

    @classmethod
    def from_filename(cls, filename: str) -> Optional["SupportedFileType"]:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        mapping = {"docx": cls.DOCX, "xlsx": cls.XLSX, "csv": cls.CSV, "pptx": cls.PPTX}
        return mapping.get(ext)

    @property
    def upload_subdir(self) -> str:
        return {"docx": "word", "xlsx": "excel", "csv": "excel", "pptx": "ppt"}[self.value]

    @property
    def mime_type(self) -> str:
        return {
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "csv": "text/csv",
            "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        }[self.value]


class DocumentUploadResponse(BaseModel):
    task_id: str = Field(..., description="异步任务ID")
    filename: str = Field(..., description="上传的文件名")
    file_type: SupportedFileType = Field(..., description="文件类型")
    file_size: int = Field(..., description="文件大小(字节)")
    upload_time: datetime = Field(default_factory=datetime.now)
    message: str = "文件上传成功，已进入处理队列"


class DocumentProcessRequest(BaseModel):
    task_id: str = Field(..., description="上传时返回的任务ID")
    model: Optional[str] = Field(None, description="指定AI模型")
    max_retries: int = Field(3, ge=1, le=5, description="每个表格最大重试次数")
    selected_tables: Optional[List[int]] = Field(None, description="指定处理的表格索引列表，None则处理全部")


class ChatMessage(BaseModel):
    role: str = Field(..., description="消息角色: user / assistant")
    content: str = Field(..., description="消息内容")


class FollowUpRequest(BaseModel):
    query: str = Field(..., description="用户新的追问内容")
    history: Optional[List[ChatMessage]] = Field(None, description="历史对话列表")


class DocumentProcessResponse(BaseModel):
    task_id: str = Field(..., description="任务ID")
    status: TaskStatus = Field(..., description="任务状态")
    tables_total: int = Field(0, description="表格总数")
    tables_processed: int = Field(0, description="已处理表格数")
    download_url: Optional[str] = Field(None, description="结果文件下载URL")
    output_filename: Optional[str] = Field(None, description="输出文件名")
    message: str = "处理请求已提交"


class TableProcessResult(BaseModel):
    index: int
    review_result: str = "unknown"
    retry_count: int = 0
    row_count: int = 0
    col_count: int = 0
    error_message: Optional[str] = None


class KnowledgeUploadRequest(BaseModel):
    collection_name: str = Field(..., description="知识库集合名称")
    description: Optional[str] = Field(None, description="集合描述")


class KnowledgeRecord(BaseModel):
    data: Dict[str, Any] = Field(..., description="知识库记录数据")


class KnowledgeUploadResponse(BaseModel):
    collection_name: str = Field(..., description="知识库集合名称")
    record_count: int = Field(..., description="导入的记录数")
    message: str = "知识库数据上传成功"


class TaskProgress(BaseModel):
    task_id: str = Field(..., description="任务ID")
    status: TaskStatus = Field(..., description="任务状态")
    progress: float = Field(0.0, ge=0.0, le=100.0, description="进度百分比")
    stage: str = Field("", description="当前阶段描述")
    tables_total: int = Field(0, description="表格总数")
    tables_completed: int = Field(0, description="已完成表格数")
    error_message: Optional[str] = Field(None, description="错误信息")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TaskResult(BaseModel):
    task_id: str
    status: TaskStatus
    output_file: Optional[str] = None
    tables: List[Dict[str, Any]] = Field(default_factory=list)
    timing_stats: Optional[Dict[str, float]] = None


class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str
    uptime: float


class FlashcardResponse(BaseModel):
    id: int
    user_id: str
    document_name: str
    question: str
    answer: str
    next_review_date: Optional[date] = None
    interval: int = 0
    ease_factor: float = 2.5
    repetitions: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class FlashcardCreate(BaseModel):
    document_name: str = Field(..., description="卡片来源文档名")
    question: str = Field(..., description="问题")
    answer: str = Field(..., description="答案")


class ReviewSubmit(BaseModel):
    quality: int = Field(
        ...,
        ge=0,
        le=5,
        description="回答质量：0=彻底忘记，1=有印象但想不起来，2=想起来了但很吃力，3=想起来了但不太确定，4=轻松回忆，5=完美记住",
    )


class FlashcardListResponse(BaseModel):
    total: int
    cards: List[FlashcardResponse]


class DueCardsResponse(BaseModel):
    total_due: int
    cards: List[FlashcardResponse]
