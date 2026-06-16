"""
应用全局状态管理
在 lifespan 中初始化，在 endpoints 中通过延迟导入获取
"""

from typing import Optional


class AppState:
    """应用全局状态容器"""

    def __init__(self):
        self.rag_engine = None
        self.llm_client = None
        self.document_service = None
        self.ai_client = None
        self.graph_engine = None


app_state = AppState()
