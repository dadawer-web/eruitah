"""
Tour Generator —— 基于项目依赖图的代码导览路径生成器

读取 project_structure.json 中的 CALLS 边，结合用户提问，
调用大模型规划出一条结构化的代码阅读路径。

输出格式（强制 Structured Output）：
[
    {
        "step": 1,
        "file": "src/foo.py",
        "function": "handle_connection",
        "start_line": 42,
        "end_line": 67,
        "explanation": "这步做了什么..."
    },
    ...
]

使用方式：
    1. 独立运行（CLI）：
        python tour_generator.py --question "请梳理 Muduo 处理新连接的流程"
    2. 作为 Agent 工具调用：
        from tour_generator import execute_code_tour
        result, is_error = execute_code_tour(question="...", work_dir="/path/to/project")
"""

import json
import os
import sys
import re
import logging
from pathlib import Path
from typing import Optional
from collections import defaultdict

logger = logging.getLogger(__name__)

_DEFAULT_SANDBOX_DIR = os.environ.get(
    "ERUITAH_SANDBOX_DIR", str(Path(__file__).parent)
)


def _load_project_structure(work_dir: str) -> dict:
    json_path = Path(work_dir) / "project_structure.json"
    if not json_path.exists():
        raise FileNotFoundError(
            f"project_structure.json 不存在: {json_path}\n"
            f"请先运行 project_grapher.py 生成依赖图数据。"
        )
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_call_graph(data: dict) -> dict:
    nodes_by_id = {}
    for n in data.get("nodes", []):
        nodes_by_id[n["id"]] = n

    calls_edges = [e for e in data.get("edges", []) if e.get("type") == "CALLS"]
    imports_edges = [e for e in data.get("edges", []) if e.get("type") == "IMPORTS"]
    contains_edges = [e for e in data.get("edges", []) if e.get("type") == "CONTAINS"]

    adjacency = defaultdict(list)
    reverse_adj = defaultdict(list)
    for e in calls_edges:
        src, tgt = e["source"], e["target"]
        adjacency[src].append(tgt)
        reverse_adj[tgt].append(src)

    for e in imports_edges:
        src, tgt = e["source"], e["target"]
        adjacency[src].append(tgt)
        reverse_adj[tgt].append(src)

    contains_children = defaultdict(list)
    contains_parent = {}
    for e in contains_edges:
        src, tgt = e["source"], e["target"]
        contains_children[src].append(tgt)
        contains_parent[tgt] = src

    return {
        "nodes": nodes_by_id,
        "calls_edges": calls_edges,
        "imports_edges": imports_edges,
        "contains_edges": contains_edges,
        "adjacency": adjacency,
        "reverse_adj": reverse_adj,
        "contains_children": contains_children,
        "contains_parent": contains_parent,
    }


def _extract_keywords(question: str) -> list[str]:
    stop_words = {
        "的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都",
        "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你",
        "会", "着", "没有", "看", "好", "自己", "这", "他", "她", "它",
        "请", "给", "梳理", "一下", "流程", "代码", "执行", "过程",
        "讲解", "分析", "解释", "理解", "详细", "帮", "帮忙", "能",
        "可以", "什么", "怎么", "如何", "为什么", "哪", "哪个",
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "can", "shall",
        "to", "of", "in", "for", "on", "with", "at", "by", "from",
        "as", "into", "through", "during", "before", "after", "and",
        "but", "or", "not", "no", "nor", "so", "if", "then", "than",
        "that", "this", "these", "those", "it", "its",
        "please", "show", "explain", "trace", "describe", "me",
    }
    tokens = []
    for m in re.finditer(r"[a-zA-Z_]\w*", question):
        tokens.append(m.group())
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", question)
    tokens.extend(chinese_chars)
    for i in range(len(chinese_chars) - 1):
        bigram = chinese_chars[i] + chinese_chars[i + 1]
        tokens.append(bigram)
    return [t for t in tokens if t.lower() not in stop_words and len(t) > 1]


