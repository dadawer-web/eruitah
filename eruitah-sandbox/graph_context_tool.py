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
import sqlite3
from collections import deque
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
# 爆炸半径分析 (Blast Radius Analysis)
# ══════════════════════════════════════════════════════════

def _find_db_path(work_dir: str) -> Optional[str]:
    """查找工作区下的 SQLite 图谱数据库"""
    db_path = os.path.join(work_dir, ".eruitah_cache", "codegraph.db")
    if os.path.isfile(db_path):
        return db_path
    return None


def analyze_blast_radius(symbol_name: str, work_dir: str = "") -> tuple[str, bool]:
    """
    分析目标符号的爆炸半径：递归查找所有下游调用者，评估修改该符号的影响面。

    通过 BFS 遍历 edges 表，找出直接下游 (1-hop) 和间接下游 (2-hop+)，
    并根据被依赖的文件数量计算风险等级。

    Args:
        symbol_name: 目标符号名称（类名、函数名等）
        work_dir: 工作目录

    Returns:
        (结果文本, 是否出错)
    """
    if not symbol_name:
        return "错误: symbol_name 不能为空", True

    if not work_dir:
        work_dir = os.getcwd()

    # 1. 查找数据库
    db_path = _find_db_path(work_dir)
    if not db_path:
        # 降级到 JSON 图谱
        graph_data = _load_graph(work_dir)
        if not graph_data:
            return (
                "未找到项目图谱数据库 (codegraph.db) 或 JSON 图谱。"
                "请先使用 '解析项目架构' 功能生成图谱。",
                True,
            )
        return _analyze_blast_radius_from_json(symbol_name, graph_data)

    # 2. 从 SQLite 查询
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    except Exception as e:
        return f"无法连接图谱数据库: {e}", True

    try:
        # 模糊匹配找到目标节点
        target_rows = conn.execute(
            "SELECT id, name, file_path, layer FROM nodes WHERE name LIKE ? OR id LIKE ? LIMIT 20",
            (f"%{symbol_name}%", f"%{symbol_name}%"),
        ).fetchall()

        if not target_rows:
            sample = conn.execute("SELECT name FROM nodes LIMIT 20").fetchall()
            sample_names = [r["name"] for r in sample if r["name"]]
            conn.close()
            return (
                f"未找到匹配 '{symbol_name}' 的节点。\n"
                f"部分节点名称: {', '.join(sample_names)}...",
                True,
            )

        # 取最佳匹配：优先精确匹配 name，其次精确匹配 id，最后取第一个
        primary = None
        for row in target_rows:
            if row["name"] and row["name"].lower() == symbol_name.lower():
                primary = row
                break
            if row["id"] and row["id"].lower() == symbol_name.lower():
                primary = row
                break
        if not primary:
            primary = target_rows[0]

        target_id = primary["id"]

        # 3. WITH RECURSIVE 递归查询所有依赖节点
        # 从 target_id 出发，反向查找 edges 中 target == current 的 source（谁依赖了它）
        # 递归向上溯源，记录深度(hop)，区分直接依赖和间接依赖
        recursive_sql = """
            WITH RECURSIVE dependency_chain AS (
                -- 基础查询：直接依赖（1-hop）
                SELECT
                    e.source AS node_id,
                    e.type AS edge_type,
                    1 AS hop
                FROM edges e
                WHERE e.target = ?

                UNION ALL

                -- 递归查询：间接依赖（2-hop 及以上）
                SELECT
                    e.source AS node_id,
                    e.type AS edge_type,
                    dc.hop + 1 AS hop
                FROM edges e
                INNER JOIN dependency_chain dc ON e.target = dc.node_id
                WHERE dc.hop < 10
            )
            SELECT
                dc.node_id,
                dc.edge_type,
                dc.hop,
                n.name,
                n.file_path,
                n.layer
            FROM dependency_chain dc
            LEFT JOIN nodes n ON dc.node_id = n.id
            ORDER BY dc.hop, dc.node_id
        """
        chain_rows = conn.execute(recursive_sql, (target_id,)).fetchall()
        conn.close()

        # 去重（WITH RECURSIVE 可能产生重复路径，保留最短 hop）
        seen_ids = set()
        downstream_by_hop = {}
        all_affected_files = set()

        for row in chain_rows:
            dep_id = row["node_id"]
            if dep_id in seen_ids:
                continue
            seen_ids.add(dep_id)

            hop = row["hop"]
            entry = {
                "id": dep_id,
                "name": row["name"] or dep_id,
                "file_path": row["file_path"] or "",
                "edge_type": row["edge_type"],
            }

            downstream_by_hop.setdefault(hop, []).append(entry)
            if entry["file_path"]:
                all_affected_files.add(entry["file_path"])

        # 4. 计算风险等级
        file_count = len(all_affected_files)
        if file_count > 5:
            risk_level = "High Risk"
        elif file_count >= 2:
            risk_level = "Medium Risk"
        elif file_count == 1:
            risk_level = "Low Risk"
        else:
            risk_level = "No Dependency"

        # 5. 生成结构化结果
        lines = []
        lines.append(f"[爆炸半径分析] {primary['name'] or target_id}")
        lines.append(f"[节点ID]: {target_id}")
        if primary["file_path"]:
            lines.append(f"[所在文件]: {primary['file_path']}")
        lines.append(f"[风险等级]: {risk_level} (影响 {file_count} 个文件)")
        lines.append("")

        for hop in sorted(downstream_by_hop.keys()):
            entries = downstream_by_hop[hop]
            hop_label = "直接下游 (1-hop)" if hop == 1 else f"间接下游 ({hop}-hop)"
            lines.append(f"[{hop_label}]: {len(entries)} 个节点")
            for e in entries:
                fp = f" → {e['file_path']}" if e["file_path"] else ""
                lines.append(f"  - {e['name']} ({e['edge_type']}){fp}")

        if not downstream_by_hop:
            lines.append("[下游依赖]: 无 (叶子节点，修改影响面极小)")

        # 汇总
        total_affected = sum(len(v) for v in downstream_by_hop.values())
        lines.append("")
        lines.append(f"[汇总]: 共 {total_affected} 个下游节点, {file_count} 个受影响文件, 风险等级: {risk_level}")

        result = "\n".join(lines)
        logger.info(f"爆炸半径分析: '{symbol_name}' → {total_affected} 下游, {file_count} 文件, {risk_level}")

        return result, False

    except Exception as e:
        conn.close()
        return f"爆炸半径分析失败: {e}", True


