"""
LangGraph 全域工作流 - 路由网络 + 多文件类型处理 + SSE 流式推送

架构:
  START → Gateway → Router (条件路由)
                        ├─ docx → ExtractContext → RetrieveKnowledge → ReasonAndFill → CriticReview → END
                        │                                                                   ↑ retry ↓
                        │                                                          increment_retry (循环)
                        ├─ xlsx → ProcessExcel (Data Agent + Self-Correction) → END
                        └─ pptx → ProcessPPT → END
                        └─ generate_ppt → GeneratePPT → CriticReviewPPT ──→ PASS → END
                                                              ↑  REJECT  ↓
                                                              └── (循环，最多3次)
"""

import logging
import os
from typing import Any, Dict, Literal, Optional

from langgraph.checkpoint.memory import MemorySaver

from langgraph.graph import END, StateGraph

from app.agent_workflow.state import WorkflowState
from app.agent_workflow.nodes.gateway_node import gateway_node, route_by_file_type
from app.agent_workflow.nodes.extract_context import extract_context
from app.agent_workflow.nodes.retrieve_knowledge import retrieve_knowledge_async
from app.agent_workflow.nodes.reason_and_fill import reason_and_fill
from app.agent_workflow.nodes.critic_review import critic_review, critic_review_ppt, PPT_MAX_RETRIES
from app.agent_workflow.nodes.process_excel import process_excel_node
from app.agent_workflow.nodes.process_ppt import process_ppt_node
from app.agent_workflow.nodes.generate_ppt import generate_ppt_node
from app.agent_workflow.nodes.process_summary import generate_summary_node
from app.agent_workflow.nodes.supervisor import supervisor_node
from app.agent_workflow.nodes.web_researcher import web_researcher_node
from app.agent_workflow.nodes.knowledge_librarian import knowledge_librarian_node
from app.agent_workflow.nodes.auto_tagging import auto_tagging_node
from app.agent_workflow.nodes.literature_guide import literature_guide_node
from app.services.rag_engine import RAGEngine
from app.services.excel_service import ExcelDataProcessor
from app.services.ppt_service import PPTAnalyzer

logger = logging.getLogger(__name__)


def _make_retrieve_knowledge_node(rag_engine: RAGEngine, llm_client=None):
    async def node(state: WorkflowState) -> WorkflowState:
        return await retrieve_knowledge_async(state, rag_engine, llm_client)
    return node


def _make_reason_and_fill_node(llm_client):
    async def node(state: WorkflowState) -> WorkflowState:
        return await reason_and_fill(state, llm_client)
    return node


def _make_critic_review_node(llm_client):
    async def node(state: WorkflowState) -> WorkflowState:
        return await critic_review(state, llm_client)
    return node


def _make_critic_review_ppt_node(llm_client):
    async def node(state: WorkflowState) -> WorkflowState:
        return await critic_review_ppt(state, llm_client)
    return node


def _make_process_excel_node(llm_client, rag_engine=None):
    processor = ExcelDataProcessor()

    async def node(state: WorkflowState) -> WorkflowState:
        return await process_excel_node(state, processor, llm_client, rag_engine=rag_engine)
    return node


def _make_process_ppt_node(llm_client=None, rag_engine=None):
    analyzer = PPTAnalyzer()

    async def node(state: WorkflowState) -> WorkflowState:
        return await process_ppt_node(state, analyzer, llm_client, rag_engine=rag_engine)
    return node


def _make_generate_ppt_node(llm_client=None, rag_engine=None):
    async def node(state: WorkflowState) -> WorkflowState:
        return await generate_ppt_node(state, llm_client, rag_engine)
    return node


def _make_supervisor_node(llm_client=None):
    async def node(state: WorkflowState) -> dict:
        return await supervisor_node(state, llm_client)
    return node


def _make_generate_summary_node(llm_client=None):
    async def node(state: WorkflowState) -> dict:
        return await generate_summary_node(state, llm_client)
    return node


