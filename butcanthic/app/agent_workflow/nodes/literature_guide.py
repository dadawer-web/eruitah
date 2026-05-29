import logging
import re

from app.agent_workflow.state import WorkflowState

logger = logging.getLogger(__name__)


async def literature_guide_node(state: WorkflowState, llm_client=None) -> dict:
    logger.info("📖 [LiteratureGuide] 正在生成文献导读...")

    from app.core.prompt_manager import PromptManager

    document_content = ""
    uploaded_files = state.get("uploaded_files", [])
    for f in uploaded_files:
        from app.agent_workflow.nodes.generate_ppt import _extract_document_content
        result = await _extract_document_content(f.get("path", ""), f.get("type", ""))
        if result.get("text"):
            document_content += result["text"] + "\n\n"

    if not document_content.strip():
        document_content = state.get("current_html", "")[:5000]

    if not document_content.strip():
        logger.warning("📖 [LiteratureGuide] 无文档内容可分析")
        return {"guide_html": "<p>无法生成导读：文档内容为空</p>", "current_progress": 50, "current_action": "导读生成失败"}

    system_prompt = PromptManager.get_prompt("literature_guide_system")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"请为以下文档生成阅读指南：\n\n{document_content[:8000]}"},
    ]

    try:
        response = await llm_client.acall_api(messages, max_tokens=8192)

        if not response or not response.strip():
            logger.warning("📖 [LiteratureGuide] 大模型返回空")
            return {"guide_html": "<p>导读生成失败：模型返回空</p>", "current_progress": 50, "current_action": "导读生成失败"}

        guide_html = response.strip()
        for prefix in ["```markdown", "```md", "```"]:
            if guide_html.startswith(prefix):
                guide_html = guide_html[len(prefix):]
        if guide_html.endswith("```"):
            guide_html = guide_html[:-3]
        guide_html = guide_html.strip()

        import markdown
        try:
            guide_html = markdown.markdown(guide_html, extensions=["tables", "fenced_code", "codehilite"])
        except ImportError:
            pass

        logger.info(f"📖 [LiteratureGuide] 导读生成完成 ({len(guide_html)} chars)")
        return {
            "guide_html": guide_html,
            "current_progress": 70,
            "current_action": "文献导读生成完成",
        }

    except Exception as e:
        logger.error(f"📖 [LiteratureGuide] 失败: {e}")
        return {"guide_html": f"<p>导读生成失败: {e}</p>", "current_progress": 50, "current_action": f"导读生成失败: {e}"}
