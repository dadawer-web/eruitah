"""
Eruitah 智能编程沙盒 - 图谱上下文认知工具

参考 Understand-Anything 的上下文剪裁理念:
  不让大模型读取整个源码文件来理解架构，而是基于 AST 图谱做精准的图论关系检索，
  只返回目标节点在系统中的架构位置和上下游依赖关系，大幅降低 Token 消耗。

核心能力:
  ┌──────────────────────────────────────────────────────────────────┐
  │  输入: target_node_name (如 "UserService", "auth.py")           │
  │                                                                  │
  │  1. 读取 project_structure.json 图谱                             │
  │  2. 模糊匹配找到目标 Node ID                                     │
  │  3. 遍历 edges，检索上游调用者 (In-edges) 和下游依赖 (Out-edges)  │
  │  4. 生成精简结构化文本返回给大模型                                │
  │                                                                  │
  │  输出格式:                                                       │
  │    [节点]: UserService                                           │
  │    [分层]: business                                              │
  │    [被谁调用 (上游)]: UserController (api层)                      │
  │    [调用了谁 (下游)]: UserRepository (data层), RedisUtil (infra层)│
  └──────────────────────────────────────────────────────────────────┘
"""

import json
import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _find_graph_file(work_dir: str) -> Optional[str]:
    """查找工作区下的 project_structure.json"""
    candidates = [
        os.path.join(work_dir, "project_structure.json"),
        os.path.join(work_dir, ".eruitah_cache", "project_structure.json"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def _load_graph(work_dir: str) -> Optional[dict]:
    """加载图谱 JSON"""
    graph_path = _find_graph_file(work_dir)
    if not graph_path:
        return None
    try:
        with open(graph_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"读取图谱文件失败: {e}")
        return None


def _fuzzy_match_nodes(nodes: list, target_name: str) -> list[dict]:
    """
    模糊匹配节点，返回按相关度排序的候选列表。
    匹配策略:
      1. 精确匹配 name 字段
      2. 精确匹配 id 字段
      3. name 包含 target_name
      4. id 包含 target_name
      5. target_name 包含 name
    """
    target_lower = target_name.lower().strip()
    if not target_lower:
        return []

    exact_name = []
    exact_id = []
    contains_name = []
    contains_id = []
    name_contains_target = []

    for node in nodes:
        name = (node.get("name") or "").lower()
        node_id = (node.get("id") or "").lower()

        if name == target_lower:
            exact_name.append(node)
        elif node_id == target_lower:
            exact_id.append(node)
        elif target_lower in name:
            contains_name.append(node)
        elif target_lower in node_id:
            contains_id.append(node)
        elif name and name in target_lower:
            name_contains_target.append(node)

    # 按优先级合并，去重
    seen = set()
    result = []
    for bucket in [exact_name, exact_id, contains_name, contains_id, name_contains_target]:
        for node in bucket:
            nid = node.get("id", "")
            if nid not in seen:
                seen.add(nid)
                result.append(node)

    return result


def _build_node_index(nodes: list) -> dict:
    """构建 node_id → node 的索引"""
    return {n["id"]: n for n in nodes if "id" in n}


def _get_layer_label(layer_id: str, graph_data: dict) -> str:
    """获取分层的中文标签"""
    layers = graph_data.get("layers", [])
    for layer in layers:
        if layer.get("id") == layer_id:
            return layer.get("name", layer_id)
    return layer_id


def _find_upstream(node_id: str, edges: list, node_index: dict, graph_data: dict) -> list[str]:
    """
    找上游调用者：谁指向了当前节点（In-edges）。
    即 edges 中 target == node_id 的边的 source 节点。
    """
    upstream = []
    for edge in edges:
        if edge.get("target") == node_id:
            source_id = edge.get("source", "")
            source_node = node_index.get(source_id)
            edge_type = edge.get("type", "")
            if source_node:
                layer = source_node.get("layer", "unknown")
                layer_label = _get_layer_label(layer, graph_data)
                name = source_node.get("name", source_id)
                upstream.append(f"{name} ({layer_label}层, {edge_type})")
            else:
                upstream.append(f"{source_id} ({edge_type})")
    return upstream


def _find_downstream(node_id: str, edges: list, node_index: dict, graph_data: dict) -> list[str]:
    """
    找下游依赖项：当前节点指向了谁（Out-edges）。
    即 edges 中 source == node_id 的边的 target 节点。
    """
    downstream = []
    for edge in edges:
        if edge.get("source") == node_id:
            target_id = edge.get("target", "")
            target_node = node_index.get(target_id)
            edge_type = edge.get("type", "")
            if target_node:
                layer = target_node.get("layer", "unknown")
                layer_label = _get_layer_label(layer, graph_data)
                name = target_node.get("name", target_id)
                downstream.append(f"{name} ({layer_label}层, {edge_type})")
            else:
                downstream.append(f"{target_id} ({edge_type})")
    return downstream


def get_graph_context(target_node_name: str, work_dir: str = "") -> tuple[str, bool]:
    """
    基于项目图谱获取目标节点的架构上下文。

    Args:
        target_node_name: 目标节点名称（类名、函数名、文件名等）
        work_dir: 工作目录

    Returns:
        (结果文本, 是否出错)
    """
    if not target_node_name:
        return "错误: target_node_name 不能为空", True

    if not work_dir:
        work_dir = os.getcwd()

    # 1. 加载图谱
    graph_data = _load_graph(work_dir)
    if not graph_data:
        return (
            "未找到项目图谱 (project_structure.json)。"
            "请先使用 '解析项目架构' 功能生成图谱，然后再调用此工具。",
            True,
        )

    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])

    if not nodes:
        return "图谱中没有节点数据", True

    # 2. 模糊匹配
    matched = _fuzzy_match_nodes(nodes, target_node_name)

    if not matched:
        # 给出一些可用的节点名提示
        sample_names = [n.get("name", n.get("id", "")) for n in nodes[:20]]
        return (
            f"未找到匹配 '{target_node_name}' 的节点。\n"
            f"图谱中共有 {len(nodes)} 个节点，部分节点名称: {', '.join(sample_names)}...\n"
            f"提示: 尝试使用更精确的名称，如类名、函数名或文件名。",
            True,
        )

    # 3. 构建索引和检索关系
    node_index = _build_node_index(nodes)

    # 如果匹配到多个，取最相关的（第一个），但列出其他候选
    primary = matched[0]
    primary_id = primary.get("id", "")

    layer = primary.get("layer", "unknown")
    layer_label = _get_layer_label(layer, graph_data)
    node_type = primary.get("type", "unknown")
    file_path = primary.get("file_path", "")

    upstream = _find_upstream(primary_id, edges, node_index, graph_data)
    downstream = _find_downstream(primary_id, edges, node_index, graph_data)

    # 4. 生成结构化文本
    lines = []
    lines.append(f"[节点]: {primary.get('name', primary_id)}")
    lines.append(f"[ID]: {primary_id}")
    lines.append(f"[类型]: {node_type}")
    lines.append(f"[分层]: {layer_label} ({layer}层)")

    if file_path:
        lines.append(f"[文件]: {file_path}")

    # Diff 状态
    diff_status = primary.get("diff_status")
    if diff_status:
        lines.append(f"[变更状态]: {diff_status}")

    if upstream:
        lines.append(f"[被谁调用 (上游)]: {', '.join(upstream)}")
    else:
        lines.append("[被谁调用 (上游)]: 无 (顶层节点)")

    if downstream:
        lines.append(f"[调用了谁 (下游)]: {', '.join(downstream)}")
    else:
        lines.append("[调用了谁 (下游)]: 无 (叶子节点)")

    # 如果有多个匹配，列出其他候选
    if len(matched) > 1:
        lines.append("")
        lines.append(f"[其他匹配节点]: 共 {len(matched)} 个匹配")
        for m in matched[1:6]:  # 最多显示 5 个额外候选
            mid = m.get("id", "")
            mname = m.get("name", mid)
            mlayer = _get_layer_label(m.get("layer", "unknown"), graph_data)
            lines.append(f"  - {mname} ({mlayer}层) [{mid}]")
        if len(matched) > 6:
            lines.append(f"  ... 还有 {len(matched) - 6} 个匹配")

    # 统计信息
    lines.append("")
    lines.append(f"[图谱统计]: {len(nodes)} 节点, {len(edges)} 边")

    result = "\n".join(lines)
    logger.info(f"📊 图谱上下文查询: '{target_node_name}' → 匹配 {len(matched)} 个节点, "
                f"上游 {len(upstream)}, 下游 {len(downstream)}")

    return result, False