def _make_knowledge_librarian_node(rag_engine=None, llm_client=None):
    async def node(state: WorkflowState) -> dict:
        return await knowledge_librarian_node(state, rag_engine, llm_client)
    return node


def _make_web_researcher_node(llm_client=None):
    async def node(state: WorkflowState) -> dict:
        return await web_researcher_node(state, llm_client)
    return node


def _make_auto_tagging_node(llm_client=None):
    async def node(state: WorkflowState) -> dict:
        return await auto_tagging_node(state, llm_client)
    return node


def _make_literature_guide_node(llm_client=None):
    async def node(state: WorkflowState) -> dict:
        return await literature_guide_node(state, llm_client)
    return node


def _route_from_supervisor(state: WorkflowState) -> str:
    next_node = state.get("next_node", "generate_ppt")

    user_instruction = state.get("user_instruction", "").lower()
    ppt_keywords = ["ppt", "幻灯片", "演示文稿", "课件", "slides"]
    needs_ppt = any(kw in user_instruction for kw in ppt_keywords)
    has_ppt_output = bool(state.get("ppt_slides")) or bool(state.get("ppt_output_path"))

    if needs_ppt and not has_ppt_output and next_node in ("FINISH", "generate_summary"):
        logger.info("🛡️ [Graph] Supervisor routed to %s but PPT not yet generated, forcing → generate_ppt", next_node)
        return "generate_ppt"

    if next_node == "FINISH":
        return END
    return next_node


def route_after_agent(state: WorkflowState) -> str:
    next_node = state.get("next_node", "")
    if next_node == "FINISH" or not next_node:
        return END
    return "supervisor"


def _passthrough_node(state: WorkflowState) -> WorkflowState:
    return state


def _check_initial_route(state: WorkflowState) -> str:
    user_instruction = state.get("user_instruction", "").lower()
    file_path = state.get("file_path", "")
    uploaded_files = state.get("uploaded_files", [])

    ppt_keywords = ["ppt", "幻灯片", "演示文稿", "课件", "slides"]
    force_knowledge_keywords = [
        "算法", "知识库", "文档", "项目", "408", "内部", "公司",
        "报告", "方案", "规范", "标准", "手册", "制度", "流程",
        "根据", "参考", "按照", "基于",
    ]

    if len(uploaded_files) > 1:
        logger.info(f"🚀 [Graph] 检测到 {len(uploaded_files)} 个文件上传，判定为跨文档协同任务，派往 supervisor 统筹调度")
        return "supervisor"

    if file_path or len(uploaded_files) == 1:
        logger.info("🚀 [Graph] 检测到用户上传文件，强制首发派往 knowledge_librarian")
        return "knowledge_librarian"

    if any(kw in user_instruction for kw in ppt_keywords):
        logger.info("🚀 [Graph] 检测到PPT关键词，派往 supervisor 统筹调度（优先保证PPT生成）")
        return "supervisor"

    if any(kw in user_instruction for kw in force_knowledge_keywords):
        logger.info(f"🚀 [Graph] 检测到专业主题关键词，强制首发派往 knowledge_librarian")
        return "knowledge_librarian"

    return "supervisor"


def _should_retry(state: WorkflowState) -> Literal["retry", "end"]:
    review_result = state.get("review_result", "fail")
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)

    if review_result == "pass":
        return "end"
    if retry_count < max_retries:
        return "retry"
    return "end"


def _should_retry_ppt(state: WorkflowState) -> Literal["retry", "end"]:
    review_result = state.get("review_result", "fail")
    retry_count = state.get("retry_count", 0)

    if review_result == "pass":
        return "end"
    if retry_count >= PPT_MAX_RETRIES:
        logger.warning(f"PPT self-correction: max retries ({PPT_MAX_RETRIES}) reached, accepting current result")
        return "end"
    return "retry"


