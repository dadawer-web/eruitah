"""
Eruitah 智能编程沙盒 - Memory Store (Agent 记忆引擎)

核心设计:
  Prompt 是工作台，文件系统是仓库。
  不把规则写死在 Python 的 System Prompt 中，
  而是存放在 .agent_memory/ 目录下的结构化文件里。

架构:
  .agent_memory/
    ├── AGENT.md           ← 项目约定 (自动注入 System Prompt)
    ├── preferences.json   ← 用户偏好
    ├── rules_c++.md       ← C++ 项目规范
    ├── rules_python.md    ← Python 项目规范
    └── learnings.md       ← 过去踩过的坑 (带 TTL Frontmatter)

TTL 机制:
  每条 learning 带有 Frontmatter:
    ---
    date: 2026-04-28
    related_files: ["src/network/server.cpp"]
    status: active
    ---
  search_memory 读取时，如果相关文件已发生重大变更，
  标注 [WARNING: STALE MEMORY] 或直接过滤。
"""

import os
import json
import time
import hashlib
import logging
import re
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

DEFAULT_AGENT_MD_CONTENT = """# 🤖 Agentic Coding 团队规范

## 验证与测试原则
1. **禁止写测试框架**：不要编写 `pytest` 或 `unittest`。
2. **快速验证**：写完代码后，请在文件末尾写 `if __name__ == '__main__':`，直接打印结果，并在终端运行该 Python/C++ 文件。只要不报错就算成功。

## 提交流程
1. 所有的变更由外部系统自动提交。
2. 当你确认代码运行无误后，只需在回复的最后一行输出 `[STATUS: TASK_DONE]`。
"""

MEMORY_DIR_NAME = ".agent_memory"


def _get_memory_dir(work_dir: str) -> str:
    return os.path.join(work_dir, MEMORY_DIR_NAME)


def init_memory_store(work_dir: str) -> str:
    memory_dir = _get_memory_dir(work_dir)
    os.makedirs(memory_dir, exist_ok=True)

    root_agent_md = os.path.join(work_dir, "AGENT.md")
    if not os.path.exists(root_agent_md):
        with open(root_agent_md, "w", encoding="utf-8") as f:
            f.write(DEFAULT_AGENT_MD_CONTENT)
        logger.info(f"📝 已创建默认 AGENT.md: {root_agent_md}")

    memory_agent_md = os.path.join(memory_dir, "AGENT.md")
    if not os.path.exists(memory_agent_md):
        with open(memory_agent_md, "w", encoding="utf-8") as f:
            f.write("# Project Agent Rules\n\n")
            f.write("This file is automatically loaded into the Agent's system prompt.\n")
            f.write("Add project-specific conventions, architecture constraints, and coding standards here.\n\n")
            f.write("## Conventions\n\n- (Add your project conventions here)\n")
        logger.info(f"📝 已创建默认 .agent_memory/AGENT.md: {memory_agent_md}")

    learnings_path = os.path.join(memory_dir, "learnings.md")
    if not os.path.exists(learnings_path):
        with open(learnings_path, "w", encoding="utf-8") as f:
            f.write("# Agent Learnings\n\n")
            f.write("Auto-generated experience records from Agent task execution.\n")
            f.write("Each entry has a TTL frontmatter with date, related_files, and status.\n\n")
        logger.info(f"📝 已创建默认 learnings.md: {learnings_path}")

    prefs_path = os.path.join(memory_dir, "preferences.json")
    if not os.path.exists(prefs_path):
        with open(prefs_path, "w", encoding="utf-8") as f:
            json.dump({"language_preferences": {}, "framework_preferences": {}}, f, indent=2, ensure_ascii=False)
        logger.info(f"📝 已创建默认 preferences.json: {prefs_path}")

    return memory_dir


