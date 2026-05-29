"""
文档处理服务 - 全流程业务逻辑
DOCX上传 → 表格提取 → LangGraph工作流填充 → XML回写 → 生成新DOCX
"""

import asyncio
import logging
import os
import re
import shutil
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.agent_workflow.graph import run_table_fill_workflow
from app.models.schemas import TaskStatus, TableProcessResult
from app.services.rag_engine import RAGEngine
from app.services.docx_parser import DocxParser, XmlProcessor

logger = logging.getLogger(__name__)


def strip_images_from_html(html: str) -> tuple:
    """
    强制剥离 HTML 中所有 Base64 图片数据
    使用正则 + BeautifulSoup 双重保险，确保绝不遗漏
    返回: (cleaned_html, images_dict)
    images_dict: {"IMG_CACHE_0": "data:image/png;base64,...", ...}
    """
    if not html:
        return html, {}

    image_cache = {}
    idx = 0

    # Pass 1: 正则强制替换所有 base64 src（最可靠，不依赖 BS4 解析）
    def _replace_base64_src(match):
        nonlocal idx
        key = f"IMG_CACHE_{idx}"
        image_cache[key] = match.group(0)
        idx += 1
        return f'src="IMG_CACHE_{idx - 1}"'

    cleaned = re.sub(
        r'src="(data:image/[^"]+)"',
        _replace_base64_src,
        html,
    )

    # Pass 2: BS4 兜底，处理单引号或其他变体
    if "data:image" in cleaned:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(cleaned, "html.parser")
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if src and src.startswith("data:image"):
                key = f"IMG_CACHE_{idx}"
                image_cache[key] = src
                img["src"] = key
                idx += 1
        cleaned = str(soup)

    if image_cache:
        logger.info(
            f"strip_images: removed {len(image_cache)} base64 images, "
            f"HTML size: {len(html)} → {len(cleaned)} "
            f"(saved {len(html) - len(cleaned)} chars)"
        )

    return cleaned, image_cache


def restore_images_to_html(html: str, images: dict) -> str:
    """
    将之前剥离的 base64 图片数据恢复到 HTML 中
    """
    if not images:
        return html

    for key, src in images.items():
        html = html.replace(f'src="{key}"', f'src="{src}"')
        html = html.replace(f"src='{key}'", f"src='{src}'")
        html = html.replace(key, src)

    logger.info(f"restore_images: restored {len(images)} images to HTML")
    return html


class DocumentService:
    """文档处理服务 - 全流程业务逻辑"""

    def __init__(self, rag_engine=None, llm_client=None):
        self.rag_engine = rag_engine
        self.llm_client = llm_client
        self.docx_parser = DocxParser()

    async def process_docx(
        self,
        file_path: str,
        user_instruction: str = "",
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        if not self.rag_engine or not self.llm_client:
            return {"error": "RAG引擎或LLM客户端未初始化"}

        from app.agent_workflow.graph import run_workflow
        result = await run_workflow(
            file_path=file_path,
            rag_engine=self.rag_engine,
            llm_client=self.llm_client,
            user_instruction=user_instruction,
            max_retries=max_retries,
        )
        return result

    async def convert_docx_to_html(self, file_path: str) -> str:
        return await self.docx_parser.convert_docx_to_html(file_path)
