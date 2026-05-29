"""
LangGraph 全局工作流状态定义
支持 Word / Excel / PPT 三种文件类型的统一状态流转
"""

import operator
from typing import Annotated, Any, Dict, List, Optional, Sequence, TypedDict

from langchain_core.messages import BaseMessage


class WorkflowState(TypedDict, total=False):
    file_path: str
    file_type: str
    user_instruction: str

    uploaded_files: List[Dict[str, Any]]
    global_context: str

    original_html: str
    current_html: str
    filled_html: str

    empty_fields: List[Dict[str, Any]]
    field_semantics: Dict[str, str]

    retrieved_context: List[Dict[str, Any]]
    context_summary: str

    retry_count: int
    max_retries: int

    review_result: str
    review_feedback: str

    table_index: int
    table_metadata: Dict[str, Any]

    generated_code: str
    code_execution_log: List[str]
    code_execution_error: str

    structured_data: Dict[str, Any]

    has_fields_to_fill: bool

    placeholder_map: Dict[str, Any]

    image_store: Dict[str, str]

    current_progress: int
    current_action: str

    task_intent: str
    ppt_data: dict

    feedback: str

    output_path: str
    error_message: str

    messages: Annotated[Sequence[BaseMessage], operator.add]
    next_node: str

    tags: List[str]
    description: str
    guide_html: str
    user_id: str
