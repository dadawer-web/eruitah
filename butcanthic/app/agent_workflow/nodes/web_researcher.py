"""
Deep Research Agent - 具备自我规划与递归反思机制的深度研究节点

架构:
  Step 1: Planning  → LLM 拆解搜索关键词
  Step 2: Search & Scrape → DDGS 搜索 + aiohttp 异步抓取
  Step 3: Reflection → LLM 评估信息充分性，决定继续或停止
  Step 4: Synthesis → LLM 撰写深度调研报告 (Markdown)

最大循环: max_iterations = 3
"""

import asyncio
import json
import logging
import re
from typing import Dict, List, Optional

from langchain_core.messages import HumanMessage

from app.agent_workflow.state import WorkflowState

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 3
MAX_CHARS_PER_PAGE = 3000
SEARCH_MAX_RESULTS = 2
FETCH_TIMEOUT = 15
FETCH_CONCURRENCY = 3
LLM_RETRY_ATTEMPTS = 2

PLANNING_PROMPT = """你是一个搜索策略规划专家。用户提出了以下研究问题：

"{user_instruction}"

请将这个问题拆解为3个具体的搜索关键词或短问题，用于在搜索引擎上查找相关信息。
要求：
1. 每个关键词/问题针对问题的不同侧面
2. 关键词要具体、可搜索
3. 覆盖最新信息和深度分析

请严格以JSON数组格式返回，不要输出其他内容：
["关键词1", "关键词2", "关键词3"]"""

REFLECTION_PROMPT = """你是一个信息充分性评估专家。

用户的研究问题：{user_instruction}

目前已收集到的信息摘要（共{info_length}字）：
{gathered_info_summary}

请评估当前收集的信息是否足够回答用户的研究问题。

评估标准：
- 信息是否覆盖了问题的主要方面？
- 是否有足够的细节和数据支撑？
- 是否有明显的知识盲区？

如果信息已经足够，回复：SUFFICIENT
如果信息不够，回复两行：
第一行：INSUFFICIENT
第二行：以JSON数组格式提供2个全新的搜索关键词（不要重复之前的搜索词），例如：["新关键词1", "新关键词2"]"""

SYNTHESIS_PROMPT = """你是一个深度研究分析师。请基于以下收集到的信息，撰写一篇极其详尽的深度调研报告。

用户的研究问题：{user_instruction}

收集到的信息：
{gathered_info}

要求：
1. 使用 Markdown 格式，包含清晰的层级标题（##、###）
2. 每个主要论点都要引用信息来源（用 [来源] 标注）
3. 包含数据、趋势、对比分析
4. 如有不同观点，客观呈现各方立场
5. 最后给出总结与展望
6. 报告长度不少于800字"""

KG_EXTRACT_PROMPT = """请从以下报告中提取核心实体与关系网络，输出纯JSON格式。

报告内容：
{report_text}

要求：
1. 提取5-15个核心实体（人名、公司、技术、产品、概念等）
2. 提取实体之间的关键关系
3. 严格输出以下JSON格式，不要输出任何其他内容：
{{"nodes": [{{"id": "实体名称", "category": "人/公司/技术/产品/概念/事件"}}], "edges": [{{"source": "实体1", "target": "实体2", "label": "关系说明"}}]}}"""