def _analyze_blast_radius_from_json(symbol_name: str, graph_data: dict) -> tuple[str, bool]:
    """降级：从 JSON 图谱执行爆炸半径分析"""
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])

    if not nodes:
        return "图谱中没有节点数据", True

    matched = _fuzzy_match_nodes(nodes, symbol_name)
    if not matched:
        sample_names = [n.get("name", n.get("id", "")) for n in nodes[:20]]
        return (
            f"未找到匹配 '{symbol_name}' 的节点。\n"
            f"部分节点名称: {', '.join(sample_names)}...",
            True,
        )

    primary = matched[0]
    target_id = primary.get("id", "")
    node_index = _build_node_index(nodes)

    # BFS
    visited = set()
    queue = deque([(target_id, 0)])
    visited.add(target_id)
    downstream_by_hop = {}
    all_affected_files = set()

    while queue:
        current_id, hop = queue.popleft()
        for edge in edges:
            if edge.get("target") != current_id:
                continue
            dep_id = edge.get("source", "")
            if dep_id in visited:
                continue
            visited.add(dep_id)

            next_hop = hop + 1
            dep_node = node_index.get(dep_id, {})
            entry = {
                "name": dep_node.get("name", dep_id),
                "file_path": dep_node.get("file_path", ""),
                "edge_type": edge.get("type", ""),
            }
            downstream_by_hop.setdefault(next_hop, []).append(entry)
            if entry["file_path"]:
                all_affected_files.add(entry["file_path"])
            queue.append((dep_id, next_hop))

    file_count = len(all_affected_files)
    if file_count > 5:
        risk_level = "High Risk"
    elif file_count >= 2:
        risk_level = "Medium Risk"
    elif file_count == 1:
        risk_level = "Low Risk"
    else:
        risk_level = "No Dependency"

    lines = []
    lines.append(f"[爆炸半径分析] {primary.get('name', target_id)}")
    lines.append(f"[节点ID]: {target_id}")
    if primary.get("file_path"):
        lines.append(f"[所在文件]: {primary['file_path']}")
    lines.append(f"[风险等级]: {risk_level} (影响 {file_count} 个文件)")
    lines.append("")

    for hop in sorted(downstream_by_hop.keys()):
        entries = downstream_by_hop[hop]
        hop_label = "直接下游 (1-hop)" if hop == 1 else f"间接下游 ({hop}-hop)"
        lines.append(f"[{hop_label}]: {len(entries)} 个节点")
        for e in entries:
            fp = f" → {e['file_path']}" if e["file_path"] else ""
            lines.append(f"  - {e['name']} ({e['edge_type']}){fp}")

    if not downstream_by_hop:
        lines.append("[下游依赖]: 无 (叶子节点，修改影响面极小)")

    total_affected = sum(len(v) for v in downstream_by_hop.values())
    lines.append("")
    lines.append(f"[汇总]: 共 {total_affected} 个下游节点, {file_count} 个受影响文件, 风险等级: {risk_level}")

    result = "\n".join(lines)
    logger.info(f"爆炸半径分析(JSON): '{symbol_name}' → {total_affected} 下游, {file_count} 文件, {risk_level}")

    return result, False