def _build_relevant_subgraph(
    question: str,
    graph: dict,
    max_nodes: int = 60,
    max_hops: int = 3,
) -> dict:
    keywords = _extract_keywords(question)
    if not keywords:
        return graph

    nodes = graph["nodes"]
    adjacency = graph["adjacency"]
    reverse_adj = graph["reverse_adj"]

    seed_ids = set()
    for nid, node in nodes.items():
        text = f"{nid} {node.get('name', '')} {node.get('file_path', '')}"
        if node.get("parent"):
            text += f" {node['parent']}"
        text_lower = text.lower()
        for kw in keywords:
            if kw.lower() in text_lower:
                seed_ids.add(nid)
                break

    if not seed_ids:
        return graph

    expanded = set(seed_ids)
    frontier = set(seed_ids)
    for _ in range(max_hops):
        next_frontier = set()
        for nid in frontier:
            for neighbor in adjacency.get(nid, []):
                if neighbor not in expanded:
                    next_frontier.add(neighbor)
            for neighbor in reverse_adj.get(nid, []):
                if neighbor not in expanded:
                    next_frontier.add(neighbor)
        expanded |= next_frontier
        frontier = next_frontier
        if len(expanded) >= max_nodes:
            break

    if len(expanded) > max_nodes:
        scored = []
        for nid in expanded:
            score = 0
            node = nodes.get(nid, {})
            text = f"{nid} {node.get('name', '')}".lower()
            for kw in keywords:
                if kw.lower() in text:
                    score += 10
            scored.append((score, nid))
        scored.sort(reverse=True)
        expanded = {nid for _, nid in scored[:max_nodes]}

    filtered_nodes = {nid: nodes[nid] for nid in expanded if nid in nodes}
    filtered_calls = [
        e for e in graph["calls_edges"]
        if e["source"] in expanded and e["target"] in expanded
    ]
    filtered_imports = [
        e for e in graph["imports_edges"]
        if e["source"] in expanded and e["target"] in expanded
    ]

    return {
        "nodes": filtered_nodes,
        "calls_edges": filtered_calls,
        "imports_edges": filtered_imports,
        "contains_edges": graph["contains_edges"],
        "adjacency": {k: [v for v in vs if v in expanded] for k, vs in adjacency.items() if k in expanded},
        "reverse_adj": {k: [v for v in vs if v in expanded] for k, vs in reverse_adj.items() if k in expanded},
    }


def _format_graph_context(subgraph: dict) -> str:
    nodes = subgraph["nodes"]
    calls_edges = subgraph["calls_edges"]
    imports_edges = subgraph["imports_edges"]

    lines = ["=== 项目依赖图上下文 ===\n"]

    lines.append("【节点列表】")
    for nid, node in sorted(nodes.items()):
        ntype = node.get("type", "?")
        name = node.get("name", "?")
        fpath = node.get("file_path", "?")
        start = node.get("line", "?")
        end = node.get("end_line", "?")
        parent = node.get("parent", "")
        params = node.get("params", [])
        ret = node.get("return_type", "")

        if ntype == "File":
            lines.append(f"  [{ntype}] {nid}  (path: {fpath})")
        elif ntype == "Class":
            lines.append(f"  [{ntype}] {nid}  (file: {fpath}, lines: {start}-{end})")
        else:
            param_str = ", ".join(params) if params else ""
            sig = f"({param_str})"
            if ret:
                sig += f" -> {ret}"
            parent_info = f"  class: {parent}" if parent else ""
            lines.append(
                f"  [{ntype}] {nid}{parent_info}  "
                f"(file: {fpath}, lines: {start}-{end})  signature: {sig}"
            )

    if calls_edges:
        lines.append(f"\n【CALLS 边（共 {len(calls_edges)} 条）— 函数调用关系】")
        for e in calls_edges:
            lines.append(f"  {e['source']}  --CALLS-->  {e['target']}")

    if imports_edges:
        lines.append(f"\n【IMPORTS 边（共 {len(imports_edges)} 条）— 文件导入关系】")
        for e in imports_edges:
            lines.append(f"  {e['source']}  --IMPORTS-->  {e['target']}")

    if not calls_edges and not imports_edges:
        lines.append("\n【注意】当前项目没有 CALLS 或 IMPORTS 边，请根据节点信息推断调用关系。")

    return "\n".join(lines)


