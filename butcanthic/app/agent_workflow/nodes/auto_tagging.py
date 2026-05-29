import json
import logging
import re

from app.agent_workflow.state import WorkflowState

logger = logging.getLogger(__name__)


async def auto_tagging_node(state: WorkflowState, llm_client=None) -> dict:
    logger.info("🏷️ [AutoTagging] 正在为文档提取标签...")

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
        logger.warning("🏷️ [AutoTagging] 无文档内容可分析")
        return {"tags": [], "current_progress": 50, "current_action": "标签提取失败：无内容"}

    system_prompt = PromptManager.get_prompt("literature_classification_system")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"请为以下文档内容生成分类标签和描述：\n\n{document_content[:8000]}"},
    ]

    try:
        response = await llm_client.acall_api(messages, max_tokens=8192)

        if not response or not response.strip():
            logger.warning("🏷️ [AutoTagging] 大模型返回空")
            return {"tags": [], "current_progress": 50, "current_action": "标签提取：模型返回空"}

        cleaned = re.sub(r'<think[^>]*>.*?</think\s*>', '', response.strip(), flags=re.DOTALL).strip()
        json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                tags = parsed.get("tags", [])
                desc = parsed.get("desc", "")
                logger.info(f"🏷️ [AutoTagging] 提取到 {len(tags)} 个标签: {tags}")
                return {
                    "tags": tags[:5],
                    "description": desc,
                    "current_progress": 55,
                    "current_action": f"标签提取完成：{', '.join(tags[:3])}",
                }
            except json.JSONDecodeError:
                pass

        raw_tags = [t.strip() for t in response.strip().split(",") if t.strip()][:5]
        return {"tags": raw_tags, "current_progress": 55, "current_action": f"标签提取完成（原始）：{', '.join(raw_tags[:3])}"}

    except Exception as e:
        logger.error(f"🏷️ [AutoTagging] 失败: {e}")
        return {"tags": [], "current_progress": 50, "current_action": f"标签提取失败: {e}"}