# ══════════════════════════════════════════════════════════
# 工具 Schema 定义 (OpenAI + Anthropic 双格式)
# ══════════════════════════════════════════════════════════

GRAPH_CONTEXT_TOOL_DEFINITION_OPENAI = {
    "type": "function",
    "function": {
        "name": "get_graph_context",
        "description": (
            "基于项目代码图谱获取目标节点的架构上下文和依赖关系。"
            "输入一个类名、函数名或文件名，返回它在系统中的分层位置、谁调用了它（上游）、"
            "它调用了谁（下游）等结构化信息。"
            "当你需要理解某个模块在整个系统中的架构位置和依赖关系时，"
            "优先调用此工具，而不是直接读取源码全文——它能用极少的 Token 让你快速建立认知。"
            "特别适合: 理解陌生代码架构、定位修改影响范围、追踪调用链。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "target_node_name": {
                    "type": "string",
                    "description": (
                        "目标节点名称，可以是类名(如 UserService)、"
                        "函数名(如 handle_login)、文件名(如 auth.py) 或模块路径。"
                        "支持模糊匹配。"
                    ),
                },
            },
            "required": ["target_node_name"],
        },
    },
}

GRAPH_CONTEXT_TOOL_DEFINITION_ANTHROPIC = {
    "name": "get_graph_context",
    "description": (
        "基于项目代码图谱获取目标节点的架构上下文和依赖关系。"
        "输入一个类名、函数名或文件名，返回它在系统中的分层位置、谁调用了它（上游）、"
        "它调用了谁（下游）等结构化信息。"
        "当你需要理解某个模块在整个系统中的架构位置和依赖关系时，"
        "优先调用此工具，而不是直接读取源码全文——它能用极少的 Token 让你快速建立认知。"
        "特别适合: 理解陌生代码架构、定位修改影响范围、追踪调用链。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "target_node_name": {
                "type": "string",
                "description": (
                    "目标节点名称，可以是类名(如 UserService)、"
                    "函数名(如 handle_login)、文件名(如 auth.py) 或模块路径。"
                    "支持模糊匹配。"
                ),
            },
        },
        "required": ["target_node_name"],
    },
}
