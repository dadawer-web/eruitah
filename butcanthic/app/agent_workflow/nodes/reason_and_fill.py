"""
Node 3: ReasonAndFill - 精准占位符填空
不再让 AI 返回整个 HTML！
Step 1: 从 state 取出 placeholder_map 和 tagged_html
Step 2: 给 LLM 看占位符上下文，要求返回 JSON: {"[[ANS_0]]": "答案", ...}
Step 3: 在节点中做字符串替换，将答案填入 HTML
Step 4: 恢复 Base64 图片数据
优势: LLM 输出极短，不会截断；HTML 结构完全不变
"""

import json
import logging
import re
from typing import Any, Dict

from app.agent_workflow.state import WorkflowState
from app.core.prompt_manager import PromptManager

logger = logging.getLogger(__name__)


async def reason_and_fill(state: WorkflowState, llm_client) -> WorkflowState:
    tagged_html = state.get("current_html", "")
    placeholder_map = state.get("placeholder_map", {})
    context_summary = state.get("context_summary", "")
    review_feedback = state.get("review_feedback", "")
    retry_count = state.get("retry_count", 0)

    if not placeholder_map:
        logger.info("ReasonAndFill: no placeholders, returning original HTML")
        return {**state, "filled_html": tagged_html}

    all_placeholders = set(placeholder_map.keys())
    html_placeholders = set(re.findall(r'\[\[ANS_\d+\]\]', tagged_html))
    all_placeholders = all_placeholders | html_placeholders

    placeholder_desc = _describe_placeholders(placeholder_map)
    full_html_text = _html_to_clean_text(tagged_html)

    user_prompt = PromptManager.get_prompt(
        "reason_and_fill_user",
        placeholder_desc=placeholder_desc,
        full_html_text=full_html_text,
        context_summary=context_summary or "（无知识库参考，请基于自身知识作答）",
        review_feedback=review_feedback or "（首次处理，无审查反馈）",
    )

    logger.info(f"准备调用大模型，发送的 Prompt 长度为: {len(user_prompt)}")
    logger.info(
        f"ReasonAndFill: calling LLM for {len(placeholder_map)} placeholders "
        f"(retry={retry_count})"
    )

    messages = [
        {"role": "system", "content": PromptManager.get_prompt("reason_and_fill_system")},
        {"role": "user", "content": user_prompt},
    ]

    answers = {}

    try:
        model_info = llm_client.get_model_info() if hasattr(llm_client, 'get_model_info') else {}
        logger.info(
            f"🚀 [FillAgent] 即将调用大模型 | "
            f"model={model_info.get('model', 'unknown')} | "
            f"provider={model_info.get('provider', 'unknown')} | "
            f"model_name={model_info.get('model_name', 'unknown')} | "
            f"initialized={getattr(llm_client, 'langchain_initialized', 'N/A')}"
        )
        response = await llm_client.acall_api(messages)
    except Exception as e:
        logger.error(
            f"🚨 大模型 API 底层调用发生致命错误 | "
            f"exception_type={type(e).__name__} | "
            f"exception_repr={repr(e)}"
        )
        import traceback
        logger.error(f"🚨 完整堆栈追踪:\n{traceback.format_exc()}")
        response = None

    else:
        if not response:
            logger.error(
                "🚨 [FillAgent] 大模型返回空响应！可能原因: "
                "1) API Key 无效/余额不足 2) 网络超时 3) Token 超限 4) 模型名称配置错误"
            )
            logger.error(
                f"🚨 [FillAgent] LLM 客户端状态 | "
                f"initialized={getattr(llm_client, 'langchain_initialized', 'N/A')} | "
                f"selected_model={getattr(llm_client, 'selected_model', 'N/A')} | "
                f"current_config={getattr(llm_client, 'current_config', {})}"
            )
        else:
            logger.warning(f"📋 [FillAgent] 大模型原始返回内容: '{response[:500]}'")
            if not response.strip():
                logger.error("🚨 [FillAgent] 大模型返回内容为纯空白！可能是 Content Filter 拦截")
            answers = _parse_json_answers(response)
            if not answers:
                logger.warning("[FillAgent] JSON解析失败，大模型输出异常")
                logger.warning(f"[FillAgent] LLM raw response (first 500 chars): {response[:500]}")

    missing = all_placeholders - set(answers.keys())
    if missing:
        logger.error(f"大模型罢工或解析失败，启动兜底机制！缺失 {len(missing)} 个占位符")
        for placeholder in missing:
            answers[placeholder] = f"⚠️ AI生成失败({placeholder})"

    filled_html = tagged_html
    filled_count = 0
    for tag, answer in answers.items():
        if tag in all_placeholders:
            formatted = _format_ai_answer(answer)
            filled_html = filled_html.replace(tag, formatted)
            filled_count += 1

    logger.info(
        f"ReasonAndFill: filled {filled_count}/{len(all_placeholders)} placeholders "
        f"(fallback={len(missing)})"
    )

    return {**state, "filled_html": filled_html}


def _describe_placeholders(placeholder_map: Dict[str, Any]) -> str:
    if not placeholder_map:
        return "无占位符"

    lines = []
    for tag, info in placeholder_map.items():
        ptype = info.get("type", "unknown")
        if ptype == "table_empty":
            header = info.get("header", "未知")
            context = info.get("context", "")
            desc = f"- {tag} [空表格单元格] 列名「{header}」"
            if context:
                desc += f"，同行上下文: {context}"
        elif ptype == "qa":
            question = info.get("question", "")
            desc = f"- {tag} [问答题] 问题: {question[:150]}"
        elif ptype == "fill_blank":
            surrounding = info.get("surrounding_text", "")
            desc = f"- {tag} [填空题] 上下文: {surrounding[:150]}"
        else:
            desc = f"- {tag} [未知类型]"
        lines.append(desc)

    return "\n".join(lines)