# ══════════════════════════════════════════════════════════
# 执行流追踪 (Execution Flow Tracing)
# ══════════════════════════════════════════════════════════

# 执行流边类型：顺着这些类型的边向下追踪
_FLOW_EDGE_TYPES = {"CALLS", "routes_to", "symbol_call"}

# 认识论边界：这些路径/名称模式表示外部依赖，不应继续向下遍历
_EXTERNAL_PATH_PATTERNS = {
    "node_modules", "vendor", "third_party", "external",
    "/usr/include", "/usr/lib", "/usr/local/",
    "site-packages", "dist-packages",
}
_EXTERNAL_NAME_PREFIXES = {
    "std::", "boost::", "google::", "grpc::", "protobuf::",
    "java.", "javax.", "sun.", "com.google.", "org.apache.",
    "org.springframework.", "io.netty.", "react.", "vue.",
    "numpy.", "pandas.", "django.", "flask.", "fastapi.",
    "sqlalchemy.", "requests.", "httpx.", "aiohttp.",
}


def _is_boundary_node(node_info: dict) -> bool:
    """
    认识论边界检测：判断节点是否属于外部库/系统调用/其他微服务。

    边界判断依据：
    1. 文件路径包含第三方库路径（node_modules, vendor, site-packages 等）
    2. 符号名以已知外部库前缀开头（std::, java., org.apache. 等）
    3. layer 为 infrastructure 且文件路径不在项目内
    """
    name = node_info.get("name", "")
    file_path = node_info.get("file_path", "")

    # 检查名称前缀
    for prefix in _EXTERNAL_NAME_PREFIXES:
        if name.startswith(prefix):
            return True

    # 检查文件路径
    for pattern in _EXTERNAL_PATH_PATTERNS:
        if pattern in file_path:
            return True

    # 检查是否为系统头文件
    if file_path.startswith("/") and "include" in file_path and not file_path.startswith("/home/"):
        return True

    return False


def _trace_flow_from_db(entry_id: str, max_depth: int, conn) -> dict:
    """从 SQLite 数据库追踪执行流，返回调用树结构（含边界检测）"""
    # BFS 遍历
    visited = set()
    queue = deque([(entry_id, 0)])
    visited.add(entry_id)

    # 调用树: {node_id: {"node": {...}, "children": [node_id, ...], "is_boundary": bool}}
    tree = {}
    # 记录每层的调用关系
    parent_map = {entry_id: None}
    order = []  # BFS 访问顺序
    boundary_nodes = set()  # 边界节点集合

    while queue:
        current_id, depth = queue.popleft()
        if depth > max_depth:
            continue

        # 获取当前节点信息
        node_row = conn.execute(
            "SELECT id, name, file_path, layer FROM nodes WHERE id = ?",
            (current_id,),
        ).fetchone()

        node_info = {
            "id": current_id,
            "name": node_row["name"] if node_row else current_id,
            "file_path": node_row["file_path"] if node_row else "",
            "layer": node_row["layer"] if node_row else "unknown",
        } if node_row else {"id": current_id, "name": current_id, "file_path": "", "layer": "unknown"}

        is_boundary = _is_boundary_node(node_info)
        tree[current_id] = {"node": node_info, "children": [], "is_boundary": is_boundary}
        order.append(current_id)

        if is_boundary:
            boundary_nodes.add(current_id)

        if depth >= max_depth or is_boundary:
            continue

        # 查找下游调用边 (source == current_id)
        out_edges = conn.execute(
            "SELECT e.target, e.type, n.name, n.file_path, n.layer FROM edges e "
            "LEFT JOIN nodes n ON e.target = n.id "
            "WHERE e.source = ? AND e.type IN (?, ?, ?)",
            (current_id, *_FLOW_EDGE_TYPES),
        ).fetchall()

        for edge in out_edges:
            target_id = edge["target"]
            if target_id in visited:
                continue
            visited.add(target_id)
            parent_map[target_id] = current_id
            tree[current_id]["children"].append(target_id)
            queue.append((target_id, depth + 1))

    return {
        "tree": tree, "order": order, "entry_id": entry_id,
        "max_depth": max_depth, "boundary_nodes": boundary_nodes,
    }


