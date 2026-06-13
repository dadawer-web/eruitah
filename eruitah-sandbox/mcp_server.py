"""
Eruitah Architecture Brain - MCP Server

将代码图谱数据库封装为标准 MCP (Model Context Protocol) Server，
让外部 AI 智能体能够直接查询项目架构、依赖关系和符号表。

启动方式:
  python mcp_server.py                          # stdio 模式（默认）
  python mcp_server.py --transport sse --port 8765  # SSE 模式

Tools:
  search_architecture  - 自然语言搜索代码模块
  get_module_impact    - 查询修改某文件的影响范围
  get_module_symbols   - 获取模块内部的 AST 符号表
  list_layers          - 列出项目的架构分层
  get_dependency_graph - 获取指定深度内的依赖子图
"""

import sqlite3
import json
import os
import math
import logging
from typing import Optional

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("mcp_server")
logging.basicConfig(level=logging.INFO)

# ── MCP 服务器实例 ──
mcp = FastMCP("Eruitah Architecture Brain")

# ── 数据库路径 ──
DEFAULT_DB_PATH = os.environ.get(
    "CODEGRAPH_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".eruitah_cache", "codegraph.db")
)


def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """获取 SQLite 数据库连接（只读模式）"""
    path = db_path or DEFAULT_DB_PATH
    if not os.path.isfile(path):
        raise FileNotFoundError(f"codegraph.db 不存在: {path}")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _cosine_similarity(a: list, b: list) -> float:
    """计算两个向量的余弦相似度"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _semantic_search(query: str, top_k: int = 5, db_path: Optional[str] = None) -> list:
    """
    语义向量检索：编码查询 → 计算余弦相似度 → 返回 top_k 结果
    如果向量引擎不可用，降级为关键词匹配
    """
    # 1. 从 SQLite 加载 embeddings
    node_embeddings = {}
    try:
        conn = get_db_connection(db_path)
        rows = conn.execute(
            "SELECT id, embedding FROM nodes WHERE embedding IS NOT NULL AND embedding != ''"
        ).fetchall()
        conn.close()
        for row in rows:
            try:
                emb = json.loads(row["embedding"])
                if isinstance(emb, list) and len(emb) > 0:
                    node_embeddings[row["id"]] = emb
            except (json.JSONDecodeError, TypeError):
                continue
    except Exception as e:
        logger.warning(f"加载 embeddings 失败: {e}")

    # 2. 尝试向量检索
    if node_embeddings:
        try:
            from semantic_search_tool import _VectorEngine
            engine = _VectorEngine()
            if engine.available:
                query_embedding = engine._encode([query.strip()])[0].tolist()
                scores = []
                for nid, emb in node_embeddings.items():
                    sim = _cosine_similarity(query_embedding, emb)
                    scores.append((nid, sim))
                scores.sort(key=lambda x: x[1], reverse=True)
                return [nid for nid, _ in scores[:top_k]]
        except Exception as e:
            logger.warning(f"向量检索失败，降级为关键词匹配: {e}")

    # 3. 降级：关键词匹配
    try:
        conn = get_db_connection(db_path)
        rows = conn.execute(
            "SELECT id FROM nodes WHERE name LIKE ? OR ai_summary LIKE ? LIMIT ?",
            (f"%{query}%", f"%{query}%", top_k)
        ).fetchall()
        conn.close()
        return [row["id"] for row in rows]
    except Exception:
        return []


def _build_fts_query(query: str) -> str:
    """
    将用户输入的查询字符串转换为 FTS5 MATCH 语法。
    - 空格分隔的词自动变为 AND: "login auth" → "login AND auth"
    - 已包含 OR/AND 的保持原样
    - 对每个词加引号防止特殊字符导致语法错误
    """
    query = query.strip()
    if not query:
        return '""'

    # 如果用户已经使用了 FTS5 操作符，直接返回
    upper = query.upper()
    if " OR " in upper or " AND " in upper or " NOT " in upper or " NEAR " in upper:
        return query

    # 空格分隔的多关键词 → AND 组合
    words = query.split()
    if len(words) == 1:
        return f'"{words[0]}"'
    return " AND ".join(f'"{w}"' for w in words)


# ════════════════════════════════════════════════════════════════
# MCP Tools
# ════════════════════════════════════════════════════════════════

@mcp.tool()
def search_architecture(query: str, top_k: int = 5) -> str:
    """
    根据自然语言查询相关的代码模块。
    使用 FTS5 全文索引进行高性能搜索，支持高级查询语法（如 "login" OR "auth"）。
    也支持语义向量检索（如果可用）作为补充。

    Args:
        query: 自然语言查询，如 "登录认证流程" 或 "数据库连接池"。
               支持空格分隔的多关键词 AND 查询，以及 OR 组合查询。
        top_k: 返回结果数量，默认 5
    """
    try:
        # 先尝试语义检索获取 node IDs
        matched_ids = _semantic_search(query, top_k)

        if not matched_ids:
            # 语义检索无结果，使用 FTS5 全文索引
            conn = get_db_connection()
            try:
                # FTS5 MATCH 查询: 高性能全文搜索
                fts_query = _build_fts_query(query)
                rows = conn.execute(
                    "SELECT n.id, n.file_path, n.name, n.layer, n.ai_summary "
                    "FROM nodes_fts f "
                    "JOIN nodes n ON f.node_id = n.id "
                    "WHERE nodes_fts MATCH ? "
                    "ORDER BY rank "
                    "LIMIT ?",
                    (fts_query, top_k)
                ).fetchall()
            except Exception:
                # FTS5 查询失败（如特殊字符），降级为 LIKE
                rows = conn.execute(
                    "SELECT id, file_path, name, layer, ai_summary FROM nodes "
                    "WHERE name LIKE ? OR ai_summary LIKE ? LIMIT ?",
                    (f"%{query}%", f"%{query}%", top_k)
                ).fetchall()
            conn.close()
            if not rows:
                return f"未找到与 '{query}' 相关的模块。"
            matched_ids = [row["id"] for row in rows]

        # 根据 IDs 查询完整信息
        conn = get_db_connection()
        placeholders = ",".join("?" * len(matched_ids))
        rows = conn.execute(
            f"SELECT id, file_path, name, layer, ai_summary FROM nodes "
            f"WHERE id IN ({placeholders})",
            matched_ids
        ).fetchall()
        conn.close()

        if not rows:
            return f"未找到与 '{query}' 相关的模块。"

        lines = [f"🔍 查询: {query}", f"📊 找到 {len(rows)} 个相关模块:\n"]
        for i, row in enumerate(rows, 1):
            layer_badge = f"[{row['layer']}]" if row["layer"] else "[unknown]"
            summary = row["ai_summary"] or "暂无摘要"
            # 截断过长的摘要
            if len(summary) > 200:
                summary = summary[:200] + "..."
            lines.append(f"  {i}. {layer_badge} {row['name']}")
            lines.append(f"     📁 {row['file_path']}")
            lines.append(f"     💡 {summary}")
            lines.append("")

        return "\n".join(lines)

    except FileNotFoundError as e:
        return f"❌ 数据库未找到: {e}"
    except Exception as e:
        return f"❌ 查询失败: {e}"


@mcp.tool()
def get_module_impact(file_path: str) -> str:
    """
    查询修改某个特定文件时的影响范围（依赖树）。
    返回该文件依赖了谁（上游），以及谁依赖了这个文件（下游）。

    Args:
        file_path: 文件路径，如 "src/auth/login.py"
    """
    try:
        conn = get_db_connection()

        # 先查找该文件对应的节点
        nodes = conn.execute(
            "SELECT id, name, layer, ai_summary FROM nodes WHERE file_path LIKE ?",
            (f"%{file_path}%",)
        ).fetchall()

        if not nodes:
            conn.close()
            return f"未找到文件: {file_path}"

        lines = [f"💥 影响分析: {file_path}\n"]

        for node in nodes:
            nid = node["id"]
            layer_badge = f"[{node['layer']}]" if node["layer"] else "[unknown]"

            lines.append(f"📌 {layer_badge} {node['name']} (id: {nid})")

            # 上游：该节点依赖了谁 (source = nid)
            upstream = conn.execute(
                "SELECT e.target, n.name, n.file_path, n.layer, e.type, e.detail "
                "FROM edges e LEFT JOIN nodes n ON e.target = n.id "
                "WHERE e.source = ?",
                (nid,)
            ).fetchall()

            # 下游：谁依赖了该节点 (target = nid)
            downstream = conn.execute(
                "SELECT e.source, n.name, n.file_path, n.layer, e.type, e.detail "
                "FROM edges e LEFT JOIN nodes n ON e.source = n.id "
                "WHERE e.target = ?",
                (nid,)
            ).fetchall()

            if upstream:
                lines.append(f"  ⬆️  上游依赖 ({len(upstream)} 个):")
                for row in upstream:
                    dep_layer = f"[{row['layer']}]" if row["layer"] else "[?]"
                    dep_name = row["name"] or row["source"]
                    dep_path = row["file_path"] or ""
                    edge_type = row["type"] or "calls"
                    detail = row["detail"] or ""
                    detail_info = f" (具体调用了 {detail})" if detail and edge_type == "symbol_call" else ""
                    lines.append(f"     → {dep_layer} {dep_name} ({edge_type}){detail_info} 📁{dep_path}")
            else:
                lines.append("  ⬆️  上游依赖: 无")

            if downstream:
                lines.append(f"  ⬇️  下游影响 ({len(downstream)} 个):")
                for row in downstream:
                    dep_layer = f"[{row['layer']}]" if row["layer"] else "[?]"
                    dep_name = row["name"] or row["source"]
                    dep_path = row["file_path"] or ""
                    edge_type = row["type"] or "calls"
                    detail = row["detail"] or ""
                    detail_info = f" (具体调用了 {detail})" if detail and edge_type == "symbol_call" else ""
                    lines.append(f"     ← {dep_layer} {dep_name} ({edge_type}){detail_info} 📁{dep_path}")
            else:
                lines.append("  ⬇️  下游影响: 无")

            lines.append("")

        conn.close()
        return "\n".join(lines)

    except FileNotFoundError as e:
        return f"❌ 数据库未找到: {e}"
    except Exception as e:
        return f"❌ 查询失败: {e}"


@mcp.tool()
def get_module_symbols(file_path: str) -> str:
    """
    获取某个特定模块内部的 AST 符号表（有哪些类和函数）。
    此工具现在支持精确提取 C++, Java, Python 的类与方法符号，用于深度的上下文理解。
    返回层级化的 Markdown 格式符号列表，包含类名、方法名、行号和父类关系。

    Args:
        file_path: 文件路径，如 "src/auth/login.py"
    """
    try:
        conn = get_db_connection()

        # 从 nodes 表查询
        rows = conn.execute(
            "SELECT name, layer, symbols, ai_summary FROM nodes WHERE file_path LIKE ?",
            (f"%{file_path}%",)
        ).fetchall()

        if not rows:
            # 尝试从 files 表查询
            file_row = conn.execute(
                "SELECT symbols FROM files WHERE path LIKE ?",
                (f"%{file_path}%",)
            ).fetchone()
            conn.close()
            if file_row and file_row["symbols"]:
                try:
                    symbols = json.loads(file_row["symbols"])
                    return _format_symbols_markdown(file_path, symbols, "unknown", "")
                except (json.JSONDecodeError, TypeError):
                    return f"无法解析符号表: {file_path}"
            return f"未找到文件: {file_path}"

        all_output = []
        for row in rows:
            layer_badge = f"[{row['layer']}]" if row["layer"] else "[unknown]"
            ai_summary = row["ai_summary"] or ""

            symbols_raw = row["symbols"]
            if symbols_raw:
                try:
                    if isinstance(symbols_raw, str):
                        symbols = json.loads(symbols_raw)
                    else:
                        symbols = symbols_raw
                    output = _format_symbols_markdown(
                        file_path, symbols, layer_badge, ai_summary
                    )
                    all_output.append(output)
                except (json.JSONDecodeError, TypeError):
                    all_output.append(f"📌 {layer_badge} {row['name']}\n  符号数据（原始）: {str(symbols_raw)[:300]}")
            else:
                all_output.append(f"📌 {layer_badge} {row['name']}\n  ⚠️ 无符号数据")

        conn.close()
        return "\n\n".join(all_output)

    except FileNotFoundError as e:
        return f"❌ 数据库未找到: {e}"
    except Exception as e:
        return f"❌ 查询失败: {e}"


def _format_symbols_markdown(
    file_path: str, symbols: list, layer_badge: str, ai_summary: str
) -> str:
    """
    将符号列表格式化为 Markdown 层级结构，适合大模型阅读。

    输出格式:
    📋 符号表: src/auth/login.py [service]

    ## 🏗️ ChatServer (class, L10)
    - 🔧 __init__(self, host, port) — constructor, L12
    - ⚡ start() — method, L15
    - ⚡ send_msg(client, message) — method, L20

    ## ⚡ parse_config(path) — function, L30

    💡 AI 摘要: 处理用户登录认证...
    """
    if not isinstance(symbols, list) or not symbols:
        return f"📋 符号表: {file_path} {layer_badge}\n\n  ⚠️ 无符号数据"

    lines = [f"📋 符号表: {file_path} {layer_badge}\n"]

    # 按层级分组：类 → 方法，独立函数
    classes = {}  # class_name → [methods]
    standalone = []  # 独立函数/方法

    for sym in symbols:
        name = sym.get("name", "?")
        kind = sym.get("kind", sym.get("type", "?"))
        line = sym.get("line", sym.get("lineno", "?"))
        parent = sym.get("parent_name", sym.get("parent", ""))

        if kind in ("class", "ClassDef"):
            classes[name] = {"line": line, "methods": [], "kind": kind}
        elif kind in ("interface", "enum", "record", "struct"):
            classes[name] = {"line": line, "methods": [], "kind": kind}
        elif parent and parent in classes:
            classes[parent]["methods"].append((name, kind, line))
        elif parent:
            # 父类不在当前符号表中，归入独立列表
            standalone.append((name, kind, line, parent))
        else:
            standalone.append((name, kind, line, ""))

    # 输出类和其方法
    for cls_name, cls_info in classes.items():
        kind_label = cls_info["kind"]
        lines.append(f"## 🏗️ {cls_name} ({kind_label}, L{cls_info['line']})")

        for method_name, method_kind, method_line in cls_info["methods"]:
            icon = "🔧" if method_kind in ("constructor", "destructor") else "⚡"
            lines.append(f"  - {icon} {method_name}() — {method_kind}, L{method_line}")

        if not cls_info["methods"]:
            lines.append("  - (无方法)")

        lines.append("")

    # 输出独立函数
    if standalone:
        lines.append("## ⚡ 独立函数/方法")
        for name, kind, line, parent in standalone:
            parent_info = f" (in {parent})" if parent else ""
            lines.append(f"  - ⚡ {name}() — {kind}, L{line}{parent_info}")
        lines.append("")

    # AI 摘要
    if ai_summary:
        summary = ai_summary
        if len(summary) > 300:
            summary = summary[:300] + "..."
        lines.append(f"💡 AI 摘要: {summary}")

    return "\n".join(lines)


@mcp.tool()
def list_layers() -> str:
    """
    列出项目的架构分层统计。
    返回每个层级（api, service, data, ui 等）的模块数量和代表模块。
    """
    try:
        conn = get_db_connection()

        rows = conn.execute(
            "SELECT layer, COUNT(*) as cnt FROM nodes GROUP BY layer ORDER BY cnt DESC"
        ).fetchall()

        if not rows:
            conn.close()
            return "数据库中暂无节点数据。"

        lines = ["📊 项目架构分层统计:\n"]

        for row in rows:
            layer = row["layer"] or "unknown"
            count = row["cnt"]

            # 获取该层级的代表模块
            reps = conn.execute(
                "SELECT name, file_path FROM nodes WHERE layer = ? LIMIT 3",
                (layer,)
            ).fetchall()

            rep_names = ", ".join(r["name"] for r in reps)
            lines.append(f"  🏷️  {layer}: {count} 个模块")
            lines.append(f"      代表: {rep_names}")

        # 总计
        total = conn.execute("SELECT COUNT(*) as total FROM nodes").fetchone()["total"]
        total_edges = conn.execute("SELECT COUNT(*) as total FROM edges").fetchone()["total"]
        lines.append(f"\n  📈 总计: {total} 个模块, {total_edges} 条依赖关系")

        conn.close()
        return "\n".join(lines)

    except FileNotFoundError as e:
        return f"❌ 数据库未找到: {e}"
    except Exception as e:
        return f"❌ 查询失败: {e}"


@mcp.tool()
def get_dependency_graph(file_path: str, depth: int = 2) -> str:
    """
    获取指定文件周围指定深度内的依赖子图。
    返回节点列表和边列表，适合可视化或进一步分析。

    Args:
        file_path: 起始文件路径
        depth: 遍历深度，默认 2（建议不超过 4）
    """
    try:
        conn = get_db_connection()

        # 查找起始节点
        start_nodes = conn.execute(
            "SELECT id, name, layer FROM nodes WHERE file_path LIKE ?",
            (f"%{file_path}%",)
        ).fetchall()

        if not start_nodes:
            conn.close()
            return f"未找到文件: {file_path}"

        # BFS 遍历
        visited_ids = set()
        queue = [row["id"] for row in start_nodes]
        visited_ids.update(queue)
        current_depth = 0

        while queue and current_depth < depth:
            next_queue = []
            placeholders = ",".join("?" * len(queue))
            edges = conn.execute(
                f"SELECT source, target FROM edges WHERE source IN ({placeholders}) OR target IN ({placeholders})",
                queue * 2
            ).fetchall()

            for edge in edges:
                for nid in (edge["source"], edge["target"]):
                    if nid not in visited_ids:
                        visited_ids.add(nid)
                        next_queue.append(nid)

            queue = next_queue
            current_depth += 1

        # 查询所有访问到的节点
        placeholders = ",".join("?" * len(visited_ids))
        nodes = conn.execute(
            f"SELECT id, name, file_path, layer FROM nodes WHERE id IN ({placeholders})",
            list(visited_ids)
        ).fetchall()

        edges = conn.execute(
            f"SELECT source, target, type, detail FROM edges "
            f"WHERE source IN ({placeholders}) AND target IN ({placeholders})",
            list(visited_ids) * 2
        ).fetchall()

        conn.close()

        # 格式化输出
        lines = [
            f"🕸️ 依赖子图: {file_path} (深度={depth})",
            f"📊 {len(nodes)} 个节点, {len(edges)} 条边\n",
            "📋 节点列表:"
        ]

        for node in nodes:
            layer_badge = f"[{node['layer']}]" if node["layer"] else "[?]"
            lines.append(f"  • {layer_badge} {node['name']} 📁{node['file_path']}")

        if edges:
            lines.append(f"\n🔗 依赖关系:")
            for edge in edges:
                edge_type = edge["type"] or "calls"
                detail = edge["detail"] or ""
                detail_info = f" [{detail}]" if detail and edge_type == "symbol_call" else ""
                lines.append(f"  {edge['source']} --({edge_type}{detail_info})--> {edge['target']}")

        return "\n".join(lines)

    except FileNotFoundError as e:
        return f"❌ 数据库未找到: {e}"
    except Exception as e:
        return f"❌ 查询失败: {e}"


@mcp.tool()
def resolve_api_route(route_path: str) -> str:
    """
    排查某个具体的 HTTP API 接口是由哪段代码处理的。
    当需要理解某个 URL 路由（如 /api/farm/plant）对应的后端实现时调用此工具。
    支持精确匹配和模糊匹配，路径中包含路径变量（如 {id}）也能正确匹配。

    Args:
        route_path: API 路由路径，如 "/api/users" 或 "/api/users/{id}"
    """
    try:
        conn = get_db_connection()

        # 1. 精确匹配路由节点
        route_nodes = conn.execute(
            "SELECT id, name, file_path, layer FROM nodes WHERE layer = 'api_route' AND name LIKE ?",
            (f"%{route_path}%",)
        ).fetchall()

        if not route_nodes:
            # 2. 模糊匹配: 去掉路径变量部分再试
            import re
            clean_path = re.sub(r'\{[^}]+\}', '{}', route_path)
            route_nodes = conn.execute(
                "SELECT id, name, file_path, layer FROM nodes WHERE layer = 'api_route' AND name LIKE ?",
                (f"%{clean_path}%",)
            ).fetchall()

        if not route_nodes:
            conn.close()
            return f"未找到路由: {route_path}\n提示: 请检查路径是否正确，或该路由尚未被解析。"

        lines = [f"🎯 路由解析: {route_path}\n"]

        for node in route_nodes:
            route_id = node["id"]
            route_name = node["name"]
            route_file = node["file_path"] or ""

            lines.append(f"📌 路由节点: {route_name}")
            lines.append(f"   📁 定义文件: {route_file}")

            # 查找 routes_to 边
            targets = conn.execute(
                "SELECT e.target, n.name, n.file_path, n.layer "
                "FROM edges e LEFT JOIN nodes n ON e.target = n.id "
                "WHERE e.source = ? AND e.type = 'routes_to'",
                (route_id,)
            ).fetchall()

            if targets:
                lines.append(f"   🔗 指向的处理代码:")
                for t in targets:
                    target_name = t["name"] or t["target"]
                    target_file = t["file_path"] or ""
                    target_layer = f"[{t['layer']}]" if t["layer"] else "[?]"
                    lines.append(f"      → {target_layer} {target_name} 📁{target_file}")
            else:
                lines.append(f"   🔗 未找到指向的处理代码")

            lines.append("")

        conn.close()
        return "\n".join(lines)

    except FileNotFoundError as e:
        return f"❌ 数据库未找到: {e}"
    except Exception as e:
        return f"❌ 查询失败: {e}"


# ════════════════════════════════════════════════════════════════
# 启动入口
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Eruitah Architecture Brain MCP Server")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio", help="传输模式")
    parser.add_argument("--port", type=int, default=8765, help="SSE 模式端口")
    parser.add_argument("--db", type=str, default=None, help="codegraph.db 路径")
    args = parser.parse_args()

    if args.db:
        DEFAULT_DB_PATH = args.db
        logger.info(f"使用自定义数据库路径: {args.db}")

    logger.info(f"🚀 Eruitah Architecture Brain MCP Server 启动 (transport={args.transport})")
    logger.info(f"📦 数据库: {DEFAULT_DB_PATH}")

    if args.transport == "sse":
        mcp.run(transport="sse", port=args.port)
    else:
        mcp.run(transport="stdio")