def _route_after_extract(state: WorkflowState) -> Literal["continue_fill", "circuit_break"]:
    has_fields = state.get("has_fields_to_fill", True)
    if has_fields:
        return "continue_fill"
    logger.warning("Circuit breaker: has_fields_to_fill=False, skipping to END")
    return "circuit_break"


def _increment_retry(state: WorkflowState) -> WorkflowState:
    retry_count = state.get("retry_count", 0) + 1
    return {
        **state,
        "retry_count": retry_count,
        "current_html": state.get("filled_html", state.get("current_html", "")),
    }


memory = MemorySaver()


def build_workflow_graph(
    rag_engine: RAGEngine,
    llm_client,
    max_retries: int = 3,
) -> StateGraph:
    graph = StateGraph(WorkflowState)

    graph.add_node("gateway", gateway_node)
    graph.add_node("extract_context", extract_context)
    graph.add_node("retrieve_knowledge", _make_retrieve_knowledge_node(rag_engine, llm_client))
    graph.add_node("reason_and_fill", _make_reason_and_fill_node(llm_client))
    graph.add_node("critic_review", _make_critic_review_node(llm_client))
    graph.add_node("increment_retry", _increment_retry)
    graph.add_node("process_excel", _make_process_excel_node(llm_client, rag_engine=rag_engine))
    graph.add_node("process_ppt", _make_process_ppt_node(llm_client, rag_engine=rag_engine))
    graph.add_node("supervisor", _make_supervisor_node(llm_client))
    graph.add_node("web_researcher", _make_web_researcher_node(llm_client))
    graph.add_node("knowledge_librarian", _make_knowledge_librarian_node(rag_engine, llm_client))
    graph.add_node("generate_ppt", _make_generate_ppt_node(llm_client, rag_engine))
    graph.add_node("critic_review_ppt", _make_critic_review_ppt_node(llm_client))
    graph.add_node("generate_summary", _make_generate_summary_node(llm_client))
    graph.add_node("generate_ppt_entry", _passthrough_node)
    graph.add_node("auto_tagging", _make_auto_tagging_node(llm_client))
    graph.add_node("literature_guide", _make_literature_guide_node(llm_client))

    graph.set_entry_point("gateway")

    graph.add_conditional_edges(
        "gateway",
        route_by_file_type,
        {
            "process_word": "extract_context",
            "process_excel": "process_excel",
            "process_ppt": "process_ppt",
            "generate_ppt": "generate_ppt_entry",
            "supervisor": "supervisor",
            "error": END,
        },
    )

    graph.add_conditional_edges(
        "generate_ppt_entry",
        _check_initial_route,
        {
            "knowledge_librarian": "knowledge_librarian",
            "supervisor": "supervisor",
        },
    )

    graph.add_conditional_edges(
        "extract_context",
        _route_after_extract,
        {"continue_fill": "retrieve_knowledge", "circuit_break": END},
    )

    graph.add_edge("retrieve_knowledge", "reason_and_fill")
    graph.add_edge("reason_and_fill", "critic_review")

    graph.add_conditional_edges(
        "critic_review",
        _should_retry,
        {"retry": "increment_retry", "end": END},
    )

    graph.add_edge("increment_retry", "reason_and_fill")
    graph.add_edge("process_excel", END)
    graph.add_edge("process_ppt", END)

    graph.add_conditional_edges("supervisor", _route_from_supervisor)
    graph.add_conditional_edges(
        "web_researcher",
        route_after_agent,
        {"supervisor": "supervisor", END: END},
    )
    graph.add_edge("knowledge_librarian", "supervisor")
    graph.add_edge("generate_ppt", "critic_review_ppt")
    graph.add_conditional_edges(
        "critic_review_ppt",
        _should_retry_ppt,
        {"retry": "generate_ppt", "end": END},
    )
    graph.add_edge("generate_summary", END)

    graph.add_conditional_edges("auto_tagging", route_after_agent, {"supervisor": "supervisor", END: END})
    graph.add_conditional_edges("literature_guide", route_after_agent, {"supervisor": "supervisor", END: END})

    compiled = graph.compile(checkpointer=memory)
    logger.info("Workflow graph compiled successfully (Word + Excel + PPT + MemorySaver)")
    return compiled


