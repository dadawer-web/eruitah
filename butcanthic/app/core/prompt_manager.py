import logging
import os
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class PromptManager:
    _instance = None
    _prompts: Dict[str, str] = {}

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, prompts_dir: str = None):
        if prompts_dir and not self._prompts:
            self._load_all(prompts_dir)

    def _load_all(self, prompts_dir: str):
        if not os.path.isdir(prompts_dir):
            logger.warning(f"Prompts directory not found: {prompts_dir}")
            return
        for filename in os.listdir(prompts_dir):
            if filename.endswith(".md") or filename.endswith(".txt"):
                name = os.path.splitext(filename)[0]
                filepath = os.path.join(prompts_dir, filename)
                with open(filepath, "r", encoding="utf-8") as f:
                    self._prompts[name] = f.read().strip()
                logger.info(f"Loaded prompt: {name} ({len(self._prompts[name])} chars)")
        logger.info(f"PromptManager: {len(self._prompts)} prompts loaded from {prompts_dir}")

    @classmethod
    def get_prompt(cls, name: str, **kwargs) -> str:
        instance = cls()
        if not instance._prompts:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            prompts_dir = os.path.join(base_dir, "prompts")
            instance._load_all(prompts_dir)
        template = instance._prompts.get(name, "")
        if not template:
            logger.warning(f"Prompt not found: {name}")
            return ""
        if kwargs:
            try:
                return template.format(**kwargs)
            except KeyError as e:
                logger.warning(f"Prompt template variable missing: {e} | prompt={name}")
                return template
        return template

    @classmethod
    def reload(cls):
        instance = cls()
        instance._prompts.clear()
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        prompts_dir = os.path.join(base_dir, "prompts")
        instance._load_all(prompts_dir)
