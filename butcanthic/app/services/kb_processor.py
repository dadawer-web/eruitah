import asyncio
import gc
import json
import logging
import os
import re
import shutil
from app.core.decorators import aios_notify
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

_worker_rag_engine = None
_worker_ai_client = None
_worker_graph_engine = None


def _publish_kb_event(user_id: str, state: str, message: str, percent: int):
    """
    将知识库处理进度同步到 RabbitMQ 事件总线，供 C++ 桌宠订阅。

    状态映射:
        INITIALIZING / EXTRACTING / ANALYZING / GENERATING / EMBEDDING / GRAPH_BUILDING → working
        COMPLETED → success
        error → error
    """
    try:
        from app.core.event_bus import aios_event_bus

        # 状态 → action 映射
        if state == "COMPLETED":
            action = "success"
        elif state in ("ERROR", "FAILED"):
            action = "error"
        else:
            action = "working"

        aios_event_bus.publish(
            user_id=str(user_id),
            source="knowledge_base",
            action=action,
            message=message,
        )
    except Exception as e:
        logger.debug(f"[KB] 事件总线发布失败（不阻断）: {e}")

# ── Wiki 页面持久化目录（按 user_id 隔离） ──
WIKI_PAGES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "wiki_pages",
)

# ── 页面合并配置（参考 llm_wiki page-merge.ts） ──
UNION_FIELDS = ["sources", "tags", "related"]  # frontmatter 数组字段做并集合并
LOCKED_FIELDS = ["type", "title", "created"]   # 合并后锁定为旧值
BODY_SHRINK_THRESHOLD = 0.7                    # LLM 合并后 body 长度不得低于 max(旧,新)*0.7


def _get_graph_engine():
    """获取 GraphRAG 引擎（延迟初始化）"""
    global _worker_graph_engine
    if _worker_graph_engine is not None:
        return _worker_graph_engine

    from app.core.app_state import app_state
    if app_state.graph_engine is not None:
        _worker_graph_engine = app_state.graph_engine
        return _worker_graph_engine

    try:
        from app.services.graph_engine import create_graph_engine
        ai_client = _get_ai_client()
        _worker_graph_engine = create_graph_engine(ai_client=ai_client)
        logger.info("Wiki Generator: standalone GraphRAG engine initialized")
    except Exception as e:
        logger.error(f"Wiki Generator: GraphRAG engine init failed: {e}")
        _worker_graph_engine = None

    return _worker_graph_engine


# ─────────────────────────────────────────────────────────
# YAML Frontmatter 解析器
# ─────────────────────────────────────────────────────────

def parse_yaml_frontmatter(md_text: str) -> Tuple[Dict[str, Any], str]:
    """
    从 Markdown 文本中提取 YAML Frontmatter 和正文。
    支持宽容模式：前 6 行内找到 ---...--- 即可。

    返回: (metadata_dict, body_text)
    """
    if not md_text or not md_text.strip():
        return {}, ""

    text = md_text.strip()

    # 宽容模式：跳过前导垃圾行（LLM 可能在 frontmatter 前输出空行或注释）
    lines = text.split("\n")
    start_idx = -1
    for i in range(min(6, len(lines))):
        if lines[i].strip() == "---":
            start_idx = i
            break

    if start_idx == -1:
        return {}, text

    # 找到闭合的 ---
    end_idx = -1
    for i in range(start_idx + 1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx == -1:
        return {}, text

    yaml_str = "\n".join(lines[start_idx + 1:end_idx])
    body = "\n".join(lines[end_idx + 1:]).strip()

    # 简易 YAML 解析（不引入 pyyaml 依赖）
    metadata = {}
    for line in yaml_str.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        colon_idx = line.find(":")
        if colon_idx == -1:
            continue
        key = line[:colon_idx].strip()
        value = line[colon_idx + 1:].strip()

        # 解析数组格式: [a, b, c] 或 ["a", "b", "c"]
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            if inner:
                items = re.split(r',\s*', inner)
                items = [re.sub(r'^["\']|["\']$', '', item.strip()) for item in items if item.strip()]
                metadata[key] = items
            else:
                metadata[key] = []
        elif value.startswith('"') and value.endswith('"'):
            metadata[key] = value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
            metadata[key] = value[1:-1]
        else:
            metadata[key] = value

    return metadata, body


# ─────────────────────────────────────────────────────────
# 两步走 Wiki 生成引擎
# ─────────────────────────────────────────────────────────

def _get_ai_client():
    """获取 AI 客户端（延迟初始化，支持 Celery worker）"""
    global _worker_ai_client
    if _worker_ai_client is not None:
        return _worker_ai_client

    from app.core.app_state import app_state
    if app_state.ai_client is not None:
        _worker_ai_client = app_state.ai_client
        return _worker_ai_client

    try:
        from app.services.ai_client import UnifiedAIClient
        _worker_ai_client = UnifiedAIClient()
        logger.info("Wiki Generator: standalone AI client initialized")
    except Exception as e:
        logger.error(f"Wiki Generator: AI client init failed: {e}")
        _worker_ai_client = None

    return _worker_ai_client


async def _wiki_analysis_step(source_text: str, filename: str, ai_client) -> Optional[str]:
    """Step 1: 调用大模型分析源文本，提取实体/事实/概念"""
    from app.core.prompt_manager import PromptManager

    system_prompt = PromptManager.get_prompt("wiki_analysis_system")
    if not system_prompt:
        logger.warning("[Wiki] wiki_analysis_system prompt not found, skipping analysis step")
        return None

    # 截断过长文本（保留 12000 字符，约 4000 token）
    truncated = source_text[:12000] if len(source_text) > 12000 else source_text

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"请分析以下源文本：\n\n文件名：{filename}\n\n---\n\n{truncated}"},
    ]

    try:
        response = await ai_client.acall_api(messages, max_tokens=4096)
        if response and response.strip():
            logger.info(f"[Wiki] Step 1 分析完成: {filename} ({len(response)} chars)")
            return response.strip()
        else:
            logger.warning(f"[Wiki] Step 1 分析返回空: {filename}")
            return None
    except Exception as e:
        logger.error(f"[Wiki] Step 1 分析失败: {filename} - {e}")
        return None


