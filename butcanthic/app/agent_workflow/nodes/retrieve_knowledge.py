"""
Node 2: RetrieveKnowledge - LLM 驱动的 Query Rewrite + 语义检索
Step 1: 将文档上下文发送给 LLM，让它重写出 1-3 个精准的检索查询词
Step 2: 用重写后的查询词调用 RAGEngine.semantic_search
Step 3: 去重合并结果，存入 state
容错: LLM 重写失败时回退到模板查询；知识库为空时设 "无参考知识"
"""

import json
import logging
import re
from typing import Any, Dict, List

from app.agent_workflow.state import WorkflowState
from app.services.rag_engine import RAGEngine

logger = logging.getLogger(__name__)

REWRITE_SYSTEM_PROMPT = """你是一个资深的知识库检索智能体。请分析以下文档上下文，文档中包含一些空缺或问答题。为了准确补全这份文档，我们需要去知识库查询什么？请提炼出 1 到 3 个最精准的搜索长句或关键字。

要求：严格以 JSON 字符串数组格式返回，例如：["二叉树的定义", "红黑树的特性"]，不要输出任何额外的解释。"""

REWRITE_USER_TEMPLATE = """## 文档上下文

{document_context}

## 文档中识别到的意图

{intent_summary}

请分析以上内容，提炼出 1-3 个最精准的知识库检索查询词。"""

FALLBACK_TEMPLATES = {
    "person_name": "{header} 人员姓名",
    "gender": "性别信息",
    "ethnicity": "民族信息",
    "birth_date": "出生年月日期",
    "id_number": "身份证号码",
    "education_level": "学历教育背景",
    "degree": "学位信息",
    "major": "专业学科",
    "school": "学校院校教育经历",
    "workplace": "工作单位",
    "position": "职务岗位",
    "title": "职称技术职务",
    "phone": "联系电话方式",
    "contact": "联系方式电话邮箱",
    "email": "邮箱电子邮件",
    "date": "时间日期年月",
    "date_range": "起止时间年月",
    "evaluation": "考核结果评价",
    "health": "健康状况",
    "address": "地址住址",
    "course": "课程教学授课",
    "award": "获奖奖励荣誉",
    "project": "项目课题研究",
    "experience": "经历工作学习",
    "generic": "{header}",
}


async def retrieve_knowledge_async(
    state: WorkflowState,
    rag_engine: RAGEngine,
    llm_client=None,
) -> WorkflowState:
    empty_fields = state.get("empty_fields", [])
    field_semantics = state.get("field_semantics", {})
    user_id = state.get("user_id", "")

    if not user_id:
        logger.warning("RetrieveKnowledge: user_id 缺失，跳过知识库检索（Collection 物理隔离要求必须提供 user_id）")
        return {
            **state,
            "retrieved_context": [],
            "context_summary": "无参考知识（未关联用户，无法访问私有知识库）",
        }

    search_queries = []

    if empty_fields:
        document_context = _build_document_context(state)
        intent_summary = _build_intent_summary(empty_fields)

        search_queries = await _rewrite_queries(
            llm_client=llm_client,
            document_context=document_context,
            intent_summary=intent_summary,
            empty_fields=empty_fields,
            field_semantics=field_semantics,
        )

    if not search_queries:
        user_instruction = state.get("user_instruction", "")
        if user_instruction:
            search_queries = [user_instruction]
            logger.info(f"RetrieveKnowledge: no empty_fields, using user_instruction as query: '{user_instruction[:80]}'")
        else:
            document_context = _build_document_context(state)
            if document_context and len(document_context) > 20:
                search_queries = [document_context[:500]]
                logger.info(f"RetrieveKnowledge: no empty_fields or user_instruction, using document prefix as query")
            else:
                logger.info("RetrieveKnowledge: no viable query source, skipping retrieval")
                return {
                    **state,
                    "retrieved_context": [],
                    "context_summary": "无参考知识",
                }

    logger.info(f"RetrieveKnowledge: search queries = {search_queries}")

    all_results: List[Dict[str, Any]] = []
    seen_contents = set()
    search_errors = 0

    for query in search_queries:
        try:
            results = await rag_engine.semantic_search(query=query, top_k=3, user_id=user_id)
            for r in results:
                content = r.get("content", "")
                if content not in seen_contents:
                    seen_contents.add(content)
                    all_results.append(r)
        except Exception as e:
            search_errors += 1
            logger.warning(f"RetrieveKnowledge: search failed for query='{query}': {e}")

    if not all_results:
        if search_errors > 0:
            logger.warning(
                f"RetrieveKnowledge: all {len(search_queries)} queries failed, "
                "falling back to LLM-only mode"
            )
        else:
            logger.info(
                "RetrieveKnowledge: knowledge base is empty or no matches found, "
                "falling back to LLM-only mode"
            )
        return {
            **state,
            "retrieved_context": [],
            "context_summary": "无参考知识",
        }

    context_summary = _summarize_context(all_results)

    logger.info(
        f"RetrieveKnowledge: retrieved {len(all_results)} unique results from {len(search_queries)} queries"
    )

    return {
        **state,
        "retrieved_context": all_results,
        "context_summary": context_summary,
    }


