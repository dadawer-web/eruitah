import json
import logging
import re

from app.agent_workflow.state import WorkflowState
from app.agent_workflow.nodes.generate_ppt import _extract_document_content
from app.core.prompt_manager import PromptManager

logger = logging.getLogger(__name__)

KG_EXTRACT_PROMPT = """请从以下总结中提取核心实体与关系网络，输出纯JSON格式。

总结内容：
{summary_text}

要求：
1. 提取5-15个核心实体（人名、公司、技术、产品、概念等）
2. 提取实体之间的关键关系
3. 严格输出以下JSON格式，不要输出任何其他内容：
{{"nodes": [{{"id": "实体名称", "category": "人/公司/技术/产品/概念/事件"}}], "edges": [{{"source": "实体1", "target": "实体2", "label": "关系说明"}}]}}"""


async def generate_summary_node(state: WorkflowState, llm_client) -> dict:
    uploaded_files = state.get("uploaded_files", [])
    user_instruction = state.get("user_instruction", "请总结这些文档的核心内容。")

    document_content = ""
    collected_images = []
    logger.info(f"SummaryAgent: 开始提取 {len(uploaded_files)} 份文档的文字内容...")

    for f in uploaded_files:
        try:
            result = await _extract_document_content(f.get("path"), f.get("type"))
            filename = f.get("filename", "未知文件")
            text = result.get("text", "")
            images = result.get("images", [])

            if text and text.strip():
                document_content += f"\n\n=== 【文献来源：{filename}】 ===\n{text}"
                logger.info(f"SummaryAgent: 成功从 {filename} 提取了 {len(text)} 个字符。")
            else:
                logger.warning(f"SummaryAgent: ⚠️ 警告！从 {filename} 提取到的内容为空！")

            if images:
                collected_images.extend(images[:5])
                logger.info(f"SummaryAgent: 从 {filename} 提取了 {len(images)} 张图片。")
        except Exception as e:
            logger.error(f"提取文件 {f.get('filename')} 失败: {e}")

    if not document_content.strip() and not collected_images:
        logger.error("SummaryAgent: 所有文件均未提取到有效文本或图片！直接熔断，防止瞎编。")
        error_html = "<div style='padding: 20px; color: #ef4444;'><h2>🚨 解析失败</h2><p>抱歉，系统未能从您上传的文件中提取到任何有效文字。这可能是因为文件是纯图片构成的 PDF/Word，或者文件已损坏。请重试。</p></div>"
        return {"filled_html": error_html}

    messages = state.get("messages", [])
    research_context = ""
    if messages:
        parts = []
        for msg in messages:
            if hasattr(msg, 'name') and msg.name in ("Web_Researcher", "Knowledge_Librarian") and msg.content:
                parts.append(f"=== 【{msg.name} 提供的外部检索信息】 ===\n{msg.content}")

        if parts:
            research_context = "\n\n".join(parts)
            logger.info(f"SummaryAgent: 成功捕获并注入了 {len(parts)} 条外部检索/知识库数据！")
            document_content += f"\n\n{research_context}"

    logger.info(f"SummaryAgent: 资料整合完毕，总计 {len(document_content)} 字符 + {len(collected_images)} 张图片，开始呼叫大模型...")

    image_store = state.get("image_store", {})
    base64_images = list(image_store.values())
    if collected_images:
        for img in collected_images:
            if img not in base64_images:
                base64_images.append(img)

    if not base64_images:
        html_content = state.get("current_html", "")
        if html_content:
            try:
                from app.services.document_service import strip_images_from_html
                _, new_image_store = strip_images_from_html(html_content)
                base64_images = list(new_image_store.values())
                logger.info(f"SummaryAgent: 救场成功！临时从 HTML 中提取了 {len(base64_images)} 张图片。")
            except Exception as e:
                logger.error(f"SummaryAgent: 从 HTML 提取图片失败: {e}")

    if base64_images:
        logger.info(f"SummaryAgent: 最终确认有 {len(base64_images)} 张图片准备发送给视觉大模型。")

    messages_list = [
        {
            "role": "system",
            "content": PromptManager.get_prompt("process_summary_system"),
        },
        {
            "role": "user",
            "content": f"【用户需求】: {user_instruction}\n\n【参考资料库】:\n{document_content}",
            "images": base64_images
        }
    ]

    try:
        response = await llm_client.acall_api(
            messages_list,
            max_tokens=8192,
        )
    except Exception as e:
        logger.error(f"调用大模型生成总结失败: {e}")
        return {"filled_html": f"<div style='color:red;'>生成失败: {str(e)}</div>"}

    if not response:
        logger.error("SummaryAgent: 接收到的 response 为空，可能是 API 密钥错误或模型不支持图片！")
        error_html = """
        <div style='padding: 24px; background-color: #1e1e2e; color: #ef4444; border-radius: 8px;'>
            <h2>🚨 生成中断：模型调度失败</h2>
            <p>系统已成功提取文档和图片，但底层 AI 模型拒绝了包含图片的请求。这通常是因为：</p>
            <ul style='color: #d1d5db; margin-top: 10px;'>
                <li>当前配置的模型（如 mimo-v2.5-pro）是纯文本模型，不支持多模态视觉 (Vision)。</li>
                <li>API 提供商未开放该模型的图片传入接口。</li>
            </ul>
            <p style='margin-top: 10px;'><b>💡 解决方案：</b>请在 <code>ai_models_config.json</code> 中将模型切换为 <code>gpt-4o</code>、<code>claude-3.5-sonnet</code> 或 <code>qwen-vl-plus</code> 等支持视觉的多模态模型。</p>
        </div>
        """
        return {"filled_html": error_html}

    clean_response = response.replace("```html", "").replace("```", "").strip()

    preview_html = f"<div style='padding: 24px; min-height: 100%; overflow-y: auto; background-color: #1e1e2e; color: #e2e8f0; font-family: sans-serif; border-radius: 8px; box-shadow: inset 0 0 10px rgba(0,0,0,0.5);'>"
    preview_html += f"<h2 style='color: #818cf8; border-bottom: 2px solid #4f46e5; padding-bottom: 12px; margin-bottom: 20px;'>📝 深度知识图谱与全网对比</h2>"
    preview_html += f"<div style='line-height: 1.8; font-size: 15px;'>{clean_response}</div>"
    preview_html += "</div>"

    knowledge_graph = None
    try:
        kg_prompt = KG_EXTRACT_PROMPT.format(summary_text=clean_response[:4000])
        kg_messages = [{"role": "user", "content": kg_prompt}]
        kg_response = await llm_client.acall_api(kg_messages, max_tokens=8192)
        if kg_response:
            knowledge_graph = _parse_knowledge_graph(kg_response)
            if knowledge_graph:
                logger.info(f"SummaryAgent: 知识图谱抽取成功: {len(knowledge_graph.get('nodes', []))} nodes, {len(knowledge_graph.get('edges', []))} edges")
            else:
                logger.warning("SummaryAgent: 知识图谱 JSON 解析失败")
    except Exception as e:
        logger.warning(f"SummaryAgent: 知识图谱抽取失败: {e}")

    structured_data = {"knowledge_graph": knowledge_graph} if knowledge_graph else {}

    return {
        "filled_html": preview_html,
        "structured_data": structured_data,
        "current_progress": 90,
        "current_action": "深度总结生成完毕",
    }


