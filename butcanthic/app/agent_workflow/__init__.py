"""
LangGraph 全域工作流包
路由: Gateway → Router → Word/Excel/PPT 分支
支持 SSE 流式推送
"""

from app.agent_workflow.state import WorkflowState
from app.agent_workflow.graph import (
    build_workflow_graph,
    run_workflow,
    run_workflow_streaming,
    build_table_fill_graph,
    run_table_fill_workflow,
)

__all__ = [
    "WorkflowState",
    "build_workflow_graph",
    "run_workflow",
    "run_workflow_streaming",
    "build_table_fill_graph",
    "run_table_fill_workflow",
]
