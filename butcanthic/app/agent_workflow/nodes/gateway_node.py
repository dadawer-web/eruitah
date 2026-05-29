"""
Gateway Node - 工作流入口节点
检查文件路径后缀，赋值 file_type，对 DOCX 预加载 HTML，做基础校验
"""

import logging
import os
import re
from typing import Literal

from app.agent_workflow.state import WorkflowState

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {"docx", "xlsx", "csv", "pptx"}

PPT_KEYWORDS = re.compile(
    r"(?i)(ppt|幻灯片|汇报|slides?|presentation|演示文稿|生成演示|转\s*ppt)",
)


async def gateway_node(state: WorkflowState) -> WorkflowState:
    """
    入口节点: 解析文件类型，基础校验，DOCX 预加载 HTML
    同时注入用户长期记忆到 state["global_context"]

    输入: state["file_path"] / state["uploaded_files"]
    输出: state["file_type"], state["task_intent"], state["error_message"], state["original_html"], state["current_html"], state["global_context"]
    """
    file_path = state.get("file_path", "")
    user_instruction = state.get("user_instruction", "")
    uploaded_files = state.get("uploaded_files", [])
    user_id = state.get("user_id", "")

    global_context = state.get("global_context", "")
    if user_id and not global_context:
        try:
            from app.services.memory_service import memory_manager
            from app.core.app_state import app_state
            rag_engine = app_state.rag_engine
            if rag_engine:
                memory_text = await memory_manager.fetch_user_memory(user_id, rag_engine)
                if memory_text:
                    global_context = memory_text
                    logger.info(f"Gateway: injected user memory for {user_id[:8]}... ({len(memory_text)} chars)")
        except Exception as e:
            logger.warning(f"Gateway: failed to fetch user memory: {e}")

    if len(uploaded_files) > 1:
        logger.info(f"Gateway: {len(uploaded_files)} files uploaded → multi-file cross-doc mode, delegating to supervisor")
        return {
            **state,
            "file_type": "multi",
            "task_intent": "unknown",
            "error_message": "",
            "global_context": global_context,
        }

    if not file_path:
        if user_instruction and PPT_KEYWORDS.search(user_instruction):
            logger.info("Gateway: no file, but PPT intent detected → generate_ppt")
            return {
                **state,
                "file_type": "",
                "task_intent": "generate_ppt",
                "error_message": "",
                "global_context": global_context,
            }
        if user_instruction:
            logger.info("Gateway: no file, unknown instruction → delegating to supervisor")
            return {
                **state,
                "file_type": "",
                "task_intent": "unknown",
                "error_message": "",
                "global_context": global_context,
            }
        logger.error("Gateway: file_path is empty and no user_instruction")
        return {**state, "file_type": "", "error_message": "请上传文件或输入指令", "global_context": global_context}

    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""

    if ext not in SUPPORTED_EXTENSIONS:
        logger.error(f"Gateway: unsupported file type: {ext}")
        return {
            **state,
            "file_type": "",
            "error_message": f"不支持的文件类型: .{ext}，仅支持 {', '.join('.' + e for e in SUPPORTED_EXTENSIONS)}",
            "global_context": global_context,
        }

    if not os.path.exists(file_path):
        logger.warning(f"Gateway: file not found: {file_path}, type={ext} detected")
        return {
            **state,
            "file_type": ext,
            "error_message": f"文件不存在: {file_path}",
            "global_context": global_context,
        }

    logger.info(f"Gateway: file_type={ext}, file={os.path.basename(file_path)}")

    user_instruction = state.get("user_instruction", "")
    task_intent = "unknown"
    if user_instruction and PPT_KEYWORDS.search(user_instruction):
        task_intent = "generate_ppt"
        logger.info(f"Gateway: detected PPT intent in user_instruction → task_intent=generate_ppt")

    if ext == "docx":
        if "填空" in user_instruction or "填写" in user_instruction or "填充" in user_instruction:
            task_intent = "extract_context"
            logger.info("Gateway: docx with fill intent → extract_context")
        elif task_intent == "unknown":
            logger.info("Gateway: docx without explicit fill intent → delegating to supervisor")

        html_result = await _load_docx_html(file_path)
        if html_result is None:
            return {
                **state,
                "file_type": ext,
                "task_intent": task_intent,
                "error_message": "DOCX 解析失败: 无法将文件转换为 HTML，请确认文件内容有效",
                "global_context": global_context,
            }
        return {
            **state,
            "file_type": ext,
            "task_intent": task_intent,
            "error_message": "",
            "original_html": html_result,
            "current_html": html_result,
            "global_context": global_context,
        }

    return {
        **state,
        "file_type": ext,
        "task_intent": task_intent,
        "error_message": "",
        "global_context": global_context,
    }


async def _load_docx_html(file_path: str) -> str | None:
    """使用 DocxParser 将 DOCX 转为 HTML，失败返回 None"""
    try:
        from app.services.docx_parser import DocxParser
        parser = DocxParser()
        html = await parser.convert_docx_to_html(file_path)
        if html:
            logger.info(f"Gateway: DOCX HTML loaded ({len(html)} chars), preview: {html[:200]}...")
            return html
        logger.warning("Gateway: DOCX conversion returned empty HTML")
        return None
    except Exception as e:
        logger.error(f"Gateway: DOCX HTML loading failed: {e}", exc_info=True)
        return None


def route_by_file_type(
    state: WorkflowState,
) -> Literal["process_word", "process_excel", "process_ppt", "generate_ppt", "supervisor", "error"]:
    file_type = state.get("file_type", "")
    error = state.get("error_message", "")
    user_instruction = state.get("user_instruction", "")
    task_intent = state.get("task_intent", "")

    if error and not file_type and not task_intent:
        logger.warning(f"Router: routing to error - {error}")
        return "error"

    if file_type == "multi":
        logger.info("Router: multi-file mode → supervisor (intelligent routing)")
        return "supervisor"

    if task_intent == "generate_ppt" or (user_instruction and PPT_KEYWORDS.search(user_instruction)):
        logger.info(f"Router: PPT intent detected → generate_ppt")
        return "generate_ppt"

    if task_intent == "extract_context":
        logger.info("Router: fill intent → process_word")
        return "process_word"

    if task_intent == "unknown":
        logger.info("Router: unknown intent → supervisor (intelligent routing)")
        return "supervisor"

    routing_map = {
        "xlsx": "process_excel",
        "csv": "process_excel",
        "pptx": "process_ppt",
    }

    target = routing_map.get(file_type)
    if target:
        logger.info(f"Router: {file_type} → {target}")
        return target

    logger.warning(f"Router: unknown file_type '{file_type}' → supervisor")
    return "supervisor"
