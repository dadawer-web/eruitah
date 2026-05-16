import asyncio
import json
import logging
import os
import time
import uuid

import httpx

from bridge import chat_pb2
from bridge.rpc_client import RpcClient

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://token-plan-cn.xiaomimimo.com")
CAREER_MODEL = os.environ.get("CAREER_MODEL", "mimo-v2.5-tts")

JAVA_RPC_HOST = os.environ.get("JAVA_RPC_HOST", "127.0.0.1")
JAVA_RPC_PORT = int(os.environ.get("JAVA_RPC_PORT", "9999"))

ANALYSIS_PROMPT = """分析这段代码，提取出3个核心技术点（如 Epoll, 多线程等），并用 STAR 法则生成一段 50 字的秋招简历亮点描述，最后给出一句简短的进阶学习建议。请以 JSON 格式返回，格式如下：
{
  "skills": ["技术点1", "技术点2", "技术点3"],
  "resume_highlight": "STAR法则简历亮点描述",
  "learning_advice": "进阶学习建议"
}

代码内容：
{code}"""

_java_rpc_client: RpcClient | None = None


async def _get_java_client() -> RpcClient:
    global _java_rpc_client
    if _java_rpc_client and _java_rpc_client.connected:
        return _java_rpc_client
    _java_rpc_client = RpcClient(JAVA_RPC_HOST, JAVA_RPC_PORT)
    await _java_rpc_client.connect()
    logger.info(f"[CareerAnalyzer] Connected to Java RPC at {JAVA_RPC_HOST}:{JAVA_RPC_PORT}")
    return _java_rpc_client


async def _call_llm(code_content: str) -> dict | None:
    url = f"{OPENAI_BASE_URL}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": CAREER_MODEL,
        "messages": [
            {"role": "user", "content": ANALYSIS_PROMPT.format(code=code_content[:3000])}
        ],
        "temperature": 0.3,
        "max_tokens": 500,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]

            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                return json.loads(content[json_start:json_end])
            return None
    except Exception as e:
        logger.error(f"[CareerAnalyzer] LLM call failed: {e}")
        return None


async def _send_to_java(user_id: int, skills: list, resume_highlight: str, learning_advice: str):
    try:
        client = await _get_java_client()

        payload = {
            "skills": skills,
            "resume_highlight": resume_highlight,
            "learning_advice": learning_advice,
        }

        event = chat_pb2.AgentSkillEvent(
            user_id=user_id,
            skill_name="CareerMentor",
            event_type="ANALYSIS_COMPLETE",
            payload_json=json.dumps(payload, ensure_ascii=False),
            trace_id=str(uuid.uuid4()),
            timestamp=int(time.time()),
        )

        response = await client.call(
            "InternalRouterService",
            "EmitSkillEvent",
            event,
            chat_pb2.AgentSkillEventAck,
            timeout=10.0,
        )
        if response and response.success:
            logger.info(f"[CareerAnalyzer] SkillEvent sent for user={user_id} trace={event.trace_id[:8]}")
        else:
            err = response.error if response else "no response"
            logger.warning(f"[CareerAnalyzer] SkillEvent failed for user={user_id}: {err}")
    except Exception as e:
        logger.error(f"[CareerAnalyzer] Failed to send skill event to Java: {e}")


async def analyze_code_async(user_id: int, code_content: str):
    try:
        logger.info(f"[CareerAnalyzer] Starting async analysis for user={user_id}")

        result = await _call_llm(code_content)
        if not result:
            logger.warning(f"[CareerAnalyzer] LLM returned no valid JSON for user={user_id}")
            return

        skills = result.get("skills", [])
        resume_highlight = result.get("resume_highlight", "")
        learning_advice = result.get("learning_advice", "")

        if not skills and not resume_highlight:
            logger.warning(f"[CareerAnalyzer] Empty analysis result for user={user_id}")
            return

        logger.info(
            f"[CareerAnalyzer] user={user_id} skills={skills} "
            f"highlight={resume_highlight[:50]}..."
        )

        await _send_to_java(user_id, skills, resume_highlight, learning_advice)

    except Exception as e:
        logger.error(f"[CareerAnalyzer] Async analysis failed for user={user_id}: {e}")


def spawn_career_analysis(user_id: int, code_content: str):
    if not code_content or len(code_content.strip()) < 20:
        return
    asyncio.create_task(analyze_code_async(user_id, code_content))
    logger.info(f"[CareerAnalyzer] Spawned background analysis for user={user_id}")
