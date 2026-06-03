"""
Eruitah 智能编程沙盒 - 图谱变更影响分析器 (Diff & Impact Analyzer)

参考 Understand-Anything 的 fingerprint.ts / change-classifier.ts / staleness.ts 设计理念:
  1. 对比新旧两份图谱 JSON，识别 Added / Deleted / Modified 节点
  2. 基于有向边做"传染"传播：任何指向 Modified/Deleted 节点的上游节点标记为 Impacted
  3. 生成带 diff_status 标注的合成图谱，供前端可视化

核心算法:
  ┌──────────────────────────────────────────────────────────────────┐
  │  Phase 1 (DIFF):      逐节点对比 old_graph vs new_graph        │
  │    Added:    new 有 old 无                                       │
  │    Deleted:  old 有 new 无                                       │
  │    Modified: 两边都有，但内容 Hash 或文件时间戳变化               │
  │    Unchanged: 两边都有且无变化                                    │
  │                                                                  │
  │  Phase 2 (IMPACT):    沿有向边逆向传染                           │
  │    遍历所有 edges，若 target 为 Modified/Deleted                 │
  │    → 将 source 标记为 Impacted                                   │
  │    → 多轮传播直到收敛（传染可穿透中间节点）                       │
  │                                                                  │
  │  Phase 3 (SYNTHESIZE): 合成带 diff_status 的图谱                 │
  │    Node: diff_status = added | deleted | modified | impacted     │
  │    Edge: diff_status = added | deleted | impacted                │
  └──────────────────────────────────────────────────────────────────┘
"""

import hashlib
import json
import logging
from collections import defaultdict
from typing import Optional

logger = logging.getLogger(__name__)


# ── 工具函数 ──

