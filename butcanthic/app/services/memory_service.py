"""
Agentic Memory - 跨会话长期动态记忆引擎

功能:
  1. 从用户指令中提取偏好 (风格、语气、身份等)
  2. 将偏好存入用户专属记忆集合 (memory_{user_id})
  3. 检索时返回用户历史偏好，供工作流各节点参考

集合命名: memory_{user_id_with_underscores}
  例: user_id = "abc-def-123" → collection = "memory_abc_def_123"
"""

import asyncio
import json
import logging
import re
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

MEMORY_COLLECTION_PREFIX = "memory_"

EXTRACT_MEMORY_SYSTEM_PROMPT = """你是一个用户偏好分析专家。请分析用户的指令，判断其中是否包含用户的个人偏好、风格倾向或身份信息。

偏好类型包括但不限于：
- 排版风格偏好 (极简、详细、学术、商务等)
- 语气偏好 (正式、轻松、幽默等)
- 语言偏好 (中文、英文、中英混合等)
- 输出格式偏好 (表格、列表、段落等)
- 专业领域偏好 (技术、金融、法律、医疗等)
- 身份信息 (职位、角色等)

如果指令中包含明确的偏好，请以 JSON 数组格式返回简短的事实陈述，每条不超过30字。
例如：["用户偏好极简排版风格", "用户身份是产品经理"]

如果指令中不包含任何偏好信息，请返回空数组：[]

只输出 JSON 数组，不要输出任何额外解释。"""


def _make_memory_collection_name(user_id: str) -> str:
    safe_id = user_id.replace("-", "_")
    return f"{MEMORY_COLLECTION_PREFIX}{safe_id}"


class MemoryManager:

    def __init__(self):
        logger.info("MemoryManager initialized")

    async def extract_and_store_memory(
        self,
        user_instruction: str,
        user_id: str,
        llm_client,
        rag_engine,
    ) -> int:
        if not user_instruction or not user_id or not llm_client or not rag_engine:
            return 0

        try:
            memories = await self._extract_preferences(user_instruction, llm_client)
            if not memories:
                logger.info(f"Memory: no preferences found in instruction for user {user_id[:8]}...")
                return 0

            stored = await self._store_memories(memories, user_id, rag_engine)
            logger.info(f"Memory: stored {stored} new preferences for user {user_id[:8]}...")
            return stored

        except Exception as e:
            logger.error(f"Memory: extract_and_store failed: {e}")
            return 0

    async def fetch_user_memory(
        self,
        user_id: str,
        rag_engine,
    ) -> str:
        if not user_id or not rag_engine:
            return ""

        try:
            collection_name = _make_memory_collection_name(user_id)

            existing = [c.name if hasattr(c, "name") else str(c) for c in rag_engine._chroma_client.list_collections()]
            if collection_name not in existing:
                return ""

            collection = rag_engine._chroma_client.get_collection(collection_name)
            if collection.count() == 0:
                return ""

            data = collection.get(include=["documents"])
            documents = data.get("documents", [])
            if not documents:
                return ""

            memories = [doc.strip() for doc in documents if doc and doc.strip()]
            if not memories:
                return ""

            result = "【用户长期偏好】：" + "；".join(memories)
            logger.info(f"Memory: fetched {len(memories)} preferences for user {user_id[:8]}...")
            return result

        except Exception as e:
            logger.warning(f"Memory: fetch failed for user {user_id[:8]}...: {e}")
            return ""

    async def _extract_preferences(self, user_instruction: str, llm_client) -> list:
        messages = [
            {"role": "system", "content": EXTRACT_MEMORY_SYSTEM_PROMPT},
            {"role": "user", "content": user_instruction},
        ]

        try:
            response = await llm_client.acall_api(messages, max_tokens=1024)
            if not response or not response.strip():
                return []

            return self._parse_preferences(response)
        except Exception as e:
            logger.warning(f"Memory: preference extraction LLM call failed: {e}")
            return []

    def _parse_preferences(self, response: str) -> list:
        cleaned = response.strip()

        code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", cleaned, re.DOTALL)
        if code_block:
            cleaned = code_block.group(1).strip()

        bracket_match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if bracket_match:
            cleaned = bracket_match.group(0)

        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            pass

        try:
            fixed = re.sub(r"'", '"', cleaned)
            parsed = json.loads(fixed)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except (json.JSONDecodeError, Exception):
            pass

        return []

    async def _store_memories(self, memories: list, user_id: str, rag_engine) -> int:
        if not memories:
            return 0

        collection_name = _make_memory_collection_name(user_id)

        try:
            existing_memories = set()
            existing = [c.name if hasattr(c, "name") else str(c) for c in rag_engine._chroma_client.list_collections()]
            if collection_name in existing:
                collection = rag_engine._chroma_client.get_collection(collection_name)
                data = collection.get(include=["documents"])
                for doc in (data.get("documents") or []):
                    if doc and doc.strip():
                        existing_memories.add(doc.strip())

            new_memories = [m for m in memories if m not in existing_memories]
            if not new_memories:
                logger.info(f"Memory: all {len(memories)} preferences already stored, skipping")
                return 0

            import uuid
            collection = rag_engine._get_or_create_collection(collection_name)

            texts = new_memories
            metadatas = [{"source": "memory", "type": "preference", "user_id": user_id} for _ in new_memories]
            doc_ids = [f"mem_{uuid.uuid4().hex[:8]}" for _ in new_memories]

            embedding_vectors = await asyncio.to_thread(
                rag_engine._embeddings.embed_documents, texts
            )
            await asyncio.to_thread(
                collection.add,
                ids=doc_ids,
                documents=texts,
                embeddings=embedding_vectors,
                metadatas=metadatas,
            )

            logger.info(f"Memory: stored {len(new_memories)} preferences in {collection_name}")
            return len(new_memories)

        except Exception as e:
            logger.error(f"Memory: store failed: {e}")
            return 0


memory_manager = MemoryManager()
