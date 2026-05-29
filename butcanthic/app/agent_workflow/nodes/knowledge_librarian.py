import asyncio
import logging

from langchain_core.messages import AIMessage

from app.agent_workflow.state import WorkflowState
from app.core.prompt_manager import PromptManager

logger = logging.getLogger(__name__)


async def knowledge_librarian_node(state: WorkflowState, rag_engine=None, llm_client=None) -> dict:
    logger.info("📚 [KnowledgeLibrarian] 正在翻阅私有知识库...")

    user_query = state.get("user_instruction", "")
    user_id = state.get("user_id", "")
    if not user_query and state.get("messages"):
        user_query = state["messages"][-1].content

    if not user_id:
        logger.warning("📚 [KnowledgeLibrarian] user_id 缺失，无法检索私有知识库（Collection 物理隔离要求必须提供 user_id）")
        new_message = AIMessage(
            content="【私有知识库结果】:\n当前会话未关联用户，无法访问私有知识库。请先登录后再试。",
            name="Knowledge_Librarian",
        )
        return {"messages": [new_message]}

    search_queries = await _extract_search_queries(user_query, llm_client)
    logger.info(f"📚 [KnowledgeLibrarian] user={user_id[:8]}... 搜索关键词: {search_queries}")

    vector_context = ""
    graph_context = ""

    if rag_engine is None:
        vector_context = "知识库引擎未初始化，无法检索。"
        logger.warning("📚 [KnowledgeLibrarian] rag_engine is None")
    else:
        try:
            vector_context = await _vector_search(rag_engine, search_queries, user_id)
        except Exception as e:
            logger.error(f"📚 [KnowledgeLibrarian] 向量检索失败: {e}")
            vector_context = f"知识库检索失败: {e}"

    graph_engine = _get_graph_engine(rag_engine)
    if graph_engine:
        try:
            graph_context = await _graph_search(graph_engine, user_query, user_id)
        except Exception as e:
            logger.warning(f"📚 [KnowledgeLibrarian] 图谱检索失败: {e}")
            graph_context = ""

    result_text = _merge_contexts(vector_context, graph_context)

    logger.info(
        f"📚 [KnowledgeLibrarian] 双路混合检索完毕 | "
        f"vector={'✓' if vector_context and '未找到' not in vector_context else '✗'} | "
        f"graph={'✓' if graph_context else '✗'}"
    )

    new_message = AIMessage(
        content=f"【私有知识库结果】:\n{result_text}",
        name="Knowledge_Librarian",
    )
    return {"messages": [new_message]}


async def _vector_search(rag_engine, search_queries: list, user_id: str) -> str:
    all_docs = []
    for query in search_queries:
        docs = await rag_engine.semantic_search(
            query,
            top_k=5,
            use_hybrid=True,
            use_reranker=True,
            use_graph=False,
            user_id=user_id,
        )
        all_docs.extend(docs)

    seen = set()
    unique_docs = []
    for doc in all_docs:
        content_key = doc.get("content", "")[:200]
        if content_key not in seen:
            seen.add(content_key)
            unique_docs.append(doc)

    unique_docs.sort(key=lambda x: x.get("rerank_score", x.get("score", 0)), reverse=True)
    top_docs = unique_docs[:5]

    if top_docs:
        parts = []
        for i, doc in enumerate(top_docs):
            content = doc.get("content", doc.get("page_content", ""))
            source = doc.get("source", "unknown")
            score = doc.get("rerank_score", doc.get("score", 0))
            if content:
                parts.append(f"[{i+1}] (source={source}, score={score:.4f})\n{content}")
        if parts:
            return "【向量检索结果】（混合检索+重排序）：\n" + "\n\n".join(parts)

    return "私有知识库中未找到相关资料。"


async def _graph_search(graph_engine, user_query: str, user_id: str) -> str:
    subgraph_text = await graph_engine.search_subgraph_async(user_query, user_id=user_id, depth=2)
    if subgraph_text:
        logger.info(f"📚 [KnowledgeLibrarian] GraphRAG 命中: {subgraph_text[:100]}...")
        return subgraph_text
    return ""


def _get_graph_engine(rag_engine):
    if rag_engine and hasattr(rag_engine, '_graph_engine') and rag_engine._graph_engine:
        return rag_engine._graph_engine
    return None


def _merge_contexts(vector_context: str, graph_context: str) -> str:
    parts = []

    if vector_context and "未找到" not in vector_context and "检索失败" not in vector_context:
        parts.append(vector_context)

    if graph_context:
        parts.append(graph_context)

    if not parts:
        return "私有知识库中未找到相关资料。"

    return "\n\n".join(parts)


async def _extract_search_queries(user_query: str, llm_client=None) -> list:
    if not user_query or not llm_client:
        return [user_query] if user_query else []

    try:
        messages = [
            {
                "role": "system",
                "content": PromptManager.get_prompt("knowledge_librarian_keyword_extract"),
            },
            {
                "role": "user",
                "content": user_query,
            },
        ]

        response = await llm_client.acall_api(messages, max_tokens=8192)

        if response and response.strip():
            queries = [q.strip() for q in response.strip().split(",") if q.strip()]
            if queries:
                queries.insert(0, user_query)
                return queries[:4]

    except Exception as e:
        logger.warning(f"📚 [KnowledgeLibrarian] 关键词提取失败，使用原始查询: {e}")

    return [user_query] if user_query else []