def _trace_flow_from_json(entry_id: str, max_depth: int, graph_data: dict) -> dict:
    """从 JSON 图谱追踪执行流（含边界检测）"""
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])
    node_index = _build_node_index(nodes)

    visited = set()
    queue = deque([(entry_id, 0)])
    visited.add(entry_id)

    tree = {}
    order = []
    boundary_nodes = set()

    while queue:
        current_id, depth = queue.popleft()
        if depth > max_depth:
            continue

        node = node_index.get(current_id, {})
        node_info = {
            "id": current_id,
            "name": node.get("name", current_id),
            "file_path": node.get("file_path", ""),
            "layer": node.get("layer", "unknown"),
        }

        is_boundary = _is_boundary_node(node_info)
        tree[current_id] = {"node": node_info, "children": [], "is_boundary": is_boundary}
        order.append(current_id)

        if is_boundary:
            boundary_nodes.add(current_id)

        if depth >= max_depth or is_boundary:
            continue

        for edge in edges:
            if edge.get("source") != current_id:
                continue
            if edge.get("type") not in _FLOW_EDGE_TYPES:
                continue
            target_id = edge.get("target", "")
            if target_id in visited:
                continue
            visited.add(target_id)
            tree[current_id]["children"].append(target_id)
            queue.append((target_id, depth + 1))

    return {
        "tree": tree, "order": order, "entry_id": entry_id,
        "max_depth": max_depth, "boundary_nodes": boundary_nodes,
    }