async def _rewrite_queries(
    llm_client,
    document_context: str,
    intent_summary: str,
    empty_fields: List[Dict[str, Any]],
    field_semantics: Dict[str, str],
) -> List[str]:
    """
    Query Rewrite: 使用 LLM 将文档上下文重写为精准的检索查询词
    如果 LLM 不可用或返回格式异常，回退到模板查询
    """
    if llm_client is None:
        logger.info("RetrieveKnowledge: no LLM client, using fallback templates")
        return _build_fallback_queries(empty_fields, field_semantics)

    user_prompt = REWRITE_USER_TEMPLATE.format(
        document_context=document_context,
        intent_summary=intent_summary,
    )

    messages = [
        {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    logger.info(f"准备调用 Query Rewrite 大模型，Prompt 长度: {len(user_prompt)}")

    try:
        model_info = llm_client.get_model_info() if hasattr(llm_client, 'get_model_info') else {}
        logger.info(
            f"🚀 [RetrievalAgent] 即将调用 Query Rewrite | "
            f"model={model_info.get('model', 'unknown')} | "
            f"provider={model_info.get('provider', 'unknown')} | "
            f"model_name={model_info.get('model_name', 'unknown')} | "
            f"initialized={getattr(llm_client, 'langchain_initialized', 'N/A')}"
        )
        response = await llm_client.acall_api(messages)
    except Exception as e:
        logger.error(
            f"🚨 检索阶段大模型报错 | "
            f"exception_type={type(e).__name__} | "
            f"exception_repr={repr(e)}"
        )
        import traceback
        logger.error(f"🚨 完整堆栈追踪:\n{traceback.format_exc()}")
        return _build_fallback_queries(empty_fields, field_semantics)

    if not response:
        logger.error(
            "🚨 Query Rewrite 大模型返回为空！可能原因: "
            "1) API Key 无效/余额不足 2) 网络超时 3) Token 超限 4) 模型名称配置错误"
        )
        logger.error(
            f"🚨 [RetrievalAgent] LLM 客户端状态 | "
            f"initialized={getattr(llm_client, 'langchain_initialized', 'N/A')} | "
            f"selected_model={getattr(llm_client, 'selected_model', 'N/A')} | "
            f"current_config={getattr(llm_client, 'current_config', {})}"
        )
        return _build_fallback_queries(empty_fields, field_semantics)

    logger.warning(f"📋 [RetrievalAgent] Query Rewrite 大模型原始返回内容: '{response[:300]}'")
    if not response.strip():
        logger.error("🚨 [RetrievalAgent] Query Rewrite 返回内容为纯空白！可能是 Content Filter 拦截")
        return _build_fallback_queries(empty_fields, field_semantics)

    queries = _parse_json_queries(response)

    if not queries:
        logger.warning(
            f"RetrieveKnowledge: failed to parse LLM rewrite response: {response[:200]}, using fallback"
        )
        return _build_fallback_queries(empty_fields, field_semantics)

    logger.info(f"RetrieveKnowledge: 智能重写查询词成功: {queries}，正在检索...")
    return queries


def _parse_json_queries(response: str) -> List[str]:
    if not response or not response.strip():
        logger.error("🚨 [_parse_json_queries] 输入为空或纯空白，跳过所有正则解析")
        return []

    cleaned = response.strip()

    code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", cleaned, re.DOTALL)
    if code_block:
        cleaned = code_block.group(1).strip()

    bracket_match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if bracket_match:
        cleaned = bracket_match.group(0)

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            return [str(q).strip() for q in parsed if str(q).strip()]
    except json.JSONDecodeError:
        pass

    try:
        fixed = re.sub(r"'", '"', cleaned)
        parsed = json.loads(fixed)
        if isinstance(parsed, list):
            return [str(q).strip() for q in parsed if str(q).strip()]
    except (json.JSONDecodeError, Exception):
        pass

    return []


def _build_document_context(state: WorkflowState) -> str:
    html = state.get("current_html", "")
    if not html:
        return ""

    from bs4 import BeautifulSoup
    try:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator="\n", strip=True)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()

    return text[:2000]


def _build_intent_summary(empty_fields: List[Dict[str, Any]]) -> str:
    if not empty_fields:
        return "无"

    table_empties = [f for f in empty_fields if f.get("type") == "table_empty"]
    qa_items = [f for f in empty_fields if f.get("type") == "qa"]
    fill_blank_items = [f for f in empty_fields if f.get("type") == "fill_blank"]

    parts = []
    if table_empties:
        headers = list(set(f.get("header", "") for f in table_empties if f.get("header")))
        parts.append(f"空缺表格字段: {', '.join(headers[:10])}")
    if qa_items:
        texts = [f.get("text", "")[:50] for f in qa_items[:5]]
        parts.append(f"问答题: {'; '.join(texts)}")
    if fill_blank_items:
        texts = [f.get("text", "")[:50] for f in fill_blank_items[:5]]
        parts.append(f"填空题: {'; '.join(texts)}")

    return "\n".join(parts) if parts else "无"


def _build_fallback_queries(
    empty_fields: List[Dict[str, Any]],
    field_semantics: Dict[str, str],
) -> List[str]:
    """
    Fallback: 提取占位符周围的 50 个字符作为搜索词
    优先使用 placeholder_map 中的上下文信息
    """
    queries = []
    seen = set()

    for field in empty_fields:
        ptype = field.get("type", "")

        if ptype == "table_empty":
            header = field.get("header", "")
            context = field.get("context", "")
            query = header if header else ""
            if context:
                surrounding = context[:50]
                query = f"{query} {surrounding}" if query else surrounding
        elif ptype == "qa":
            question = field.get("question", "")
            query = question[:50] if question else ""
        elif ptype == "fill_blank":
            surrounding = field.get("surrounding_text", "")
            query = surrounding[:50] if surrounding else ""
        else:
            header = field.get("header", "")
            query = header

        query = _clean_query(query)

        if len(query) < 2:
            continue

        if query not in seen:
            seen.add(query)
            queries.append(query)

    if not queries:
        queries = ["文档内容"]

    return queries[:5]


def _clean_query(query: str) -> str:
    query = re.sub(r'\[\[ANS_\d+\]\]', '', query)
    query = query.replace('|', ' ')
    query = re.sub(r'\s+', ' ', query).strip()
    return query


def _summarize_context(results: List[Dict[str, Any]]) -> str:
    if not results:
        return ""
    parts = []
    for i, r in enumerate(results[:10], 1):
        content = r.get("content", "")
        score = r.get("score", 0)
        collection = r.get("collection", "")
        parts.append(f"[{i}] (来源:{collection}, 相关度:{score:.2f}) {content}")
    return "\n".join(parts)
