"""
GraphRAG 引擎 - 适配器模式 (Adapter Pattern)

支持两种底层实现，通过环境变量 GRAPH_ENGINE_TYPE 切换：
  - 'neo4j' (默认): 工业级 Neo4j 图数据库，支持 MERGE 动态融合
  - 'networkx': 轻量级 NetworkX + JSON 持久化，离线/开发降级方案

对外 API 签名完全一致，上层代码无感知。
"""

import asyncio
import json
import logging
import os
import re
from collections import deque
from typing import Any, Dict, List, Optional

import networkx as nx

from app.core.prompt_manager import PromptManager

logger = logging.getLogger(__name__)

GRAPH_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "graph_data")


# ═══════════════════════════════════════════════════════════════════════
#  NetworkX 引擎 (原有逻辑，重命名保留)
# ═══════════════════════════════════════════════════════════════════════

class NetworkXGraphEngine:

    def __init__(self, persist_dir: str = "", ai_client=None):
        self.persist_dir = persist_dir or GRAPH_DB_DIR
        self.ai_client = ai_client
        self._graphs: Dict[str, nx.DiGraph] = {}
        self._graph_mtimes: Dict[str, float] = {}
        os.makedirs(self.persist_dir, exist_ok=True)
        logger.info(f"NetworkXGraphEngine initialized | persist_dir={self.persist_dir}")

    def _user_graph_path(self, user_id: str) -> str:
        safe_id = user_id.replace("-", "_")
        return os.path.join(self.persist_dir, f"graph_kb_{safe_id}.json")

    def _load_graph_from_disk(self, user_id: str) -> nx.DiGraph:
        graph = nx.DiGraph()
        path = self._user_graph_path(user_id)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for node_data in data.get("nodes", []):
                    graph.add_node(node_data["id"], **node_data.get("attrs", {}))
                for edge_data in data.get("edges", []):
                    graph.add_edge(edge_data["source"], edge_data["target"], relation=edge_data.get("relation", ""), **edge_data.get("attrs", {}))
                logger.info(f"Graph loaded from disk for user {user_id[:8]}...: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
            except Exception as e:
                logger.warning(f"Failed to load graph for user {user_id[:8]}...: {e}")
        return graph

    def _get_disk_mtime(self, user_id: str) -> float:
        path = self._user_graph_path(user_id)
        try:
            return os.path.getmtime(path)
        except OSError:
            return 0.0

    def _get_user_graph(self, user_id: str) -> nx.DiGraph:
        disk_mtime = self._get_disk_mtime(user_id)
        cached_mtime = self._graph_mtimes.get(user_id, 0.0)

        if disk_mtime > cached_mtime:
            if disk_mtime > 0:
                logger.info(f"[Graph] 检测到磁盘文件更新 (mtime {cached_mtime:.0f} → {disk_mtime:.0f})，重载 user={user_id[:8]}...")
            graph = self._load_graph_from_disk(user_id)
            self._graphs[user_id] = graph
            self._graph_mtimes[user_id] = disk_mtime
            return graph

        if user_id in self._graphs:
            return self._graphs[user_id]

        graph = self._load_graph_from_disk(user_id)
        self._graphs[user_id] = graph
        self._graph_mtimes[user_id] = disk_mtime
        return graph

    def _save_user_graph(self, user_id: str):
        graph = self._graphs.get(user_id)
        if graph is None:
            return
        path = self._user_graph_path(user_id)
        try:
            data = {
                "nodes": [{"id": n, "attrs": dict(d)} for n, d in graph.nodes(data=True)],
                "edges": [{"source": u, "target": v, "relation": d.get("relation", ""), "attrs": {k: v for k, v in d.items() if k != "relation"}} for u, v, d in graph.edges(data=True)],
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._graph_mtimes[user_id] = os.path.getmtime(path)
            logger.info(f"Graph saved for user {user_id[:8]}...: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
        except Exception as e:
            logger.error(f"Failed to save graph for user {user_id[:8]}...: {e}")

    async def extract_entities_and_relations(self, text: str) -> List[Dict[str, str]]:
        if not self.ai_client or not text or not text.strip():
            return []
        try:
            messages = [
                {"role": "system", "content": PromptManager.get_prompt("graph_engine_extract_triplets")},
                {"role": "user", "content": f"请从以下文本中提取实体关系三元组：\n\n{text[:8000]}"},
            ]
            response = await self.ai_client.acall_api(messages, max_tokens=8192)
            if not response or not response.strip():
                return []
            triplets = _extract_json_from_reasoning(response)
            if isinstance(triplets, list):
                valid = []
                for t in triplets:
                    if isinstance(t, dict) and t.get("head") and t.get("relation") and t.get("tail"):
                        valid.append({"head": str(t["head"]).strip(), "relation": str(t["relation"]).strip(), "tail": str(t["tail"]).strip()})
                return valid
            return []
        except json.JSONDecodeError:
            logger.warning("Graph extraction: LLM output is not valid JSON")
            return []
        except Exception as e:
            logger.error(f"Graph extraction failed: {e}")
            return []

    def add_triplets(self, triplets: List[Dict[str, str]], user_id: str, source: str = "", source_text: str = ""):
        if not user_id:
            logger.error("安全拦截: add_triplets 拒绝无 user_id 的图谱写入")
            raise PermissionError("图谱写入被拒绝: 必须提供 user_id (用户隔离策略)")

        graph = self._get_user_graph(user_id)
        added_nodes = 0
        added_edges = 0

        for t in triplets:
            head = t.get("head", "").strip()
            relation = t.get("relation", "").strip()
            tail = t.get("tail", "").strip()
            if not head or not relation or not tail:
                continue

            if not graph.has_node(head):
                graph.add_node(head, type="entity", sources=[], source_texts=[])
                added_nodes += 1
            if not graph.has_node(tail):
                graph.add_node(tail, type="entity", sources=[], source_texts=[])
                added_nodes += 1

            if source:
                for node_name in [head, tail]:
                    sources = graph.nodes[node_name].get("sources", [])
                    if source not in sources:
                        sources.append(source)
                        graph.nodes[node_name]["sources"] = sources

            if source_text:
                truncated = source_text[:500] if len(source_text) > 500 else source_text
                for node_name in [head, tail]:
                    texts = graph.nodes[node_name].get("source_texts", [])
                    if truncated not in texts:
                        texts.append(truncated)
                        if len(texts) > 5:
                            texts = texts[-5:]
                        graph.nodes[node_name]["source_texts"] = texts

            if graph.has_edge(head, tail):
                existing = graph.edges[head, tail].get("relation", "")
                if existing and existing != relation:
                    graph.edges[head, tail]["relation"] = f"{existing}; {relation}"
            else:
                graph.add_edge(head, tail, relation=relation)
                added_edges += 1

        if added_edges > 0:
            self._save_user_graph(user_id)
            logger.info(f"🔒 NetworkX user {user_id[:8]}...: added {added_nodes} nodes, {added_edges} edges | total: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")

    def remove_document(self, user_id: str, source_id: str):
        """文档级联删除（NetworkX 实现）"""
        if not user_id:
            return
        graph = self._get_user_graph(user_id)

        # 从节点中移除 source_id
        nodes_to_clean = []
        for node, data in graph.nodes(data=True):
            sources = data.get("sources", [])
            if source_id in sources:
                sources.remove(source_id)
                data["sources"] = sources
                nodes_to_clean.append(node)

        # 删除 sources 为空的孤儿节点
        orphans = [n for n, d in graph.nodes(data=True)
                    if not d.get("sources") and graph.degree(n) == 0]
        for n in orphans:
            graph.remove_node(n)

        # 删除两端都没有该 source 的边
        edges_to_remove = []
        for u, v, data in graph.edges(data=True):
            u_sources = graph.nodes[u].get("sources", [])
            v_sources = graph.nodes[v].get("sources", [])
            if source_id not in u_sources and source_id not in v_sources:
                edges_to_remove.append((u, v))
        for u, v in edges_to_remove:
            graph.remove_edge(u, v)

        # 再次清理孤儿节点
        orphans2 = [n for n, d in graph.nodes(data=True)
                     if not d.get("sources") and graph.degree(n) == 0]
        for n in orphans2:
            graph.remove_node(n)

        self._save_user_graph(user_id)
        logger.info(
            f"🔒 NetworkX remove_document: user={user_id[:8]}..., source='{source_id}' | "
            f"cleaned_nodes={len(nodes_to_clean)}, deleted_edges={len(edges_to_remove)}, "
            f"deleted_orphans={len(orphans) + len(orphans2)}"
        )

    def search_subgraph(self, query: str, user_id: str, depth: int = 2) -> str:
        if not user_id:
            return ""
        graph = self._get_user_graph(user_id)
        if graph.number_of_nodes() == 0:
            return ""

        query_entities = self._fuzzy_match_entities(query, graph)
        if not query_entities:
            return ""

        visited_nodes, visited_edges = set(), set()
        queue = deque()
        for entity in query_entities:
            queue.append((entity, 0))
            visited_nodes.add(entity)

        while queue:
            current, d = queue.popleft()
            if d >= depth:
                continue
            for successor in graph.successors(current):
                edge_key = (current, successor)
                if edge_key not in visited_edges:
                    visited_edges.add(edge_key)
                if successor not in visited_nodes:
                    visited_nodes.add(successor)
                    queue.append((successor, d + 1))
            for predecessor in graph.predecessors(current):
                edge_key = (predecessor, current)
                if edge_key not in visited_edges:
                    visited_edges.add(edge_key)
                if predecessor not in visited_nodes:
                    visited_nodes.add(predecessor)
                    queue.append((predecessor, d + 1))

        descriptions = []
        for u, v in visited_edges:
            relation = graph.edges[u, v].get("relation", "相关")
            descriptions.append(f"{u} —[{relation}]→ {v}")

        if not descriptions:
            return ""
        result = "【知识图谱检索结果】：\n" + "\n".join(f"- {d}" for d in descriptions)
        logger.info(f"🔒 NetworkX search user {user_id[:8]}...: {len(visited_nodes)} nodes, {len(visited_edges)} edges")
        return result

    async def search_subgraph_async(self, query: str, user_id: str, depth: int = 2) -> str:
        if not self.ai_client or not query:
            return self.search_subgraph(query, user_id, depth)
        try:
            entities = await self.extract_query_entities(query)
            if not entities:
                return self.search_subgraph(query, user_id, depth)

            graph = self._get_user_graph(user_id)
            if graph.number_of_nodes() == 0:
                return ""

            matched_entities = []
            for entity in entities:
                if graph.has_node(entity):
                    matched_entities.append(entity)
                else:
                    for node in graph.nodes():
                        if entity.lower() in node.lower() or node.lower() in entity.lower():
                            matched_entities.append(node)
                            break

            if not matched_entities:
                return ""

            visited_nodes, visited_edges = set(), set()
            queue = deque()
            for entity in matched_entities:
                queue.append((entity, 0))
                visited_nodes.add(entity)

            while queue:
                current, d = queue.popleft()
                if d >= depth:
                    continue
                for successor in graph.successors(current):
                    edge_key = (current, successor)
                    if edge_key not in visited_edges:
                        visited_edges.add(edge_key)
                    if successor not in visited_nodes:
                        visited_nodes.add(successor)
                        queue.append((successor, d + 1))
                for predecessor in graph.predecessors(current):
                    edge_key = (predecessor, current)
                    if edge_key not in visited_edges:
                        visited_edges.add(edge_key)
                    if predecessor not in visited_nodes:
                        visited_nodes.add(predecessor)
                        queue.append((predecessor, d + 1))

            descriptions = []
            for u, v in visited_edges:
                relation = graph.edges[u, v].get("relation", "相关")
                descriptions.append(f"{u} —[{relation}]→ {v}")

            if not descriptions:
                return ""
            result = "【知识图谱检索结果】：\n" + "\n".join(f"- {d}" for d in descriptions)
            return result
        except Exception as e:
            logger.warning(f"NetworkX async search failed, falling back to sync: {e}")
            return self.search_subgraph(query, user_id, depth)

    def _fuzzy_match_entities(self, query: str, graph: nx.DiGraph) -> List[str]:
        query_lower = query.lower()
        keywords = [w.strip() for w in re.split(r'[，,。.？?！!；;：:\s]+', query) if len(w.strip()) > 1]
        matched = []
        for node in graph.nodes():
            node_lower = node.lower()
            if node_lower in query_lower or query_lower in node_lower:
                matched.append(node)
                continue
            for kw in keywords:
                if kw.lower() in node_lower or node_lower in kw.lower():
                    matched.append(node)
                    break
        return matched[:5]

    async def extract_query_entities(self, query: str) -> List[str]:
        if not self.ai_client or not query:
            return []
        try:
            messages = [
                {"role": "system", "content": PromptManager.get_prompt("graph_engine_extract_query_entities")},
                {"role": "user", "content": query},
            ]
            response = await self.ai_client.acall_api(messages, max_tokens=2048)
            if response and response.strip():
                cleaned = response.strip()
                json_match = re.search(r'\[.*?\]', cleaned, re.DOTALL)
                if json_match:
                    try:
                        parsed = json.loads(json_match.group())
                        if isinstance(parsed, list):
                            return [str(e).strip() for e in parsed if str(e).strip()][:5]
                    except json.JSONDecodeError:
                        pass
                entities = [e.strip() for e in cleaned.split(",") if e.strip()]
                return entities[:5]
        except Exception as e:
            logger.warning(f"Entity extraction from query failed: {e}")
        return []

    def get_stats(self, user_id: str = "") -> Dict[str, Any]:
        if user_id:
            graph = self._get_user_graph(user_id)
            return {"user_id": user_id[:8] + "...", "nodes": graph.number_of_nodes(), "edges": graph.number_of_edges()}
        total_nodes = sum(g.number_of_nodes() for g in self._graphs.values())
        total_edges = sum(g.number_of_edges() for g in self._graphs.values())
        return {"users": len(self._graphs), "total_nodes": total_nodes, "total_edges": total_edges}

    def get_graph_data(self, user_id: str, center_node: str = "", depth: int = 2, max_nodes: int = 80) -> Dict[str, Any]:
        graph = self._get_user_graph(user_id)
        logger.info(f"[NetworkX] get_graph_data: user={user_id[:8]}..., {graph.number_of_nodes()} nodes / {graph.number_of_edges()} edges, center='{center_node}'")
        if graph.number_of_nodes() == 0:
            return {"nodes": [], "links": [], "total_nodes": 0, "total_edges": 0}

        if center_node:
            subgraph_nodes = set()
            queue = deque()
            matched = None
            if center_node in graph:
                matched = center_node
            else:
                for node in graph.nodes():
                    if center_node.lower() in node.lower():
                        matched = node
                        break
            if matched:
                queue.append((matched, 0))
                subgraph_nodes.add(matched)
                while queue and len(subgraph_nodes) < max_nodes:
                    node, d = queue.popleft()
                    if d < depth:
                        for neighbor in list(graph.successors(node)) + list(graph.predecessors(node)):
                            if neighbor not in subgraph_nodes:
                                subgraph_nodes.add(neighbor)
                                queue.append((neighbor, d + 1))
            else:
                degree_sorted = sorted(graph.degree(), key=lambda x: x[1], reverse=True)
                subgraph_nodes = set(n for n, _ in degree_sorted[:max_nodes])
        else:
            if graph.number_of_nodes() <= max_nodes:
                subgraph_nodes = set(graph.nodes())
            else:
                degree_sorted = sorted(graph.degree(), key=lambda x: x[1], reverse=True)
                subgraph_nodes = set(n for n, _ in degree_sorted[:max_nodes])

        nodes = []
        for node_id in subgraph_nodes:
            attrs = dict(graph.nodes[node_id])
            nodes.append({"id": node_id, "category": attrs.get("type", "concept"), "sources": attrs.get("sources", [])})

        links = []
        for u, v, data in graph.edges(data=True):
            if u in subgraph_nodes and v in subgraph_nodes:
                links.append({"source": u, "target": v, "relation": data.get("relation", "")})

        return {"nodes": nodes, "links": links, "edges": links, "total_nodes": graph.number_of_nodes(), "total_edges": graph.number_of_edges()}

    def get_node_detail(self, user_id: str, node_id: str) -> Dict[str, Any]:
        graph = self._get_user_graph(user_id)
        if node_id not in graph:
            for node in graph.nodes():
                if node_id.lower() in node.lower():
                    node_id = node
                    break
            else:
                return {"error": "Node not found"}

        attrs = dict(graph.nodes[node_id])
        neighbors = []
        for pred in graph.predecessors(node_id):
            rel = graph.edges[pred, node_id].get("relation", "")
            neighbors.append({"id": pred, "relation": f"—[{rel}]→", "direction": "in"})
        for succ in graph.successors(node_id):
            rel = graph.edges[node_id, succ].get("relation", "")
            neighbors.append({"id": succ, "relation": f"—[{rel}]→", "direction": "out"})

        return {"id": node_id, "category": attrs.get("type", "concept"), "sources": attrs.get("sources", []), "neighbors": neighbors}

    def search_subgraph_for_viz(self, user_id: str, keyword: str, depth: int = 1, max_nodes: int = 80) -> Dict[str, Any]:
        graph = self._get_user_graph(user_id)
        if graph.number_of_nodes() == 0:
            return {"nodes": [], "links": []}

        matched_nodes = set()
        if keyword:
            kw_lower = keyword.lower()
            for node in graph.nodes():
                if kw_lower in node.lower() or node.lower() in kw_lower:
                    matched_nodes.add(node)

        if keyword and not matched_nodes:
            return {"nodes": [], "links": [], "message": f"未找到与 '{keyword}' 相关的实体"}

        subgraph_nodes = set()
        queue = deque()
        if matched_nodes:
            for node in matched_nodes:
                queue.append((node, 0))
                subgraph_nodes.add(node)
        else:
            if graph.number_of_nodes() <= max_nodes:
                subgraph_nodes = set(graph.nodes())
            else:
                degree_sorted = sorted(graph.degree(), key=lambda x: x[1], reverse=True)
                subgraph_nodes = set(n for n, _ in degree_sorted[:max_nodes])

        while queue and len(subgraph_nodes) < max_nodes:
            current, d = queue.popleft()
            if d >= depth:
                continue
            for neighbor in list(graph.successors(current)) + list(graph.predecessors(current)):
                if neighbor not in subgraph_nodes:
                    subgraph_nodes.add(neighbor)
                    queue.append((neighbor, d + 1))

        nodes = []
        for node_id in subgraph_nodes:
            attrs = dict(graph.nodes[node_id])
            degree = graph.degree(node_id)
            nodes.append({"id": node_id, "name": node_id, "val": max(5, min(30, 5 + degree * 3)), "category": attrs.get("type", "entity"), "sources": attrs.get("sources", [])})

        links = []
        for u, v, data in graph.edges(data=True):
            if u in subgraph_nodes and v in subgraph_nodes:
                links.append({"source": u, "target": v, "name": data.get("relation", "")})

        return {"nodes": nodes, "links": links}

    def get_node_sources(self, user_id: str, node_id: str) -> Dict[str, Any]:
        graph = self._get_user_graph(user_id)
        if node_id not in graph:
            for node in graph.nodes():
                if node_id.lower() in node.lower():
                    node_id = node
                    break
            else:
                return {"error": "Node not found", "id": node_id}

        attrs = dict(graph.nodes[node_id])
        return {"id": node_id, "category": attrs.get("type", "entity"), "sources": attrs.get("sources", []), "source_texts": attrs.get("source_texts", [])}

    def retrieve_subgraph(self, query_entities: List[str], depth: int = 1) -> str:
        logger.warning("retrieve_subgraph() is deprecated, use search_subgraph(query, user_id, depth) instead")
        return ""


# ═══════════════════════════════════════════════════════════════════════
#  Neo4j 引擎 (工业级)
# ═══════════════════════════════════════════════════════════════════════

class Neo4jGraphEngine:
    """
    基于 Neo4j 的 GraphRAG 引擎

    核心优势:
      - MERGE 动态融合：相同概念自动汇聚成超级节点
      - 多进程一致：不再有内存/磁盘脑裂问题
      - ON MATCH 追加 source_id：保留所有文献来源
    """

    def __init__(self, uri: str = "", user: str = "", password: str = "", ai_client=None):
        self.ai_client = ai_client
        self._uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self._user = user or os.getenv("NEO4J_USER", "neo4j")
        self._password = password or os.getenv("NEO4J_PASSWORD", "12345678")

        try:
            from neo4j import GraphDatabase
            self._driver = GraphDatabase.driver(self._uri, auth=(self._user, self._password))
            # 验证连接
            self._driver.verify_connectivity()
            logger.info(f"Neo4jGraphEngine initialized | uri={self._uri}")
            # 创建索引（幂等）
            self._ensure_indexes()
        except Exception as e:
            logger.error(f"Neo4j connection failed: {e}")
            raise

    def _ensure_indexes(self):
        """创建约束和索引（幂等操作）"""
        with self._driver.session() as session:
            # 唯一性约束（也自动创建索引）
            try:
                session.run(
                    "CREATE CONSTRAINT concept_user_name IF NOT EXISTS "
                    "FOR (n:Concept) REQUIRE (n.user_id, n.name) IS UNIQUE"
                )
            except Exception as e:
                logger.debug(f"Constraint creation skipped (may already exist): {e}")

            # 全文索引（用于模糊搜索）
            try:
                session.run(
                    "CREATE FULLTEXT INDEX concept_name_search IF NOT EXISTS "
                    "FOR (n:Concept) ON EACH [n.name] "
                    "OPTIONS {indexConfig: {`fulltext.analyzer`: 'standard'}}"
                )
            except Exception as e:
                logger.debug(f"Fulltext index creation skipped: {e}")

    def close(self):
        if self._driver:
            self._driver.close()

    # ── 写入 ──

    def add_triplets(self, triplets: List[Dict[str, str]], user_id: str, source: str = "", source_text: str = "", source_files: Optional[List[str]] = None):
        """
        写入三元组到 Neo4j 图谱。

        Args:
            triplets: 三元组列表 [{"head": "...", "relation": "...", "tail": "..."}]
            user_id: 用户 ID（隔离键）
            source: 具体来源标识（如 "01.数据结构.pdf" 或 "wikilink_backfill:数据结构.md"）
            source_text: 来源文本摘要
            source_files: 原始文件名列表（如 ["01.数据结构.pdf"]），用于级联删除时的精确匹配。
                          无论 source 是什么格式，source_files 始终存原始上传文件名。
        """
        if not user_id:
            logger.error("安全拦截: add_triplets 拒绝无 user_id 的图谱写入")
            raise PermissionError("图谱写入被拒绝: 必须提供 user_id (用户隔离策略)")

        # 如果未传 source_files，从 source 推导（向后兼容）
        if source_files is None:
            source_files = [source] if source else []

        added_nodes = 0
        added_edges = 0

        with self._driver.session() as session:
            for t in triplets:
                head = t.get("head", "").strip()
                relation = t.get("relation", "").strip()
                tail = t.get("tail", "").strip()
                if not head or not relation or not tail:
                    continue

                # 清理 relation 类型名（Cypher 关系类型不允许特殊字符）
                rel_type = _sanitize_rel_type(relation)

                result = session.run(
                    """
                    // MERGE source node - 动态融合
                    MERGE (source:Concept {user_id: $user_id, name: $source_name})
                    ON CREATE SET source.type = 'entity',
                                  source.sources = CASE WHEN $source <> '' THEN [$source] ELSE [] END,
                                  source.source_files = $source_files,
                                  source.source_texts = CASE WHEN $source_text <> '' THEN [$source_text] ELSE [] END
                    ON MATCH SET  source.sources = CASE WHEN $source <> '' AND NOT $source IN source.sources THEN source.sources + $source ELSE source.sources END,
                                  source.source_files = CASE WHEN size(source.source_files) = 0 THEN $source_files
                                                              ELSE [x IN source.source_files WHERE NOT x IN $source_files] + $source_files END,
                                  source.source_texts = CASE WHEN $source_text <> '' AND NOT $source_text IN source.source_texts THEN source.source_texts + $source_text ELSE source.source_texts END

                    // MERGE target node - 动态融合
                    MERGE (target:Concept {user_id: $user_id, name: $target_name})
                    ON CREATE SET target.type = 'entity',
                                  target.sources = CASE WHEN $source <> '' THEN [$source] ELSE [] END,
                                  target.source_files = $source_files,
                                  target.source_texts = CASE WHEN $source_text <> '' THEN [$source_text] ELSE [] END
                    ON MATCH SET  target.sources = CASE WHEN $source <> '' AND NOT $source IN target.sources THEN target.sources + $source ELSE target.sources END,
                                  target.source_files = CASE WHEN size(target.source_files) = 0 THEN $source_files
                                                              ELSE [x IN target.source_files WHERE NOT x IN $source_files] + $source_files END,
                                  target.source_texts = CASE WHEN $source_text <> '' AND NOT $source_text IN target.source_texts THEN target.source_texts + $source_text ELSE target.source_texts END

                    // MERGE relationship
                    MERGE (source)-[r:RELATES_TO {type: $rel_type}]->(target)
                    ON CREATE SET r.relation = $relation,
                                  r.source_files = $source_files
                    ON MATCH SET  r.relation = CASE WHEN NOT $relation IN r.relation THEN r.relation + '; ' + $relation ELSE r.relation END,
                                  r.source_files = CASE WHEN size(r.source_files) = 0 THEN $source_files
                                                         ELSE [x IN r.source_files WHERE NOT x IN $source_files] + $source_files END

                    RETURN source, target, r
                    """,
                    user_id=user_id,
                    source_name=head,
                    target_name=tail,
                    rel_type=rel_type,
                    relation=relation,
                    source=source or "",
                    source_files=source_files,
                    source_text=(source_text[:500] if source_text else ""),
                )
                summary = result.consume().counters
                if summary.nodes_created > 0:
                    added_nodes += summary.nodes_created
                if summary.relationships_created > 0:
                    added_edges += summary.relationships_created

        logger.info(
            f"🔒 Neo4j user {user_id[:8]}...: added {added_nodes} nodes, {added_edges} edges "
            f"(triplets={len(triplets)}, source_files={source_files})"
        )

    def _find_wiki_pages_for_source(self, user_id: str, source_filename: str) -> list:
        """
        扫描 wiki_pages 目录，找到由指定源文件生成的所有 wiki 页面名。
        通过读取 frontmatter 中的 source_id 字段匹配。

        Args:
            user_id: 用户 ID
            source_filename: 原始文件名（如 "01.数据结构.pdf"）

        Returns:
            页面名列表（如 ["数据结构__Part1_", "数据结构基础__Part1_"]）
        """
        import os as _os
        import re as _re

        wiki_dir = _os.path.join("wiki_pages", user_id.replace("-", "_"))
        if not _os.path.isdir(wiki_dir):
            return []

        page_names = []
        # source_filename 的 base_name，用于模糊匹配
        base_name = _os.path.splitext(source_filename)[0]

        for fname in _os.listdir(wiki_dir):
            if not fname.endswith(".md"):
                continue
            fpath = _os.path.join(wiki_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read(2048)  # 只读前 2KB，frontmatter 通常在文件开头

                # 提取 frontmatter 中的 source_id
                fm_match = _re.search(r'^---\s*\n(.*?)\n---', content, _re.DOTALL)
                if fm_match:
                    fm_text = fm_match.group(1)
                    sid_match = _re.search(r'source_id:\s*["\']?(.+?)["\']?\s*$', fm_text, _re.MULTILINE)
                    if sid_match:
                        sid = sid_match.group(1).strip()
                        # 匹配：source_id 包含原始文件名
                        # 如 source_id="01.数据结构.pdf (Part1)" 匹配 source_filename="01.数据结构.pdf"
                        if source_filename in sid or base_name in sid:
                            page_name = fname[:-3]  # 去掉 .md 后缀
                            page_names.append(page_name)
            except Exception:
                continue

        return page_names

    def remove_document(self, user_id: str, source_id: str):
        """
        文档级联删除：从图谱中移除指定文档贡献的节点和边

        基于 source_files 列表精确匹配（写入时统一存入的原始文件名）。
        同时兼容旧数据（只有 sources 没有 source_files 的节点）。

        策略：
        1. 从节点和边的 source_files 列表中移除该文件名
        2. 同时从 sources 列表中移除相关变体（向后兼容旧数据）
        3. 删除 source_files 为空的边
        4. 删除 source_files 为空的孤立节点
        5. 再次清理孤儿节点

        注意：只操作 n.user_id = $user_id 的节点，不触碰 Java 微服务的静态节点（user_id IS NULL）。

        Args:
            user_id: 用户 ID
            source_id: 文档文件名（如 "01.数据结构.pdf"）
        """
        if not user_id:
            logger.error("安全拦截: remove_document 拒绝无 user_id 的操作")
            return

        with self._driver.session() as session:
            # Step 0: 查找实际所属的 user_id（兼容 user_id 格式不一致：整数 vs UUID）
            # 优先按 source_files 匹配（新数据），其次按 sources 匹配（旧数据）
            diag = session.run(
                """
                MATCH (n:Concept)
                WHERE n.user_id IS NOT NULL
                  AND (
                    ($source_id IN n.source_files)
                    OR ($source_id IN n.sources)
                    OR ANY(s IN n.sources WHERE s STARTS WITH $backfill_prefix)
                  )
                RETURN n.user_id AS uid, count(n) AS cnt
                """,
                source_id=source_id,
                backfill_prefix=f"wikilink_backfill:{os.path.splitext(source_id)[0]}",
            )
            source_matches = [(r["uid"], r["cnt"]) for r in diag]

            if source_matches:
                actual_uid = source_matches[0][0]
                if actual_uid != user_id:
                    logger.warning(
                        f"⚠️ Neo4j remove_document: 传入 user_id='{user_id}'，"
                        f"但 source='{source_id}' 实际属于 user_id='{actual_uid}'，自动修正"
                    )
                user_id = actual_uid
            else:
                logger.info(
                    f"ℹ️ Neo4j remove_document: source='{source_id}' 不存在于任何图谱节点中，无需删除"
                )
                return

            logger.info(f"🔒 Neo4j remove_document: 准备从图谱删除文件关联: {source_id}")

            # Step 1: 从节点的 source_files 和 sources 中移除该文件名
            result1 = session.run(
                """
                MATCH (n:Concept {user_id: $user_id})
                WHERE $source_id IN n.source_files
                   OR $source_id IN n.sources
                   OR ANY(s IN n.sources WHERE s STARTS WITH $backfill_prefix)
                // 从 source_files 中移除
                SET n.source_files = [x IN n.source_files WHERE x <> $source_id],
                    // 从 sources 中移除原始文件名和所有 wikilink_backfill 变体
                    n.sources = [x IN n.sources
                        WHERE x <> $source_id
                          AND NOT x STARTS WITH $backfill_prefix]
                RETURN count(n) AS updated
                """,
                user_id=user_id,
                source_id=source_id,
                backfill_prefix=f"wikilink_backfill:{os.path.splitext(source_id)[0]}",
            )
            updated_nodes = result1.single()["updated"]

            # Step 1b: 从边的 source_files 中移除该文件名
            result1b = session.run(
                """
                MATCH (:Concept {user_id: $user_id})-[r:RELATES_TO]->(:Concept {user_id: $user_id})
                WHERE $source_id IN r.source_files
                SET r.source_files = [x IN r.source_files WHERE x <> $source_id]
                RETURN count(r) AS updated
                """,
                user_id=user_id,
                source_id=source_id,
            )
            updated_edges = result1b.single()["updated"]

            # Step 2: 删除 source_files 为空的边
            result2 = session.run(
                """
                MATCH (a:Concept {user_id: $user_id})-[r:RELATES_TO]->(b:Concept {user_id: $user_id})
                WHERE size(r.source_files) = 0
                DELETE r
                RETURN count(r) AS deleted
                """,
                user_id=user_id,
            )
            deleted_edges = result2.single()["deleted"]

            # Step 3: 删除 source_files 为空的孤立节点
            result3 = session.run(
                """
                MATCH (n:Concept {user_id: $user_id})
                WHERE size(n.source_files) = 0 AND NOT (n)--()
                DETACH DELETE n
                RETURN count(n) AS deleted
                """,
                user_id=user_id,
            )
            deleted_orphans = result3.single()["deleted"]

            # Step 4: 再次清理（Step 2 删边后可能产生新的孤立节点）
            result4 = session.run(
                """
                MATCH (n:Concept {user_id: $user_id})
                WHERE size(n.source_files) = 0 AND NOT (n)--()
                DETACH DELETE n
                RETURN count(n) AS deleted
                """,
                user_id=user_id,
            )
            deleted_orphans2 = result4.single()["deleted"]

            total_orphans = deleted_orphans + deleted_orphans2
            logger.info(
                f"🔒 Neo4j remove_document: user={user_id[:8]}..., source='{source_id}' | "
                f"updated_nodes={updated_nodes}, updated_edges={updated_edges}, "
                f"deleted_edges={deleted_edges}, deleted_orphans={total_orphans}"
            )

    # ── 查询 ──

    def get_graph_data(self, user_id: str, center_node: str = "", depth: int = 2, max_nodes: int = 80) -> Dict[str, Any]:
        logger.info(f"[Neo4j] get_graph_data: user={user_id[:8]}..., center='{center_node}'")

        with self._driver.session() as session:
            if center_node:
                # 先尝试精确匹配
                result = session.run(
                    """
                    MATCH (center:Concept {user_id: $user_id})
                    WHERE center.name = $center_node OR toLower(center.name) CONTAINS toLower($center_node)
                    CALL (center) {
                        WITH center
                        MATCH path = (center)-[:RELATES_TO*1..2]-(other:Concept {user_id: $user_id})
                        RETURN DISTINCT other
                        LIMIT $max_nodes
                    }
                    WITH center, collect(DISTINCT other) AS neighbors
                    WITH [center] + neighbors AS all_nodes
                    UNWIND all_nodes AS n
                    MATCH (n)-[r:RELATES_TO]-(m:Concept {user_id: $user_id})
                    WHERE m IN all_nodes
                    RETURN DISTINCT n, r, m
                    LIMIT 2000
                    """,
                    user_id=user_id,
                    center_node=center_node,
                    max_nodes=max_nodes,
                )
            else:
                # 全图查询（按度排序截断）
                result = session.run(
                    """
                    MATCH (n:Concept {user_id: $user_id})
                    OPTIONAL MATCH (n)-[r]-()
                    WITH n, count(r) AS degree
                    ORDER BY degree DESC
                    LIMIT $max_nodes
                    WITH collect(n) AS top_nodes
                    UNWIND top_nodes AS n
                    MATCH (n)-[r:RELATES_TO]-(m:Concept {user_id: $user_id})
                    WHERE m IN top_nodes
                    RETURN DISTINCT n, r, m
                    LIMIT 2000
                    """,
                    user_id=user_id,
                    max_nodes=max_nodes,
                )

            nodes_map = {}
            links = []
            for record in result:
                n_node = record["n"]
                m_node = record["m"]
                r_rel = record["r"]

                # 添加节点
                for neo_node in [n_node, m_node]:
                    nid = neo_node["name"]
                    if nid not in nodes_map:
                        nodes_map[nid] = {
                            "id": nid,
                            "category": neo_node.get("type", "concept"),
                            "sources": neo_node.get("sources", []),
                        }

                # 添加边
                links.append({
                    "source": n_node["name"],
                    "target": m_node["name"],
                    "relation": r_rel.get("relation", r_rel.get("type", "")),
                })

            # 去重 links
            seen_links = set()
            unique_links = []
            for link in links:
                key = (link["source"], link["target"], link["relation"])
                if key not in seen_links:
                    seen_links.add(key)
                    unique_links.append(link)

            # 总数统计
            total_result = session.run(
                "MATCH (n:Concept {user_id: $user_id}) RETURN count(n) AS total_nodes",
                user_id=user_id,
            )
            total_nodes = total_result.single()["total_nodes"] if total_result.peek() else len(nodes_map)

            total_edges_result = session.run(
                "MATCH (:Concept {user_id: $user_id})-[r:RELATES_TO]->(:Concept {user_id: $user_id}) RETURN count(r) AS total_edges",
                user_id=user_id,
            )
            total_edges = total_edges_result.single()["total_edges"] if total_edges_result.peek() else len(unique_links)

        logger.info(f"[Neo4j] get_graph_data: returning {len(nodes_map)} nodes, {len(unique_links)} links (total: {total_nodes} nodes, {total_edges} edges)")

        return {
            "nodes": list(nodes_map.values()),
            "links": unique_links,
            "edges": unique_links,
            "total_nodes": total_nodes,
            "total_edges": total_edges,
        }

    def get_node_detail(self, user_id: str, node_id: str) -> Dict[str, Any]:
        with self._driver.session() as session:
            # 精确匹配 → 模糊匹配
            result = session.run(
                """
                MATCH (n:Concept {user_id: $user_id})
                WHERE n.name = $node_id OR toLower(n.name) CONTAINS toLower($node_id)
                RETURN n
                LIMIT 1
                """,
                user_id=user_id,
                node_id=node_id,
            )
            record = result.single()
            if not record:
                return {"error": "Node not found"}

            n = record["n"]
            actual_name = n["name"]

            # 获取邻居
            neighbors_result = session.run(
                """
                MATCH (n:Concept {user_id: $user_id, name: $name})-[r:RELATES_TO]-(m:Concept {user_id: $user_id})
                RETURN m.name AS neighbor_name, r.relation AS relation, r.type AS rel_type,
                       CASE WHEN startNode(r) = m THEN 'in' ELSE 'out' END AS direction
                """,
                user_id=user_id,
                name=actual_name,
            )

            neighbors = []
            for rec in neighbors_result:
                direction = rec["direction"]
                rel = rec["relation"] or rec["rel_type"] or ""
                neighbors.append({
                    "id": rec["neighbor_name"],
                    "relation": f"—[{rel}]→",
                    "direction": direction,
                })

            return {
                "id": actual_name,
                "category": n.get("type", "concept"),
                "sources": n.get("sources", []),
                "neighbors": neighbors,
            }

    def get_node_sources(self, user_id: str, node_id: str) -> Dict[str, Any]:
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (n:Concept {user_id: $user_id})
                WHERE n.name = $node_id OR toLower(n.name) CONTAINS toLower($node_id)
                RETURN n
                LIMIT 1
                """,
                user_id=user_id,
                node_id=node_id,
            )
            record = result.single()
            if not record:
                return {"error": "Node not found", "id": node_id}

            n = record["n"]
            return {
                "id": n["name"],
                "category": n.get("type", "entity"),
                "sources": n.get("sources", []),
                "source_texts": n.get("source_texts", []),
            }

    def search_subgraph_for_viz(self, user_id: str, keyword: str, depth: int = 1, max_nodes: int = 80) -> Dict[str, Any]:
        if not keyword:
            return self.get_graph_data(user_id, center_node="", depth=depth, max_nodes=max_nodes)

        with self._driver.session() as session:
            # 模糊搜索匹配节点
            result = session.run(
                """
                MATCH (center:Concept {user_id: $user_id})
                WHERE toLower(center.name) CONTAINS toLower($keyword)
                CALL (center) {
                    WITH center
                    MATCH path = (center)-[:RELATES_TO*1..2]-(other:Concept {user_id: $user_id})
                    RETURN DISTINCT other
                    LIMIT $max_nodes
                }
                WITH center, collect(DISTINCT other) AS neighbors
                WITH [center] + neighbors AS all_nodes
                UNWIND all_nodes AS n
                MATCH (n)-[r:RELATES_TO]-(m:Concept {user_id: $user_id})
                WHERE m IN all_nodes
                RETURN DISTINCT n, r, m
                LIMIT 2000
                """,
                user_id=user_id,
                keyword=keyword,
                max_nodes=max_nodes,
            )

            nodes_map = {}
            links = []
            for record in result:
                n_node = record["n"]
                m_node = record["m"]
                r_rel = record["r"]

                for neo_node in [n_node, m_node]:
                    nid = neo_node["name"]
                    if nid not in nodes_map:
                        nodes_map[nid] = {
                            "id": nid,
                            "name": nid,
                            "val": 10,
                            "category": neo_node.get("type", "entity"),
                            "sources": neo_node.get("sources", []),
                        }

                links.append({
                    "source": n_node["name"],
                    "target": m_node["name"],
                    "name": r_rel.get("relation", r_rel.get("type", "")),
                })

            seen_links = set()
            unique_links = []
            for link in links:
                key = (link["source"], link["target"])
                if key not in seen_links:
                    seen_links.add(key)
                    unique_links.append(link)

            # 计算 val (degree)
            for nid in nodes_map:
                degree = sum(1 for l in unique_links if l["source"] == nid or l["target"] == nid)
                nodes_map[nid]["val"] = max(5, min(30, 5 + degree * 3))

        if not nodes_map:
            return {"nodes": [], "links": [], "message": f"未找到与 '{keyword}' 相关的实体"}

        return {"nodes": list(nodes_map.values()), "links": unique_links}

    def search_subgraph(self, query: str, user_id: str, depth: int = 2) -> str:
        if not user_id:
            return ""

        with self._driver.session() as session:
            # 模糊匹配
            result = session.run(
                """
                MATCH (center:Concept {user_id: $user_id})
                WHERE toLower(center.name) CONTAINS toLower($search_query)
                OR toLower($search_query) CONTAINS toLower(center.name)
                CALL (center) {
                    WITH center
                    MATCH path = (center)-[:RELATES_TO*1..2]-(other:Concept {user_id: $user_id})
                    RETURN DISTINCT other, relationships(path) AS rels
                    LIMIT 50
                }
                UNWIND rels AS r
                RETURN DISTINCT startNode(r).name AS from_name, endNode(r).name AS to_name, r.relation AS relation
                """,
                user_id=user_id,
                search_query=query,
            )

            descriptions = []
            for record in result:
                from_name = record["from_name"]
                to_name = record["to_name"]
                relation = record["relation"] or "相关"
                descriptions.append(f"{from_name} —[{relation}]→ {to_name}")

        if not descriptions:
            return ""
        result_text = "【知识图谱检索结果】：\n" + "\n".join(f"- {d}" for d in descriptions)
        logger.info(f"🔒 Neo4j search user {user_id[:8]}...: {len(descriptions)} edges found")
        return result_text

    async def search_subgraph_async(self, query: str, user_id: str, depth: int = 2) -> str:
        # Neo4j 版本直接用 Cypher 搜索，不需要 LLM 提取实体
        return self.search_subgraph(query, user_id, depth)

    async def extract_entities_and_relations(self, text: str) -> List[Dict[str, str]]:
        if not self.ai_client or not text or not text.strip():
            return []
        try:
            messages = [
                {"role": "system", "content": PromptManager.get_prompt("graph_engine_extract_triplets")},
                {"role": "user", "content": f"请从以下文本中提取实体关系三元组：\n\n{text[:8000]}"},
            ]
            response = await self.ai_client.acall_api(messages, max_tokens=8192)
            if not response or not response.strip():
                return []
            triplets = _extract_json_from_reasoning(response)
            if isinstance(triplets, list):
                valid = []
                for t in triplets:
                    if isinstance(t, dict) and t.get("head") and t.get("relation") and t.get("tail"):
                        valid.append({"head": str(t["head"]).strip(), "relation": str(t["relation"]).strip(), "tail": str(t["tail"]).strip()})
                return valid
            return []
        except Exception as e:
            logger.error(f"Graph extraction failed: {e}")
            return []

    async def extract_query_entities(self, query: str) -> List[str]:
        if not self.ai_client or not query:
            return []
        try:
            messages = [
                {"role": "system", "content": PromptManager.get_prompt("graph_engine_extract_query_entities")},
                {"role": "user", "content": query},
            ]
            response = await self.ai_client.acall_api(messages, max_tokens=2048)
            if response and response.strip():
                cleaned = response.strip()
                json_match = re.search(r'\[.*?\]', cleaned, re.DOTALL)
                if json_match:
                    try:
                        parsed = json.loads(json_match.group())
                        if isinstance(parsed, list):
                            return [str(e).strip() for e in parsed if str(e).strip()][:5]
                    except json.JSONDecodeError:
                        pass
                entities = [e.strip() for e in cleaned.split(",") if e.strip()]
                return entities[:5]
        except Exception as e:
            logger.warning(f"Entity extraction from query failed: {e}")
        return []

    def get_stats(self, user_id: str = "") -> Dict[str, Any]:
        with self._driver.session() as session:
            if user_id:
                result = session.run(
                    "MATCH (n:Concept {user_id: $user_id}) "
                    "OPTIONAL MATCH (:Concept {user_id: $user_id})-[r:RELATES_TO]->(:Concept {user_id: $user_id}) "
                    "RETURN count(DISTINCT n) AS nodes, count(DISTINCT r) AS edges",
                    user_id=user_id,
                )
                record = result.single()
                return {"user_id": user_id[:8] + "...", "nodes": record["nodes"], "edges": record["edges"]}

            result = session.run(
                "MATCH (n:Concept) RETURN count(DISTINCT n.user_id) AS users, count(n) AS total_nodes"
            )
            record = result.single()
            edges_result = session.run("MATCH ()-[r:RELATES_TO]->() RETURN count(r) AS total_edges")
            edges_record = edges_result.single()
            return {
                "users": record["users"],
                "total_nodes": record["total_nodes"],
                "total_edges": edges_record["total_edges"],
            }

    def retrieve_subgraph(self, query_entities: List[str], depth: int = 1) -> str:
        logger.warning("retrieve_subgraph() is deprecated, use search_subgraph(query, user_id, depth) instead")
        return ""


# ═══════════════════════════════════════════════════════════════════════
#  工厂函数 + Feature Flag
# ═══════════════════════════════════════════════════════════════════════

def create_graph_engine(ai_client=None, **kwargs) -> Any:
    """
    根据 GRAPH_ENGINE_TYPE 环境变量创建图谱引擎

    - 'neo4j' (默认): 尝试连接 Neo4j，失败则降级到 NetworkX
    - 'networkx': 直接使用 NetworkX + JSON
    """
    engine_type = os.getenv("GRAPH_ENGINE_TYPE", "neo4j").lower()

    if engine_type == "neo4j":
        try:
            engine = Neo4jGraphEngine(ai_client=ai_client, **kwargs)
            logger.info("✅ Graph engine: Neo4j (industrial mode)")
            # 自动迁移 NetworkX JSON 历史数据到 Neo4j
            _auto_migrate_json_to_neo4j(engine)
            return engine
        except Exception as e:
            logger.warning(f"⚠️ Neo4j connection failed: {e}")
            logger.warning("⚠️ Falling back to NetworkX engine (offline mode)")
            return NetworkXGraphEngine(ai_client=ai_client, **kwargs)

    logger.info("📦 Graph engine: NetworkX (offline mode)")
    return NetworkXGraphEngine(ai_client=ai_client, **kwargs)


def _auto_migrate_json_to_neo4j(neo4j_engine: Neo4jGraphEngine):
    """自动将 graph_data/ 目录下的 JSON 文件迁移到 Neo4j（幂等）"""
    if not os.path.exists(GRAPH_DB_DIR):
        return

    migrated_file = os.path.join(GRAPH_DB_DIR, ".neo4j_migrated")
    already_migrated = set()
    if os.path.exists(migrated_file):
        try:
            with open(migrated_file, "r") as f:
                already_migrated = set(f.read().strip().splitlines())
        except Exception:
            pass

    import glob as glob_mod
    json_files = glob_mod.glob(os.path.join(GRAPH_DB_DIR, "graph_kb_*.json"))
    new_migrations = []

    for json_path in json_files:
        fname = os.path.basename(json_path)
        if fname in already_migrated:
            continue

        # 从文件名提取 user_id: graph_kb_22.json → "22", graph_kb_62b1f609_4628_...json → "62b1f609-4628-..."
        raw_id = fname.replace("graph_kb_", "").replace(".json", "")
        user_id = raw_id.replace("_", "-")

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            nodes = data.get("nodes", [])
            edges = data.get("edges", [])
            if not nodes:
                new_migrations.append(fname)
                continue

            with neo4j_engine._driver.session() as session:
                for node in nodes:
                    nid = node["id"]
                    attrs = node.get("attrs", {})
                    sources = attrs.get("sources", [])
                    source_texts = attrs.get("source_texts", [])
                    ntype = attrs.get("type", "entity")
                    session.run(
                        """MERGE (n:Concept {user_id: $uid, name: $name})
                        ON CREATE SET n.type = $ntype, n.sources = $sources, n.source_texts = $st
                        ON MATCH SET n.sources = CASE WHEN size($sources) > 0 THEN $sources ELSE n.sources END,
                                     n.source_texts = CASE WHEN size($st) > 0 THEN $st ELSE n.source_texts END""",
                        uid=user_id, name=nid, ntype=ntype, sources=sources, st=source_texts,
                    )
                for edge in edges:
                    src, tgt = edge["source"], edge["target"]
                    relation = edge.get("relation", "")
                    rel_type = _sanitize_rel_type(relation) if relation else "RELATES_TO"
                    session.run(
                        """MATCH (s:Concept {user_id: $uid, name: $src})
                        MATCH (t:Concept {user_id: $uid, name: $tgt})
                        MERGE (s)-[r:RELATES_TO {type: $rt}]->(t)
                        ON CREATE SET r.relation = $rel
                        ON MATCH SET r.relation = $rel""",
                        uid=user_id, src=src, tgt=tgt, rt=rel_type, rel=relation,
                    )

            logger.info(f"📦 Migrated {fname}: {len(nodes)} nodes, {len(edges)} edges → Neo4j")
            new_migrations.append(fname)
        except Exception as e:
            logger.warning(f"Migration failed for {fname}: {e}")

    if new_migrations:
        try:
            with open(migrated_file, "a") as f:
                for fname in new_migrations:
                    f.write(fname + "\n")
        except Exception:
            pass


# 向后兼容：GraphRAGEngine 是工厂函数返回的实例的别名
GraphRAGEngine = create_graph_engine


# ═══════════════════════════════════════════════════════════════════════
#  工具函数
# ═══════════════════════════════════════════════════════════════════════

def _sanitize_rel_type(relation: str) -> str:
    """将关系名转换为合法的 Neo4j 关系类型（大写、下划线、仅字母数字）"""
    # 替换中文和特殊字符
    cleaned = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff]', '_', relation)
    cleaned = re.sub(r'_+', '_', cleaned).strip('_')
    if not cleaned:
        cleaned = "RELATES_TO"
    # Neo4j 关系类型建议大写
    return cleaned.upper()[:64]


def _extract_json_from_reasoning(text: str):
    if not text or not text.strip():
        return []

    cleaned = text.strip()
    cleaned = re.sub(r'<think[^>]*>.*?</think\s*>', '', cleaned, flags=re.DOTALL)
    cleaned = cleaned.strip()

    match = re.search(r'```json\s*(.*?)\s*```', cleaned, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        match = re.search(r'```\s*(.*?)\s*```', cleaned, re.DOTALL)
        if match:
            json_str = match.group(1)
        else:
            bracket_match = re.search(r'(\[.*\])', cleaned, re.DOTALL)
            if bracket_match:
                json_str = bracket_match.group(1)
            else:
                start_idx = cleaned.find('[')
                end_idx = cleaned.rfind(']')
                if start_idx != -1 and end_idx != -1 and start_idx <= end_idx:
                    json_str = cleaned[start_idx:end_idx + 1]
                else:
                    start_idx = cleaned.find('{')
                    end_idx = cleaned.rfind('}')
                    if start_idx != -1 and end_idx != -1 and start_idx <= end_idx:
                        json_str = cleaned[start_idx:end_idx + 1]
                    else:
                        json_str = cleaned

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse failed after reasoning cleanup: {e} | raw: {json_str[:200]}")
        return []