def _sanitize_mermaid_text(text: str) -> str:
    """
    Mermaid 语法清洗器：将特殊字符转义为安全文本。

    Mermaid 不支持 < > :: () 等特殊字符出现在节点 ID 或连线标签中。
    """
    replacements = [
        ("<", "&lt;"), (">", "&gt;"),
        ("::", "."), ("->", "."),
        ("(", "_"), (")", ""),
        ("{", "_"), ("}", ""),
        ("[", "_"), ("]", ""),
        ("'", "&#39;"), ('"', "&quot;"),
        ("#", "_"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text.strip("_").strip()


def _generate_mermaid_sequence(trace_result: dict) -> str:
    """
    根据追踪结果生成 Mermaid 时序图（含语法清洗 + 边界检测）。

    核心设计：
    1. 每个节点分配纯字母数字别名（node_A, node_B...），真实名称用双引号包裹
    2. 连线描述附带目标真实函数名：node_A->>node_B: calls "Codec::decode()"
    3. 边界/深度截断节点使用虚线 + Note 说明
    4. 所有文本经过 _sanitize_mermaid_text 清洗，防止渲染崩溃
    """
    tree = trace_result["tree"]
    entry_id = trace_result["entry_id"]
    boundary_nodes = trace_result.get("boundary_nodes", set())
    max_depth = trace_result.get("max_depth", 5)

    if not tree or entry_id not in tree:
        return "sequenceDiagram\n    Note over Entry: 无执行流数据"

    lines = ["sequenceDiagram"]

    # 别名映射：node_id -> "node_A", "node_B"...
    alias_map = {}
    alias_counter = [0]

    layer_map = {
        "api": "Controller", "business": "Service", "data": "Repository",
        "infra": "Infra", "config": "Config", "model": "Model",
        "domain": "Domain", "route": "Route",
    }

    def _assign_alias(node_id: str) -> str:
        if node_id in alias_map:
            return alias_map[node_id]
        alias_counter[0] += 1
        # 生成 node_A, node_B, ... node_Z, node_AA, node_AB, ...
        n = alias_counter[0]
        chars = []
        while n > 0:
            n -= 1
            chars.append(chr(ord('A') + (n % 26)))
            n //= 26
        alias = "node_" + "".join(reversed(chars))
        alias_map[node_id] = alias
        return alias

    def _get_display_label(node_info: dict) -> str:
        name = node_info.get("name", node_info.get("id", "unknown"))
        layer = node_info.get("layer", "unknown")
        layer_label = layer_map.get(layer, layer.capitalize())
        return f"{name}({layer_label})"

    def _escape_mermaid_label(text: str) -> str:
        """转义 Mermaid 连线标签中的特殊字符，用双引号包裹"""
        # 替换最危险的字符，保留可读性
        text = text.replace('"', "'")
        return text

    # 遍历树，生成 participant 声明和消息
    def _traverse(node_id: str, parent_alias: str, depth: int):
        if node_id not in tree:
            return
        node_data = tree[node_id]
        node_info = node_data["node"]
        is_boundary = node_data.get("is_boundary", False) or node_id in boundary_nodes
        is_max_depth = (depth >= max_depth) and not is_boundary

        alias = _assign_alias(node_id)
        display_label = _get_display_label(node_info)

        # 声明 participant（用别名 + 双引号包裹的真实名称）
        lines.append(f'    participant {alias} as "{display_label}"')

        if parent_alias:
            real_name = _escape_mermaid_label(node_info.get("name", ""))
            if is_boundary:
                # 边界节点：虚线 + external_call + 真实函数名
                lines.append(f'    {parent_alias}-->>{alias}: external_call "{real_name}"')
            else:
                # 正常连线：附带真实函数名
                lines.append(f'    {parent_alias}->>{alias}: calls "{real_name}"')

        # 边界节点：添加说明 + 停止遍历
        if is_boundary:
            lines.append(f"    Note over {alias}: Reached boundary - external dependency")
            return

        # 深度截断：添加说明 + 停止遍历
        if is_max_depth:
            lines.append(f"    Note over {alias}: Reached boundary or max depth")
            return

        for child_id in node_data["children"]:
            _traverse(child_id, alias, depth + 1)

    # 入口节点
    entry_data = tree[entry_id]
    entry_alias = _assign_alias(entry_id)
    entry_display = _get_display_label(entry_data["node"])
    lines.append(f'    participant {entry_alias} as "{entry_display}"')

    for child_id in entry_data["children"]:
        _traverse(child_id, entry_alias, 1)

    return "\n".join(lines)


def _generate_call_chain_tree(trace_result: dict) -> str:
    """根据追踪结果生成结构化调用链树文本（含边界标记）"""
    tree = trace_result["tree"]
    entry_id = trace_result["entry_id"]
    boundary_nodes = trace_result.get("boundary_nodes", set())

    if not tree or entry_id not in tree:
        return "无执行流数据"

    layer_icons = {
        "api": "🌐", "business": "⚙️", "data": "🗄️",
        "infra": "🔧", "config": "📋", "model": "📦",
        "domain": "💎", "route": "🛤️", "controller": "🌐",
        "service": "⚙️", "repository": "🗄️",
    }

    lines = []

    def _render(node_id: str, prefix: str, is_last: bool, depth: int):
        if node_id not in tree:
            return
        node_data = tree[node_id]
        node_info = node_data["node"]
        name = node_info.get("name", node_id)
        layer = node_info.get("layer", "unknown")
        fp = node_info.get("file_path", "")
        is_boundary = node_data.get("is_boundary", False) or node_id in boundary_nodes
        icon = layer_icons.get(layer, "📍")

        connector = "└── " if is_last else "├── "
        fp_str = f" → {fp}" if fp else ""
        boundary_tag = " ⚠️[外部边界-停止遍历]" if is_boundary else ""

        if depth == 0:
            lines.append(f"{icon} {name} [{layer}]{fp_str}{boundary_tag}")
        else:
            lines.append(f"{prefix}{connector}{icon} {name} [{layer}]{fp_str}{boundary_tag}")

        # 边界节点不展开子节点
        if is_boundary:
            return

        children = node_data["children"]
        child_prefix = prefix + ("    " if is_last else "│   ")
        for i, child_id in enumerate(children):
            _render(child_id, child_prefix, i == len(children) - 1, depth + 1)

    _render(entry_id, "", True, 0)
    return "\n".join(lines)


def trace_execution_flow(entry_point: str, max_depth: int = 5, work_dir: str = "") -> tuple[str, bool]:
    """
    从指定入口点追踪执行流，生成 Mermaid 时序图和调用链树。

    顺着 CALLS / routes_to / symbol_call 类型的边向下遍历，
    直到达到 max_depth，生成完整的调用链可视化。

    Args:
        entry_point: 入口节点名称（如 main 函数、API 路由名、Controller 方法名）
        max_depth: 最大追踪深度（默认 5）
        work_dir: 工作目录

    Returns:
        (结果文本, 是否出错)
    """
    if not entry_point:
        return "错误: entry_point 不能为空", True

    max_depth = max(1, min(max_depth, 10))

    if not work_dir:
        work_dir = os.getcwd()

    # 1. 查找入口节点
    db_path = _find_db_path(work_dir)
    entry_id = None
    entry_info = None

    if db_path:
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row

            # 模糊匹配
            rows = conn.execute(
                "SELECT id, name, file_path, layer FROM nodes WHERE name LIKE ? OR id LIKE ? LIMIT 20",
                (f"%{entry_point}%", f"%{entry_point}%"),
            ).fetchall()

            if not rows:
                conn.close()
                return f"未找到匹配 '{entry_point}' 的入口节点", True

            # 优先精确匹配
            for row in rows:
                if row["name"] and row["name"].lower() == entry_point.lower():
                    entry_id = row["id"]
                    entry_info = dict(row)
                    break
                if row["id"] and row["id"].lower() == entry_point.lower():
                    entry_id = row["id"]
                    entry_info = dict(row)
                    break
            if not entry_id:
                entry_id = rows[0]["id"]
                entry_info = dict(rows[0])

            # 追踪执行流
            trace_result = _trace_flow_from_db(entry_id, max_depth, conn)
            conn.close()

        except Exception as e:
            return f"执行流追踪失败: {e}", True
    else:
        # 降级到 JSON 图谱
        graph_data = _load_graph(work_dir)
        if not graph_data:
            return (
                "未找到项目图谱数据库或 JSON 图谱。"
                "请先使用 '解析项目架构' 功能生成图谱。",
                True,
            )

        nodes = graph_data.get("nodes", [])
        matched = _fuzzy_match_nodes(nodes, entry_point)
        if not matched:
            return f"未找到匹配 '{entry_point}' 的入口节点", True

        primary = matched[0]
        entry_id = primary.get("id", "")
        entry_info = {
            "id": entry_id,
            "name": primary.get("name", ""),
            "file_path": primary.get("file_path", ""),
            "layer": primary.get("layer", "unknown"),
        }

        trace_result = _trace_flow_from_json(entry_id, max_depth, graph_data)

    # 2. 生成输出
    tree = trace_result["tree"]
    total_nodes = len(tree)
    boundary_nodes = trace_result.get("boundary_nodes", set())

    if total_nodes <= 1:
        return (
            f"入口 '{entry_info.get('name', entry_id)}' 没有下游调用链。\n"
            f"可能原因: 该节点是叶子节点，或图谱中缺少 CALLS 类型的边。",
            False,
        )

    # 生成调用链树
    call_tree = _generate_call_chain_tree(trace_result)

    # 生成 Mermaid 时序图
    mermaid = _generate_mermaid_sequence(trace_result)

    boundary_info = ""
    if boundary_nodes:
        boundary_names = []
        for bid in boundary_nodes:
            if bid in tree:
                boundary_names.append(tree[bid]["node"].get("name", bid))
        boundary_info = f"\n[边界节点]: {len(boundary_nodes)} 个 ({', '.join(boundary_names[:5])})"

    lines = [
        f"[执行流追踪] {entry_info.get('name', entry_id)}",
        f"[入口ID]: {entry_id}",
        f"[最大深度]: {max_depth}",
        f"[覆盖节点]: {total_nodes}",
        f"[内部节点]: {total_nodes - len(boundary_nodes)}",
        f"[边界截断]: {len(boundary_nodes)} 个外部依赖边界{boundary_info}",
        "",
        "── 调用链树 ──",
        call_tree,
        "",
        "── Mermaid 时序图 ──",
        "```mermaid",
        mermaid,
        "```",
    ]

    result = "\n".join(lines)
    logger.info(f"执行流追踪: '{entry_point}' → {total_nodes} 节点, 深度 {max_depth}")

    return result, False

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

# ── analyze_blast_radius 工具定义 ──

ANALYZE_BLAST_RADIUS_TOOL_DEFINITION_OPENAI = {
    "type": "function",
    "function": {
        "name": "analyze_blast_radius",
        "description": (
            "分析目标符号的爆炸半径：递归查找所有依赖该符号的下游调用者，评估修改它的影响面。"
            "返回直接下游(1-hop)和间接下游(2-hop+)的调用者列表，以及风险等级评估。"
            "风险等级: >5个文件依赖=High Risk, 2-5个=Medium Risk, 1个=Low Risk。"
            "在修改任何核心模块前，务必先调用此工具评估影响范围，避免破坏性变更。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol_name": {
                    "type": "string",
                    "description": (
                        "目标符号名称，可以是类名(如 UserService)、"
                        "函数名(如 handle_login) 或模块名。支持模糊匹配。"
                    ),
                },
            },
            "required": ["symbol_name"],
        },
    },
}

ANALYZE_BLAST_RADIUS_TOOL_DEFINITION_ANTHROPIC = {
    "name": "analyze_blast_radius",
    "description": (
        "分析目标符号的爆炸半径：递归查找所有依赖该符号的下游调用者，评估修改它的影响面。"
        "返回直接下游(1-hop)和间接下游(2-hop+)的调用者列表，以及风险等级评估。"
        "风险等级: >5个文件依赖=High Risk, 2-5个=Medium Risk, 1个=Low Risk。"
        "在修改任何核心模块前，务必先调用此工具评估影响范围，避免破坏性变更。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "symbol_name": {
                "type": "string",
                "description": (
                    "目标符号名称，可以是类名(如 UserService)、"
                    "函数名(如 handle_login) 或模块名。支持模糊匹配。"
                ),
            },
        },
        "required": ["symbol_name"],
    },
}

