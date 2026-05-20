"""
Eruitah 智能编程沙盒 - Prompt 动态组装引擎

根据前端传来的技能 ID 列表，从 agent_prompts/ 目录读取对应的 .md 文件，
与默认系统提示词拼接成最终的专业 System Prompt。
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_prompts")

SKILL_FILE_MAP = {
    "performance": "performance.md",
    "security": "security.md",
    "tdd": "tdd.md",
    "doubt": "doubt.md",
    "plan": "idea-refine.md",
    "sdd": "sdd/SKILL.md",
    "debugging": "systematic_debugging.md",
    "visual": "visual_brainstorming.md",
}

PLAN_MODE_TOOLS = {"ask_user", "file_edit", "file_write", "file_read", "glob", "grep"}

PLAN_MODE_EXECUTION_DIRECTIVE = (
    "\n\n---\n"
    "⚠️ PM模式执行指令：你当前只能提问和编写需求文档，"
    "绝对不能执行任何代码。请通过 ask_user 工具与用户对话，"
    "最终将讨论结果写入 SPEC.md 或 PLAN.md。"
)

EXECUTION_DIRECTIVE = (
    "\n\n---\n"
    "⚠️ 执行指令：请直接使用工具执行上述工作流，"
    "不要用文字向用户解释你的计划，遇到错误请在沙盒内自行重试。"
)


class PromptBuilder:
    def __init__(self, prompts_dir: str = PROMPTS_DIR):
        self.prompts_dir = prompts_dir
        self._cache = {}

    def _read_skill_file(self, filename: str) -> Optional[str]:
        if filename in self._cache:
            return self._cache[filename]

        filepath = os.path.join(self.prompts_dir, filename)
        if not os.path.isfile(filepath):
            logger.warning(f"技能文件不存在: {filepath}")
            return None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read().strip()
            self._cache[filename] = content
            return content
        except Exception as e:
            logger.error(f"读取技能文件失败: {filepath} - {e}")
            return None

    def build_skill_prompt(self, skills: list[str]) -> str:
        if not skills:
            return ""

        parts = []
        for skill_id in skills:
            filename = SKILL_FILE_MAP.get(skill_id)
            if not filename:
                logger.warning(f"未知技能 ID: {skill_id}")
                continue

            content = self._read_skill_file(filename)
            if content:
                parts.append(content)

        if not parts:
            return ""

        combined = "\n\n---\n\n".join(parts)

        if "plan" in skills:
            combined += PLAN_MODE_EXECUTION_DIRECTIVE
        else:
            combined += EXECUTION_DIRECTIVE

        logger.info(f"📋 PromptBuilder: 拼接了 {len(parts)} 个技能提示词 (skills={skills})")
        return combined

    def build_full_prompt(self, base_prompt: str, skills: list[str]) -> str:
        skill_prompt = self.build_skill_prompt(skills)
        if not skill_prompt:
            return base_prompt

        return f"{base_prompt}\n\n{'=' * 60}\n# 🎯 专家技能激活\n{'=' * 60}\n\n{skill_prompt}"

    def clear_cache(self):
        self._cache.clear()


_prompt_builder = None


def get_prompt_builder() -> PromptBuilder:
    global _prompt_builder
    if _prompt_builder is None:
        _prompt_builder = PromptBuilder()
    return _prompt_builder