def _make_initial_state(file_path: str, user_instruction: str, max_retries: int, uploaded_files: list = None, user_id: str = "") -> WorkflowState:
    return {
        "file_path": file_path,
        "file_type": "",
        "user_instruction": user_instruction,
        "uploaded_files": uploaded_files or [],
        "global_context": "",
        "original_html": "",
        "current_html": "",
        "filled_html": "",
        "empty_fields": [],
        "field_semantics": {},
        "retrieved_context": [],
        "context_summary": "",
        "retry_count": 0,
        "max_retries": max_retries,
        "review_result": "",
        "review_feedback": "",
        "table_index": 0,
        "table_metadata": {},
        "generated_code": "",
        "code_execution_log": [],
        "code_execution_error": "",
        "structured_data": {},
        "has_fields_to_fill": True,
        "placeholder_map": {},
        "image_store": {},
        "current_progress": 0,
        "current_action": "",
        "task_intent": "fill_document",
        "ppt_data": {},
        "feedback": "",
        "output_path": "",
        "error_message": "",
        "messages": [],
        "next_node": "",
        "tags": [],
        "description": "",
        "guide_html": "",
        "user_id": user_id,
    }


async def run_workflow(
    file_path: str,
    rag_engine: RAGEngine,
    llm_client,
    user_instruction: str = "",
    max_retries: int = 3,
) -> Dict[str, Any]:
    graph = build_workflow_graph(rag_engine, llm_client, max_retries)
    update_state = {
        "user_instruction": user_instruction,
        "max_retries": max_retries,
    }
    if file_path:
        update_state["file_path"] = file_path
    final_state = await graph.ainvoke(update_state)

    return {
        "file_type": final_state.get("file_type", ""),
        "filled_html": final_state.get("filled_html", ""),
        "review_result": final_state.get("review_result", ""),
        "review_feedback": final_state.get("review_feedback", ""),
        "retry_count": final_state.get("retry_count", 0),
        "generated_code": final_state.get("generated_code", ""),
        "code_execution_log": final_state.get("code_execution_log", []),
        "code_execution_error": final_state.get("code_execution_error", ""),
        "structured_data": final_state.get("structured_data", {}),
        "output_path": final_state.get("output_path", ""),
        "error_message": final_state.get("error_message", ""),
    }


NODE_DISPLAY_NAMES = {
    "gateway": "路由网关",
    "extract_context": "字段提取",
    "retrieve_knowledge": "知识检索",
    "reason_and_fill": "AI推理填充",
    "critic_review": "审查校验",
    "increment_retry": "重试优化",
    "process_excel": "数据分析Agent",
    "process_ppt": "PPT分析Agent",
    "supervisor": "主管调度",
    "web_researcher": "联网检索",
    "knowledge_librarian": "知识库检索",
    "generate_ppt_entry": "PPT路由",
    "generate_ppt": "PPT生成Agent",
    "critic_review_ppt": "PPT审查校验",
    "generate_summary": "长文总结Agent",
    "auto_tagging": "🏷️ 自动标签",
    "literature_guide": "📖 文献导读",
}

NODE_AGENT_NAMES = {
    "gateway": "包工头",
    "extract_context": "ExtractAgent",
    "retrieve_knowledge": "RetrievalAgent",
    "reason_and_fill": "FillAgent",
    "critic_review": "CriticAgent",
    "increment_retry": "RetryManager",
    "process_excel": "DataAgent",
    "process_ppt": "PPTAgent",
    "supervisor": "Supervisor",
    "web_researcher": "WebResearcher",
    "knowledge_librarian": "KnowledgeLibrarian",
    "generate_ppt_entry": "Router",
    "generate_ppt": "PPTGenAgent",
    "critic_review_ppt": "PPTCriticAgent",
    "generate_summary": "SummaryAgent",
    "auto_tagging": "Auto_Tagging",
    "literature_guide": "Literature_Guide",
}