async def _wiki_generation_step(
    analysis_result: str,
    source_text: str,
    filename: str,
    ai_client,
) -> Optional[str]:
    """Step 2: 基于分析结果生成 Wiki Markdown 页面"""
    from app.core.prompt_manager import PromptManager

    system_prompt = PromptManager.get_prompt("wiki_generation_system")
    if not system_prompt:
        logger.warning("[Wiki] wiki_generation_system prompt not found, skipping generation step")
        return None

    # 填充模板变量
    today = datetime.now().strftime("%Y-%m-%d")
    system_prompt = system_prompt.replace("{date}", today).replace("{source_id}", filename)

    # 截断源文本（分析结果已包含关键信息，源文本作为参考）
    # 长文档 Map-Reduce 后分析结果已很全面，源文本截断更多
    source_budget = 4000 if len(analysis_result) > 5000 else 8000
    truncated_source = source_text[:source_budget] if len(source_text) > source_budget else source_text

    user_content = (
        f"## Stage 1 分析结果（仅供参考，不要重复）\n\n{analysis_result}\n\n"
        f"## 源文本\n\n{truncated_source}\n\n"
        f"请基于以上分析结果和源文本，生成知识页面。"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    try:
        response = await ai_client.acall_api(messages, max_tokens=8192)
        if response and response.strip():
            # 清理 LLM 可能包裹的代码块
            cleaned = response.strip()
            if cleaned.startswith("```markdown"):
                cleaned = cleaned[len("```markdown"):]
            elif cleaned.startswith("```md"):
                cleaned = cleaned[len("```md"):]
            elif cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            logger.info(f"[Wiki] Step 2 生成完成: {filename} ({len(cleaned)} chars)")
            return cleaned
        else:
            logger.warning(f"[Wiki] Step 2 生成返回空: {filename}")
            return None
    except Exception as e:
        logger.error(f"[Wiki] Step 2 生成失败: {filename} - {e}")
        return None


# ── Map-Reduce 长文档处理常量（参考 llm_wiki ingest.ts）──
LONG_SOURCE_THRESHOLD = 8000      # 超过此字符数触发分块
CHUNK_TARGET_CHARS = 6000         # 每个分块目标字符数
CHUNK_OVERLAP_CHARS = 400         # 相邻分块重叠字符数
CHUNK_MIN_CHARS = 2000            # 分块最小字符数
GLOBAL_DIGEST_MAX = 4000          # 全局摘要最大字符数


def _split_source_into_chunks(
    content: str,
    target_chars: int = CHUNK_TARGET_CHARS,
    overlap_chars: int = CHUNK_OVERLAP_CHARS,
) -> List[Dict[str, Any]]:
    """
    语义感知分块：按 Markdown 标题和段落边界切分长文档

    参考 llm_wiki ingest.ts: splitSourceIntoSemanticChunks
    算法：
      1. 按 Markdown 标题和空行拆分为语义块
      2. 贪心合并语义块到目标大小
      3. 相邻 chunk 间添加重叠文本
    """
    if len(content) <= target_chars:
        return [{"id": "chunk-1", "index": 1, "total": 1, "heading_path": "",
                 "overlap_before": "", "main": content}]

    # 1. 提取语义块
    blocks: List[Dict[str, str]] = []
    heading_stack: List[str] = []
    paragraph: List[str] = []
    paragraph_heading = ""

    def current_heading_path():
        return " > ".join(h for h in heading_stack if h)

    def flush_paragraph():
        nonlocal paragraph
        text = "\n".join(paragraph).strip()
        if text:
            blocks.append({"text": text, "heading_path": paragraph_heading})
        paragraph = []

    for line in content.replace("\r\n", "\n").split("\n"):
        heading_match = re.match(r'^(#{1,6})\s+(.+?)\s*$', line)
        if heading_match:
            flush_paragraph()
            depth = len(heading_match.group(1))
            heading_stack = heading_stack[:depth - 1]
            if len(heading_stack) < depth:
                heading_stack.extend([""] * (depth - len(heading_stack)))
            heading_stack[depth - 1] = heading_match.group(2).strip()
            blocks.append({"text": line.strip(), "heading_path": current_heading_path()})
            paragraph_heading = current_heading_path()
            continue
        if line.strip() == "":
            flush_paragraph()
            paragraph_heading = current_heading_path()
            continue
        if not paragraph:
            paragraph_heading = current_heading_path()
        paragraph.append(line)
    flush_paragraph()

    if not blocks:
        return [{"id": "chunk-1", "index": 1, "total": 1, "heading_path": "",
                 "overlap_before": "", "main": content}]

    # 2. 贪心合并语义块到目标大小
    raw_chunks: List[Dict[str, str]] = []
    current_parts: List[str] = []
    current_length = 0
    current_heading = blocks[0].get("heading_path", "")

    def flush_chunk():
        main = "\n\n".join(current_parts).strip()
        if main:
            raw_chunks.append({"main": main, "heading_path": current_heading})

    for block in blocks:
        next_length = current_length + len(block["text"]) + (2 if current_parts else 0)
        if current_parts and next_length > target_chars:
            flush_chunk()
            current_parts = []
            current_length = 0
        if not current_parts:
            current_heading = block.get("heading_path", "")
        current_parts.append(block["text"])
        current_length += len(block["text"]) + (2 if len(current_parts) > 1 else 0)
    flush_chunk()

    # 3. 添加重叠文本
    chunks = []
    for idx, chunk in enumerate(raw_chunks):
        overlap_before = ""
        if idx > 0:
            prev_main = raw_chunks[idx - 1]["main"]
            if len(prev_main) > overlap_chars:
                # 优先在段落/句子边界截断
                raw_overlap = prev_main[-overlap_chars:]
                para_break = re.search(r'\n\s*\n', raw_overlap)
                if para_break and len(raw_overlap) - para_break.start() > overlap_chars * 0.4:
                    overlap_before = raw_overlap[para_break.start():].strip()
                else:
                    overlap_before = raw_overlap.strip()
            else:
                overlap_before = prev_main

        chunks.append({
            "id": f"chunk-{idx + 1}",
            "index": idx + 1,
            "total": len(raw_chunks),
            "heading_path": chunk["heading_path"],
            "overlap_before": overlap_before,
            "main": chunk["main"],
        })

    return chunks


async def _map_reduce_analyze(
    source_text: str,
    filename: str,
    ai_client,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Map-Reduce 长文档分析（真并发版）

    参考 llm_wiki ingest.ts: analyzeLongSourceInChunks

    Map 阶段：对每个 chunk 并发调用 _wiki_analysis_step
    Reduce 阶段：合并所有 chunk 的分析结果

    Returns:
        (consolidated_analysis, all_triplets_from_chunks)
    """
    chunks = await asyncio.to_thread(_split_source_into_chunks, source_text)

    if len(chunks) <= 1:
        analysis = await _wiki_analysis_step(source_text, filename, ai_client)
        return analysis or "", []

    logger.info(f"[MapReduce] 长文档分块: {filename} → {len(chunks)} 个分块 "
                f"(总长 {len(source_text)} 字符)")

    semaphore = asyncio.Semaphore(5)

    async def _analyze_chunk(chunk):
        chunk_text = chunk["main"]
        chunk_idx = chunk["index"]
        chunk_label = f"{filename} (分块 {chunk_idx}/{chunk['total']})"
        async with semaphore:
            t0 = asyncio.get_event_loop().time()
            logger.info(f"[MapReduce] Part{chunk_idx} 开始等待 LLM... (t={t0:.2f})")
            chunk_analysis = await _wiki_analysis_step(chunk_text, chunk_label, ai_client)
            elapsed = asyncio.get_event_loop().time() - t0
            logger.info(f"[MapReduce] Part{chunk_idx} LLM 返回 (耗时 {elapsed:.1f}s)")
        if not chunk_analysis:
            return chunk_idx, None, []
        # 提取三元组（CPU 密集型，卸载到线程池）
        wiki_chunk_result = {"analysis": chunk_analysis, "metadata": {}}
        chunk_triplets = await asyncio.to_thread(_extract_wiki_triplets, wiki_chunk_result, filename)
        if chunk_triplets:
            logger.info(f"[MapReduce] Part{chunk_idx} 提取 {len(chunk_triplets)} 三元组")
        return chunk_idx, chunk_analysis, chunk_triplets

    results = await asyncio.gather(
        *[_analyze_chunk(chunk) for chunk in chunks],
        return_exceptions=True,
    )

    all_analyses: List[str] = []
    all_triplets: List[Dict[str, str]] = []

    for result in results:
        if isinstance(result, Exception):
            logger.warning(f"[MapReduce] 分析异常: {result}")
            continue
        chunk_idx, analysis, triplets = result
        if analysis:
            chunk = next(c for c in chunks if c["index"] == chunk_idx)
            all_analyses.append(f"### 分块 {chunk_idx}/{len(chunks)}"
                                f" [{chunk['heading_path']}]\n\n{analysis}")
            all_triplets.extend(triplets)
        else:
            all_analyses.append(f"### 分块 {chunk_idx}/{len(chunks)}\n\n（分析失败）")

    consolidated = "# 长文档综合分析\n\n" + "\n\n".join(all_analyses)

    logger.info(f"[MapReduce] 分析完成: {len(chunks)} 分块 → "
                f"综合分析 {len(consolidated)} 字符, {len(all_triplets)} 三元组")

    return consolidated, all_triplets


async def _generate_sub_wiki_pages(
    source_text: str,
    filename: str,
    ai_client,
    progress_callback=None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """
    高密度切片：每个分块独立生成子 Wiki 页面（真并发版）

    核心优化：
    1. Phase 1（Map）：所有分块并发执行 Step1(分析)，semaphore=3
    2. Phase 2（Generate）：所有分块并发执行 Step2(生成)，semaphore=3
    3. Phase 3（Post-process）：CPU 密集型任务卸载到线程池

    这样 semaphore 的利用率从 (Step1+Step2) 降到单步时间，
    实际吞吐量提升约 2x。

    Returns:
        (sub_pages, all_triplets)
    """
    # ── 语义分块（CPU 密集型，卸载到线程池）──
    chunks = await asyncio.to_thread(_split_source_into_chunks, source_text)

    if len(chunks) <= 1:
        # 短文档：走原有单页面流程
        result = await generate_wiki_page(source_text, filename, progress_callback=progress_callback)
        if result:
            return [result], result.get("map_reduce_triplets", [])
        return [], []

    logger.info(f"[HighDensity] 长文档分块: {filename} → {len(chunks)} 个分块 "
                f"(总长 {len(source_text)} 字符)")

    if progress_callback:
        progress_callback('ANALYZING', f'正在进行高密度知识分块 ({len(chunks)} 块)，启动并发分析...', 35)
        progress_callback('ANALYZING', f'🧠 大模型正在进行深度推理与结构化提炼，该过程极度消耗算力，预计耗时 2~5 分钟，请保持神经接入...', 37)

    semaphore = asyncio.Semaphore(5)

    # ── Phase 1: 并发执行所有分块的 Step1(分析) ──
    async def _analyze_chunk(chunk):
        """并发分析单个分块"""
        chunk_idx = chunk["index"]
        chunk_label = f"{filename} (Part{chunk_idx})"
        async with semaphore:
            t0 = asyncio.get_event_loop().time()
            logger.info(f"[HighDensity] Part{chunk_idx} Step1 开始等待 LLM... "
                        f"(t={t0:.2f})")
            analysis = await _wiki_analysis_step(chunk["main"], chunk_label, ai_client)
            elapsed = asyncio.get_event_loop().time() - t0
            logger.info(f"[HighDensity] Part{chunk_idx} Step1 LLM 返回 "
                        f"({len(analysis or '')} chars, 耗时 {elapsed:.1f}s)")
            return chunk_idx, analysis

    analysis_results = await asyncio.gather(
        *[_analyze_chunk(chunk) for chunk in chunks],
        return_exceptions=True,
    )

    # 收集成功的分析结果
    analysis_map = {}  # chunk_idx -> analysis_text
    for result in analysis_results:
        if isinstance(result, Exception):
            logger.warning(f"[HighDensity] 分析异常: {result}")
            continue
        chunk_idx, analysis = result
        if analysis:
            analysis_map[chunk_idx] = analysis

    logger.info(f"[HighDensity] Phase 1 完成: {len(analysis_map)}/{len(chunks)} 分块分析成功")

    if progress_callback:
        progress_callback('GENERATING', f'大模型正在撰写 Wiki 百科页面 (已完成分析 {len(analysis_map)}/{len(chunks)} 块)...', 50)
        progress_callback('GENERATING', f'🧠 大模型正在撰写百科级知识页面，该过程极度消耗算力，预计耗时 3~8 分钟，请保持神经接入...', 52)

    # ── Phase 2: 并发执行所有分块的 Step2(生成) ──
    async def _generate_chunk(chunk, analysis):
        """并发生成单个分块的 Wiki 页面"""
        chunk_idx = chunk["index"]
        chunk_label = f"{filename} (Part{chunk_idx})"
        async with semaphore:
            t0 = asyncio.get_event_loop().time()
            logger.info(f"[HighDensity] Part{chunk_idx} Step2 开始等待 LLM... "
                        f"(t={t0:.2f})")
            wiki_md = await _wiki_generation_step(analysis, chunk["main"], chunk_label, ai_client)
            elapsed = asyncio.get_event_loop().time() - t0
            logger.info(f"[HighDensity] Part{chunk_idx} Step2 LLM 返回 "
                        f"({len(wiki_md or '')} chars, 耗时 {elapsed:.1f}s)")
            return chunk_idx, wiki_md

    generate_tasks = []
    for chunk in chunks:
        if chunk["index"] in analysis_map:
            generate_tasks.append(_generate_chunk(chunk, analysis_map[chunk["index"]]))

    generate_results = await asyncio.gather(
        *generate_tasks,
        return_exceptions=True,
    )

    # ── Phase 3: 后处理（CPU 密集型，卸载到线程池）──
    sub_pages = []
    all_triplets = []

    for result in generate_results:
        if isinstance(result, Exception):
            logger.warning(f"[HighDensity] 生成异常: {result}")
            continue
        chunk_idx, wiki_md = result
        if not wiki_md:
            continue

        chunk = next(c for c in chunks if c["index"] == chunk_idx)
        chunk_total = chunk["total"]

        # CPU 密集型：解析 frontmatter + 正则提取 wikilinks + 三元组
        metadata, body = await asyncio.to_thread(parse_yaml_frontmatter, wiki_md)
        wikilinks = await asyncio.to_thread(re.findall, r'\[\[([^\]]+)\]\]', body)
        if wikilinks:
            metadata["wikilinks"] = wikilinks

        wiki_result = {"analysis": analysis_map.get(chunk_idx, ""), "metadata": metadata, "body": body}
        triplets = await asyncio.to_thread(_extract_wiki_triplets, wiki_result, filename)

        # 给标题加源文件名前缀 + 序号后缀
        # 命名规范：{源文件名去后缀} Part{N} {LLM生成的主题}
        # 例如：01.数据结构 Part3 树与图
        orig_title = metadata.get("title", "").strip()
        base_filename = os.path.splitext(filename)[0]  # "01.数据结构" from "01.数据结构.pdf"
        if chunk_total > 1:
            if orig_title:
                metadata["title"] = f"{base_filename} Part{chunk_idx} {orig_title}"
            else:
                metadata["title"] = f"{base_filename} Part{chunk_idx}"
        else:
            # 单分块也加源文件名前缀，方便删除时定位
            if orig_title:
                metadata["title"] = f"{base_filename} {orig_title}"
            else:
                metadata["title"] = base_filename
        wiki_md = _set_frontmatter_field(wiki_md, "title", metadata["title"])
        _, body = parse_yaml_frontmatter(wiki_md)

        sub_page = {
            "markdown": wiki_md,
            "metadata": metadata,
            "body": body,
            "analysis": analysis_map.get(chunk_idx, ""),
            "map_reduce_triplets": triplets,
        }

        sub_pages.append(sub_page)
        all_triplets.extend(triplets)
        logger.info(f"[HighDensity] Part{chunk_idx}/{chunk_total} 完成: "
                    f"{len(body)} chars, {len(triplets)} 三元组")

    logger.info(f"[HighDensity] 全部完成: {len(chunks)} 分块 → "
                f"{len(sub_pages)} 篇子页面, {len(all_triplets)} 三元组")

    return sub_pages, all_triplets


def _rolling_digest(existing_digest: str, new_analysis: str, ai_client=None) -> str:
    """
    滚动式全局摘要：将新分析结果融入已有摘要

    参考 llm_wiki ingest.ts: Updated Global Digest
    简化实现：截断拼接，避免额外 LLM 调用
    """
    combined = f"{existing_digest}\n\n{new_analysis}" if existing_digest else new_analysis
    if len(combined) <= GLOBAL_DIGEST_MAX:
        return combined
    # 保留前面已有的摘要 + 新分析的核心部分
    half = GLOBAL_DIGEST_MAX // 2
    return combined[:half] + "\n\n...（摘要省略）...\n\n" + combined[-half:]


async def generate_wiki_page(source_text: str, filename: str, progress_callback=None) -> Optional[Dict[str, Any]]:
    """
    两步走 Wiki 生成主函数（短文档单页面，长文档走高密度切片）

    短文档（≤8000字符）：Step1 → Step2 → 单篇 Wiki
    长文档（>8000字符）：调用 _generate_sub_wiki_pages → 多篇子 Wiki

    返回: {"markdown": str, "metadata": dict, "body": str, "analysis": str,
           "map_reduce_triplets": list, "sub_pages": list} 或 None
    """
    ai_client = _get_ai_client()
    if not ai_client:
        logger.warning("[Wiki] AI client unavailable, falling back to raw chunks")
        return None

    # 长文档：高密度切片（每块独立生成子 Wiki）
    if len(source_text) > LONG_SOURCE_THRESHOLD:
        sub_pages, all_triplets = await _generate_sub_wiki_pages(
            source_text, filename, ai_client, progress_callback=progress_callback,
        )
        if not sub_pages:
            logger.warning(f"[Wiki] 高密度切片失败，降级为原始切块: {filename}")
            return None

        # 将所有子页面拼接为一个超长 Markdown（供 Embedding 切块）
        all_bodies = []
        all_wikilinks = []
        for page in sub_pages:
            all_bodies.append(page["body"])
            all_wikilinks.extend(page.get("metadata", {}).get("wikilinks", []))

        combined_body = "\n\n---\n\n".join(all_bodies)
        combined_wikilinks = list(dict.fromkeys(all_wikilinks))  # 去重保序

        # 使用第一个子页面的 metadata 作为基础
        base_meta = sub_pages[0].get("metadata", {})
        combined_meta = {
            "title": base_meta.get("title", filename),
            "type": base_meta.get("type", "concept"),
            "sources": base_meta.get("sources", [filename]),
            "tags": base_meta.get("tags", []),
            "wikilinks": combined_wikilinks,
        }

        return {
            "markdown": f"---\ntitle: {combined_meta['title']}\n---\n\n{combined_body}",
            "metadata": combined_meta,
            "body": combined_body,
            "analysis": "\n\n".join(p.get("analysis", "") for p in sub_pages),
            "map_reduce_triplets": all_triplets,
            "sub_pages": sub_pages,  # 保留子页面供独立切块
        }

    # 短文档：原有单页面流程
    if progress_callback:
        progress_callback('ANALYZING', f'正在分析 {filename}，提取知识实体...', 35)
        progress_callback('ANALYZING', f'🧠 大模型正在进行深度推理与结构化提炼，该过程极度消耗算力，预计耗时 2~5 分钟，请保持神经接入...', 37)
    analysis_result = await _wiki_analysis_step(source_text, filename, ai_client)
    if not analysis_result:
        logger.warning(f"[Wiki] 分析步骤失败，降级为原始切块: {filename}")
        return None

    if progress_callback:
        progress_callback('GENERATING', f'大模型正在撰写 {filename} 的 Wiki 百科页面...', 50)
        progress_callback('GENERATING', f'🧠 大模型正在撰写百科级知识页面，该过程极度消耗算力，预计耗时 3~8 分钟，请保持神经接入...', 52)
    wiki_markdown = await _wiki_generation_step(analysis_result, source_text, filename, ai_client)
    if not wiki_markdown:
        logger.warning(f"[Wiki] 生成步骤失败，降级为原始切块: {filename}")
        return None

    metadata, body = await asyncio.to_thread(parse_yaml_frontmatter, wiki_markdown)

    wikilinks = await asyncio.to_thread(re.findall, r'\[\[([^\]]+)\]\]', body)
    if wikilinks:
        metadata["wikilinks"] = wikilinks
        logger.info(f"[Wiki] 提取到 {len(wikilinks)} 个双向链接: {wikilinks[:5]}...")

    return {
        "markdown": wiki_markdown,
        "metadata": metadata,
        "body": body,
        "analysis": analysis_result,
        "map_reduce_triplets": [],
        "sub_pages": [],
    }


# ─────────────────────────────────────────────────────────
# 智能页面融合 (Intelligent Page Merge)
# 参考 llm_wiki: src/lib/page-merge.ts + ingest.ts buildPageMerger
# ─────────────────────────────────────────────────────────

def _wiki_page_path(user_id: str, page_name: str) -> str:
    """获取 wiki 页面的磁盘路径"""
    safe_name = re.sub(r'[^\w\u4e00-\u9fff\-]', '_', page_name)
    user_dir = os.path.join(WIKI_PAGES_DIR, user_id.replace("-", "_"))
    os.makedirs(user_dir, exist_ok=True)
    return os.path.join(user_dir, f"{safe_name}.md")


def _read_existing_page(user_id: str, page_name: str) -> Optional[str]:
    """读取已有的 wiki 页面内容，不存在返回 None"""
    path = _wiki_page_path(user_id, page_name)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.warning(f"[PageMerge] 读取已有页面失败: {page_name} - {e}")
    return None


def _write_wiki_page(user_id: str, page_name: str, content: str):
    """写入 wiki 页面到磁盘"""
    path = _wiki_page_path(user_id, page_name)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"[PageMerge] 页面已写入: {page_name}")
    except Exception as e:
        logger.error(f"[PageMerge] 写入页面失败: {page_name} - {e}")


def _backup_page(user_id: str, page_name: str, content: str):
    """备份已有页面（合并前快照，支持回滚）"""
    try:
        user_dir = os.path.join(WIKI_PAGES_DIR, user_id.replace("-", "_"))
        backup_dir = os.path.join(user_dir, ".history")
        os.makedirs(backup_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = re.sub(r'[^\w\u4e00-\u9fff\-]', '_', page_name)
        backup_path = os.path.join(backup_dir, f"{safe_name}_{stamp}.md")
        with open(backup_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"[PageMerge] 备份已创建: {page_name} → {backup_path}")
    except Exception as e:
        logger.warning(f"[PageMerge] 备份失败（不阻断合并）: {page_name} - {e}")


def _merge_lists(existing: List[str], incoming: List[str]) -> List[str]:
    """大小写不敏感的去重并集（参考 llm_wiki mergeLists）"""
    seen = set()
    result = []
    for item in existing + incoming:
        key = item.lower().strip()
        if key and key not in seen:
            seen.add(key)
            result.append(item.strip())
    return result


def _set_frontmatter_field(md_text: str, field: str, value) -> str:
    """在 frontmatter 中设置/更新一个字段"""
    metadata, body = parse_yaml_frontmatter(md_text)
    metadata[field] = value

    # 重建 frontmatter
    lines = ["---"]
    for k, v in metadata.items():
        if isinstance(v, list):
            items = ", ".join(f'"{item}"' for item in v)
            lines.append(f"{k}: [{items}]")
        elif isinstance(v, str) and (" " in v or "\n" in v):
            lines.append(f'{k}: "{v}"')
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")

    return "\n".join(lines) + "\n\n" + body


def _deterministic_merge_frontmatter(existing_md: str, new_md: str) -> Tuple[str, Dict[str, Any]]:
    """
    确定性 frontmatter 合并（不调用 LLM）：
    - UNION_FIELDS 做并集
    - 返回合并后的 new_md 和合并统计
    """
    existing_meta, existing_body = parse_yaml_frontmatter(existing_md)
    new_meta, new_body = parse_yaml_frontmatter(new_md)

    merged_fields = {}
    for field in UNION_FIELDS:
        old_list = existing_meta.get(field, [])
        new_list = new_meta.get(field, [])
        if isinstance(old_list, str):
            old_list = [old_list]
        if isinstance(new_list, str):
            new_list = [new_list]
        merged = _merge_lists(old_list, new_list)
        if merged:
            merged_fields[field] = merged
            new_md = _set_frontmatter_field(new_md, field, merged)

    return new_md, {"merged_fields": merged_fields, "body_changed": new_body.strip() != existing_body.strip()}


async def _llm_merge_pages(
    existing_content: str,
    new_content: str,
    source_filename: str,
    ai_client,
) -> Optional[str]:
    """
    调用 LLM 合并两份 wiki 页面（参考 llm_wiki buildPageMerger）
    """
    from app.core.prompt_manager import PromptManager

    system_prompt = PromptManager.get_prompt("wiki_merge_system")
    if not system_prompt:
        logger.warning("[PageMerge] wiki_merge_system prompt 未找到，跳过 LLM 合并")
        return None

    user_message = (
        f"## 知识库中已有的版本\n\n{existing_content}\n\n"
        f"---\n\n"
        f"## 从新文档「{source_filename}」中提取的版本\n\n{new_content}\n\n"
        f"---\n\n"
        f"请输出合并后的完整文件，首行以 `---` 开头。"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    try:
        response = await ai_client.acall_api(messages, max_tokens=8192)
        if not response or not response.strip():
            logger.warning("[PageMerge] LLM 合并返回空")
            return None

        cleaned = response.strip()
        # 清理代码块包裹
        if cleaned.startswith("```markdown"):
            cleaned = cleaned[len("```markdown"):]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        # 健全性检查：必须以 --- 开头（有 frontmatter）
        if not cleaned.startswith("---"):
            logger.warning("[PageMerge] LLM 合并结果缺少 frontmatter，拒绝")
            return None

        return cleaned
    except Exception as e:
        logger.error(f"[PageMerge] LLM 合并调用失败: {e}")
        return None


async def merge_wiki_page(
    user_id: str,
    new_markdown: str,
    page_name: str,
    source_filename: str,
) -> str:
    """
    智能页面融合主函数（参考 llm_wiki mergePageContent）

    流程：
    1. 检查是否已有同名页面
    2. 无 → 直接写入
    3. 有 → 确定性 frontmatter 合并 + LLM body 合并
    4. 健全性检查（body 长度不得低于 70%）
    5. 锁定字段回写 + 备份

    返回: 最终的 markdown 内容
    """
    existing_content = _read_existing_page(user_id, page_name)

    # 快速路径 1：全新页面，直接写入
    if existing_content is None:
        _write_wiki_page(user_id, page_name, new_markdown)
        logger.info(f"[PageMerge] 新页面创建: {page_name}")
        return new_markdown

    # 快速路径 2：内容完全相同
    if new_markdown.strip() == existing_content.strip():
        logger.info(f"[PageMerge] 页面内容无变化: {page_name}")
        return existing_content

    # 步骤 1：确定性 frontmatter 合并（UNION_FIELDS 做并集）
    merged_md, merge_info = _deterministic_merge_frontmatter(existing_content, new_markdown)

    # 快速路径 3：仅 frontmatter 变化，body 未变
    if not merge_info["body_changed"]:
        _write_wiki_page(user_id, page_name, merged_md)
        logger.info(f"[PageMerge] 仅 frontmatter 更新: {page_name}")
        return merged_md

    # 步骤 2：LLM body 合并
    ai_client = _get_ai_client()
    _, existing_body = parse_yaml_frontmatter(existing_content)
    _, new_body = parse_yaml_frontmatter(new_markdown)

    llm_merged = None
    if ai_client:
        llm_merged = await _llm_merge_pages(existing_content, new_markdown, source_filename, ai_client)

    if llm_merged:
        # 健全性检查：body 长度不得低于 max(旧,新) * 0.7
        _, llm_body = parse_yaml_frontmatter(llm_merged)
        max_body_len = max(len(existing_body.strip()), len(new_body.strip()))
        min_acceptable = int(max_body_len * BODY_SHRINK_THRESHOLD)

        if len(llm_body.strip()) < min_acceptable:
            logger.warning(
                f"[PageMerge] LLM 合并后 body 过短 "
                f"({len(llm_body.strip())} < {min_acceptable})，拒绝合并结果"
            )
            llm_merged = None
        else:
            # 步骤 3：锁定字段回写
            existing_meta, _ = parse_yaml_frontmatter(existing_content)
            for field in LOCKED_FIELDS:
                old_val = existing_meta.get(field)
                if old_val and isinstance(old_val, str) and old_val.strip():
                    llm_merged = _set_frontmatter_field(llm_merged, field, old_val)

            # 防御性再次合并 UNION_FIELDS
            for field in UNION_FIELDS:
                merged_list = merge_info.get("merged_fields", {}).get(field, [])
                if merged_list:
                    llm_merged = _set_frontmatter_field(llm_merged, field, merged_list)

            # 设置 updated 日期
            llm_merged = _set_frontmatter_field(llm_merged, "updated", datetime.now().strftime("%Y-%m-%d"))

    # 回退路径：LLM 合并失败 → 使用新版本 + 确定性 frontmatter
    final_content = llm_merged if llm_merged else merged_md

    # 备份旧版本
    _backup_page(user_id, page_name, existing_content)

    # 写入合并结果
    _write_wiki_page(user_id, page_name, final_content)

    if llm_merged:
        logger.info(
            f"[PageMerge] ✅ LLM 合并成功: {page_name} "
            f"(旧={len(existing_body)} chars, 新={len(new_body)} chars, "
            f"合并={len(llm_body.strip())} chars)"
        )
    else:
        logger.info(
            f"[PageMerge] ⚠️ LLM 合并失败，使用新版本覆盖: {page_name}"
        )

    return final_content


def _extract_wiki_triplets(wiki_result: Dict[str, Any], filename: str) -> List[Dict[str, str]]:
    """
    从 Wiki 分析结果中提取图谱三元组

    参考 llm_wiki wiki-graph.ts: 页面 A 含 [[B]] → 生成边 A→B
    两路来源:
      1. 分析 JSON 中的 facts/entities/key_concepts（结构化三元组）
      2. wikilinks（页面间引用关系，无论 JSON 是否解析成功都写入）
    """
    triplets = []

    # ── 来源 1：从分析 JSON 中提取结构化三元组 ──
    analysis_text = wiki_result.get("analysis", "")
    if analysis_text:
        try:
            json_match = re.search(r'\{[\s\S]*\}', analysis_text)
            if json_match:
                analysis_data = json.loads(json_match.group())

                # 从 facts 字段提取三元组
                for fact in analysis_data.get("facts", []):
                    head = fact.get("subject", "").strip()
                    relation = fact.get("predicate", "").strip()
                    tail = fact.get("object", "").strip()
                    if head and relation and tail:
                        triplets.append({"head": head, "relation": relation, "tail": tail})

                # 从 entities 字段提取实体-类型关系
                for entity in analysis_data.get("entities", []):
                    name = entity.get("name", "").strip()
                    etype = entity.get("type", "").strip()
                    if name and etype:
                        triplets.append({"head": name, "relation": "类型为", "tail": etype})

                # 从 key_concepts 字段提取概念关系
                for concept in analysis_data.get("key_concepts", []):
                    name = concept.get("name", "").strip()
                    if name:
                        main_theme = analysis_data.get("main_theme", "").strip()
                        if main_theme:
                            triplets.append({"head": name, "relation": "属于", "tail": main_theme})

        except (json.JSONDecodeError, AttributeError) as e:
            logger.debug(f"[Wiki] JSON 解析分析结果失败: {e}")

    # ── 来源 2：从 wikilinks 提取页面间引用关系（参考 llm_wiki buildWikiGraph）──
    # 无论 JSON 是否解析成功，wikilinks 都应写入图谱
    wikilinks = wiki_result.get("metadata", {}).get("wikilinks", [])
    page_title = wiki_result.get("metadata", {}).get("title", "").strip()

    if wikilinks:
        # 用页面标题作为 head（更语义化），降级用 filename
        source_name = page_title if page_title else filename
        for link in wikilinks:
            link = link.strip()
            if not link or link == source_name:
                continue  # 跳过自引用
            triplets.append({"head": source_name, "relation": "引用", "tail": link})

    return triplets


def _get_rag_engine():
    global _worker_rag_engine
    if _worker_rag_engine is not None:
        return _worker_rag_engine

    from app.core.app_state import app_state
    if app_state.rag_engine is not None:
        _worker_rag_engine = app_state.rag_engine
        return _worker_rag_engine

    logger.info("KB Processor: initializing standalone RAG engine for Celery worker...")
    try:
        from app.services.rag_engine import RAGEngine

        config_path = "ai_models_config.json"
        ai_config = {}
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                ai_config = json.load(f)

        embedding_config = ai_config.get("embedding", {})
        embedding_api_key = (
            embedding_config.get("api_key")
            or os.getenv("EMBEDDING_API_KEY")
            or os.getenv("DASHSCOPE_API_KEY")
        )
        embedding_base_url = embedding_config.get("base_url", "https://api.siliconflow.cn/v1")
        embedding_model = embedding_config.get("model", "BAAI/bge-m3")
        embedding_dimension = embedding_config.get("dimension", 1024)

        _worker_rag_engine = RAGEngine(
            embedding_api_key=embedding_api_key,
            embedding_base_url=embedding_base_url,
            embedding_model=embedding_model,
            embedding_dimension=embedding_dimension,
        )
        logger.info(f"KB Processor: standalone RAG engine initialized | model={embedding_model}")
    except Exception as e:
        logger.error(f"KB Processor: standalone RAG engine init failed: {e}")
        _worker_rag_engine = None

    return _worker_rag_engine


async def backfill_wikilinks_to_graph(user_id: str):
    """
    存量 wikilink 回填：扫描已有 wiki 页面，将 [[wikilinks]] 写入图谱

    参考 llm_wiki wiki-graph.ts buildWikiGraph:
      遍历所有 .md 文件 → 提取 [[target]] → 生成边 source→target
    """
    graph_engine = _get_graph_engine()
    if not graph_engine:
        logger.warning("[WikilinkBackfill] 图谱引擎不可用，跳过回填")
        return

    user_dir = os.path.join(WIKI_PAGES_DIR, user_id.replace("-", "_"))
    if not os.path.isdir(user_dir):
        return

    total_triplets = 0
    for fname in os.listdir(user_dir):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(user_dir, fname)
        if os.path.isfile(fpath):
            try:
                content = open(fpath, "r", encoding="utf-8").read()
                meta, body = parse_yaml_frontmatter(content)
                page_title = meta.get("title", "").strip()
                if not page_title:
                    page_title = os.path.splitext(fname)[0]

                wikilinks = re.findall(r'\[\[([^\]]+)\]\]', body)
                if not wikilinks:
                    continue

                triplets = []
                for link in wikilinks:
                    link = link.strip()
                    if not link or link == page_title:
                        continue
                    triplets.append({"head": page_title, "relation": "引用", "tail": link})

                if triplets:
                    # 从 frontmatter 提取原始文件名作为 source_files
                    raw_source_id = meta.get("source_id", "")
                    # source_id 格式如 "01.数据结构.pdf" 或 "01.数据结构.pdf (Part1)"
                    # 提取纯文件名（去掉 Part 后缀）
                    original_filename = re.sub(r'\s*\(Part\d+\)\s*$', '', raw_source_id).strip()
                    source_files_list = [original_filename] if original_filename else []

                    await asyncio.to_thread(
                        graph_engine.add_triplets,
                        triplets,
                        user_id=user_id,
                        source=f"wikilink_backfill:{fname}",
                        source_text=body[:500],
                        source_files=source_files_list,
                    )
                    total_triplets += len(triplets)

            except Exception as e:
                logger.warning(f"[WikilinkBackfill] 处理 {fname} 失败: {e}")

    if total_triplets > 0:
        logger.info(f"[WikilinkBackfill] 用户 {user_id[:8]}... 回填 {total_triplets} 条 wikilink 三元组")


@aios_notify(
    source="knowledge_base",
    action_start="working",
    action_error="error",
    action_success="success",
    start_msg_template="大模型正在吞噬您的文献，准备生成闪卡...",
    success_msg_template="图谱构建与闪卡抽取完成！",
)
async def process_kb_files_sync(user_id: str, files: List[Dict[str, Any]], progress_callback=None) -> Dict[str, Any]:
    """知识库文件处理主入口（已接入 AIOS 事件总线装饰器）"""
    rag_engine = _get_rag_engine()
    if rag_engine is None:
        logger.error("KB Processor: RAG engine not initialized (both app_state and standalone)")
        return {"status": "error", "message": "RAG引擎未初始化"}

    try:
        return await _process_kb_files_inner(user_id, files, rag_engine, progress_callback=progress_callback)
    except Exception as e:
        logger.error(f"KB Processor: unhandled exception for user={user_id}: {e}", exc_info=True)
        _mark_files_failed(files, str(e))
        return {"status": "error", "message": str(e), "files": files}


async def _process_kb_files_inner(user_id: str, files: List[Dict[str, Any]], rag_engine, progress_callback=None) -> Dict[str, Any]:

    from app.core.file_manager import calculate_file_hash
    from app.models.database import DocumentCache, get_session

    # ── 进度上报辅助 ──
    def _progress(state: str, message: str, percent: int = 0, **meta):
        if progress_callback:
            try:
                progress_callback(state, message, percent, **meta)
            except Exception as e:
                logger.warning(f"[KB] progress_callback failed (state={state}): {e}")
        # 同步事件到 RabbitMQ → 桌宠大管家
        _publish_kb_event(user_id, state, message, percent)

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100,
        separators=["\n\n", "\n", "。", "！", "？", "；", " ", ""],
    )

    all_chunks: List[Document] = []
    file_results = []

    total_files = len(files)
    _progress('INITIALIZING', f'正在初始化处理管线，共 {total_files} 个文件待处理...', 5)

    for file_idx, file_info in enumerate(files):
        filename = file_info.get("filename", "unknown")
        saved_path = file_info.get("saved_path", "")
        ext = file_info.get("ext", "")
        doc_id = file_info.get("doc_id")

        if not saved_path or not os.path.exists(saved_path):
            file_results.append({"filename": filename, "status": "error", "reason": "文件不存在", "doc_id": doc_id})
            continue

        # ── 增量 Hash 缓存拦截 ──
        try:
            current_hash = calculate_file_hash(saved_path)
        except Exception as e:
            logger.warning(f"[Cache] 无法计算文件哈希 {filename}: {e}")
            current_hash = None

        if current_hash:
            cache_session = get_session()
            try:
                cache_entry = cache_session.query(DocumentCache).filter(
                    DocumentCache.file_path == saved_path,
                    DocumentCache.user_id == user_id,
                ).first()

                if cache_entry and cache_entry.file_hash == current_hash:
                    logger.info(f"[Cache] 文件未修改，跳过处理: {filename} (hash={current_hash[:12]}...)")
                    file_results.append({
                        "filename": filename,
                        "status": "skipped",
                        "reason": "unchanged",
                        "doc_id": doc_id,
                    })
                    # 标记 DocumentMeta 为 completed（如果存在）
                    if doc_id:
                        doc_meta = cache_session.query(DocumentMeta).filter(DocumentMeta.id == doc_id).first()
                        if doc_meta and doc_meta.status == "processing":
                            doc_meta.status = "completed"
                            cache_session.add(doc_meta)
                            cache_session.commit()
                    continue
                elif cache_entry:
                    logger.info(f"[Cache] 文件已变更，重新处理: {filename} (old={cache_entry.file_hash[:12]}... new={current_hash[:12]}...)")
                else:
                    logger.info(f"[Cache] 新文件，首次处理: {filename} (hash={current_hash[:12]}...)")
            except Exception as e:
                logger.warning(f"[Cache] 缓存查询失败，继续处理: {e}")
            finally:
                cache_session.close()

        try:
            # ── 文档提取（CPU 密集型，卸载到线程池）──
            _progress('EXTRACTING', f'正在解析 {filename}，提取文本与图片...', 10 + int(file_idx / total_files * 15))
            documents = await asyncio.to_thread(_extract_documents, saved_path, filename, ext, rag_engine, _progress)

            if not documents:
                file_results.append({"filename": filename, "status": "empty", "chunks": 0, "doc_id": doc_id})
                _progress('EXTRACTING', f'⚠️ {filename} 文本提取为空，跳过...', 15)
                continue

            _progress('EXTRACTING', f'📄 {filename} 文本提取完成，共 {len(documents)} 页内容', 20)

            # ── 两步走 Wiki 生成（优先） → 降级为暴力切块 ──
            source_text = "\n\n".join(doc.page_content for doc in documents)
            _progress('ANALYZING', f'正在分析 {filename}，提取知识实体与概念...', 30 + int(file_idx / total_files * 20))
            wiki_result = await generate_wiki_page(source_text, filename, progress_callback=_progress)

            if wiki_result and wiki_result.get("body"):
                # Wiki 生成成功
                sub_pages = wiki_result.get("sub_pages", [])

                if sub_pages and len(sub_pages) > 1:
                    # ── 高密度切片模式：每个子页面独立切块 ──
                    chunk_count = 0
                    for sp_idx, sub_page in enumerate(sub_pages):
                        sp_body = sub_page["body"]
                        sp_meta = sub_page.get("metadata", {})

                        # 智能页面融合（每个子页面独立融合）
                        sp_title = sp_meta.get("title", "").strip()
                        if sp_title:
                            try:
                                merged_md = await merge_wiki_page(
                                    user_id=user_id,
                                    new_markdown=sub_page["markdown"],
                                    page_name=sp_title,
                                    source_filename=filename,
                                )
                                merged_m, merged_b = await asyncio.to_thread(parse_yaml_frontmatter, merged_md)
                                sp_body = merged_b
                                sp_meta = merged_m
                                # 重新提取 wikilinks
                                sp_wikilinks = await asyncio.to_thread(re.findall, r'\[\[([^\]]+)\]\]', merged_b)
                                if sp_wikilinks:
                                    sp_meta["wikilinks"] = sp_wikilinks
                            except Exception as e:
                                logger.warning(f"[PageMerge] 子页面 {sp_title} 融合失败: {e}")

                        sp_doc = Document(
                            page_content=sp_body,
                            metadata={
                                "source": filename,
                                "type": sp_meta.get("type", "wiki"),
                                "title": sp_meta.get("title", filename),
                                "wiki_mode": True,
                                "sub_page_index": sp_idx,
                            },
                        )

                        if len(sp_body) > 1500:
                            sp_chunks = await asyncio.to_thread(text_splitter.split_documents, [sp_doc])
                            for i, chunk in enumerate(sp_chunks):
                                chunk.metadata["source"] = filename
                                chunk.metadata["chunk_index"] = chunk_count + i
                                chunk.metadata["wiki_mode"] = True
                            all_chunks.extend(sp_chunks)
                            chunk_count += len(sp_chunks)
                        else:
                            sp_doc.metadata["chunk_index"] = chunk_count
                            all_chunks.append(sp_doc)
                            chunk_count += 1

                    # 图谱三元组写入（合并所有子页面的三元组）
                    try:
                        all_triplets = wiki_result.get("map_reduce_triplets", [])
                        # 去重
                        seen_keys = set()
                        unique_triplets = []
                        for t in all_triplets:
                            key = (t["head"], t["relation"], t["tail"])
                            if key not in seen_keys:
                                seen_keys.add(key)
                                unique_triplets.append(t)

                        if unique_triplets:
                            _progress('GRAPH_BUILDING', f'正在向 Neo4j 神经网络注入 {len(unique_triplets)} 条核心实体三元组...', 65)
                            graph_engine = _get_graph_engine()
                            if graph_engine:
                                source_text_for_graph = wiki_result.get("body", "")[:500]
                                await asyncio.to_thread(
                                    graph_engine.add_triplets,
                                    unique_triplets, user_id=user_id, source=filename,
                                    source_text=source_text_for_graph,
                                    source_files=[filename],
                                )
                                logger.info(f"[Wiki] 图谱写入: {filename} → {len(unique_triplets)} 三元组")
                    except Exception as e:
                        logger.warning(f"[Wiki] 图谱写入失败: {e}")

                else:
                    # ── 单页面模式（短文档或高密度切片只有1篇）──
                    wiki_body = wiki_result["body"]
                    wiki_metadata = wiki_result.get("metadata", {})

                    # 智能页面融合
                    page_title = wiki_metadata.get("title", "").strip()
                    # 加入源文件名前缀，方便删除时定位派生文件
                    base_filename = os.path.splitext(filename)[0]
                    if page_title and not page_title.startswith(base_filename):
                        page_title = f"{base_filename} {page_title}"
                        wiki_metadata["title"] = page_title
                        wiki_result["metadata"]["title"] = page_title
                    if page_title:
                        try:
                            merged_markdown = await merge_wiki_page(
                                user_id=user_id,
                                new_markdown=wiki_result["markdown"],
                                page_name=page_title,
                                source_filename=filename,
                            )
                            merged_meta, merged_body = await asyncio.to_thread(parse_yaml_frontmatter, merged_markdown)
                            wiki_body = merged_body
                            wiki_metadata = merged_meta
                            wiki_result["body"] = merged_body
                            wiki_result["markdown"] = merged_markdown
                            wiki_result["metadata"] = merged_meta

                            merged_wikilinks = await asyncio.to_thread(re.findall, r'\[\[([^\]]+)\]\]', merged_body)
                            if merged_wikilinks:
                                wiki_metadata["wikilinks"] = merged_wikilinks
                                wiki_result["metadata"]["wikilinks"] = merged_wikilinks
                                logger.info(f"[PageMerge] 融合后提取到 {len(merged_wikilinks)} 个 wikilinks")
                        except Exception as e:
                            logger.warning(f"[PageMerge] 页面融合失败，使用原始版本: {e}")

                    wiki_doc = Document(
                        page_content=wiki_body,
                        metadata={
                            "source": filename,
                            "type": wiki_metadata.get("type", "wiki"),
                            "title": wiki_metadata.get("title", filename),
                            "wiki_mode": True,
                        },
                    )

                    if len(wiki_body) > 1500:
                        wiki_chunks = await asyncio.to_thread(text_splitter.split_documents, [wiki_doc])
                        for i, chunk in enumerate(wiki_chunks):
                            chunk.metadata["source"] = filename
                            chunk.metadata["chunk_index"] = i
                            chunk.metadata["wiki_mode"] = True
                        all_chunks.extend(wiki_chunks)
                        chunk_count = len(wiki_chunks)
                    else:
                        wiki_doc.metadata["chunk_index"] = 0
                        all_chunks.append(wiki_doc)
                        chunk_count = 1

                    # 图谱三元组写入
                    try:
                        triplets = await asyncio.to_thread(_extract_wiki_triplets, wiki_result, filename)
                        map_reduce_triplets = wiki_result.get("map_reduce_triplets", [])
                        if map_reduce_triplets:
                            seen_keys = set()
                            for t in triplets:
                                seen_keys.add((t["head"], t["relation"], t["tail"]))
                            for t in map_reduce_triplets:
                                key = (t["head"], t["relation"], t["tail"])
                                if key not in seen_keys:
                                    triplets.append(t)
                                    seen_keys.add(key)

                        if triplets:
                            _progress('GRAPH_BUILDING', f'正在向 Neo4j 神经网络注入 {len(triplets)} 条核心实体三元组...', 65)
                            graph_engine = _get_graph_engine()
                            if graph_engine:
                                source_text = wiki_result.get("body", "")[:500]
                                await asyncio.to_thread(
                                    graph_engine.add_triplets,
                                    triplets, user_id=user_id, source=filename,
                                    source_text=source_text,
                                    source_files=[filename],
                                )
                                logger.info(f"[Wiki] 图谱写入: {filename} → {len(triplets)} 三元组")
                    except Exception as e:
                        logger.warning(f"[Wiki] 图谱写入失败: {e}")

                file_results.append({
                    "filename": filename,
                    "status": "success",
                    "chunks": chunk_count,
                    "doc_id": doc_id,
                    "saved_path": saved_path,
                    "file_hash": current_hash,
                    "wiki_mode": True,
                })
                total_body_len = len(wiki_result.get("body", ""))
                logger.info(f"[Wiki] {filename} → Wiki 页面 ({chunk_count} chunks, {total_body_len} chars)")
            else:
                # 降级：Wiki 生成失败，回退到暴力切块
                logger.info(f"[Wiki] 降级为原始切块: {filename}")
                chunks = await asyncio.to_thread(text_splitter.split_documents, documents)
                for i, chunk in enumerate(chunks):
                    chunk.metadata["source"] = filename
                    chunk.metadata["chunk_index"] = i
                    chunk.metadata["wiki_mode"] = False

                all_chunks.extend(chunks)
                file_results.append({
                    "filename": filename,
                    "status": "success",
                    "chunks": len(chunks),
                    "doc_id": doc_id,
                    "saved_path": saved_path,
                    "file_hash": current_hash,
                    "wiki_mode": False,
                })
                logger.info(f"KB Processor: {filename} → {len(chunks)} chunks (fallback)")

        except Exception as e:
            logger.error(f"KB Processor: failed to process {filename}: {e}")
            file_results.append({"filename": filename, "status": "error", "reason": str(e)})

    total_chunks = 0
    effective_collection = ""
    ingest_error = None
    if all_chunks:
        _progress('EMBEDDING', f'正在向量化 {len(all_chunks)} 个知识块并写入向量数据库...', 75)
        try:
            result = await rag_engine.ingest_documents_batch(all_chunks, "default", user_id=user_id)
            total_chunks = result["ingested_count"]
            effective_collection = result["collection"]
            logger.info(f"KB Processor: {len(all_chunks)} chunks → [{effective_collection}], ingested={total_chunks}")
        except Exception as e:
            logger.error(f"KB Processor: batch ingest failed: {e}")
            ingest_error = str(e)
            for fr in file_results:
                if fr.get("status") == "success":
                    fr["status"] = "error"
                    fr["reason"] = f"向量化入库失败: {ingest_error}"

    # ── 更新 DocumentMeta 状态 ──
    try:
        from app.models.database import DocumentMeta, get_session
        session = get_session()
        for fr in file_results:
            doc_id = fr.get("doc_id")
            if doc_id:
                doc_meta = session.query(DocumentMeta).filter(DocumentMeta.id == doc_id).first()
                if doc_meta:
                    if fr.get("status") == "success":
                        doc_meta.status = "completed"
                        doc_meta.chunk_count = fr.get("chunks", 0)
                        doc_meta.collection_name = effective_collection
                    elif fr.get("status") == "skipped":
                        doc_meta.status = "completed"
                    else:
                        doc_meta.status = "failed"
                    session.add(doc_meta)
            elif fr.get("status") == "success":
                doc_meta = DocumentMeta(
                    filename=fr["filename"],
                    file_type=os.path.splitext(fr["filename"])[1].lower().lstrip("."),
                    chunk_count=fr.get("chunks", 0),
                    status="completed",
                    collection_name=effective_collection,
                    owner_id=user_id,
                    user_id=user_id,
                )
                session.add(doc_meta)
        session.commit()
    except Exception as e:
        logger.warning(f"KB Processor: failed to update document metadata: {e}")
    finally:
        try:
            session.close()
        except Exception:
            pass

    # ── 处理成功后更新 Hash 缓存（参考 llm_wiki：只有成功才保存） ──
    if not ingest_error:
        _update_document_cache(user_id, file_results)

    _trigger_flashcard_extraction(user_id, files)

    if ingest_error:
        return {
            "status": "error",
            "collection_name": effective_collection,
            "total_chunks": total_chunks,
            "files": file_results,
            "message": f"向量化入库失败: {ingest_error}",
        }

    # ── 存量 wikilink 回填：将已有 wiki 页面的 [[wikilinks]] 写入图谱 ──
    _progress('GRAPH_BUILDING', f'正在将知识图谱写入 Neo4j 神经网络...', 90)
    try:
        await backfill_wikilinks_to_graph(user_id)
    except Exception as e:
        logger.warning(f"[WikilinkBackfill] 回填失败（非致命）: {e}")

    _progress('WIKILINK_BACKFILL', f'深度语义提取完成！正在增量回填 Wikilink 概念连接边...', 92)

    # ── 主动回收内存，防止 OOM ──
    gc.collect()
    logger.info(f"KB Processor: gc.collect() 完成，释放内存")

    _progress('COMPLETED', f'知识网络构建完成！共 {total_chunks} 个知识块已入库', 100)

    return {
        "status": "success",
        "collection_name": effective_collection,
        "total_chunks": total_chunks,
        "files": file_results,
    }


def _trigger_flashcard_extraction(user_id: str, files: List[Dict[str, Any]]):
    try:
        from app.core.config import settings
        if not settings.USE_CELERY:
            logger.info("KB Processor: skipping flashcard extraction (Celery disabled)")
            return

        from app.worker.tasks import extract_flashcards_task
        for f in files:
            saved_path = f.get("saved_path", "")
            filename = f.get("filename", "")
            ext = f.get("ext", "")
            if saved_path and os.path.exists(saved_path) and ext in (".pdf", ".docx", ".txt", ".md"):
                extract_flashcards_task.delay(
                    user_id=user_id,
                    file_path=saved_path,
                    document_name=filename,
                )
                logger.info(f"KB Processor: dispatched flashcard extraction for {filename}")
    except Exception as e:
        logger.warning(f"KB Processor: failed to trigger flashcard extraction: {e}")


def _update_document_cache(user_id: str, file_results: List[Dict[str, Any]]):
    """处理成功后更新 Hash 缓存（参考 llm_wiki：只有无硬失败才保存）"""
    from app.models.database import DocumentCache, get_session

    session = get_session()
    try:
        for fr in file_results:
            if fr.get("status") != "success":
                continue
            saved_path = fr.get("saved_path")
            file_hash = fr.get("file_hash")
            if not saved_path or not file_hash:
                continue

            cache_entry = session.query(DocumentCache).filter(
                DocumentCache.file_path == saved_path,
                DocumentCache.user_id == user_id,
            ).first()

            if cache_entry:
                cache_entry.file_hash = file_hash
                cache_entry.last_processed_at = datetime.utcnow()
                logger.info(f"[Cache] 更新缓存: {fr['filename']} (hash={file_hash[:12]}...)")
            else:
                cache_entry = DocumentCache(
                    file_path=saved_path,
                    user_id=user_id,
                    file_hash=file_hash,
                )
                session.add(cache_entry)
                logger.info(f"[Cache] 新增缓存: {fr['filename']} (hash={file_hash[:12]}...)")

        session.commit()
    except Exception as e:
        session.rollback()
        logger.warning(f"[Cache] 缓存更新失败: {e}")
    finally:
        session.close()


def _mark_files_failed(files: List[Dict[str, Any]], error_msg: str):
    try:
        from app.models.database import DocumentMeta, get_session
        session = get_session()
        try:
            for f in files:
                doc_id = f.get("doc_id")
                if doc_id:
                    doc = session.query(DocumentMeta).filter(DocumentMeta.id == doc_id).first()
                    if doc and doc.status == "processing":
                        doc.status = "failed"
                        doc.description = error_msg[:500]
                        session.add(doc)
            session.commit()
            logger.info(f"KB Processor: marked docs as 'failed' after exception")
        except Exception as e:
            session.rollback()
            logger.error(f"KB Processor: _mark_files_failed DB error: {e}")
        finally:
            session.close()
    except Exception as e:
        logger.error(f"KB Processor: _mark_files_failed total failure: {e}")


def _append_image_captions_sync(documents: List[Document], file_path: str, filename: str, ext: str, progress_callback=None):
    """
    从 PDF/DOCX 中流式逐图提取图片，调用 Vision LLM 生成深度描述，
    将 Markdown 融合格式追加到文档文本中，使图片可被语义检索。

    流式内存管控（Streaming Memory Management）：
    - 使用生成器逐张提取图片，绝不全量囤积
    - 每张图处理完立即 del + gc.collect() 释放内存
    - 图片在提取阶段即降级缩放（max 1024px）

    注意：此函数通过 asyncio.to_thread() 在线程池中运行，
    因此内部使用 asyncio.run() 创建独立事件循环是安全的。
    """
    try:
        from app.services.ocr_helper import (
            iter_images_from_pdf,
            iter_images_from_docx,
            process_images_streaming,
        )

        # 选择对应的生成器
        if ext == ".pdf":
            image_iter = iter_images_from_pdf(file_path)
        elif ext == ".docx":
            image_iter = iter_images_from_docx(file_path)
        else:
            return

        # 先计数图片数量（生成器无法预知，先收集到列表再处理）
        # 注意：为避免全量囤积，改为先 peek 第一张图来确认有图片
        peek_images = []
        try:
            first_img = next(image_iter)
            peek_images.append(first_img)
        except StopIteration:
            # 无图片
            return

        # 获取 AI 客户端
        ai_client = _get_ai_client()
        base_name = os.path.splitext(filename)[0]

        # 上报视觉处理开始
        if progress_callback:
            progress_callback('VISION_PROCESSING', f'👁️ 发现核心图表，开始唤醒系统内置【多模态视觉大模型引擎】进行深度语义解读...', 18)

        # 在线程中用独立事件循环运行流式图片处理
        import asyncio
        from app.services.ocr_helper import process_images_streaming_with_peek

        caption_texts = asyncio.run(
            process_images_streaming_with_peek(peek_images, image_iter, ai_client, base_name=base_name, progress_callback=progress_callback)
        )

        if not caption_texts:
            return

        # 将图片描述追加到文档末尾
        image_section = "\n\n## 嵌入图片深度解析\n\n" + "\n\n".join(caption_texts)

        if documents:
            # 追加到最后一个文档
            documents[-1].page_content += image_section
        else:
            # 如果没有文本文档，创建一个纯图片描述文档
            documents.append(Document(
                page_content=image_section,
                metadata={"source": filename, "type": "image_captions"},
            ))

        logger.info(f"[Vision] {filename}: {len(caption_texts)} 张图片深度解析完成，已融合进文档（流式模式）")

    except Exception as e:
        logger.warning(f"[Vision] 图片深度解析失败 ({filename}): {e}")


def _extract_documents(file_path: str, filename: str, ext: str, rag_engine, progress_callback=None) -> List[Document]:
    documents = []

    if ext == ".pdf":
        # ── 逐页读取 PDF 文本（严禁全量加载） ──
        try:
            import pypdf
            reader = pypdf.PdfReader(file_path)
            for page_num in range(len(reader.pages)):
                try:
                    page = reader.pages[page_num]
                    text = page.extract_text() or ""
                    if text.strip():
                        documents.append(Document(
                            page_content=text,
                            metadata={"source": filename, "page": page_num + 1},
                        ))
                except Exception as e:
                    logger.debug(f"Failed to extract text from page {page_num + 1}: {e}")
                finally:
                    # 逐页释放
                    reader.pages[page_num] = None
            # 释放 reader
            del reader
            gc.collect()
        except Exception as e:
            logger.error(f"KB Processor: pypdf failed for {filename}: {e}")
            if progress_callback:
                progress_callback('EXTRACTING', f'⚠️ pypdf 发生结构性损坏，已自动启动底层强力容错引擎降级扫描...', 12)

        # ── 多模态图片深度解析（流式逐图） ──
        _append_image_captions_sync(documents, file_path, filename, ext, progress_callback=progress_callback)

    elif ext == ".docx":
        try:
            from app.services.docx_parser import DocxParser
            import asyncio
            parser = DocxParser()
            loop = asyncio.new_event_loop()
            try:
                html = loop.run_until_complete(parser.convert_docx_to_html(file_path))
            finally:
                loop.close()
            if html:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")
                text = soup.get_text(separator="\n", strip=True)
                if text.strip():
                    documents.append(Document(page_content=text, metadata={"source": filename}))
        except Exception:
            try:
                from langchain_community.document_loaders import Docx2txtLoader
                loader = Docx2txtLoader(file_path)
                documents = loader.load()
            except Exception as e:
                logger.error(f"KB Processor: DOCX parse failed for {filename}: {e}")

        # ── 多模态图片深度解析 ──
        _append_image_captions_sync(documents, file_path, filename, ext)

    elif ext == ".jsonl":
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        except UnicodeDecodeError:
            with open(file_path, "r", encoding="gbk", errors="ignore") as f:
                text = f.read()

        for line_idx, line in enumerate(text.strip().split("\n")):
            line = line.strip()
            if line:
                try:
                    record = json.loads(line)
                    field_parts = [f"{k}: {v}" for k, v in record.items() if v is not None and str(v).strip()]
                    page_content = " | ".join(field_parts)
                    documents.append(Document(page_content=page_content, metadata={"source": filename, "record_index": line_idx}))
                except json.JSONDecodeError:
                    continue

    elif ext in (".txt", ".md"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        except UnicodeDecodeError:
            with open(file_path, "r", encoding="gbk", errors="ignore") as f:
                text = f.read()
        if text.strip():
            documents.append(Document(page_content=text, metadata={"source": filename}))

    return documents
