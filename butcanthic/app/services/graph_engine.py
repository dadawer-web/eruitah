"""
GraphRAG 引擎 - 基于 NetworkX 和大模型的轻量级知识图谱

技术选型:
  - 图数据库: NetworkX DiGraph (内存 + JSON 持久化)
  - 实体关系抽取: 大模型结构化输出 (三元组)
  - 子图检索: BFS 广度优先搜索

用户隔离策略:
  - 每个用户拥有独立的图谱 (graph_kb_{user_id}.json)
  - 内存中按 user_id 缓存各自的 DiGraph 实例
  - 检索时仅查询当前用户的图谱，防止越权
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


class GraphRAGEngine:

    def __init__(self, persist_dir: str = "", ai_client=None):
        self.persist_dir = persist_dir or GRAPH_DB_DIR
        self.ai_client = ai_client
        self._graphs: Dict[str, nx.DiGraph] = {}
        os.makedirs(self.persist_dir, exist_ok=True)
        logger.info(f"GraphRAGEngine initialized | persist_dir={self.persist_dir}")

    def _user_graph_path(self, user_id: str) -> str:
        safe_id = user_id.replace("-", "_")
        return os.path.join(self.persist_dir, f"graph_kb_{safe_id}.json")

    def _get_user_graph(self, user_id: str) -> nx.DiGraph:
        if user_id in self._graphs:
            return self._graphs[user_id]
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
                logger.info(f"Graph loaded for user {user_id[:8]}...: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
            except Exception as e:
                logger.warning(f"Failed to load graph for user {user_id[:8]}...: {e}")
        self._graphs[user_id] = graph
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
            logger.info(f"Graph saved for user {user_id[:8]}...: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
        except Exception as e:
            logger.error(f"Failed to save graph for user {user_id[:8]}...: {e}")

    async def extract_entities_and_relations(self, text: str) -> List[Dict[str, str]]:
        if not self.ai_client or not text or not text.strip():
            return []

        try:
            messages = [
                {
                    "role": "system",
                    "content": PromptManager.get_prompt("graph_engine_extract_triplets"),
                },
                {
                    "role": "user",
                    "content": f"请从以下文本中提取实体关系三元组：\n\n{text[:8000]}",
                },
            ]

            response = await self.ai_client.acall_api(messages, max_tokens=8192)

            if not response or not response.strip():
                return []

            triplets = _extract_json_from_reasoning(response)

            if isinstance(triplets, list):
                valid = []
                for t in triplets:
                    if isinstance(t, dict) and t.get("head") and t.get("relation") and t.get("tail"):
                        valid.append({
                            "head": str(t["head"]).strip(),
                            "relation": str(t["relation"]).strip(),
                            "tail": str(t["tail"]).strip(),
                        })
                return valid

            return []

        except json.JSONDecodeError:
            logger.warning("Graph extraction: LLM output is not valid JSON")
            return []
        except Exception as e:
            logger.error(f"Graph extraction failed: {e}")
            return []

    def add_triplets(self, triplets: List[Dict[str, str]], user_id: str, source: str = ""):
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
                graph.add_node(head, type="entity", sources=[])
                added_nodes += 1
            if not graph.has_node(tail):
                graph.add_node(tail, type="entity", sources=[])
                added_nodes += 1
            if source:
                for node_name in [head, tail]:
                    sources = graph.nodes[node_name].get("sources", [])
                    if source not in sources:
                        sources.append(source)
                        graph.nodes[node_name]["sources"] = sources
            if graph.has_edge(head, tail):
                existing = graph.edges[head, tail].get("relation", "")
                if existing and existing != relation:
                    graph.edges[head, tail]["relation"] = f"{existing}; {relation}"
            else:
                graph.add_edge(head, tail, relation=relation)
                added_edges += 1

        if added_edges > 0:
            self._save_user_graph(user_id)
            logger.info(
                f"🔒 Graph for user {user_id[:8]}...: added {added_nodes} nodes, {added_edges} edges | "
                f"total: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges"
            )

    def search_subgraph(self, query: str, user_id: str, depth: int = 2) -> str:
        if not user_id:
            logger.error("安全拦截: search_subgraph 拒绝无 user_id 的图谱检索")
            return ""

        graph = self._get_user_graph(user_id)

        if graph.number_of_nodes() == 0:
            return ""

        query_entities = self._fuzzy_match_entities(query, graph)

        if not query_entities:
            return ""

        visited_nodes = set()
        visited_edges = set()
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
        logger.info(
            f"🔒 GraphRAG search for user {user_id[:8]}...: "
            f"query_entities={query_entities} → {len(visited_nodes)} nodes, {len(visited_edges)} edges"
        )
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

            visited_nodes = set()
            visited_edges = set()
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
            logger.info(
                f"🔒 GraphRAG async search for user {user_id[:8]}...: "
                f"entities={matched_entities} → {len(visited_nodes)} nodes, {len(visited_edges)} edges"
            )
            return result

        except Exception as e:
            logger.warning(f"GraphRAG async search failed, falling back to sync: {e}")
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
                {
                    "role": "system",
                    "content": PromptManager.get_prompt("graph_engine_extract_query_entities"),
                },
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
            return {
                "user_id": user_id[:8] + "...",
                "nodes": graph.number_of_nodes(),
                "edges": graph.number_of_edges(),
            }
        total_nodes = sum(g.number_of_nodes() for g in self._graphs.values())
        total_edges = sum(g.number_of_edges() for g in self._graphs.values())
        return {
            "users": len(self._graphs),
            "total_nodes": total_nodes,
            "total_edges": total_edges,
        }

    def retrieve_subgraph(self, query_entities: List[str], depth: int = 1) -> str:
        logger.warning("retrieve_subgraph() is deprecated, use search_subgraph(query, user_id, depth) instead")
        return ""


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