async def run_workflow_streaming(
    uploaded_files: list,
    rag_engine: RAGEngine,
    llm_client,
    user_instruction: str = "",
    max_retries: int = 3,
    thread_id: str = "",
    user_id: str = "",
):
    """
    流式执行工作流，逐步 yield SSE 事件

    Yields:
        dict: {"status", "node", "agent", "message", "data"}
    """
    graph = build_workflow_graph(rag_engine, llm_client, max_retries)

    file_path = ""
    file_type = ""
    if uploaded_files:
        file_path = uploaded_files[0].get("path", "")
        file_type = uploaded_files[0].get("type", "")

    update_state = {
        "user_instruction": user_instruction,
        "max_retries": max_retries,
        "uploaded_files": uploaded_files,
        "user_id": user_id,
    }
    if file_path:
        update_state["file_path"] = file_path
    if file_type:
        update_state["file_type"] = file_type

    config = {"configurable": {"thread_id": thread_id}} if thread_id else None

    file_desc = ", ".join(f.get("filename", "") for f in uploaded_files) if uploaded_files else ""
    yield {
        "status": "processing",
        "node": "",
        "agent": "System",
        "message": f"[System] 开始处理: {file_desc or '纯文本模式（无文件）'}",
        "data": {},
    }

    final_output_path = ""
    final_file_type = ""
    final_filled_html = ""
    final_image_store = {}
    final_structured_data = {}
    final_ppt_data = {}

    try:
        async for event in graph.astream(update_state, config=config):
            for node_name, node_state in event.items():
                if not isinstance(node_state, dict):
                    continue

                display = NODE_DISPLAY_NAMES.get(node_name, node_name)
                agent = NODE_AGENT_NAMES.get(node_name, node_name)
                error = node_state.get("error_message", "")
                file_type = node_state.get("file_type", "")
                final_file_type = file_type or final_file_type

                filled = node_state.get("filled_html", "")
                if filled:
                    final_filled_html = filled

                img_store = node_state.get("image_store", {})
                if img_store:
                    final_image_store = img_store

                sd = node_state.get("structured_data", {})
                if sd:
                    final_structured_data = sd

                pd = node_state.get("ppt_data", {})
                if pd:
                    final_ppt_data = pd

                if error and not file_type:
                    yield {
                        "status": "error",
                        "node": node_name,
                        "agent": agent,
                        "message": f"[{agent}] {display}失败: {error}",
                        "data": {"error": error},
                    }
                    continue

                sse_event = _build_node_event(node_name, node_state, display, agent)
                if sse_event:
                    yield sse_event

                kg_data = None
                if sd and isinstance(sd, dict):
                    kg_data = sd.get("knowledge_graph")
                if kg_data and isinstance(kg_data, dict) and kg_data.get("nodes"):
                    logger.info(f"🧠 [Graph] 检测到知识图谱数据: {len(kg_data.get('nodes', []))} nodes, {len(kg_data.get('edges', []))} edges → yield generative_ui")
                    yield {
                        "status": "generative_ui",
                        "component": "knowledge_graph",
                        "data": kg_data,
                    }

                output = node_state.get("output_path", "")
                if output:
                    final_output_path = output

    except Exception as e:
        logger.error(f"Workflow streaming error: {e}", exc_info=True)
        yield {
            "status": "error",
            "node": "",
            "agent": "System",
            "message": f"[System] 工作流执行异常: {str(e)}",
            "data": {"error": str(e)},
        }

    download_url = ""
    if final_output_path and os.path.exists(final_output_path):
        filename = os.path.basename(final_output_path)
        download_url = f"/api/v1/files/output/{filename}"

    if final_filled_html:
        from app.services.document_service import restore_images_to_html
        preview_html = restore_images_to_html(final_filled_html, final_image_store)

        yield {
            "status": "preview",
            "node": "",
            "agent": "System",
            "message": "[System] 文档预览已生成",
            "data": {"html": preview_html},
        }

    presentation_data = final_ppt_data or final_structured_data.get("presentation")
    if presentation_data:
        yield {
            "status": "ppt_ready",
            "ppt_data": presentation_data,
        }

    yield {
        "status": "success",
        "node": "",
        "agent": "System",
        "message": "[System] 处理完成!",
        "data": {
            "url": download_url,
            "file_type": final_file_type,
            "output_path": final_output_path,
        },
    }