async def web_researcher_node(state: WorkflowState, llm_client) -> dict:
    user_instruction = state.get("user_instruction", "")
    if not user_instruction:
        return {"messages": [HumanMessage(content="未提供研究问题，跳过深度研究。", name="Web_Researcher")]}

    logger.info(f"🔍 [DeepResearch] 启动深度研究 | 问题: {user_instruction[:80]}...")

    gathered_info = ""
    all_search_queries = []
    iteration = 0

    try:
        search_queries = await _plan_search_queries(user_instruction, llm_client)
        all_search_queries.extend(search_queries)
        logger.info(f"🔍 [DeepResearch] Step1 Planning: 初始搜索词 = {search_queries}")
    except Exception as e:
        logger.warning(f"🔍 [DeepResearch] Planning failed, using raw instruction: {e}")
        search_queries = [user_instruction]

    while iteration < MAX_ITERATIONS:
        iteration += 1
        logger.info(f"🔍 [DeepResearch] === 循环 {iteration}/{MAX_ITERATIONS} ===")

        for query in search_queries:
            try:
                logger.info(f"🔍 [DeepResearch] Step2 Search: 搜索 '{query}'...")
                urls = await _search_ddg(query)

                if not urls:
                    logger.info(f"🔍 [DeepResearch] Search: '{query}' 无结果")
                    continue

                logger.info(f"🔍 [DeepResearch] Search: '{query}' → {len(urls)} 个URL")

                page_contents = await _fetch_pages(urls)
                for url, content in page_contents.items():
                    if content:
                        gathered_info += f"\n\n--- 来源: {url} ---\n{content}"
                        logger.info(f"🔍 [DeepResearch] Scrape: 抓取成功 {url[:60]}... ({len(content)} chars)")

            except Exception as e:
                logger.warning(f"🔍 [DeepResearch] Search & Scrape failed for '{query}': {e}")

        logger.info(f"🔍 [DeepResearch] Step3 Reflection: 评估信息充分性 (gathered={len(gathered_info)} chars)...")

        should_continue, new_queries = await _reflect(
            user_instruction, gathered_info, llm_client
        )

        if not should_continue:
            logger.info(f"🔍 [DeepResearch] Reflection: 信息已充分，结束循环")
            break
        else:
            search_queries = new_queries
            all_search_queries.extend(new_queries)
            logger.info(f"🔍 [DeepResearch] Reflection: 信息不足，新搜索词 = {new_queries}")

    logger.info(f"🔍 [DeepResearch] Step4 Synthesis: 撰写深度报告 (gathered={len(gathered_info)} chars)...")

    try:
        report = await _synthesize_report(user_instruction, gathered_info, llm_client)
        logger.info(f"🔍 [DeepResearch] 报告生成完毕 ({len(report)} chars, {iteration} 轮循环)")
    except Exception as e:
        logger.error(f"🔍 [DeepResearch] Synthesis failed: {e}")
        report = f"深度研究完成，但报告生成失败。\n\n收集到的原始信息：\n{gathered_info[:3000]}"

    output_path = ""
    try:
        from app.services.word_export_service import export_markdown_to_word
        output_path = await export_markdown_to_word(report)
        if output_path:
            logger.info(f"🔍 [DeepResearch] Word 导出成功: {output_path}")
        else:
            logger.warning("🔍 [DeepResearch] Word 导出返回空路径")
    except Exception as e:
        logger.warning(f"🔍 [DeepResearch] Word 导出失败: {e}")

    html_content = ""
    try:
        import markdown as md_lib
        html_content = md_lib.markdown(
            report,
            extensions=["tables", "fenced_code", "toc"],
        )
        logger.info(f"🔍 [DeepResearch] Markdown→HTML 预览转换成功 ({len(html_content)} chars)")
    except Exception as e:
        logger.warning(f"🔍 [DeepResearch] Markdown→HTML 转换失败: {e}")
        html_content = report.replace("\n", "<br>")

    knowledge_graph = None
    try:
        kg_prompt = KG_EXTRACT_PROMPT.format(report_text=report[:4000])
        kg_messages = [{"role": "user", "content": kg_prompt}]
        kg_response = await _call_llm_with_retry(llm_client, kg_messages, max_tokens=8192, label="KG_Extract")
        if kg_response:
            knowledge_graph = _parse_knowledge_graph(kg_response)
            if knowledge_graph:
                logger.info(f"🔍 [DeepResearch] 知识图谱抽取成功: {len(knowledge_graph.get('nodes', []))} nodes, {len(knowledge_graph.get('edges', []))} edges")
            else:
                logger.warning("🔍 [DeepResearch] 知识图谱 JSON 解析失败")
    except Exception as e:
        logger.warning(f"🔍 [DeepResearch] 知识图谱抽取失败: {e}")

    structured_data = {"knowledge_graph": knowledge_graph} if knowledge_graph else {}

    msg = HumanMessage(content=report, name="Web_Researcher")
    return {
        "messages": [msg],
        "output_path": output_path,
        "file_type": "docx",
        "filled_html": html_content,
        "structured_data": structured_data,
        "next_node": "FINISH",
    }


async def _call_llm_with_retry(llm_client, messages, max_tokens, label="LLM"):
    for attempt in range(LLM_RETRY_ATTEMPTS):
        response = await llm_client.acall_api(messages, max_tokens=max_tokens)
        if response and response.strip():
            return response
        logger.warning(
            f"🔍 [DeepResearch] {label} 返回为空 (attempt {attempt+1}/{LLM_RETRY_ATTEMPTS}), "
            f"max_tokens={max_tokens} — 可能被推理模型截断"
        )
    return None


