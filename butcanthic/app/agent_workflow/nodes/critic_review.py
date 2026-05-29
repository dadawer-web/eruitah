"""
Node 4: CriticReview - 审查填充后的 HTML / PPT JSON
检查格式完整性、数据幻觉、结构破坏等问题
返回 pass 或 fail + 具体反馈
"""

import json
import logging
import re
from typing import Any, Dict, List, Tuple

from bs4 import BeautifulSoup

from app.agent_workflow.state import WorkflowState
from app.core.prompt_manager import PromptManager

logger = logging.getLogger(__name__)


async def critic_review(state: WorkflowState, llm_client) -> WorkflowState:
    original_html = state.get("original_html", "")
    filled_html = state.get("filled_html", "")
    context_summary = state.get("context_summary", "")

    if not filled_html:
        return {**state, "review_result": "fail", "review_feedback": "填充结果为空"}

    structural_result = _check_structural_integrity(original_html, filled_html)
    if not structural_result["passed"]:
        logger.warning(f"CriticReview: structural check failed - {structural_result['reason']}")
        return {**state, "review_result": "fail", "review_feedback": f"结构检查失败: {structural_result['reason']}"}

    user_prompt = PromptManager.get_prompt(
        "critic_review_user",
        original_html=original_html,
        filled_html=filled_html,
        context_summary=context_summary or "（无知识库数据）",
    )

    messages = [
        {"role": "system", "content": PromptManager.get_prompt("critic_review_system")},
        {"role": "user", "content": user_prompt},
    ]

    try:
        response = await llm_client.acall_api(messages, max_tokens=2048)
    except Exception as e:
        logger.error(f"CriticReview: LLM call failed: {e}")
        return {**state, "review_result": "fail", "review_feedback": f"审查LLM调用失败: {e}"}

    if not response:
        return {**state, "review_result": "fail", "review_feedback": "审查LLM返回空响应"}

    review_result, review_feedback = _parse_review_response(response)

    retry_count = state.get("retry_count", 0)
    logger.info(f"CriticReview: result={review_result}, retry_count={retry_count}")

    return {**state, "review_result": review_result, "review_feedback": review_feedback}


def _check_structural_integrity(original_html: str, filled_html: str) -> Dict[str, Any]:
    try:
        orig_soup = BeautifulSoup(original_html, "html.parser")
        filled_soup = BeautifulSoup(filled_html, "html.parser")

        orig_tables = orig_soup.find_all("table")
        filled_tables = filled_soup.find_all("table")

        if orig_tables and not filled_tables:
            return {"passed": False, "reason": "原始文档有表格但处理后缺失"}

        for i, (orig_table, filled_table) in enumerate(zip(orig_tables, filled_tables)):
            orig_rows = orig_table.find_all("tr")
            filled_rows = filled_table.find_all("tr")
            if orig_rows and filled_rows:
                if abs(len(orig_rows) - len(filled_rows)) > max(1, len(orig_rows) * 0.2):
                    return {
                        "passed": False,
                        "reason": f"表格{i+1}行数不一致: 原始{len(orig_rows)}行, 处理后{len(filled_rows)}行",
                    }

        unclosed = _check_unclosed_tags(filled_html)
        if unclosed:
            return {"passed": False, "reason": f"存在未闭合标签: {unclosed}"}

        return {"passed": True, "reason": ""}
    except Exception as e:
        return {"passed": False, "reason": f"HTML解析异常: {e}"}


def _check_unclosed_tags(html: str) -> list:
    problems = []
    for tag in ["table", "tr", "td", "th"]:
        opens = len(re.findall(f"<{tag}[\\s>]", html, re.IGNORECASE))
        closes = len(re.findall(f"</{tag}>", html, re.IGNORECASE))
        if opens != closes:
            problems.append(f"{tag}(开:{opens}/闭:{closes})")
    return problems


def _parse_review_response(response: str) -> tuple:
    lines = response.strip().split("\n")
    if not lines:
        return ("fail", "审查响应为空")

    first_line = lines[0].strip().upper()
    if "PASS" in first_line and "FAIL" not in first_line:
        feedback = "\n".join(lines[1:]).strip() if len(lines) > 1 else "审查通过"
        return ("pass", feedback)

    feedback = "\n".join(lines[1:]).strip() if len(lines) > 1 else "审查未通过"
    return ("fail", feedback)


PPT_MAX_RETRIES = 3

VALID_LAYOUTS = {"cover", "section", "content", "split", "comparison", "quote", "closing", "blank"}

REQUIRED_SLIDE_FIELDS = {"layout", "title"}

ABSTRACT_KEYWORDS = frozenset({
    "summary", "conclusion", "business", "strategy", "development",
    "overview", "introduction", "analysis", "management", "growth",
    "innovation", "ai", "teamwork", "technology", "future",
    "success", "progress", "vision", "mission", "value",
    "report", "review", "plan", "goal", "result",
    "concept", "idea", "approach", "solution", "framework",
})