def _build_node_event(
    node_name: str,
    node_state: dict,
    display: str,
    agent: str,
) -> Optional[dict]:
    """根据节点类型构建 SSE 事件，消息格式: [Agent名] 描述"""

    if node_name == "gateway":
        file_type = node_state.get("file_type", "未知")
        task_intent = node_state.get("task_intent", "fill_document")
        type_labels = {"docx": "Word文档", "xlsx": "Excel表格", "csv": "CSV数据表", "pptx": "PPT演示"}
        label = type_labels.get(file_type, file_type)

        if task_intent == "generate_ppt":
            return {
                "status": "processing",
                "node": node_name,
                "agent": agent,
                "message": f"[{agent}] 检测到 PPT 生成意图，正在切换至演示文稿流水线...",
                "data": {"file_type": file_type, "task_intent": task_intent},
            }

        agent_map = {"docx": "FillAgent", "xlsx": "DataAgent", "csv": "DataAgent", "pptx": "PPTAgent"}
        target_agent = agent_map.get(file_type, "Agent")
        return {
            "status": "processing",
            "node": node_name,
            "agent": agent,
            "message": f"[{agent}] 发现是{label}，正在分配给{target_agent}...",
            "data": {"file_type": file_type},
        }

    elif node_name == "extract_context":
        empty_count = len([f for f in node_state.get("empty_fields", []) if f.get("type") == "table_empty"])
        qa_count = len([f for f in node_state.get("empty_fields", []) if f.get("type") == "qa"])
        fb_count = len([f for f in node_state.get("empty_fields", []) if f.get("type") == "fill_blank"])
        has_fields = node_state.get("has_fields_to_fill", True)
        if not has_fields:
            return {
                "status": "processing",
                "node": node_name,
                "agent": agent,
                "message": f"[{agent}] 未发现需要处理的内容，触发熔断",
                "data": {"empty_fields_count": 0, "circuit_break": True},
            }
        parts = []
        if empty_count:
            parts.append(f"{empty_count}个空缺单元格")
        if qa_count:
            parts.append(f"{qa_count}个问答题")
        if fb_count:
            parts.append(f"{fb_count}个填空题")
        summary = "、".join(parts) if parts else "0个"
        return {
            "status": "processing",
            "node": node_name,
            "agent": agent,
            "message": f"[{agent}] 文档分析完毕，发现{summary}需要处理",
            "data": {"empty_fields_count": empty_count, "qa_count": qa_count, "fill_blank_count": fb_count},
        }

    elif node_name == "retrieve_knowledge":
        ctx_count = len(node_state.get("retrieved_context", []))
        ctx_summary = node_state.get("context_summary", "")
        if ctx_count == 0 or ctx_summary == "无参考知识":
            return {
                "status": "processing",
                "node": node_name,
                "agent": agent,
                "message": f"[{agent}] 知识库为空或未命中，将仅依赖大模型自身知识进行处理...",
                "data": {"context_count": 0, "fallback": True},
            }
        return {
            "status": "processing",
            "node": node_name,
            "agent": agent,
            "message": f"[{agent}] 智能重写查询词成功，从知识库检索到 {ctx_count} 条相关信息",
            "data": {"context_count": ctx_count},
        }

    elif node_name == "reason_and_fill":
        retry = node_state.get("retry_count", 0)
        suffix = f" (第{retry + 1}次尝试)" if retry > 0 else ""
        return {
            "status": "processing",
            "node": node_name,
            "agent": agent,
            "message": f"[{agent}] 正在调用AI模型生成填充内容{suffix}...",
            "data": {"retry_count": retry},
        }

    elif node_name == "critic_review":
        review = node_state.get("review_result", "")
        if review == "pass":
            return {
                "status": "processing",
                "node": node_name,
                "agent": agent,
                "message": f"[{agent}] 审查通过 ✓，数据质量合格",
                "data": {"review_result": "pass"},
            }
        else:
            feedback = node_state.get("review_feedback", "")[:200]
            return {
                "status": "processing",
                "node": node_name,
                "agent": agent,
                "message": f"[{agent}] 审查未通过 ✗，需要修正: {feedback[:80]}...",
                "data": {"review_result": "fail", "feedback": feedback},
            }

    elif node_name == "increment_retry":
        retry = node_state.get("retry_count", 0)
        return {
            "status": "processing",
            "node": node_name,
            "agent": agent,
            "message": f"[{agent}] 根据审查反馈优化填充 (重试 #{retry})",
            "data": {"retry_count": retry},
        }

    elif node_name == "process_excel":
        code_err = node_state.get("code_execution_error", "")
        generated_code = node_state.get("generated_code", "")
        structured = node_state.get("structured_data", {})

        if code_err:
            return {
                "status": "processing",
                "node": node_name,
                "agent": agent,
                "message": f"[{agent}] 代码执行出错，正在自我纠错: {code_err[:100]}",
                "data": {"error": code_err, "generated_code": generated_code},
            }

        if structured:
            orig = structured.get("original_shape", [])
            result = structured.get("result_shape", [])
            attempts = structured.get("attempts", 1)
            self_corrected = structured.get("self_corrected", False)
            correction_tag = " (经自我纠错修复)" if self_corrected else ""
            return {
                "status": "processing",
                "node": node_name,
                "agent": agent,
                "message": f"[{agent}] 数据清洗完成{correction_tag}! {orig} → {result} (尝试{attempts}次)",
                "data": {"structured_data": structured, "generated_code": generated_code},
            }

        return {
            "status": "processing",
            "node": node_name,
            "agent": agent,
            "message": f"[{agent}] 正在提取数据Schema并生成清洗代码...",
            "data": {},
        }

    elif node_name == "process_ppt":
        structured = node_state.get("structured_data", {})
        slide_count = structured.get("slide_count", 0) if structured else 0
        slide_deck = structured.get("slide_deck") if structured else None
        event_data = {"slide_count": slide_count}
        if slide_deck:
            event_data["slide_deck"] = slide_deck
        return {
            "status": "processing",
            "node": node_name,
            "agent": agent,
            "message": f"[{agent}] PPT分析完成，提取了 {slide_count} 页幻灯片",
            "data": event_data,
        }

    elif node_name == "generate_ppt":
        structured = node_state.get("structured_data", {})
        presentation = structured.get("presentation") if structured else None
        slide_count = len(presentation.get("slides", [])) if presentation else 0
        retry_count = node_state.get("retry_count", 0)
        event_data = {"slide_count": slide_count}
        if presentation:
            event_data["presentation"] = presentation
        suffix = f" (自我纠错第{retry_count}次)" if retry_count > 0 else ""
        return {
            "status": "processing",
            "node": node_name,
            "agent": agent,
            "message": f"[{agent}] PPT生成完成{suffix}，共 {slide_count} 页幻灯片",
            "data": event_data,
        }

    elif node_name == "critic_review_ppt":
        review = node_state.get("review_result", "")
        retry_count = node_state.get("retry_count", 0)
        if review == "pass":
            return {
                "status": "processing",
                "node": node_name,
                "agent": agent,
                "message": f"[{agent}] PPT审查通过 ✓，格式与内容质量合格",
                "data": {"review_result": "pass"},
            }
        else:
            feedback = node_state.get("feedback", "")[:200]
            return {
                "status": "processing",
                "node": node_name,
                "agent": agent,
                "message": f"[{agent}] PPT审查未通过 ✗ (重试 {retry_count}/{PPT_MAX_RETRIES})，正在自我修正: {feedback[:80]}...",
                "data": {"review_result": "fail", "feedback": feedback, "retry_count": retry_count},
            }

    elif node_name == "supervisor":
        next_node = node_state.get("next_node", "generate_ppt")
        next_label = {"web_researcher": "联网检索", "generate_ppt": "PPT生成", "generate_summary": "长文总结", "FINISH": "结束"}.get(next_node, next_node)
        return {
            "status": "processing",
            "node": node_name,
            "agent": agent,
            "message": f"[{agent}] 任务调度完成，指派给: {next_label}",
            "data": {"next_node": next_node},
        }

    elif node_name == "web_researcher":
        messages = node_state.get("messages", [])
        result_len = 0
        if messages:
            last_msg = messages[-1].content if messages else ""
            result_len = len(last_msg)
        return {
            "status": "processing",
            "node": node_name,
            "agent": agent,
            "message": f"[{agent}] 联网检索完成，获得 {result_len} 字符的资料",
            "data": {"result_length": result_len},
        }

    elif node_name == "knowledge_librarian":
        messages = node_state.get("messages", [])
        result_len = 0
        if messages:
            last_msg = messages[-1].content if messages else ""
            result_len = len(last_msg)
        return {
            "status": "processing",
            "node": node_name,
            "agent": agent,
            "message": f"[{agent}] 知识库检索完成，获得 {result_len} 字符的资料",
            "data": {"result_length": result_len},
        }

    elif node_name == "generate_summary":
        filled = node_state.get("filled_html", "")
        has_result = bool(filled)
        return {
            "status": "processing",
            "node": node_name,
            "agent": agent,
            "message": f"[{agent}] 多文档知识点提炼{'完成' if has_result else '中...'}",
            "data": {"has_summary": has_result},
        }

    elif node_name == "auto_tagging":
        tags = node_state.get("tags", [])
        desc = node_state.get("description", "")
        tag_str = ", ".join(tags[:3]) if tags else "无"
        return {
            "status": "processing",
            "node": node_name,
            "agent": agent,
            "message": f"[{agent}] 标签提取完成: {tag_str}" + (f" | 描述: {desc[:60]}" if desc else ""),
            "data": {"tags": tags, "description": desc},
        }

    elif node_name == "literature_guide":
        guide_html = node_state.get("guide_html", "")
        has_guide = bool(guide_html)
        return {
            "status": "processing",
            "node": node_name,
            "agent": agent,
            "message": f"[{agent}] 文献导读{'生成完成' if has_guide else '生成中...'}",
            "data": {"has_guide": has_guide},
        }

    return {
        "status": "processing",
        "node": node_name,
        "agent": agent,
        "message": f"[{agent}] 执行节点: {display}",
        "data": {},
    }


def build_table_fill_graph(
    rag_engine: RAGEngine,
    llm_client,
    max_retries: int = 3,
) -> StateGraph:
    return build_workflow_graph(rag_engine, llm_client, max_retries)


async def run_table_fill_workflow(
    html: str,
    rag_engine: RAGEngine,
    llm_client,
    table_index: int = 0,
    max_retries: int = 3,
) -> Dict[str, Any]:
    graph = build_workflow_graph(rag_engine, llm_client, max_retries)
    initial_state = _make_initial_state("", "", max_retries)
    initial_state.update({
        "file_type": "docx",
        "original_html": html,
        "current_html": html,
        "table_index": table_index,
    })

    final_state = await graph.ainvoke(initial_state)

    return {
        "filled_html": final_state.get("filled_html", ""),
        "review_result": final_state.get("review_result", "unknown"),
        "review_feedback": final_state.get("review_feedback", ""),
        "retry_count": final_state.get("retry_count", 0),
        "retrieved_context": final_state.get("retrieved_context", []),
        "error_message": final_state.get("error_message", ""),
    }
