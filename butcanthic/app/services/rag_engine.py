"""
RAG 引擎 - 三路混合检索 + 重排序 (Hybrid Search + GraphRAG + Reranker) 企业级架构
用户级 Collection 物理隔离: 每个用户拥有独立 Chroma 集合 (kb_user_{user_id})

技术选型:
  - 向量数据库: ChromaDB (嵌入式，零运维)
  - Embedding: BGE-m3 via SiliconFlow (OpenAI 兼容接口)
  - 稀疏检索: BM25 + jieba 中文分词
  - 图谱检索: NetworkX + LLM 实体关系抽取 (GraphRAG)
  - 重排序: BGE-Reranker-V2-m3 via SiliconFlow Rerank API
  - 三路召回: 向量 Top10 + BM25 Top10 + GraphRAG → 去重合并 → Rerank Top5
"""

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb
import jieba
import requests
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)


class RAGEngine:

    def __init__(
        self,
        persist_directory: str = "chroma_db",
        embedding_api_key: Optional[str] = None,
        embedding_base_url: str = "https://api.siliconflow.cn/v1",
        embedding_model: str = "BAAI/bge-m3",
        embedding_dimension: int = 1024,
        reranker_api_key: Optional[str] = None,
        reranker_base_url: str = "https://api.siliconflow.cn/v1",
        reranker_model: str = "BAAI/bge-reranker-v2-m3",
        ai_client=None,
    ):
        self.persist_directory = persist_directory
        self.embedding_model = embedding_model
        self.embedding_dimension = embedding_dimension
        self.reranker_model = reranker_model
        self.reranker_base_url = reranker_base_url
        self._reranker_api_key = reranker_api_key or embedding_api_key or os.getenv("SILICONFLOW_API_KEY", "")
        self._ai_client = ai_client

        self._init_chroma(persist_directory)
        self._init_embeddings(embedding_api_key, embedding_base_url, embedding_model)
        self._collection_cache: Dict[str, chromadb.Collection] = {}

        self._bm25_corpus: List[str] = []
        self._bm25_tokenized: List[List[str]] = []
        self._bm25_engine: Optional[BM25Okapi] = None
        self._bm25_doc_map: Dict[int, Dict[str, Any]] = {}

        self._graph_engine = None
        try:
            from app.services.graph_engine import GraphRAGEngine
            self._graph_engine = GraphRAGEngine(ai_client=ai_client)
        except Exception as e:
            logger.warning(f"GraphRAGEngine init skipped: {e}")

        logger.info(
            f"RAGEngine initialized | db={persist_directory} | model={embedding_model} | "
            f"dim={embedding_dimension} | reranker={reranker_model} | hybrid=ON | graph={'ON' if self._graph_engine else 'OFF'}"
        )

    def _init_chroma(self, persist_directory: str):
        os.makedirs(persist_directory, exist_ok=True)
        self._chroma_client = chromadb.PersistentClient(path=persist_directory)
        try:
            self._chroma_client.heartbeat()
        except Exception as e:
            logger.error(f"ChromaDB init failed: {e}")
            raise

    def _init_embeddings(self, api_key: Optional[str], base_url: str, model: str):
        resolved_key = api_key or os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        if not resolved_key:
            logger.warning("No embedding API key found. Set DASHSCOPE_API_KEY env var.")
        else:
            logger.info(
                f"Embedding init | base_url={base_url} | model={model} | "
                f"api_key=***{resolved_key[-4:]}"
            )

        try:
            self._embeddings = OpenAIEmbeddings(
                api_key=resolved_key,
                base_url=base_url,
                model=model,
                check_embedding_ctx_length=False,
            )
        except Exception as e:
            logger.error(f"Embedding init failed: {e}")
            raise

    def _tokenize_chinese(self, text: str) -> List[str]:
        tokens = jieba.lcut(text)
        return [t.strip() for t in tokens if t.strip() and len(t.strip()) > 0]

    def _build_bm25_index(self):
        if not self._bm25_corpus:
            self._bm25_engine = None
            return
        self._bm25_tokenized = [self._tokenize_chinese(doc) for doc in self._bm25_corpus]
        self._bm25_engine = BM25Okapi(self._bm25_tokenized)
        logger.info(f"BM25 index built | corpus_size={len(self._bm25_corpus)}")

    def _add_to_bm25(self, text: str, metadata: Dict[str, Any]):
        idx = len(self._bm25_corpus)
        self._bm25_corpus.append(text)
        self._bm25_doc_map[idx] = metadata
        self._build_bm25_index()

    def _add_batch_to_bm25(self, texts: List[str], metadatas: List[Dict[str, Any]]):
        start_idx = len(self._bm25_corpus)
        for i, (text, meta) in enumerate(zip(texts, metadatas)):
            idx = start_idx + i
            self._bm25_corpus.append(text)
            self._bm25_doc_map[idx] = meta
        self._build_bm25_index()

    def _bm25_search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        if not self._bm25_engine or not self._bm25_corpus:
            return []
        tokenized_query = self._tokenize_chinese(query)
        scores = self._bm25_engine.get_scores(tokenized_query)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                results.append({
                    "content": self._bm25_corpus[idx],
                    "metadata": self._bm25_doc_map.get(idx, {}),
                    "score": float(scores[idx]),
                    "collection": "bm25",
                    "source": "sparse",
                })
        return results

    def _rerank_documents(self, query: str, docs: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
        if not docs or not self._reranker_api_key:
            logger.warning("Reranker skipped: no docs or no API key")
            return docs[:top_k]

        documents = [doc.get("content", "") for doc in docs]
        if not any(documents):
            return docs[:top_k]

        try:
            url = f"{self.reranker_base_url}/rerank"
            payload = {
                "model": self.reranker_model,
                "query": query,
                "documents": documents,
                "top_n": min(top_k, len(documents)),
                "return_documents": False,
            }
            headers = {
                "Authorization": f"Bearer {self._reranker_api_key}",
                "Content-Type": "application/json",
            }

            response = requests.post(url, json=payload, headers=headers, timeout=30)

            if response.status_code != 200:
                logger.warning(f"Reranker API failed: {response.status_code} - {response.text[:200]}")
                return docs[:top_k]

            result = response.json()
            ranked_results = []
            for item in result.get("results", []):
                idx = item.get("index", 0)
                score = item.get("relevance_score", 0.0)
                if idx < len(docs):
                    doc = docs[idx].copy()
                    doc["rerank_score"] = score
                    doc["source"] = "hybrid_reranked"
                    ranked_results.append(doc)

            ranked_results.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
            logger.info(
                f"Reranker: {len(docs)} candidates → {len(ranked_results)} results | "
                f"top_score={ranked_results[0].get('rerank_score', 0):.4f}" if ranked_results else "Reranker: no results"
            )
            return ranked_results[:top_k]

        except Exception as e:
            logger.warning(f"Reranker exception: {e}, falling back to vector scores")
            return docs[:top_k]

    USER_COLLECTION_PREFIX = "kb_"

    @staticmethod
    def _make_collection_name(user_id: str) -> str:
        safe_id = user_id.replace("-", "_")
        return f"{RAGEngine.USER_COLLECTION_PREFIX}{safe_id}"

    def _get_or_create_collection(self, collection_name: str) -> chromadb.Collection:
        if collection_name in self._collection_cache:
            return self._collection_cache[collection_name]
        collection = self._chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine", "dimension": self.embedding_dimension},
        )
        self._collection_cache[collection_name] = collection
        return collection

    def _get_user_collection(self, user_id: str) -> chromadb.Collection:
        collection_name = self._make_collection_name(user_id)
        logger.info(f"🔒 User collection resolved: user_id={user_id} → collection={collection_name}")
        return self._get_or_create_collection(collection_name)

    @staticmethod
    def _resolve_collection_name(collection_name: Optional[str], user_id: Optional[str]) -> Optional[str]:
        if user_id:
            return RAGEngine._make_collection_name(user_id)
        if collection_name:
            return collection_name
        return None

    @staticmethod
    def _record_to_document(record: Dict[str, Any], collection_name: str, record_index: int = 0) -> Document:
        field_parts = []
        for key, value in record.items():
            if value is not None and str(value).strip():
                field_parts.append(f"{key}: {value}")
        page_content = " | ".join(field_parts)
        metadata = {"collection": collection_name, "record_index": record_index, "field_count": len(record)}
        for k, v in record.items():
            if isinstance(v, (str, int, float, bool)):
                metadata[f"field_{k}"] = v
        return Document(page_content=page_content, metadata=metadata)

    async def ingest_data(self, data: Dict[str, Any], collection_name: str, user_id: str = "") -> Dict[str, Any]:
        if not user_id:
            logger.error("安全拦截: ingest_data 拒绝无 user_id 的入库请求")
            raise PermissionError("入库被拒绝: 必须提供 user_id 才能写入知识库 (Collection 物理隔离策略)")

        effective_collection = self._make_collection_name(user_id)
        try:
            records = self._normalize_records(data)
            if not records:
                return {"collection": effective_collection, "ingested_count": 0, "document_ids": []}

            documents = []
            doc_ids = []
            for idx, record in enumerate(records):
                doc = self._record_to_document(record, effective_collection, idx)
                if user_id:
                    doc.metadata["user_id"] = user_id
                documents.append(doc)
                doc_ids.append(f"{effective_collection}_{idx}_{uuid.uuid4().hex[:8]}")

            await self._ingest_documents(documents, doc_ids, effective_collection)

            texts = [doc.page_content for doc in documents]
            metadatas = [doc.metadata for doc in documents]
            self._add_batch_to_bm25(texts, metadatas)

            result = {"collection": effective_collection, "ingested_count": len(documents), "document_ids": doc_ids}
            logger.info(f"🔒 正在将 {len(documents)} 个 Chunk 存入用户私有库: {effective_collection} (vector + BM25)")
            return result
        except Exception as e:
            logger.error(f"ingest_data failed for [{effective_collection}]: {e}")
            raise

    async def _ingest_documents(self, documents: List[Document], doc_ids: List[str], collection_name: str):
        texts = [doc.page_content for doc in documents]
        metadatas = [doc.metadata for doc in documents]
        embedding_vectors = await asyncio.to_thread(self._embeddings.embed_documents, texts)
        collection = self._get_or_create_collection(collection_name)
        await asyncio.to_thread(
            collection.add, ids=doc_ids, documents=texts, embeddings=embedding_vectors, metadatas=metadatas,
        )

    async def ingest_documents_batch(self, documents: List[Document], collection_name: str, batch_size: int = 50, user_id: str = "") -> Dict[str, Any]:
        if not user_id:
            logger.error("安全拦截: ingest_documents_batch 拒绝无 user_id 的入库请求")
            raise PermissionError("入库被拒绝: 必须提供 user_id 才能写入知识库 (Collection 物理隔离策略)")

        effective_collection = self._make_collection_name(user_id)
        try:
            if user_id:
                for doc in documents:
                    doc.metadata["user_id"] = user_id

            all_ids = []
            for i in range(0, len(documents), batch_size):
                batch = documents[i: i + batch_size]
                batch_ids = [f"{effective_collection}_{i + j}_{uuid.uuid4().hex[:8]}" for j in range(len(batch))]
                await self._ingest_documents(batch, batch_ids, effective_collection)
                all_ids.extend(batch_ids)

            texts = [doc.page_content for doc in documents]
            metadatas = [doc.metadata for doc in documents]
            self._add_batch_to_bm25(texts, metadatas)

            if self._graph_engine and self._ai_client:
                asyncio.create_task(self._background_graph_extract(texts, metadatas, user_id=user_id))

            logger.info(f"🔒 正在将 {len(documents)} 个 Chunk 存入用户私有库: {effective_collection} (vector + BM25 + graph)")
            return {"collection": effective_collection, "ingested_count": len(documents), "document_ids": all_ids}
        except Exception as e:
            logger.error(f"ingest_documents_batch failed: {e}")
            raise

    async def semantic_search(
        self,
        query: str,
        top_k: int = 5,
        collection_name: Optional[str] = None,
        filter_metadata: Optional[Dict[str, Any]] = None,
        use_hybrid: bool = True,
        use_reranker: bool = True,
        use_graph: bool = True,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        三路混合检索 + 重排序 (用户级 Collection 物理隔离)

        安全策略:
          - user_id 是必须参数，缺失时抛出 PermissionError 拒绝检索
          - 向量检索仅在 kb_user_{user_id} 集合中执行
          - BM25 检索仅返回该用户的数据
          - 不允许无 user_id 的降级搜索（防止跨用户数据泄露）
        """
        if not user_id:
            logger.error(f"安全拦截: semantic_search 拒绝无 user_id 的检索请求 | query='{query[:50]}'")
            raise PermissionError("检索被拒绝: 必须提供 user_id 才能访问知识库 (Collection 物理隔离策略)")

        target_collection_name = self._make_collection_name(user_id)
        logger.info(f"🔒 安全审计: 正在执行用户 {user_id[:8]}... 的专属空间检索, 目标集合: {target_collection_name}")

        try:
            effective_collection = target_collection_name

            vector_results = await self._vector_search(query, top_k=10, collection_name=effective_collection, filter_metadata=filter_metadata)

            bm25_results = []
            if use_hybrid:
                bm25_results = self._bm25_search(query, top_k=10)
                bm25_results = [r for r in bm25_results if r.get("metadata", {}).get("user_id") == user_id]

            graph_results = []
            if use_graph and self._graph_engine:
                graph_results = await self._graph_search(query, user_id=user_id)

            if use_hybrid and bm25_results:
                merged = self._merge_results(vector_results, bm25_results)
                logger.info(f"Hybrid merge: vector={len(vector_results)} + bm25={len(bm25_results)} → merged={len(merged)}")
            else:
                merged = vector_results

            if graph_results:
                merged = self._merge_results(merged, graph_results)
                logger.info(f"GraphRAG merge: + graph={len(graph_results)} → total={len(merged)}")

            if use_reranker and len(merged) > 0 and self._reranker_api_key:
                final = self._rerank_documents(query, merged, top_k=top_k)
                logger.info(f"Reranked: {len(merged)} candidates → {len(final)} final results")
                return final
            else:
                merged.sort(key=lambda x: x.get("score", 0), reverse=True)
                return merged[:top_k]

        except PermissionError:
            raise
        except Exception as e:
            logger.error(f"semantic_search failed: {e} | user={user_id[:8]}... | query='{query[:50]}'")
            return []

    async def _vector_search(self, query: str, top_k: int = 10, collection_name: Optional[str] = None, filter_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        try:
            query_embedding = await asyncio.to_thread(self._embeddings.embed_query, query)

            if collection_name:
                collections = [self._get_or_create_collection(collection_name)]
            else:
                collections = self._chroma_client.list_collections()
                collections = [self._chroma_client.get_collection(c.name) if hasattr(c, "name") else c for c in collections]

            all_results: List[Dict[str, Any]] = []
            for coll in collections:
                if coll.count() == 0:
                    continue
                query_params: Dict[str, Any] = {"query_embeddings": [query_embedding], "n_results": min(top_k, coll.count())}
                if filter_metadata:
                    query_params["where"] = filter_metadata
                results = await asyncio.to_thread(coll.query, **query_params)
                coll_name = coll.name
                if results and results["ids"] and results["ids"][0]:
                    for idx in range(len(results["ids"][0])):
                        all_results.append({
                            "content": results["documents"][0][idx],
                            "metadata": results["metadatas"][0][idx],
                            "score": 1.0 - results["distances"][0][idx],
                            "collection": coll_name,
                            "source": "dense",
                        })

            all_results.sort(key=lambda x: x["score"], reverse=True)
            return all_results[:top_k]
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []

    async def mmr_search(
        self,
        query: str,
        user_id: str,
        fetch_k: int = 20,
        k: int = 5,
        lambda_mult: float = 0.5,
    ) -> List[Dict[str, Any]]:
        if not user_id:
            raise PermissionError("MMR检索被拒绝: 必须提供 user_id (Collection 物理隔离策略)")

        collection_name = self._make_collection_name(user_id)
        try:
            collection = self._get_or_create_collection(collection_name)
            if collection.count() == 0:
                return []

            query_embedding = await asyncio.to_thread(self._embeddings.embed_query, query)

            effective_fetch_k = min(fetch_k, collection.count())
            effective_k = min(k, effective_fetch_k)

            results = await asyncio.to_thread(
                collection.query,
                query_embeddings=[query_embedding],
                n_results=effective_fetch_k,
                include=["documents", "metadatas", "distances", "embeddings"],
            )

            if not results or not results["ids"] or not results["ids"][0]:
                return []

            candidate_embeddings = results["embeddings"][0]
            if candidate_embeddings is None or len(candidate_embeddings) == 0:
                logger.warning("mmr_search: no embeddings returned, falling back to similarity")
                fallback_results = []
                for idx in range(min(effective_k, len(results["ids"][0]))):
                    fallback_results.append({
                        "content": results["documents"][0][idx],
                        "metadata": results["metadatas"][0][idx],
                        "score": 1.0 - results["distances"][0][idx],
                        "collection": collection_name,
                        "source": "mmr_fallback",
                    })
                return fallback_results

            import numpy as np
            query_emb = np.array(query_embedding)
            candidate_embs = np.array(candidate_embeddings)

            selected_indices = []
            remaining_indices = list(range(len(candidate_embs)))

            query_sims = np.dot(candidate_embs, query_emb) / (
                np.linalg.norm(candidate_embs, axis=1) * np.linalg.norm(query_emb) + 1e-10
            )

            best_idx = int(np.argmax(query_sims))
            selected_indices.append(best_idx)
            remaining_indices.remove(best_idx)

            while len(selected_indices) < effective_k and remaining_indices:
                best_score = -float("inf")
                best_remaining_idx = remaining_indices[0]

                for idx in remaining_indices:
                    relevance = query_sims[idx]
                    if selected_indices:
                        selected_embs = candidate_embs[selected_indices]
                        sims_to_selected = np.dot(candidate_embs[idx], selected_embs.T) / (
                            np.linalg.norm(candidate_embs[idx]) * np.linalg.norm(selected_embs, axis=1) + 1e-10
                        )
                        diversity_penalty = float(np.max(sims_to_selected))
                    else:
                        diversity_penalty = 0.0

                    mmr_score = lambda_mult * relevance - (1 - lambda_mult) * diversity_penalty
                    if mmr_score > best_score:
                        best_score = mmr_score
                        best_remaining_idx = idx

                selected_indices.append(best_remaining_idx)
                remaining_indices.remove(best_remaining_idx)

            mmr_results = []
            for idx in selected_indices:
                mmr_results.append({
                    "content": results["documents"][0][idx],
                    "metadata": results["metadatas"][0][idx],
                    "score": 1.0 - results["distances"][0][idx],
                    "collection": collection_name,
                    "source": "mmr",
                })

            logger.info(f"mmr_search: query='{query[:30]}' → fetch_k={effective_fetch_k}, k={effective_k}, λ={lambda_mult}, returned={len(mmr_results)}")
            return mmr_results

        except PermissionError:
            raise
        except Exception as e:
            logger.error(f"mmr_search failed: {e} | user={user_id[:8]}... | query='{query[:50]}'")
            return []

    @staticmethod
    def _merge_results(vector_results: List[Dict[str, Any]], bm25_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen_contents = set()
        merged = []

        for doc in vector_results:
            content_key = doc.get("content", "")[:200]
            if content_key not in seen_contents:
                seen_contents.add(content_key)
                merged.append(doc)

        for doc in bm25_results:
            content_key = doc.get("content", "")[:200]
            if content_key not in seen_contents:
                seen_contents.add(content_key)
                merged.append(doc)

        return merged

    async def delete_documents_by_source(self, source_filename: str, user_id: str) -> int:
        if not user_id:
            raise PermissionError("删除被拒绝: 必须提供 user_id (Collection 物理隔离策略)")
        collection_name = self._make_collection_name(user_id)
        try:
            collection = self._chroma_client.get_collection(name=collection_name)
        except Exception:
            logger.info(f"delete_documents_by_source: collection [{collection_name}] not found, nothing to delete")
            return 0

        try:
            result = collection.get(where={"source": source_filename})
            ids_to_delete = result.get("ids", [])
            if not ids_to_delete:
                logger.info(f"delete_documents_by_source: no chunks found for source='{source_filename}' in [{collection_name}]")
                return 0

            collection.delete(ids=ids_to_delete)
            self._collection_cache.pop(collection_name, None)
            logger.info(f"delete_documents_by_source: deleted {len(ids_to_delete)} chunks for source='{source_filename}' from [{collection_name}]")
            return len(ids_to_delete)
        except Exception as e:
            logger.error(f"delete_documents_by_source failed: {e}")
            return 0

    async def delete_collection(self, collection_name: str, user_id: str = "") -> bool:
        if user_id:
            expected = self._make_collection_name(user_id)
            if collection_name != expected:
                logger.error(f"安全拦截: delete_collection 拒绝越权删除 | 请求集合={collection_name} 用户应有={expected}")
                raise PermissionError("删除被拒绝: 只能删除自己的专属知识库集合 (Collection 物理隔离策略)")
        try:
            self._chroma_client.delete_collection(collection_name)
            self._collection_cache.pop(collection_name, None)
            logger.info(f"Deleted collection [{collection_name}]")
            return True
        except PermissionError:
            raise
        except Exception as e:
            logger.error(f"delete_collection failed: {e}")
            return False

    async def list_collections(self) -> List[Dict[str, Any]]:
        try:
            collections = self._chroma_client.list_collections()
            result = []
            for coll_info in collections:
                name = coll_info.name if hasattr(coll_info, "name") else str(coll_info)
                coll = self._chroma_client.get_collection(name)
                result.append({"name": name, "count": coll.count()})
            return result
        except Exception as e:
            logger.error(f"list_collections failed: {e}")
            return []

    async def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        try:
            coll = self._get_or_create_collection(collection_name)
            return {"name": collection_name, "count": coll.count()}
        except Exception as e:
            return {"name": collection_name, "error": str(e)}

    async def get_knowledge_stats(self, user_id: str) -> Dict[str, Any]:
        if not user_id:
            logger.error("安全拦截: get_knowledge_stats 拒绝无 user_id 的请求")
            raise PermissionError("查询被拒绝: 必须提供 user_id 才能获取知识库统计 (Collection 物理隔离策略)")

        collection_name = self._make_collection_name(user_id)
        logger.info(f"🔒 安全审计: 查询用户 {user_id[:8]}... 的知识库统计, 目标集合: {collection_name}")

        try:
            collection = self._chroma_client.get_collection(name=collection_name)

            collection_data = collection.get(include=["metadatas"])

            unique_files = set()
            if collection_data and collection_data.get("metadatas"):
                for meta in collection_data["metadatas"]:
                    if meta and "source" in meta:
                        unique_files.add(meta["source"])

            return {
                "total_chunks": collection.count(),
                "total_documents": len(unique_files),
                "files": list(unique_files),
            }
        except Exception as e:
            logger.info(f"用户 {user_id[:8]}... 的私有知识库尚不存在，返回空列表。详情: {e}")
            return {"total_documents": 0, "total_chunks": 0, "files": []}

    async def ingest_from_jsonl(self, jsonl_path: str, collection_name: Optional[str] = None, user_id: str = "") -> Dict[str, Any]:
        if not user_id:
            logger.error("安全拦截: ingest_from_jsonl 拒绝无 user_id 的入库请求")
            raise PermissionError("入库被拒绝: 必须提供 user_id 才能写入知识库 (Collection 物理隔离策略)")

        try:
            if collection_name is None:
                collection_name = Path(jsonl_path).parent.name
            records = []
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
            if not records:
                return {"collection": collection_name, "ingested_count": 0, "document_ids": []}
            return await self.ingest_data({"records": records}, collection_name, user_id=user_id)
        except Exception as e:
            logger.error(f"ingest_from_jsonl failed for {jsonl_path}: {e}")
            raise

    async def _graph_search(self, query: str, user_id: str = "") -> List[Dict[str, Any]]:
        if not self._graph_engine:
            return []
        if not user_id:
            logger.warning("Graph search skipped: user_id is required for user-isolated graph retrieval")
            return []
        try:
            subgraph_text = await self._graph_engine.search_subgraph_async(query, user_id=user_id, depth=2)
            if not subgraph_text:
                return []
            return [{
                "content": subgraph_text,
                "metadata": {"source": "graph_rag", "user_id": user_id},
                "score": 0.85,
                "collection": "graph",
                "source": "graph",
            }]
        except Exception as e:
            logger.warning(f"Graph search failed: {e}")
            return []

    async def _background_graph_extract(self, texts: List[str], metadatas: List[Dict[str, Any]], user_id: str = ""):
        try:
            for i, text in enumerate(texts):
                if not text or len(text) < 50:
                    continue
                source = metadatas[i].get("source", f"doc_{i}") if i < len(metadatas) else f"doc_{i}"
                triplets = await self._graph_engine.extract_entities_and_relations(text)
                if triplets:
                    self._graph_engine.add_triplets(triplets, user_id=user_id, source=source)
                    logger.info(f"Graph extract: {source} → {len(triplets)} triplets (user={user_id[:8]}...)")
        except Exception as e:
            logger.error(f"Background graph extraction failed: {e}")

    @staticmethod
    def _normalize_records(data: Dict[str, Any]) -> List[Dict[str, Any]]:
        if "records" in data and isinstance(data["records"], list):
            return data["records"]
        if any(isinstance(v, dict) for v in data.values()):
            return [data]
        return [data]