def _node_content_hash(node: dict) -> str:
    """
    基于节点的语义字段计算 SHA-256 Hash。
    排除 file_path 等可能因路径调整而变化的字段，聚焦于：
    name, type, params, return_type, methods, parent, line, end_line
    """
    signature_parts = [
        node.get("name", ""),
        node.get("type", ""),
        json.dumps(node.get("params", []), sort_keys=True, ensure_ascii=False),
        node.get("return_type", ""),
        json.dumps(sorted(node.get("methods", [])), ensure_ascii=False),
        node.get("parent", ""),
        str(node.get("line", 0)),
        str(node.get("end_line", 0)),
    ]
    raw = "|".join(signature_parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _build_node_index(graph: dict) -> dict:
    """构建 node_id → node 的索引"""
    return {n["id"]: n for n in graph.get("nodes", [])}


def _build_reverse_adj(edges: list) -> dict:
    """
    构建逆向邻接表: target → [source, ...]
    用于从 Modified/Deleted 节点反向查找受影响的上游节点
    """
    rev = defaultdict(list)
    for e in edges:
        rev[e["target"]].append(e["source"])
    return dict(rev)


def _build_forward_adj(edges: list) -> dict:
    """
    构建正向邻接表: source → [target, ...]
    用于传染传播时沿正向边向下传播
    """
    fwd = defaultdict(list)
    for e in edges:
        fwd[e["source"]].append(e["target"])
    return dict(fwd)


# ── Phase 1: 基础 Diff 对比 ──

def _classify_nodes(
    old_graph: dict,
    new_graph: dict,
    modified_file_paths: Optional[list] = None,
) -> dict:
    """
    对比新旧图谱，将每个节点分类为 added / deleted / modified / unchanged。

    Args:
        old_graph: 修改前的图谱 {"nodes": [...], "edges": [...]}
        new_graph: 修改后的图谱 {"nodes": [...], "edges": [...]}
        modified_file_paths: Agent 本次修改的文件路径列表（可选）。
            如果提供，属于这些文件的节点直接标记为 modified，
            无需依赖 Hash 对比。

    Returns:
        {
            "added": set(node_id, ...),
            "deleted": set(node_id, ...),
            "modified": set(node_id, ...),
            "unchanged": set(node_id, ...),
        }
    """
    old_idx = _build_node_index(old_graph)
    new_idx = _build_node_index(new_graph)

    old_ids = set(old_idx.keys())
    new_ids = set(new_idx.keys())

    added_ids = new_ids - old_ids
    deleted_ids = old_ids - new_ids
    common_ids = old_ids & new_ids

    # 构建修改文件集合（用于直接标记）
    modified_files = set(modified_file_paths or [])

    modified_ids = set()
    unchanged_ids = set()

    for nid in common_ids:
        old_node = old_idx[nid]
        new_node = new_idx[nid]

        # 策略 1: 如果节点所属文件在 modified_file_paths 中，直接标记 modified
        node_file = new_node.get("file_path", "")
        if node_file in modified_files:
            modified_ids.add(nid)
            continue

        # 策略 2: 基于内容 Hash 对比
        old_hash = _node_content_hash(old_node)
        new_hash = _node_content_hash(new_node)
        if old_hash != new_hash:
            modified_ids.add(nid)
        else:
            unchanged_ids.add(nid)

    result = {
        "added": added_ids,
        "deleted": deleted_ids,
        "modified": modified_ids,
        "unchanged": unchanged_ids,
    }

    logger.info(
        f"📊 Diff 分类完成: "
        f"added={len(added_ids)}, deleted={len(deleted_ids)}, "
        f"modified={len(modified_ids)}, unchanged={len(unchanged_ids)}"
    )

    return result


# ── Phase 2: 爆炸半径传染算法 ──

def _propagate_impact(
    classification: dict,
    old_edges: list,
    new_edges: list,
) -> set:
    """
    传染算法：沿有向边逆向传播影响。

    规则:
      - 任何节点的出边指向 Modified 或 Deleted 节点 → 该节点标记为 Impacted
      - Impacted 节点本身又会导致指向它的上游节点也变为 Impacted（多轮传播）
      - Added 节点不触发传染（它是新增的，不会破坏上游）

    Returns:
        impacted_ids: 被传染标记的节点 ID 集合
    """
    modified_or_deleted = classification["modified"] | classification["deleted"]

    if not modified_or_deleted:
        return set()

    # 合并新旧边以覆盖所有可能的依赖关系
    all_edges = []
    seen = set()
    for e in old_edges + new_edges:
        key = (e.get("source", ""), e.get("target", ""), e.get("type", ""))
        if key not in seen:
            seen.add(key)
            all_edges.append(e)

    # 构建逆向邻接表: target → [source]
    rev_adj = _build_reverse_adj(all_edges)

    # BFS 多轮传染
    impacted_ids = set()
    queue = list(modified_or_deleted)

    while queue:
        current = queue.pop(0)
        # 找到所有指向 current 的上游节点
        upstream_nodes = rev_adj.get(current, [])
        for source_id in upstream_nodes:
            # 只传染给未被分类的节点（unchanged）或已被传染的节点（继续向上传播）
            if source_id in classification["unchanged"] or source_id in impacted_ids:
                if source_id not in impacted_ids:
                    impacted_ids.add(source_id)
                    queue.append(source_id)
            # 已经是 modified/added 的节点不需要再标记为 impacted

    logger.info(f"💥 爆炸半径计算完成: {len(impacted_ids)} 个节点被标记为 Impacted")

    return impacted_ids


# ── Phase 3: 合成图谱生成 ──

def _classify_edges(
    old_graph: dict,
    new_graph: dict,
    classification: dict,
    impacted_ids: set,
) -> dict:
    """
    对边进行分类:
      - added: 新图谱有但旧图谱没有的边
      - deleted: 旧图谱有但新图谱没有的边
      - impacted: 边的 source 或 target 是 modified/deleted/impacted 节点
      - unchanged: 无变化的边
    """
    def _edge_key(e):
        return (e.get("source", ""), e.get("target", ""), e.get("type", ""))

    old_edge_keys = {_edge_key(e) for e in old_graph.get("edges", [])}
    new_edge_keys = {_edge_key(e) for e in new_graph.get("edges", [])}

    added_edge_keys = new_edge_keys - old_edge_keys
    deleted_edge_keys = old_edge_keys - new_edge_keys

    changed_node_ids = classification["modified"] | classification["deleted"] | impacted_ids

    edge_classification = {
        "added": added_edge_keys,
        "deleted": deleted_edge_keys,
        "impacted": set(),
        "unchanged": set(),
    }

    # 对新图谱中的边判断是否受影响
    for e in new_graph.get("edges", []):
        key = _edge_key(e)
        if key in added_edge_keys:
            continue
        source = e.get("source", "")
        target = e.get("target", "")
        if source in changed_node_ids or target in changed_node_ids:
            edge_classification["impacted"].add(key)
        else:
            edge_classification["unchanged"].add(key)

    return edge_classification


def _synthesize_graph(
    old_graph: dict,
    new_graph: dict,
    classification: dict,
    impacted_ids: set,
    edge_classification: dict,
) -> dict:
    """
    生成带 diff_status 标注的合成图谱。

    - 节点: 以新图谱为基础，附加 diff_status
    - 删除的节点: 从旧图谱中提取，标记 diff_status=deleted
    - 边: 以新图谱为基础，附加 diff_status
    - 删除的边: 从旧图谱中提取，标记 diff_status=deleted
    """
    new_idx = _build_node_index(new_graph)
    old_idx = _build_node_index(old_graph)

    def _edge_key(e):
        return (e.get("source", ""), e.get("target", ""), e.get("type", ""))

    # ── 合成节点 ──
    synth_nodes = []

    # 新图谱中的节点（包含 added / modified / unchanged / impacted）
    for node in new_graph.get("nodes", []):
        nid = node["id"]
        n = dict(node)
        if nid in classification["added"]:
            n["diff_status"] = "added"
        elif nid in classification["modified"]:
            n["diff_status"] = "modified"
        elif nid in impacted_ids:
            n["diff_status"] = "impacted"
        else:
            n["diff_status"] = "unchanged"
        synth_nodes.append(n)

    # 旧图谱中删除的节点
    for nid in classification["deleted"]:
        if nid in old_idx:
            n = dict(old_idx[nid])
            n["diff_status"] = "deleted"
            synth_nodes.append(n)

    # ── 合成边 ──
    synth_edges = []

    # 新图谱中的边
    for edge in new_graph.get("edges", []):
        key = _edge_key(edge)
        e = dict(edge)
        if key in edge_classification["added"]:
            e["diff_status"] = "added"
        elif key in edge_classification["impacted"]:
            e["diff_status"] = "impacted"
        else:
            e["diff_status"] = "unchanged"
        synth_edges.append(e)

    # 旧图谱中删除的边
    for edge in old_graph.get("edges", []):
        key = _edge_key(edge)
        if key in edge_classification["deleted"]:
            e = dict(edge)
            e["diff_status"] = "deleted"
            synth_edges.append(e)

    # ── 统计摘要 ──
    summary = {
        "added_nodes": len(classification["added"]),
        "deleted_nodes": len(classification["deleted"]),
        "modified_nodes": len(classification["modified"]),
        "impacted_nodes": len(impacted_ids),
        "unchanged_nodes": len(classification["unchanged"]),
        "added_edges": len(edge_classification["added"]),
        "deleted_edges": len(edge_classification["deleted"]),
        "impacted_edges": len(edge_classification["impacted"]),
        "unchanged_edges": len(edge_classification["unchanged"]),
        "blast_radius": len(classification["modified"]) + len(classification["deleted"]) + len(impacted_ids),
    }

    return {
        "nodes": synth_nodes,
        "edges": synth_edges,
        "diff_summary": summary,
    }


# ── 主入口函数 ──

def calculate_graph_diff(
    old_graph: dict,
    new_graph: dict,
    modified_file_paths: Optional[list] = None,
) -> dict:
    """
    计算两个图谱之间的变更差异与影响范围。

    Args:
        old_graph: 修改前的图谱 JSON，格式 {"nodes": [...], "edges": [...]}
        new_graph: 修改后的图谱 JSON，格式 {"nodes": [...], "edges": [...]}
        modified_file_paths: 可选。Agent 本次修改的文件路径列表。
            提供后，属于这些文件的节点会直接标记为 modified，
            无需依赖 Hash 对比（适用于无法获取时间戳的场景）。

    Returns:
        合成图谱 JSON，格式:
        {
            "nodes": [
                {"id": "...", "type": "...", "name": "...", "diff_status": "added|deleted|modified|impacted|unchanged", ...},
                ...
            ],
            "edges": [
                {"source": "...", "target": "...", "type": "...", "diff_status": "added|deleted|impacted|unchanged", ...},
                ...
            ],
            "diff_summary": {
                "added_nodes": N,
                "deleted_nodes": N,
                "modified_nodes": N,
                "impacted_nodes": N,
                "unchanged_nodes": N,
                "added_edges": N,
                "deleted_edges": N,
                "impacted_edges": N,
                "unchanged_edges": N,
                "blast_radius": N,   # 修改+删除+受影响 的总节点数
            }
        }
    """
    logger.info("🔍 开始图谱变更影响分析...")

    # Phase 1: 基础 Diff 对比
    classification = _classify_nodes(old_graph, new_graph, modified_file_paths)

    # Phase 2: 爆炸半径传染
    impacted_ids = _propagate_impact(
        classification,
        old_graph.get("edges", []),
        new_graph.get("edges", []),
    )

    # 边分类
    edge_classification = _classify_edges(old_graph, new_graph, classification, impacted_ids)

    # Phase 3: 合成图谱
    result = _synthesize_graph(old_graph, new_graph, classification, impacted_ids, edge_classification)

    summary = result["diff_summary"]
    logger.info(
        f"✅ 图谱 Diff 分析完成: "
        f"+{summary['added_nodes']} -{summary['deleted_nodes']} "
        f"~{summary['modified_nodes']} ⚡{summary['impacted_nodes']} "
        f"(爆炸半径: {summary['blast_radius']} 节点)"
    )

    return result


# ── CLI 入口 ──

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if len(sys.argv) < 3:
        print("用法: python graph_diff.py <old_graph.json> <new_graph.json> [modified_files.txt]")
        print("")
        print("  old_graph.json    修改前的图谱 JSON")
        print("  new_graph.json    修改后的图谱 JSON")
        print("  modified_files.txt  可选，每行一个被修改的文件路径")
        sys.exit(1)

    old_path = sys.argv[1]
    new_path = sys.argv[2]

    with open(old_path, "r", encoding="utf-8") as f:
        old_graph = json.load(f)
    with open(new_path, "r", encoding="utf-8") as f:
        new_graph = json.load(f)

    modified_files = None
    if len(sys.argv) >= 4:
        with open(sys.argv[3], "r", encoding="utf-8") as f:
            modified_files = [line.strip() for line in f if line.strip()]

    result = calculate_graph_diff(old_graph, new_graph, modified_files)

    output_path = new_path.replace(".json", "_diff.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    s = result["diff_summary"]
    print(f"\n📊 变更影响分析结果:")
    print(f"  节点: +{s['added_nodes']} -{s['deleted_nodes']} ~{s['modified_nodes']} ⚡{s['impacted_nodes']} (爆炸半径: {s['blast_radius']})")
    print(f"  边:   +{s['added_edges']} -{s['deleted_edges']} ⚡{s['impacted_edges']}")
    print(f"\n  合成图谱已写入: {output_path}")