# ── trace_execution_flow 工具定义 ──

TRACE_EXECUTION_FLOW_TOOL_DEFINITION_OPENAI = {
    "type": "function",
    "function": {
        "name": "trace_execution_flow",
        "description": (
            "从指定入口点追踪执行流，生成完整的调用链可视化和 Mermaid 时序图。"
            "顺着 CALLS / routes_to 类型的边向下遍历，展示请求从入口到终点的完整生命周期。"
            "特别适合: 理解 Web 请求的 Controller→Service→Repository 链路、"
            "追踪某个 API 的完整调用路径、分析函数执行流程。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "entry_point": {
                    "type": "string",
                    "description": (
                        "入口节点名称，如 main 函数、API 路由名(如 /api/users)、"
                        "Controller 方法名(如 UserController.get_users)。支持模糊匹配。"
                    ),
                },
                "max_depth": {
                    "type": "integer",
                    "description": "最大追踪深度，默认5，最大10",
                },
            },
            "required": ["entry_point"],
        },
    },
}

TRACE_EXECUTION_FLOW_TOOL_DEFINITION_ANTHROPIC = {
    "name": "trace_execution_flow",
    "description": (
        "从指定入口点追踪执行流，生成完整的调用链可视化和 Mermaid 时序图。"
        "顺着 CALLS / routes_to 类型的边向下遍历，展示请求从入口到终点的完整生命周期。"
        "特别适合: 理解 Web 请求的 Controller→Service→Repository 链路、"
        "追踪某个 API 的完整调用路径、分析函数执行流程。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "entry_point": {
                "type": "string",
                "description": (
                    "入口节点名称，如 main 函数、API 路由名、Controller 方法名。支持模糊匹配。"
                ),
            },
            "max_depth": {
                "type": "integer",
                "description": "最大追踪深度，默认5，最大10",
            },
        },
        "required": ["entry_point"],
    },
}
