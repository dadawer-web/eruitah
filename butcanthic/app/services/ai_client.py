"""
统一AI客户端 - 基于LangChain框架，支持多个AI模型提供商
支持阿里云通义千问和火山引擎豆包模型
"""

import json
import logging
import os
import random
import time
import asyncio
from typing import Dict, List, Optional, Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
import httpx
import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
    before_sleep_log,
)

logger = logging.getLogger(__name__)


# ── 可重试异常判断：429 / 5xx / 网络超时 ──
def _is_retryable_error(exc: BaseException) -> bool:
    """判断异常是否值得重试（429/5xx/网络错误）"""
    status_code = None
    if hasattr(exc, 'status_code'):
        status_code = exc.status_code
    elif hasattr(exc, 'response') and hasattr(exc.response, 'status_code'):
        status_code = exc.response.status_code
    else:
        import re as _re
        code_match = _re.search(r'(\d{3})', repr(exc))
        if code_match:
            candidate = int(code_match.group(1))
            if candidate in (429, 500, 502, 503, 504):
                status_code = candidate

    if status_code in (429, 500, 502, 503, 504):
        return True

    # 网络级错误（连接超时、DNS 等）也重试
    error_name = type(exc).__name__.lower()
    if any(kw in error_name for kw in ('timeout', 'connection', 'network')):
        return True

    return False