def load_agent_md(work_dir: str) -> str:
    memory_dir = _get_memory_dir(work_dir)
    agent_md_path = os.path.join(memory_dir, "AGENT.md")

    if not os.path.exists(agent_md_path):
        return ""

    try:
        with open(agent_md_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if content:
            logger.info(f"📖 已加载项目记忆 AGENT.md ({len(content)} chars)")
        return content
    except Exception as e:
        logger.warning(f"读取 AGENT.md 失败: {e}")
        return ""


def load_all_memory_files(work_dir: str) -> str:
    memory_dir = _get_memory_dir(work_dir)
    if not os.path.exists(memory_dir):
        return ""

    parts = []

    agent_md = load_agent_md(work_dir)
    if agent_md:
        parts.append(f"=== 项目约定 (AGENT.md) ===\n{agent_md}\n")

    prefs_path = os.path.join(memory_dir, "preferences.json")
    if os.path.exists(prefs_path):
        try:
            with open(prefs_path, "r", encoding="utf-8") as f:
                prefs = json.load(f)
            if prefs and any(prefs.values()):
                parts.append(f"=== 用户偏好 (preferences.json) ===\n{json.dumps(prefs, ensure_ascii=False, indent=2)}\n")
        except Exception:
            pass

    for filename in sorted(os.listdir(memory_dir)):
        if filename.startswith("rules_") and filename.endswith(".md"):
            filepath = os.path.join(memory_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if content:
                    rule_name = filename[6:-3]
                    parts.append(f"=== 项目规范 ({rule_name}) ===\n{content}\n")
            except Exception:
                pass

    return "\n".join(parts)


def search_memory(query: str, work_dir: str) -> str:
    memory_dir = _get_memory_dir(work_dir)
    if not os.path.exists(memory_dir):
        return "No memory store found. This is a fresh project with no prior learnings."

    results = []
    query_lower = query.lower()
    query_keywords = set(query_lower.split())

    for filename in sorted(os.listdir(memory_dir)):
        if not filename.endswith(".md"):
            continue

        filepath = os.path.join(memory_dir, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            continue

        entries = _parse_entries_with_frontmatter(content)

        for entry in entries:
            body = entry["body"].lower()
            title_match = entry.get("title", "").lower()

            score = 0
            for kw in query_keywords:
                if kw in body:
                    score += 2
                if kw in title_match:
                    score += 3

            if score == 0:
                continue

            staleness = _check_staleness(entry, work_dir)
            prefix = ""
            if staleness == "stale":
                prefix = "⚠️ [WARNING: STALE MEMORY - related files have changed significantly since this was recorded]\n"
            elif staleness == "aged":
                prefix = "⏰ [AGED MEMORY - recorded over 30 days ago, may be outdated]\n"

            source = f"({filename})"
            title = entry.get("title", "Untitled")
            date_str = entry.get("date", "unknown")

            results.append({
                "score": score,
                "text": f"{prefix}📌 {title} [{date_str}] {source}\n{entry['body'].strip()}",
            })

    if not results:
        return f"No relevant memories found for query: '{query}'"

    results.sort(key=lambda x: x["score"], reverse=True)
    top_results = results[:5]

    output_parts = [f"🔍 Found {len(results)} memory entries for '{query}' (showing top {len(top_results)}):\n"]
    for r in top_results:
        output_parts.append(r["text"])
        output_parts.append("---")

    return "\n".join(output_parts)


def record_learning(
    category: str,
    lesson: str,
    work_dir: str,
    related_files: Optional[List[str]] = None,
) -> str:
    memory_dir = _get_memory_dir(work_dir)
    os.makedirs(memory_dir, exist_ok=True)

    learnings_path = os.path.join(memory_dir, "learnings.md")

    file_hashes = {}
    if related_files:
        for rf in related_files:
            full_path = os.path.join(work_dir, rf) if not os.path.isabs(rf) else rf
            file_hashes[rf] = _file_hash(full_path)

    date_str = time.strftime("%Y-%m-%d")
    related_files_str = json.dumps(related_files or [], ensure_ascii=False)
    hashes_str = json.dumps(file_hashes, ensure_ascii=False)

    frontmatter = (
        f"---\n"
        f"date: {date_str}\n"
        f"category: {category}\n"
        f"related_files: {related_files_str}\n"
        f"file_hashes: {hashes_str}\n"
        f"status: active\n"
        f"---\n"
    )

    entry = f"\n{frontmatter}\n# [{category}] {lesson[:80]}\n\n{lesson}\n"

    try:
        with open(learnings_path, "a", encoding="utf-8") as f:
            f.write(entry)
        logger.info(f"📝 已记录经验: [{category}] {lesson[:50]}")

        try:
            from sandbox_manager import get_sandbox
            sandbox = get_sandbox(work_dir)
            sandbox.commit_agent_changes(
                "memory_store",
                f"memory: record_learning [{category}]",
                model_name="system",
            )
        except Exception as e:
            logger.debug(f"记忆写入后 Git commit 失败: {e}")

        return f"✅ Learning recorded: [{category}] {lesson[:60]}"
    except Exception as e:
        logger.error(f"记录经验失败: {e}")
        return f"❌ Failed to record learning: {e}"


def _parse_entries_with_frontmatter(content: str) -> List[Dict[str, Any]]:
    entries = []
    parts = re.split(r'\n---\n', content)

    for part in parts:
        part = part.strip()
        if not part:
            continue

        entry = {"date": "", "category": "", "related_files": [], "file_hashes": {}, "status": "active", "title": "", "body": part}

        fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', part, re.DOTALL)
        if fm_match:
            fm_text = fm_match.group(1)
            body_text = fm_match.group(2)

            for line in fm_text.strip().split("\n"):
                if ":" in line:
                    key, _, val = line.partition(":")
                    key = key.strip()
                    val = val.strip()
                    if key == "date":
                        entry["date"] = val
                    elif key == "category":
                        entry["category"] = val
                    elif key == "related_files":
                        try:
                            entry["related_files"] = json.loads(val)
                        except Exception:
                            entry["related_files"] = []
                    elif key == "file_hashes":
                        try:
                            entry["file_hashes"] = json.loads(val)
                        except Exception:
                            entry["file_hashes"] = {}
                    elif key == "status":
                        entry["status"] = val

            title_match = re.search(r'^#\s+(.+)', body_text, re.MULTILINE)
            if title_match:
                entry["title"] = title_match.group(1).strip()
            entry["body"] = body_text

        entries.append(entry)

    return entries


def _file_hash(filepath: str) -> str:
    if not os.path.exists(filepath):
        return ""
    try:
        with open(filepath, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()[:12]
    except Exception:
        return ""


def _check_staleness(entry: Dict[str, Any], work_dir: str) -> str:
    date_str = entry.get("date", "")
    if date_str:
        try:
            record_time = time.mktime(time.strptime(date_str, "%Y-%m-%d"))
            age_days = (time.time() - record_time) / 86400
            if age_days > 60:
                return "aged"
        except Exception:
            pass

    file_hashes = entry.get("file_hashes", {})
    related_files = entry.get("related_files", [])

    if file_hashes and related_files:
        for rf in related_files:
            full_path = os.path.join(work_dir, rf) if not os.path.isabs(rf) else rf
            old_hash = file_hashes.get(rf, "")
            current_hash = _file_hash(full_path)
            if old_hash and current_hash and old_hash != current_hash:
                return "stale"

    return "fresh"