def _html_to_clean_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator="\n", strip=True)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()

    max_len = 50000
    if len(text) > max_len:
        text = text[:max_len] + "\n...(文档过长，已截断)"
    logger.info(f"[_html_to_clean_text] 传给LLM的文档纯文本长度: {len(text)} 字符")
    return text


def _format_ai_answer(text: str) -> str:
    if not text:
        return text

    is_short_table_value = len(text) <= 20 and '\n' not in text and '```' not in text
    if is_short_table_value:
        return text

    def _code_replacer(match):
        code_content = match.group(2).strip()
        lang = match.group(1).strip() if match.group(1) else ""
        escaped = code_content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        lang_label = f'<div style="font-size: 11px; color: #6c757d; margin-bottom: 4px; font-family: Consolas, monospace;">{lang}</div>' if lang else ''
        return (
            f'<div style="background-color: #f8f9fa; border: 1px solid #e9ecef; '
            f'border-radius: 6px; padding: 12px; margin: 8px 0; overflow-x: auto;">'
            f'{lang_label}'
            f'<pre style="margin: 0; font-family: Consolas, monospace; font-size: 13px; '
            f'white-space: pre-wrap; word-wrap: break-word; color: #333; line-height: 1.5;">'
            f'{escaped}</pre></div>'
        )

    processed = re.sub(r'```([a-zA-Z]*)\n?(.*?)```', _code_replacer, text, flags=re.DOTALL)

    if '<div style="background-color: #f8f9fa' in processed:
        parts = processed.split('</div>')
        final_parts = []
        for part in parts:
            if '<div style="background-color: #f8f9fa' in part:
                sub_parts = part.split('<div style="background-color: #f8f9fa', 1)
                normal_text = sub_parts[0].replace('\n', '<br>')
                code_html = '<div style="background-color: #f8f9fa' + sub_parts[1]
                final_parts.append(normal_text + code_html)
            else:
                final_parts.append(part.replace('\n', '<br>'))
        processed = '</div>'.join(final_parts)
    else:
        processed = processed.replace('\n', '<br>')

    return processed


def _parse_json_answers(response: str) -> Dict[str, str]:
    if not response or not response.strip():
        logger.error("🚨 [_parse_json_answers] 输入为空或纯空白，跳过所有正则解析，直接返回空字典")
        return {}

    cleaned = response.strip()

    code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", cleaned, re.DOTALL)
    if code_block:
        cleaned = code_block.group(1).strip()

    brace_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if brace_match:
        cleaned = brace_match.group(0)

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return {str(k): str(v) for k, v in parsed.items() if str(k).startswith("[[ANS_")}
    except json.JSONDecodeError:
        pass

    try:
        fixed = re.sub(r"'", '"', cleaned)
        fixed = re.sub(r',\s*}', '}', fixed)
        fixed = re.sub(r',\s*]', ']', fixed)
        parsed = json.loads(fixed)
        if isinstance(parsed, dict):
            return {str(k): str(v) for k, v in parsed.items() if str(k).startswith("[[ANS_")}
    except (json.JSONDecodeError, Exception):
        pass

    repaired = _try_repair_truncated_json(cleaned)
    if repaired:
        return repaired

    answers = {}
    for match in re.finditer(r'(\[\[ANS_\d+\]])\s*[:：]\s*["\'](.+?)["\']', cleaned):
        answers[match.group(1)] = match.group(2)

    if not answers:
        for match in re.finditer(r'(\[\[ANS_\d+\]])\s*[:：]\s*([^\s,}]+)', cleaned):
            val = match.group(2).strip().rstrip(',').rstrip('"').rstrip("'")
            if val:
                answers[match.group(1)] = val

    return answers


def _try_repair_truncated_json(text: str) -> Dict[str, str]:
    if not text.strip().startswith("{"):
        return {}

    open_braces = text.count("{") - text.count("}")
    open_brackets = text.count("[") - text.count("]")
    open_quotes = 0
    escaped = False
    for ch in text:
        if escaped:
            escaped = False
            continue
        if ch == '\\':
            escaped = True
            continue
        if ch == '"':
            open_quotes += 1

    in_string = open_quotes % 2 == 1

    repaired = text
    if in_string:
        repaired += '"'
    for _ in range(max(0, open_brackets)):
        repaired += ']'
    for _ in range(max(0, open_braces)):
        repaired += '}'

    if repaired == text:
        return {}

    try:
        parsed = json.loads(repaired)
        if isinstance(parsed, dict):
            result = {str(k): str(v) for k, v in parsed.items() if str(k).startswith("[[ANS_")}
            if result:
                logger.info(f"🔧 [_try_repair_truncated_json] 截断修复成功！恢复 {len(result)} 个答案")
            return result
    except json.JSONDecodeError:
        pass

    try:
        fixed = re.sub(r"'", '"', repaired)
        fixed = re.sub(r',\s*}', '}', fixed)
        fixed = re.sub(r',\s*]', ']', fixed)
        parsed = json.loads(fixed)
        if isinstance(parsed, dict):
            result = {str(k): str(v) for k, v in parsed.items() if str(k).startswith("[[ANS_")}
            if result:
                logger.info(f"🔧 [_try_repair_truncated_json] 截断修复+引号修复成功！恢复 {len(result)} 个答案")
            return result
    except (json.JSONDecodeError, Exception):
        pass

    logger.warning("🔧 [_try_repair_truncated_json] 截断修复失败，回退到正则提取")
    return {}