class UnifiedAIClient:
    """统一AI客户端，基于LangChain框架，支持多个模型提供商"""

    def __init__(self, config_path: str = "ai_models_config.json", selected_model: str = None):
        self.config_path = config_path
        self.models_config = self._load_models_config()
        self.selected_model = selected_model or self.models_config.get("default_model", "qwen-plus")
        self.current_config = self._get_current_model_config()

        self.langchain_llm = None
        self.langchain_initialized = False
        self.is_available = None

        self.vision_llm = None
        self.vision_model_name = None

        self._init_langchain_llm()
        self._init_vision_llm()

    def _load_models_config(self) -> Dict:
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                logger.info(f"AI models config loaded: {self.config_path}")
                return config
            else:
                logger.warning(f"Config not found: {self.config_path}, using defaults")
                default_config = self._get_default_models_config()
                self._save_config(default_config)
                return default_config
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return self._get_default_models_config()

    def _get_default_models_config(self) -> Dict:
        return {
            "models": {
                "qwen-plus": {
                    "provider": "aliyun",
                    "api_key": "",
                    "base_url": "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation",
                    "model_name": "qwen-plus",
                    "max_input_tokens": 997952,
                    "max_output_tokens": 81920,
                    "temperature": 0.0,
                    "top_p": 0.1,
                    "description": "阿里云通义千问Plus",
                },
                "doubao-seed-1-6-flash": {
                    "provider": "volcano",
                    "api_key": "",
                    "base_url": "https://ark.cn-beijing.volces.com/api/v3",
                    "model_name": "doubao-seed-1-6-flash-250828",
                    "max_input_tokens": 32000,
                    "max_output_tokens": 9999,
                    "temperature": 0.0,
                    "top_p": 0.9,
                    "description": "火山引擎豆包Flash",
                },
            },
            "default_model": "qwen-plus",
            "common_config": {
                "api_timeout": 75,
                "retry_attempts": 5,
                "retry_delay": 2,
                "enable_thinking_mode": False,
                "enable_stream": False,
                "enable_reasoning": False,
            },
        }

    def _init_langchain_llm(self):
        try:
            provider = self.current_config.get("provider", "")
            max_output = int(self.current_config.get("max_output_tokens") or 16384)
            logger.info(f"🚀 [AIClient] max_output_tokens 强制转整型: {max_output}")

            if provider == "volcano":
                self.langchain_llm = ChatOpenAI(
                    model=self.current_config.get("model_name", "doubao-seed-1-6-flash-250828"),
                    api_key=self.current_config.get("api_key"),
                    base_url=self.current_config.get("base_url"),
                    temperature=self.current_config.get("temperature", 0.1),
                    max_tokens=max_output,
                    top_p=self.current_config.get("top_p", 0.9),
                    request_timeout=75.0,
                )
                logger.info(f"LangChain LLM initialized: {self.selected_model} (volcano)")
            elif provider == "aliyun":
                self.langchain_llm = self._create_aliyun_llm()
                logger.info(f"LangChain LLM initialized: {self.selected_model} (aliyun)")
            elif provider == "openai":
                self.langchain_llm = ChatOpenAI(
                    model=self.current_config.get("model_name", "gpt-3.5-turbo"),
                    api_key=self.current_config.get("api_key", ""),
                    base_url=self.current_config.get("base_url"),
                    temperature=self.current_config.get("temperature", 0.0),
                    max_tokens=max_output,
                    top_p=self.current_config.get("top_p", 0.1),
                    request_timeout=75.0,
                )
                logger.info(f"LangChain LLM initialized: {self.selected_model} (openai-compatible)")
            else:
                self.langchain_llm = ChatOpenAI(
                    model=self.current_config.get("model_name", "gpt-3.5-turbo"),
                    api_key=self.current_config.get("api_key", "dummy-key"),
                    base_url=self.current_config.get("base_url"),
                    temperature=self.current_config.get("temperature", 0.1),
                    max_tokens=max_output,
                )

            self.langchain_initialized = True

        except Exception as e:
            logger.error(
                f"🚨 [AIClient] LangChain LLM 初始化失败！| "
                f"exception_type={type(e).__name__} | "
                f"exception_repr={repr(e)} | "
                f"selected_model={self.selected_model} | "
                f"provider={self.current_config.get('provider', 'unknown')} | "
                f"base_url={self.current_config.get('base_url', 'unknown')} | "
                f"api_key={'***' + self.current_config.get('api_key', '')[-4:] if self.current_config.get('api_key') else 'NOT_SET'}"
            )
            import traceback
            logger.error(f"🚨 [AIClient] 初始化完整堆栈追踪:\n{traceback.format_exc()}")
            self.langchain_initialized = False
            self.langchain_llm = None

    def _init_vision_llm(self):
        vision_model_key = self.models_config.get("vision_model", "")
        if not vision_model_key:
            for key, cfg in self.models_config.get("models", {}).items():
                if cfg.get("supports_vision"):
                    vision_model_key = key
                    break

        if not vision_model_key:
            logger.info("No vision model configured, image input will be stripped")
            return

        vision_config = self.models_config.get("models", {}).get(vision_model_key, {})
        if not vision_config:
            logger.warning(f"Vision model '{vision_model_key}' not found in config")
            return

        try:
            max_output = int(vision_config.get("max_output_tokens") or 16384)
            self.vision_llm = ChatOpenAI(
                model=vision_config.get("model_name", "qwen3.5-omni-flash"),
                api_key=vision_config.get("api_key", ""),
                base_url=vision_config.get("base_url"),
                temperature=vision_config.get("temperature", 0.1),
                max_tokens=max_output,
                top_p=vision_config.get("top_p", 0.1),
                request_timeout=75.0,
            )
            self.vision_model_name = vision_model_key
            logger.info(f"Vision LLM initialized: {vision_model_key} ({vision_config.get('model_name', '')})")
        except Exception as e:
            logger.error(f"Vision LLM init failed: {e}")
            self.vision_llm = None

    def _create_aliyun_llm(self):
        from langchain.llms.base import LLM
        from pydantic import Field

        class AliyunLLM(LLM):
            api_key: str
            base_url: str
            model_name: str = "qwen-plus"
            temperature: float = 0.1
            max_tokens: int = 32768
            top_p: float = 0.1
            timeout: int = 75

            @property
            def _llm_type(self) -> str:
                return "aliyun_qwen"

            def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
                try:
                    messages = [{"role": "user", "content": prompt}]
                    payload = {
                        "model": self.model_name,
                        "input": {"messages": messages},
                        "parameters": {
                            "temperature": self.temperature,
                            "max_tokens": self.max_tokens,
                            "top_p": self.top_p,
                            "enable_search": False,
                            "incremental_output": False,
                        },
                    }
                    headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
                    response = requests.post(self.base_url, headers=headers, json=payload, timeout=self.timeout)
                    if response.status_code == 200:
                        return response.json().get("output", {}).get("text", "").strip()
                    return f"API request failed: {response.status_code}"
                except Exception as e:
                    return f"API call error: {e}"

            async def _acall(self, prompt: str, stop: Optional[List[str]] = None, run_manager=None, **kwargs) -> str:
                """纯异步 HTTP 调用，替代 requests.post()，避免阻塞事件循环"""
                try:
                    messages = [{"role": "user", "content": prompt}]
                    payload = {
                        "model": self.model_name,
                        "input": {"messages": messages},
                        "parameters": {
                            "temperature": self.temperature,
                            "max_tokens": self.max_tokens,
                            "top_p": self.top_p,
                            "enable_search": False,
                            "incremental_output": False,
                        },
                    }
                    headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
                    async with httpx.AsyncClient(timeout=httpx.Timeout(75.0)) as client:
                        response = await client.post(self.base_url, headers=headers, json=payload)
                        if response.status_code == 200:
                            return response.json().get("output", {}).get("text", "").strip()
                        return f"API request failed: {response.status_code}"
                except Exception as e:
                    return f"Async API call error: {e}"

        return AliyunLLM(
            api_key=self.current_config.get("api_key"),
            base_url=self.current_config.get("base_url"),
            model_name=self.current_config.get("model_name", "qwen-plus"),
            temperature=self.current_config.get("temperature", 0.1),
            max_tokens=self.current_config.get("max_output_tokens", 32768),
            top_p=self.current_config.get("top_p", 0.1),
            timeout=75,
        )

    def _get_current_model_config(self) -> Dict:
        model_config = self.models_config.get("models", {}).get(self.selected_model, {})
        if not model_config:
            available = list(self.models_config.get("models", {}).keys())
            logger.error(
                f"🚨 [AIClient] Model '{self.selected_model}' not found in config! "
                f"Available models: {available}. Falling back to first available."
            )
            if available:
                fallback = available[0]
                self.selected_model = fallback
                model_config = self.models_config.get("models", {}).get(fallback, {})
        common_config = self.models_config.get("common_config", {})
        return {**common_config, **model_config}

    def _save_config(self, config: Dict) -> bool:
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Save config failed: {e}")
            return False

    def switch_model(self, model_name: str) -> bool:
        if model_name in self.models_config.get("models", {}):
            self.selected_model = model_name
            self.current_config = self._get_current_model_config()
            self.is_available = None
            self.langchain_initialized = False
            self.langchain_llm = None
            self._init_langchain_llm()
            logger.info(f"Switched to model: {model_name}")
            return True
        return False

    def call_api(self, messages: List[Dict], max_tokens: int = None, max_retries: int = None, base64_images: List[str] = None) -> Optional[str]:
        if not self.langchain_initialized:
            logger.error(
                "🚨 [AIClient] LangChain LLM 未初始化！无法调用大模型。"
                f" | selected_model={self.selected_model}"
                f" | current_config={self.current_config}"
            )
            return None

        max_retries = max_retries or self.current_config.get("retry_attempts", 3)
        retry_delay = self.current_config.get("retry_delay", 2)

        logger.info(
            f"🚀 [AIClient] call_api 开始 | "
            f"model={self.selected_model} | "
            f"provider={self.current_config.get('provider', 'unknown')} | "
            f"model_name={self.current_config.get('model_name', 'unknown')} | "
            f"base_url={self.current_config.get('base_url', 'unknown')} | "
            f"api_key={'***' + self.current_config.get('api_key', '')[-4:] if self.current_config.get('api_key') else 'NOT_SET'} | "
            f"max_tokens={max_tokens or self.current_config.get('max_output_tokens', 'default')} | "
            f"messages_count={len(messages)} | "
            f"max_retries={max_retries}"
        )

        langchain_messages = []
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            images = message.get("images", [])
            if role == "system":
                langchain_messages.append(SystemMessage(content=str(content)))
            elif role == "user":
                if images:
                    multimodal_content = [{"type": "text", "text": str(content)}]
                    for img_base64 in images:
                        if not img_base64.startswith("data:image"):
                            img_base64 = f"data:image/jpeg;base64,{img_base64}"
                        multimodal_content.append({
                            "type": "image_url",
                            "image_url": {"url": img_base64}
                        })
                    langchain_messages.append(HumanMessage(content=multimodal_content))
                elif isinstance(content, list):
                    parts = []
                    for item in content:
                        if isinstance(item, dict):
                            if item.get("type") == "text":
                                parts.append({"type": "text", "text": item.get("text", "")})
                            elif item.get("type") == "image_url":
                                image_url = item.get("image_url", {})
                                url = image_url.get("url", "") if isinstance(image_url, dict) else str(image_url)
                                parts.append({"type": "image_url", "image_url": {"url": url}})
                        elif isinstance(item, str):
                            parts.append({"type": "text", "text": item})
                    langchain_messages.append(HumanMessage(content=parts))
                else:
                    langchain_messages.append(HumanMessage(content=str(content)))

        for attempt in range(max_retries):
            try:
                current_temperature = self.current_config.get("temperature", 0.1)

                if attempt > 0:
                    current_temperature = min(0.3, current_temperature + 0.05 * attempt)

                invoke_kwargs = {
                    "temperature": current_temperature,
                }
                if max_tokens is not None:
                    invoke_kwargs["max_tokens"] = max_tokens

                response = self.langchain_llm.invoke(
                    langchain_messages,
                    **invoke_kwargs,
                )

                if response:
                    response_text = response.content if hasattr(response, "content") else str(response)
                    metadata = response.response_metadata if hasattr(response, "response_metadata") else {}
                    if not response_text and hasattr(response, "additional_kwargs"):
                        reasoning = response.additional_kwargs.get("reasoning_content", "")
                        if reasoning:
                            response_text = reasoning
                            logger.info(f"🔄 [AIClient] content 为空，从 reasoning_content 恢复 ({len(reasoning)} chars)")
                    logger.info(f"API call success ({len(response_text)} chars)")
                    if not response_text:
                        finish_reason = metadata.get("finish_reason", "")
                        token_usage = metadata.get("token_usage", {})
                        reasoning_tokens = token_usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0) if isinstance(token_usage.get("completion_tokens_details"), dict) else 0
                        logger.warning(
                            f"🚨 [AIClient] 大模型返回 HTTP 200 但 content 为空！| "
                            f"finish_reason={finish_reason} | reasoning_tokens={reasoning_tokens} | "
                            f"model={self.selected_model}"
                        )
                    else:
                        logger.info(f"📋 [AIClient] 响应元数据: {metadata}")
                        logger.info(f"📋 [AIClient] 原始返回内容前200字: '{response_text[:200]}'")
                    return response_text
                else:
                    logger.warning(
                        f"🚨 [AIClient] attempt {attempt + 1}/{max_retries} 返回空响应 | "
                        f"model={self.selected_model}"
                    )
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        retry_delay *= 1.5
                    else:
                        logger.error(
                            f"🚨 [AIClient] 所有 {max_retries} 次重试均返回空响应！"
                            f" | model={self.selected_model}"
                            f" | provider={self.current_config.get('provider', 'unknown')}"
                            f" | base_url={self.current_config.get('base_url', 'unknown')}"
                        )
                        return None

            except Exception as e:
                logger.error(
                    f"🚨 [AIClient] attempt {attempt + 1}/{max_retries} 调用失败 | "
                    f"exception_type={type(e).__name__} | "
                    f"exception_repr={repr(e)} | "
                    f"model={self.selected_model} | "
                    f"provider={self.current_config.get('provider', 'unknown')} | "
                    f"base_url={self.current_config.get('base_url', 'unknown')}"
                )
                import traceback
                logger.error(f"🚨 [AIClient] 完整堆栈追踪:\n{traceback.format_exc()}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 1.5
                else:
                    logger.error(
                        f"🚨 [AIClient] 所有 {max_retries} 次重试均失败！"
                        f" | model={self.selected_model}"
                        f" | last_error={repr(e)}"
                    )
                    return None

        return None

    async def acall_api(self, messages: List[Dict], max_tokens: int = None, max_retries: int = None, base64_images: List[str] = None) -> Optional[str]:
        if not self.langchain_initialized:
            logger.error(
                "🚨 [AIClient] LangChain LLM 未初始化！无法调用大模型。"
                f" | selected_model={self.selected_model}"
                f" | current_config={self.current_config}"
            )
            return None

        max_retries = max_retries or self.current_config.get("retry_attempts", 5)

        logger.info(
            f"🚀 [AIClient] acall_api 开始 | "
            f"model={self.selected_model} | "
            f"provider={self.current_config.get('provider', 'unknown')} | "
            f"model_name={self.current_config.get('model_name', 'unknown')} | "
            f"max_tokens={max_tokens or self.current_config.get('max_output_tokens', 'default')} | "
            f"messages_count={len(messages)} | "
            f"max_retries={max_retries}"
        )

        langchain_messages = []
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            images = message.get("images", [])
            if role == "system":
                langchain_messages.append(SystemMessage(content=str(content)))
            elif role == "user":
                if images:
                    multimodal_content = [{"type": "text", "text": str(content)}]
                    for img_base64 in images:
                        if not img_base64.startswith("data:image"):
                            img_base64 = f"data:image/jpeg;base64,{img_base64}"
                        multimodal_content.append({
                            "type": "image_url",
                            "image_url": {"url": img_base64}
                        })
                    langchain_messages.append(HumanMessage(content=multimodal_content))
                elif isinstance(content, list):
                    parts = []
                    for item in content:
                        if isinstance(item, dict):
                            if item.get("type") == "text":
                                parts.append({"type": "text", "text": item.get("text", "")})
                            elif item.get("type") == "image_url":
                                image_url = item.get("image_url", {})
                                url = image_url.get("url", "") if isinstance(image_url, dict) else str(image_url)
                                parts.append({"type": "image_url", "image_url": {"url": url}})
                        elif isinstance(item, str):
                            parts.append({"type": "text", "text": item})
                    langchain_messages.append(HumanMessage(content=parts))
                else:
                    langchain_messages.append(HumanMessage(content=str(content)))

        if base64_images:
            last_user_idx = None
            for i, msg in enumerate(langchain_messages):
                if isinstance(msg, HumanMessage):
                    last_user_idx = i
            if last_user_idx is not None:
                existing = langchain_messages[last_user_idx].content
                if isinstance(existing, str):
                    parts = [{"type": "text", "text": existing}]
                elif isinstance(existing, list):
                    parts = existing
                else:
                    parts = [{"type": "text", "text": str(existing)}]
                for img in base64_images:
                    if not img.startswith("data:image"):
                        img = f"data:image/jpeg;base64,{img}"
                    parts.append({"type": "image_url", "image_url": {"url": img}})
                langchain_messages[last_user_idx] = HumanMessage(content=parts)
                logger.info(f"🚀 [AIClient] Injected {len(base64_images)} images into last user message (async)")

        has_images = bool(base64_images)
        if not has_images:
            for msg in messages:
                if msg.get("images"):
                    has_images = True
                    break
        if not has_images:
            for msg in langchain_messages:
                if isinstance(msg, HumanMessage) and isinstance(msg.content, list):
                    has_images = True
                    break

        use_vision = False
        if has_images and not self.current_config.get("supports_vision", False):
            if self.vision_llm:
                use_vision = True
                logger.info(f"🔄 [AIClient] Current model '{self.selected_model}' does not support Vision, auto-switching to '{self.vision_model_name}'")
            else:
                logger.warning("⚠️ [AIClient] Images detected but no Vision model available, stripping images from request")
                for i, msg in enumerate(langchain_messages):
                    if isinstance(msg, HumanMessage) and isinstance(msg.content, list):
                        text_parts = [p.get("text", "") for p in msg.content if isinstance(p, dict) and p.get("type") == "text"]
                        langchain_messages[i] = HumanMessage(content="\n".join(text_parts))

        active_llm = self.vision_llm if use_vision else self.langchain_llm

        # ── 使用 tenacity 工业级重试 ──
        @retry(
            stop=stop_after_attempt(max_retries),
            wait=wait_exponential(multiplier=2, min=3, max=30),
            retry=retry_if_exception(_is_retryable_error),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        async def _invoke_with_retry():
            current_temperature = self.current_config.get("temperature", 0.1)
            invoke_kwargs = {
                "temperature": current_temperature,
            }
            if max_tokens is not None:
                invoke_kwargs["max_tokens"] = max_tokens

            response = await active_llm.ainvoke(
                langchain_messages,
                **invoke_kwargs,
            )

            if not response:
                raise ValueError("LLM 返回空响应")

            response_text = response.content if hasattr(response, "content") else str(response)
            metadata = response.response_metadata if hasattr(response, "response_metadata") else {}

            # content 为空时尝试从 reasoning_content / tool_calls 恢复
            if not response_text and hasattr(response, "additional_kwargs"):
                reasoning = response.additional_kwargs.get("reasoning_content", "")
                if reasoning:
                    response_text = reasoning
                    logger.info(f"🔄 [AIClient] content 为空，从 reasoning_content 恢复 ({len(reasoning)} chars)")
            if not response_text and hasattr(response, 'tool_calls') and response.tool_calls:
                for tc in response.tool_calls:
                    if isinstance(tc.get("args"), dict) and tc["args"]:
                        response_text = json.dumps(tc["args"], ensure_ascii=False)
                        logger.info(f"🔄 [AIClient] content 为空，从 tool_calls 恢复")
                        break

            if not response_text:
                finish_reason = metadata.get("finish_reason", "")
                logger.warning(
                    f"🚨 [AIClient] 异步调用返回 HTTP 200 但 content 为空！| "
                    f"finish_reason={finish_reason} | model={self.selected_model}"
                )
            else:
                logger.info(f"Async API call success ({len(response_text)} chars)")
                logger.info(f"📋 [AIClient] 异步响应元数据: {metadata}")

            return response_text

        try:
            result = await _invoke_with_retry()
            return result
        except Exception as e:
            logger.error(
                f"🚨 [AIClient] 所有重试均失败！| "
                f"exception_type={type(e).__name__} | exception_repr={repr(e)} | "
                f"model={self.selected_model}"
            )
            return None

    def get_model_info(self) -> Dict:
        return {
            "model": self.selected_model,
            "provider": self.current_config.get("provider", "unknown"),
            "model_name": self.current_config.get("model_name", self.selected_model),
            "is_available": self.is_available if self.is_available is not None else False,
            "description": self.current_config.get("description", ""),
        }

    async def analyze_image(self, base64_image: str, prompt: str) -> str:
        if not base64_image:
            return ""

        if not base64_image.startswith("data:image"):
            base64_image = f"data:image/jpeg;base64,{base64_image}"

        if self.vision_llm:
            llm = self.vision_llm
            model_label = self.vision_model_name or "vision"
        elif self.langchain_initialized and self.current_config.get("supports_vision", False):
            llm = self.langchain_llm
            model_label = self.selected_model
        else:
            logger.warning("analyze_image: no Vision-capable model available")
            return ""

        try:
            multimodal_content = [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": base64_image}},
            ]
            message = HumanMessage(content=multimodal_content)

            response = await llm.ainvoke(
                [message],
                temperature=0.1,
                max_tokens=2048,
            )

            if response and hasattr(response, "content") and response.content:
                logger.info(f"analyze_image success via {model_label} ({len(response.content)} chars)")
                return response.content.strip()

            logger.warning(f"analyze_image: empty response from {model_label}")
            return ""

        except Exception as e:
            logger.error(f"analyze_image failed via {model_label}: {e}")
            return ""

    @property
    def config(self) -> Dict:
        full_config = {}
        full_config.update(self.models_config.get("common_config", {}))
        full_config.update(self.current_config)
        full_config["model_name"] = self.selected_model
        return full_config
