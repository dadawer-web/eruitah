import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.agent_workflow.state import WorkflowState
from app.core.prompt_manager import PromptManager

logger = logging.getLogger(__name__)

RESEARCH_KEYWORDS = re.compile(
    r"调研|搜索|查资料|写报告|研究报告|深度研究|调研报告|查一下|联网|对比最新|外网|最新新闻|资讯",
    re.IGNORECASE,
)
PPT_STRICT_KEYWORDS = re.compile(r"PPT|幻灯片|演示文稿|课件|slides", re.IGNORECASE)


class RouteDecision(BaseModel):
    next_node: str = Field(
        description="【强制约束】必须且只能使用 'next_node' 作为键名。值为下一步要执行的节点：'web_researcher', 'knowledge_librarian', 'generate_ppt', 'generate_summary', 或 'FINISH'"
    )


def _fallback_route(user_instruction: str) -> str:
    if RESEARCH_KEYWORDS.search(user_instruction):
        logger.info("👔 [Supervisor] 兜底路由：检测到调研/报告关键词 → web_researcher")
        return "web_researcher"
    if PPT_STRICT_KEYWORDS.search(user_instruction):
        logger.info("👔 [Supervisor] 兜底路由：检测到PPT关键词 → generate_ppt")
        return "generate_ppt"
    logger.info("👔 [Supervisor] 兜底路由：默认 → generate_summary")
    return "generate_summary"


async def supervisor_node(state: WorkflowState, llm_client=None) -> dict:
    logger.info("👔 [Supervisor] 正在评估当前任务进度...")

    user_instruction = state.get("user_instruction", "")

    if llm_client is None or llm_client.langchain_llm is None:
        fallback = _fallback_route(user_instruction)
        logger.warning(f"👔 [Supervisor] LLM 不可用，兜底路由至 {fallback}")
        return {"next_node": fallback}

    llm = llm_client.langchain_llm
    structured_llm = llm.with_structured_output(RouteDecision)

    messages = state.get("messages", [])
    history_str = "\n".join([f"[{m.name if hasattr(m, 'name') else m.type}]: {m.content[:100]}..." for m in messages])

    try:
        input_messages = state.get("messages", [])
        if not input_messages:
            user_instruction = state.get("user_instruction", "")
            input_messages = [HumanMessage(content=user_instruction)]

        system_content = PromptManager.get_prompt("supervisor_system", history_str=history_str)
        followup_content = PromptManager.get_prompt("supervisor_system_followup")

        prompt_messages = [
            SystemMessage(content=system_content),
            *input_messages,
            SystemMessage(content=followup_content),
        ]

        decision = await structured_llm.ainvoke(prompt_messages)
        next_node = decision.next_node
    except Exception as e:
        fallback = _fallback_route(user_instruction)
        logger.warning(f"👔 [Supervisor] 路由决策失败: {e}，兜底至 {fallback}")
        next_node = fallback

    logger.info(f"👔 [Supervisor] 决定将任务分配给: {next_node}")

    if PPT_STRICT_KEYWORDS.search(user_instruction):
        has_ppt_output = bool(state.get("ppt_slides")) or bool(state.get("ppt_output_path"))
        if not has_ppt_output and next_node != "generate_ppt":
            logger.info(f"👔 [Supervisor] PPT保护: 用户要求PPT但LLM路由到'{next_node}'，强制覆盖 → generate_ppt")
            next_node = "generate_ppt"

    return {
        "next_node": next_node,
        "current_progress": 20,
        "current_action": f"任务调度完成，指派给: {next_node}",
    }