def _build_prompt(question: str, graph_context: str) -> list[dict]:
    system_prompt = """你是一位资深的代码架构讲解专家。你的任务是根据项目的依赖图（CALLS 调用边、IMPORTS 导入边），为用户规划一条清晰的代码阅读路径（导览 Tour）。

## 输入
- 用户的问题（关于某段代码执行流程、某个功能的实现路径等）
- 项目的依赖图上下文（节点列表 + CALLS 边 + IMPORTS 边）

## 你的工作
1. 分析用户问题，确定需要追踪的代码执行流程
2. 优先沿着 CALLS 边追踪调用链；若 CALLS 边不足，则结合 IMPORTS 边和函数名/参数签名推断调用关系
3. 规划出一条合理的阅读路径，每一步对应一个函数/方法

## 强制输出格式
你必须输出一个 JSON 数组，每个元素包含以下字段：
```json
[
    {
        "step": 1,
        "file": "src/foo.py",
        "function": "handle_connection",
        "start_line": 42,
        "end_line": 67,
        "explanation": "这步做了什么..."
    }
]
```

字段说明：
- step: 步骤序号（从 1 开始递增）
- file: 文件路径（使用节点 ID 中的相对路径部分）
- function: 函数或方法名
- start_line: 函数起始行号（整数）
- end_line: 函数结束行号（整数）
- explanation: 用中文解释这步做了什么，在整体流程中的作用

## 规则
1. 只输出 JSON 数组，不要输出任何其他文字
2. 路径应沿着 CALLS 边的调用关系，步骤之间要有逻辑上的调用/被调用关系；当 CALLS 边不足时，根据 IMPORTS 边和函数签名推断合理的调用链
3. 每一步的 file、function、start_line、end_line 必须与依赖图中的节点信息一致
4. explanation 要简洁明了，说明这步在整体流程中的角色
5. 如果存在分支（如条件判断后走不同路径），在 explanation 中说明
6. 步骤数量控制在 5-20 步之间，聚焦核心流程"""

    user_prompt = f"""## 用户问题
{question}

## 项目依赖图上下文
{graph_context}

请根据以上依赖图信息，规划一条代码阅读路径。只输出 JSON 数组。"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _call_llm(
    messages: list[dict],
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    provider: str = "openai",
) -> str:
    api_key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
    model = model or os.environ.get("ERUITAH_TOUR_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-4o"
    base_url = base_url or os.environ.get("OPENAI_BASE_URL", "")
    provider = provider or os.environ.get("ERUITAH_API_PROVIDER", "openai")

    if not api_key:
        raise ValueError(
            "未找到 API Key。请设置环境变量 OPENAI_API_KEY 或 ANTHROPIC_API_KEY，"
            "或在调用时传入 api_key 参数。"
        )

    if provider == "anthropic":
        return _call_anthropic(messages, api_key, model, base_url)
    else:
        return _call_openai(messages, api_key, model, base_url)


def _call_openai(
    messages: list[dict],
    api_key: str,
    model: str,
    base_url: str,
) -> str:
    from openai import OpenAI

    client_kwargs = {"api_key": api_key}
    if base_url:
        if not base_url.endswith("/v1"):
            base_url = base_url.rstrip("/") + "/v1"
        client_kwargs["base_url"] = base_url

    client = OpenAI(**client_kwargs)

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=4096,
        temperature=0.2,
    )

    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("LLM 返回了空内容")
    return content


def _call_anthropic(
    messages: list[dict],
    api_key: str,
    model: str,
    base_url: str,
) -> str:
    import anthropic

    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url

    client = anthropic.Anthropic(**client_kwargs)

    system_msg = ""
    user_messages = []
    for m in messages:
        if m["role"] == "system":
            system_msg += m["content"] + "\n"
        else:
            user_messages.append(m)

    if not user_messages:
        user_messages = [{"role": "user", "content": "请开始"}]

    actual_model = model
    if not any(actual_model.startswith(p) for p in ("claude-", "claude_")):
        actual_model = "claude-sonnet-4-20250514"

    response = client.messages.create(
        model=actual_model,
        max_tokens=4096,
        system=system_msg.strip(),
        messages=user_messages,
        temperature=0.2,
    )

    content = ""
    for block in response.content:
        if block.type == "text":
            content += block.text
    if not content:
        raise RuntimeError("LLM 返回了空内容")
    return content


def _parse_tour_result(raw: str, work_dir: str = "") -> list[dict]:
    json_str = raw.strip()

    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", json_str, re.DOTALL)
    if fence_match:
        json_str = fence_match.group(1).strip()

    try:
        result = json.loads(json_str)
    except json.JSONDecodeError:
        bracket_start = json_str.find("[")
        bracket_end = json_str.rfind("]")
        if bracket_start != -1 and bracket_end != -1 and bracket_end > bracket_start:
            try:
                result = json.loads(json_str[bracket_start:bracket_end + 1])
            except json.JSONDecodeError:
                raise ValueError(f"无法解析 LLM 输出为 JSON 数组。原始输出:\n{raw}")
        else:
            raise ValueError(f"无法解析 LLM 输出为 JSON 数组。原始输出:\n{raw}")

    if not isinstance(result, list):
        raise ValueError(f"LLM 输出不是 JSON 数组，而是 {type(result).__name__}")

    required_fields = {"step", "file", "function", "start_line", "end_line", "explanation"}
    validated = []
    for i, item in enumerate(result):
        if not isinstance(item, dict):
            raise ValueError(f"第 {i + 1} 个元素不是对象: {item}")
        missing = required_fields - set(item.keys())
        if missing:
            raise ValueError(f"第 {i + 1} 个元素缺少字段: {missing}")
        item["step"] = int(item["step"])
        item["start_line"] = int(item["start_line"])
        item["end_line"] = int(item["end_line"])

        if work_dir and item.get("file"):
            file_path = item["file"]
            abs_work_dir = os.path.abspath(work_dir)
            abs_file = os.path.abspath(os.path.join(abs_work_dir, file_path)) if not os.path.isabs(file_path) else file_path
            if abs_file.startswith(abs_work_dir + os.sep) or abs_file.startswith(abs_work_dir + "/"):
                item["file"] = os.path.relpath(abs_file, abs_work_dir)
            elif file_path.startswith(abs_work_dir):
                item["file"] = os.path.relpath(file_path, abs_work_dir)

        validated.append(item)

    validated.sort(key=lambda x: x["step"])
    for i, item in enumerate(validated):
        item["step"] = i + 1

    return validated


def generate_code_tour(
    question: str,
    work_dir: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    provider: str = "openai",
    max_subgraph_nodes: int = 60,
) -> list[dict]:
    work_dir = work_dir or _DEFAULT_SANDBOX_DIR

    data = _load_project_structure(work_dir)
    graph = _build_call_graph(data)
    subgraph = _build_relevant_subgraph(question, graph, max_nodes=max_subgraph_nodes)
    graph_context = _format_graph_context(subgraph)
    messages = _build_prompt(question, graph_context)

    logger.info(f"调用 LLM 生成导览路径，问题: {question[:80]}...")
    raw = _call_llm(messages, api_key=api_key, model=model, base_url=base_url, provider=provider)

    tour = _parse_tour_result(raw, work_dir=work_dir)
    logger.info(f"导览路径生成成功，共 {len(tour)} 步")
    return tour


def execute_code_tour(
    question: str,
    context: str = "",
    work_dir: str = "",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    provider: str = "openai",
) -> tuple[str, bool]:
    try:
        if not question or not question.strip():
            return "问题不能为空", True

        actual_work_dir = work_dir or _DEFAULT_SANDBOX_DIR

        enhanced_question = question.strip()
        if context and context.strip():
            enhanced_question = f"{question.strip()}\n\n补充背景：{context.strip()}"

        tour = generate_code_tour(
            question=enhanced_question,
            work_dir=actual_work_dir,
            api_key=api_key,
            model=model,
            base_url=base_url,
            provider=provider,
        )

        result_json = json.dumps(tour, ensure_ascii=False, indent=2)

        summary_lines = [f"✅ 代码导览路径生成成功（共 {len(tour)} 步）\n"]
        for step in tour:
            summary_lines.append(
                f"  Step {step['step']}: {step['file']}::{step['function']} "
                f"(L{step['start_line']}-L{step['end_line']}) — {step['explanation']}"
            )
        summary_lines.append(f"\n完整 JSON:\n{result_json}")

        return "\n".join(summary_lines), False

    except FileNotFoundError as e:
        return str(e), True
    except ValueError as e:
        return f"导览路径解析失败: {str(e)}", True
    except Exception as e:
        logger.error(f"代码导览生成异常: {e}", exc_info=True)
        return f"代码导览生成异常: {str(e)}", True


CODE_TOUR_TOOL_DEFINITION_OPENAI = {
    "type": "function",
    "function": {
        "name": "code_tour",
        "description": (
            "这是系统内唯一的讲解工具。调用此工具即可一键完成全套复习和导览生成，绝对禁止尝试自己用其他方式完成。"
            "当用户要求你复习、讲解、梳理、分析任何代码结构、设计模式、执行流程、模块实现时，"
            "你必须且只能调用此工具！它会自动结合本地项目依赖图生成多步导览路径。"
            "绝对禁止用自然语言直接解释，绝对禁止用 bash/file_edit 自己写教程代码！"
            "适用场景：'复习 Reactor 模式'、'梳理新连接处理流程'、'讲解线程池实现'、'分析 HTTP 请求链路'。"
            "返回结构化导览路径，前端会自动展示为互动播放器。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "用户关于代码流程的问题，如 '请梳理新连接的处理流程' 或 'HTTP 请求的完整处理链路'",
                },
                "context": {
                    "type": "string",
                    "description": "如果你有关于这个概念的背景知识想要补充（如设计模式原理、架构思路等），可以写在这里，系统会将其融入导览生成。这满足你的表达需求，无需在回复中额外解释。",
                },
                "work_dir": {
                    "type": "string",
                    "description": "项目工作目录路径（包含 project_structure.json 的目录），默认为沙盒目录",
                },
                "provider": {
                    "type": "string",
                    "description": "LLM 提供商: 'openai' 或 'anthropic'，默认 'openai'",
                    "enum": ["openai", "anthropic"],
                },
                "model": {
                    "type": "string",
                    "description": "指定 LLM 模型名称（可选，默认使用环境变量配置的模型）",
                },
            },
            "required": ["question"],
        },
    },
}

CODE_TOUR_TOOL_DEFINITION_ANTHROPIC = {
    "name": "code_tour",
    "description": (
        "这是系统内唯一的讲解工具。调用此工具即可一键完成全套复习和导览生成，绝对禁止尝试自己用其他方式完成。"
        "当用户要求你复习、讲解、梳理、分析任何代码结构、设计模式、执行流程、模块实现时，"
        "你必须且只能调用此工具！它会自动结合本地项目依赖图生成多步导览路径。"
        "绝对禁止用自然语言直接解释，绝对禁止用 bash/file_edit 自己写教程代码！"
        "适用场景：'复习 Reactor 模式'、'梳理新连接处理流程'、'讲解线程池实现'、'分析 HTTP 请求链路'。"
        "返回结构化导览路径，前端会自动展示为互动播放器。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "用户关于代码流程的问题，如 '请梳理新连接的处理流程' 或 'HTTP 请求的完整处理链路'",
            },
            "context": {
                "type": "string",
                "description": "如果你有关于这个概念的背景知识想要补充（如设计模式原理、架构思路等），可以写在这里，系统会将其融入导览生成。这满足你的表达需求，无需在回复中额外解释。",
            },
            "work_dir": {
                "type": "string",
                "description": "项目工作目录路径（包含 project_structure.json 的目录），默认为沙盒目录",
            },
            "provider": {
                "type": "string",
                "description": "LLM 提供商: 'openai' 或 'anthropic'，默认 'openai'",
                "enum": ["openai", "anthropic"],
            },
            "model": {
                "type": "string",
                "description": "指定 LLM 模型名称（可选，默认使用环境变量配置的模型）",
            },
        },
        "required": ["question"],
    },
}


if __name__ == "__main__":
    import argparse

    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
    except ImportError:
        pass

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="代码导览路径生成器")
    parser.add_argument(
        "--question", "-q",
        type=str,
        required=True,
        help="用户关于代码流程的问题",
    )
    parser.add_argument(
        "--work-dir", "-w",
        type=str,
        default=_DEFAULT_SANDBOX_DIR,
        help="项目工作目录（包含 project_structure.json）",
    )
    parser.add_argument(
        "--provider", "-p",
        type=str,
        default=os.environ.get("ERUITAH_API_PROVIDER", "openai"),
        choices=["openai", "anthropic"],
        help="LLM 提供商",
    )
    parser.add_argument(
        "--model", "-m",
        type=str,
        default=None,
        help="LLM 模型名称",
    )
    parser.add_argument(
        "--base-url", "-b",
        type=str,
        default=None,
        help="API Base URL",
    )
    parser.add_argument(
        "--api-key", "-k",
        type=str,
        default=None,
        help="API Key（优先使用环境变量 OPENAI_API_KEY / ANTHROPIC_API_KEY）",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="只输出原始 JSON 数组，不附加摘要",
    )

    args = parser.parse_args()

    try:
        tour = generate_code_tour(
            question=args.question,
            work_dir=args.work_dir,
            api_key=args.api_key,
            model=args.model,
            base_url=args.base_url,
            provider=args.provider,
        )

        if args.raw:
            print(json.dumps(tour, ensure_ascii=False, indent=2))
        else:
            print(f"\n🗺️  代码导览路径（共 {len(tour)} 步）")
            print("=" * 70)
            for step in tour:
                print(
                    f"\n  Step {step['step']}: "
                    f"{step['file']}::{step['function']} "
                    f"(L{step['start_line']}-L{step['end_line']})"
                )
                print(f"    💡 {step['explanation']}")
            print("\n" + "=" * 70)
            print("\n📄 完整 JSON 输出:")
            print(json.dumps(tour, ensure_ascii=False, indent=2))

    except FileNotFoundError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"❌ 解析失败: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ 异常: {e}", file=sys.stderr)
        sys.exit(1)
