"""
RAG 自动化评测引擎 - 基于 LLM-as-a-Judge 三维评分体系

评分维度:
  1. Faithfulness (忠实度): 答案是否完全基于检索到的上下文，有无幻觉
  2. Context Relevance (检索相关性): 上下文是否包含回答问题所需的信息
  3. Answer Relevance (回答相关性): 答案是否直接回答了用户的问题

每个维度: 0-10 整数评分 + 简短理由 (JSON 格式)
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

FAITHFULNESS_PROMPT = """你是一个严格的RAG评测专家。请评估答案的【忠实度】。

忠实度定义：答案中的每一个声明是否都能在检索到的上下文中找到依据？答案是否包含上下文中没有的信息（即"幻觉"）？

评分标准：
- 10分：答案完全基于上下文，没有任何幻觉
- 7-9分：答案大部分基于上下文，有少量推断但合理
- 4-6分：答案部分基于上下文，有明显推断或轻微幻觉
- 1-3分：答案大部分不是来自上下文，存在明显幻觉
- 0分：答案完全与上下文无关

## 用户问题
{query}

## 检索到的上下文
{context}

## 系统生成的答案
{answer}

请严格以以下JSON格式返回评分，不要输出任何其他内容：
{{"score": <0-10整数>, "reason": "<简短打分理由，不超过50字>"}}"""

CONTEXT_RELEVANCE_PROMPT = """你是一个严格的RAG评测专家。请评估检索上下文的【相关性】。

检索相关性定义：检索到的上下文是否包含回答用户问题所需的关键信息？上下文是否精准、无冗余？

评分标准：
- 10分：上下文完全包含回答所需信息，无冗余
- 7-9分：上下文包含大部分所需信息，少量冗余
- 4-6分：上下文包含部分所需信息，但缺失关键内容或有大量冗余
- 1-3分：上下文与问题几乎无关
- 0分：上下文完全无关

## 用户问题
{query}

## 检索到的上下文
{context}

请严格以以下JSON格式返回评分，不要输出任何其他内容：
{{"score": <0-10整数>, "reason": "<简短打分理由，不超过50字>"}}"""

ANSWER_RELEVANCE_PROMPT = """你是一个严格的RAG评测专家。请评估答案的【回答相关性】。

回答相关性定义：答案是否直接回答了用户的问题？答案是否切题、完整、不偏题？

评分标准：
- 10分：答案完全切题，直接且完整地回答了问题
- 7-9分：答案基本切题，回答了主要问题
- 4-6分：答案部分切题，但偏离了核心问题或不够完整
- 1-3分：答案偏题，未有效回答问题
- 0分：答案完全未回答问题

## 用户问题
{query}

## 系统生成的答案
{answer}

请严格以以下JSON格式返回评分，不要输出任何其他内容：
{{"score": <0-10整数>, "reason": "<简短打分理由，不超过50字>"}}"""


class RAGEvaluator:

    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    async def evaluate_faithfulness(
        self, query: str, context: str, answer: str
    ) -> Dict[str, Any]:
        prompt = FAITHFULNESS_PROMPT.format(
            query=query, context=context, answer=answer
        )
        return await self._score(prompt, "faithfulness")

    async def evaluate_context_relevance(
        self, query: str, context: str
    ) -> Dict[str, Any]:
        prompt = CONTEXT_RELEVANCE_PROMPT.format(query=query, context=context)
        return await self._score(prompt, "context_relevance")

    async def evaluate_answer_relevance(
        self, query: str, answer: str
    ) -> Dict[str, Any]:
        prompt = ANSWER_RELEVANCE_PROMPT.format(query=query, answer=answer)
        return await self._score(prompt, "answer_relevance")

    async def evaluate_all(
        self, query: str, context: str, answer: str
    ) -> Dict[str, Any]:
        faithfulness = await self.evaluate_faithfulness(query, context, answer)
        context_relevance = await self.evaluate_context_relevance(query, context)
        answer_relevance = await self.evaluate_answer_relevance(query, answer)

        scores = [
            faithfulness.get("score", 0),
            context_relevance.get("score", 0),
            answer_relevance.get("score", 0),
        ]
        avg = sum(scores) / len(scores) if scores else 0

        return {
            "faithfulness": faithfulness,
            "context_relevance": context_relevance,
            "answer_relevance": answer_relevance,
            "average_score": round(avg, 2),
        }

    async def _score(self, prompt: str, dimension: str) -> Dict[str, Any]:
        if not self.llm_client:
            return {"score": 0, "reason": "LLM client not available"}

        messages = [{"role": "user", "content": prompt}]

        try:
            response = await self.llm_client.acall_api(messages, max_tokens=256)
            if not response:
                return {"score": 0, "reason": "LLM returned empty response"}
            return self._parse_score(response, dimension)
        except Exception as e:
            logger.error(f"Evaluation failed for {dimension}: {e}")
            return {"score": 0, "reason": f"Evaluation error: {str(e)[:50]}"}

    def _parse_score(self, response: str, dimension: str) -> Dict[str, Any]:
        cleaned = response.strip()

        code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", cleaned, re.DOTALL)
        if code_block:
            cleaned = code_block.group(1).strip()

        brace_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if brace_match:
            cleaned = brace_match.group(0)

        try:
            parsed = json.loads(cleaned)
            score = parsed.get("score", 0)
            reason = parsed.get("reason", "")
            if isinstance(score, (int, float)):
                score = max(0, min(10, int(score)))
            else:
                score = 0
            return {"score": score, "reason": str(reason)[:100]}
        except json.JSONDecodeError:
            pass

        score_match = re.search(r'"?score"?\s*[:=]\s*(\d+)', cleaned)
        if score_match:
            score = max(0, min(10, int(score_match.group(1))))
            reason_match = re.search(r'"?reason"?\s*[:=]\s*"([^"]*)"', cleaned)
            reason = reason_match.group(1) if reason_match else "Parsed from non-JSON"
            return {"score": score, "reason": reason[:100]}

        number_match = re.search(r'\b(\d+)\b', cleaned)
        if number_match:
            score = max(0, min(10, int(number_match.group(1))))
            return {"score": score, "reason": "Extracted from response"}

        logger.warning(f"Failed to parse {dimension} score from: {response[:200]}")
        return {"score": 0, "reason": "Parse failed"}