async def _plan_search_queries(user_instruction: str, llm_client) -> List[str]:
    prompt = PLANNING_PROMPT.format(user_instruction=user_instruction)
    messages = [{"role": "user", "content": prompt}]
    response = await _call_llm_with_retry(llm_client, messages, max_tokens=2048, label="Planning")

    if not response:
        logger.warning("🔍 [DeepResearch] Planning 多次重试仍为空，使用原始问题作为搜索词")
        return [user_instruction]

    return _parse_json_list(response, fallback=[user_instruction])


async def _search_ddg(query: str) -> List[str]:
    try:
        from ddgs import DDGS

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=SEARCH_MAX_RESULTS))

        urls = []
        for r in results:
            href = r.get("href") or r.get("link", "")
            if href and href.startswith("http"):
                urls.append(href)

        return urls
    except Exception as e:
        logger.warning(f"DDG search failed for '{query}': {e}")
        return []


async def _fetch_pages(urls: List[str]) -> Dict[str, str]:
    semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)

    async def _fetch_one(session, url):
        async with semaphore:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=FETCH_TIMEOUT)) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        text = _extract_text(html)
                        return url, text[:MAX_CHARS_PER_PAGE]
                    else:
                        logger.debug(f"Fetch {url}: HTTP {resp.status}")
                        return url, ""
            except Exception as e:
                logger.debug(f"Fetch {url}: {e}")
                return url, ""

    try:
        import aiohttp
    except ImportError:
        logger.warning("aiohttp not installed, skipping page fetch")
        return {}

    results = {}
    try:
        async with aiohttp.ClientSession(
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        ) as session:
            tasks = [_fetch_one(session, url) for url in urls]
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            for r in responses:
                if isinstance(r, tuple) and len(r) == 2:
                    results[r[0]] = r[1]
    except Exception as e:
        logger.warning(f"Fetch session error: {e}")

    return results


def _extract_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")

        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)
    except Exception:
        return html[:MAX_CHARS_PER_PAGE]


async def _reflect(
    user_instruction: str, gathered_info: str, llm_client
) -> tuple:
    if not gathered_info or len(gathered_info) < 100:
        return True, [user_instruction + " 详细分析", user_instruction + " 最新进展"]

    summary = gathered_info[:2000] if len(gathered_info) > 2000 else gathered_info

    prompt = REFLECTION_PROMPT.format(
        user_instruction=user_instruction,
        gathered_info_summary=summary,
        info_length=len(gathered_info),
    )

    messages = [{"role": "user", "content": prompt}]

    try:
        response = await _call_llm_with_retry(llm_client, messages, max_tokens=2048, label="Reflection")
        if not response:
            logger.warning("🔍 [DeepResearch] Reflection 多次重试仍为空，默认判定信息已充分")
            return False, []

        first_line = response.strip().split("\n")[0].strip().upper()

        if "SUFFICIENT" in first_line:
            return False, []

        remaining = "\n".join(response.strip().split("\n")[1:])
        new_queries = _parse_json_list(remaining, fallback=[])
        if new_queries:
            return True, new_queries[:2]

        return True, [user_instruction + " 深度分析", user_instruction + " 案例"]

    except Exception as e:
        logger.warning(f"Reflection failed: {e}")
        return False, []


async def _synthesize_report(
    user_instruction: str, gathered_info: str, llm_client
) -> str:
    if not gathered_info:
        return "未能收集到相关信息，无法生成深度研究报告。"

    prompt = SYNTHESIS_PROMPT.format(
        user_instruction=user_instruction,
        gathered_info=gathered_info[:12000],
    )

    messages = [{"role": "user", "content": prompt}]
    report = await _call_llm_with_retry(llm_client, messages, max_tokens=16384, label="Synthesis")

    if not report:
        logger.warning("🔍 [DeepResearch] Synthesis 多次重试仍为空，返回原始信息摘要")
        return (
            f"⚠️ 深度研究报告因模型输出截断未能完整生成。"
            f"以下为已收集的原始信息摘要：\n\n{gathered_info[:5000]}"
        )

    return report


def _parse_json_list(text: str, fallback: list = None) -> list:
    if not text:
        return fallback or []

    cleaned = text.strip()

    code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", cleaned, re.DOTALL)
    if code_block:
        cleaned = code_block.group(1).strip()

    bracket_match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if bracket_match:
        cleaned = bracket_match.group(0)

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except json.JSONDecodeError:
        pass

    items = re.findall(r'"([^"]+)"', cleaned)
    if items:
        return items

    return fallback or []


def _parse_knowledge_graph(text: str) -> Optional[Dict]:
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