def _parse_knowledge_graph(text: str) -> dict:
    if not text:
        return None

    cleaned = text.strip()

    cleaned = re.sub(r"<think[^>]*>.*?</think\s*>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    cleaned = re.sub(r"^[^{]*", "", cleaned)
    cleaned = re.sub(r"[^}]*$", "", cleaned)

    code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if code_block:
        candidate = code_block.group(1).strip()
        candidate = re.sub(r"<think[^>]*>.*?</think\s*>", "", candidate, flags=re.DOTALL | re.IGNORECASE)
        candidate = re.sub(r"<[^>]+>", "", candidate)
        if "{\"nodes\"" in candidate or "{'nodes'" in candidate:
            cleaned = candidate

    brace_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if brace_match:
        cleaned = brace_match.group(0)

    cleaned = re.sub(r",\s*}", "}", cleaned)
    cleaned = re.sub(r",\s*]", "]", cleaned)

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict) and "nodes" in parsed and "edges" in parsed:
            nodes = parsed["nodes"]
            edges = parsed["edges"]
            if isinstance(nodes, list) and isinstance(edges, list) and len(nodes) > 0:
                valid_nodes = []
                for n in nodes:
                    if isinstance(n, dict) and "id" in n:
                        valid_nodes.append({
                            "id": str(n["id"]),
                            "category": str(n.get("category", "概念")),
                        })
                valid_edges = []
                node_ids = {nd["id"] for nd in valid_nodes}
                for e in edges:
                    if isinstance(e, dict) and "source" in e and "target" in e:
                        src = str(e["source"])
                        tgt = str(e["target"])
                        if src in node_ids and tgt in node_ids:
                            valid_edges.append({
                                "source": src,
                                "target": tgt,
                                "label": str(e.get("label", "")),
                            })
                if valid_nodes:
                    return {"nodes": valid_nodes, "edges": valid_edges}
    except (json.JSONDecodeError, ValueError):
        pass

    return None