async def critic_review_ppt(state: WorkflowState, llm_client=None) -> WorkflowState:
    ppt_data = state.get("ppt_data", {})
    retry_count = state.get("retry_count", 0)

    if not ppt_data or not ppt_data.get("slides"):
        return {
            **state,
            "review_result": "fail",
            "review_feedback": "PPT数据为空或缺少slides数组",
            "feedback": "PPT数据为空或缺少slides数组，请重新生成完整的PPT JSON",
            "retry_count": retry_count + 1,
        }

    rule_issues = _validate_ppt_rules(ppt_data)

    if rule_issues:
        feedback = "; ".join(rule_issues)
        logger.warning(f"CriticReviewPPT: rule check failed (retry={retry_count}) - {feedback}")
        return {
            **state,
            "review_result": "fail",
            "review_feedback": feedback,
            "feedback": feedback,
            "retry_count": retry_count + 1,
        }

    if llm_client:
        llm_issues = await _validate_ppt_with_llm(ppt_data, state.get("user_instruction", ""), llm_client)
        if llm_issues:
            feedback = "; ".join(llm_issues)
            logger.warning(f"CriticReviewPPT: LLM check failed (retry={retry_count}) - {feedback}")
            return {
                **state,
                "review_result": "fail",
                "review_feedback": feedback,
                "feedback": feedback,
                "retry_count": retry_count + 1,
            }

    logger.info(f"CriticReviewPPT: PASS (retry={retry_count})")
    return {
        **state,
        "review_result": "pass",
        "review_feedback": "",
        "feedback": "",
    }


def _validate_ppt_rules(ppt_data: dict) -> List[str]:
    issues = []

    slides = ppt_data.get("slides", [])
    if not slides:
        issues.append("slides数组为空")
        return issues

    if len(slides) < 2:
        issues.append("PPT至少需要2页幻灯片（封面+内容）")

    has_cover = any(s.get("layout") == "cover" for s in slides if isinstance(s, dict))
    if not has_cover:
        issues.append("缺少封面页(layout=cover)")

    has_closing = any(s.get("layout") == "closing" for s in slides if isinstance(s, dict))
    if not has_closing and len(slides) > 3:
        issues.append("建议添加结束页(layout=closing)")

    for i, slide in enumerate(slides):
        if not isinstance(slide, dict):
            issues.append(f"第{i+1}页: 幻灯片数据格式错误(非dict)")
            continue

        missing = REQUIRED_SLIDE_FIELDS - set(slide.keys())
        if missing:
            issues.append(f"第{i+1}页: 缺少必需字段 {missing}")

        layout = slide.get("layout", "")
        if layout and layout not in VALID_LAYOUTS:
            issues.append(f"第{i+1}页: 无效layout '{layout}'，有效值: {VALID_LAYOUTS}")

        title = slide.get("title", "")
        if not title or not str(title).strip():
            issues.append(f"第{i+1}页: 标题为空")

        components = slide.get("components", [])
        if isinstance(components, list):
            for j, comp in enumerate(components):
                if not isinstance(comp, dict):
                    issues.append(f"第{i+1}页组件{j+1}: 格式错误(非dict)")
                    continue
                comp_type = comp.get("type", "")
                if not comp_type:
                    issues.append(f"第{i+1}页组件{j+1}: 缺少type字段")
                if comp_type in ("text", "heading") and not comp.get("content", "").strip():
                    issues.append(f"第{i+1}页组件{j+1}: 文本组件内容为空")

        if slide.get("layout") != "closing":
            keyword = slide.get("image_search_keyword", "").strip()
            if not keyword:
                issues.append(
                    f"第{i+1}页: 缺少 image_search_keyword，每页必须提供具象的英文搜索关键词"
                )
            else:
                words = set(w.lower() for w in keyword.split())
                abstract_found = words & ABSTRACT_KEYWORDS
                if abstract_found:
                    issues.append(
                        f"第{i+1}页: image_search_keyword '{keyword}' 包含抽象词 "
                        f"{abstract_found}，必须替换为具象视觉元素"
                        f"（如用 'Chess board king' 替代 'Strategy'，"
                        f"用 'People high five office' 替代 'Teamwork'）"
                    )

    meta = ppt_data.get("meta", {})
    if not meta or not meta.get("title"):
        issues.append("meta.title 缺失")

    return issues


async def _validate_ppt_with_llm(ppt_data: dict, user_instruction: str, llm_client) -> List[str]:
    slides = ppt_data.get("slides", [])
    slide_summary = []
    for i, s in enumerate(slides):
        if not isinstance(s, dict):
            continue
        summary = {
            "index": i + 1,
            "layout": s.get("layout", ""),
            "title": s.get("title", ""),
            "component_count": len(s.get("components", [])),
        }
        components = s.get("components", [])
        if components:
            comp_types = [c.get("type", "?") for c in components if isinstance(c, dict)]
            summary["component_types"] = comp_types
        slide_summary.append(summary)

    review_prompt = (
        f"你是一个PPT质量审查专家。请审查以下PPT的结构和内容质量。\n\n"
        f"用户原始需求: {user_instruction[:500]}\n\n"
        f"PPT结构概要 (共{len(slides)}页):\n"
        f"{json.dumps(slide_summary, ensure_ascii=False, indent=2)}\n\n"
        f"请检查以下问题:\n"
        f"1. 内容是否与用户需求相关\n"
        f"2. 每页内容是否充实（不是空壳占位符）\n"
        f"3. 逻辑流程是否合理\n"
        f"4. 是否有明显的内容重复\n\n"
        f"如果完美，回复: PASS\n"
        f"如果有问题，第一行回复: REJECT，然后逐条列出具体问题和修改建议。"
    )

    try:
        messages = [
            {"role": "system", "content": "你是PPT质量审查专家，严格审查PPT的格式和内容质量。"},
            {"role": "user", "content": review_prompt},
        ]
        response = await llm_client.acall_api(messages, max_tokens=1024)
        if not response:
            return []

        lines = response.strip().split("\n")
        first_line = lines[0].strip().upper()

        if "PASS" in first_line and "REJECT" not in first_line:
            return []

        feedback_lines = [l.strip() for l in lines[1:] if l.strip()]
        if feedback_lines:
            return feedback_lines[:5]

        return ["LLM审查未通过但未给出具体建议"]

    except Exception as e:
        logger.warning(f"CriticReviewPPT: LLM validation failed: {e}")
        return []
