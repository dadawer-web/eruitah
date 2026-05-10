"""
Eruitah 智能编程沙盒 - AST 代码结构工具

核心思想:
┌─────────────────────────────────────────────────────────────────────┐
│  grep "class Session" → 匹配注释、字符串、模板参数... 50+ 垃圾结果  │
│  get_code_structure → 只返回类名、函数签名、行号 → 3 个精确结果     │
│                                                                     │
│  get_function_definition("connect") → 直接返回函数完整代码块        │
│  grep "def connect" → 还要自己数行号、手动拼接                      │
│                                                                     │
│  两个工具的分工:                                                    │
│    get_code_structure:  "这个文件里有什么？" (鸟瞰图)               │
│    get_function_definition: "这个函数怎么实现的？" (精准打击)       │
└─────────────────────────────────────────────────────────────────────┘
"""

import os
import logging
from typing import Optional

from tree_sitter_index import (
    get_indexer,
    get_db,
    parse_file_with_treesitter,
    SUPPORTED_EXTENSIONS,
    KIND_CLASS,
    KIND_INTERFACE,
    KIND_STRUCT,
    KIND_FUNCTION,
    KIND_METHOD,
    KIND_ENUM,
    KIND_TRAIT,
)

logger = logging.getLogger(__name__)


def _infer_end_line(lines: list[str], start_line: int, language: str) -> int:
    if start_line < 1 or start_line > len(lines):
        return start_line

    if language == "python":
        def_line = lines[start_line - 1]
        base_indent = len(def_line) - len(def_line.lstrip())

        end = start_line
        for i in range(start_line, len(lines)):
            line = lines[i]
            stripped = line.strip()
            if not stripped:
                end = i + 1
                continue
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= base_indent:
                break
            end = i + 1
        return end

    if language in ("c", "cpp", "java", "c_sharp", "go", "rust", "kotlin", "swift"):
        brace_count = 0
        found_open = False
        for i in range(start_line - 1, min(start_line + 2000, len(lines))):
            line = lines[i]
            for ch in line:
                if ch == '{':
                    brace_count += 1
                    found_open = True
                elif ch == '}':
                    brace_count -= 1
                    if found_open and brace_count == 0:
                        return i + 1
        return min(start_line + 200, len(lines))

    if language in ("javascript", "typescript", "tsx", "jsx"):
        brace_count = 0
        found_open = False
        for i in range(start_line - 1, min(start_line + 2000, len(lines))):
            line = lines[i]
            for ch in line:
                if ch == '{':
                    brace_count += 1
                    found_open = True
                elif ch == '}':
                    brace_count -= 1
                    if found_open and brace_count == 0:
                        return i + 1
        return min(start_line + 200, len(lines))

    return min(start_line + 100, len(lines))


def execute_get_code_structure(
    file_path: str,
    work_dir: str = "",
) -> tuple[str, bool]:
    if not file_path:
        return "文件路径不能为空", True

    if work_dir and not os.path.isabs(file_path):
        file_path = os.path.join(work_dir, file_path)

    file_path = os.path.abspath(file_path)

    if not os.path.isfile(file_path):
        return f"文件不存在: {file_path}", True

    ext = os.path.splitext(file_path)[1]
    if ext not in SUPPORTED_EXTENSIONS:
        return f"不支持的语言类型: {ext}。支持: {', '.join(sorted(SUPPORTED_EXTENSIONS.keys()))}", True

    language = SUPPORTED_EXTENSIONS[ext]

    try:
        indexer = get_indexer()
        indexer.index_file(file_path, force=True)

        db = get_db()
        symbols = db.get_file_symbols(file_path)

        if not symbols:
            symbols_raw = parse_file_with_treesitter(file_path, language)
            if not symbols_raw:
                return f"文件 {os.path.basename(file_path)} 中未找到任何代码结构（类/函数/方法）", False

            symbols = [
                {
                    "name": s.name,
                    "kind": s.kind,
                    "signature": s.signature,
                    "line": s.line,
                    "end_line": s.end_line,
                    "parent_name": s.parent_name,
                    "docstring": s.docstring,
                }
                for s in symbols_raw
            ]

    except Exception as e:
        logger.error(f"AST 解析失败 {file_path}: {e}")
        return f"AST 解析失败: {str(e)}", True

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            file_lines = f.readlines()
    except Exception:
        file_lines = []

    for sym in symbols:
        if sym.get("end_line", 0) <= sym.get("line", 0) and file_lines:
            sym["end_line"] = _infer_end_line(file_lines, sym["line"], language)

    lines = [f"📐 {os.path.basename(file_path)} 代码结构 ({language}):\n"]

    kind_icons = {
        KIND_CLASS: "📦",
        KIND_INTERFACE: "🔌",
        KIND_STRUCT: "🏗️",
        KIND_FUNCTION: "⚡",
        KIND_METHOD: "🔧",
        KIND_ENUM: "📋",
        KIND_TRAIT: "🧩",
    }

    current_parent = None
    for sym in symbols:
        kind = sym.get("kind", "")
        name = sym.get("name", "")
        sig = sym.get("signature", "")
        line = sym.get("line", 0)
        end_line = sym.get("end_line", 0)
        parent = sym.get("parent_name", "")
        doc = sym.get("docstring", "")

        icon = kind_icons.get(kind, "📍")

        if kind in (KIND_CLASS, KIND_INTERFACE, KIND_STRUCT, KIND_ENUM, KIND_TRAIT):
            lines.append(f"  {icon} {kind} {name}  (L{line}-{end_line})")
            if sig:
                lines.append(f"     签名: {sig}")
            if doc:
                lines.append(f"     文档: {doc[:150]}")
            current_parent = name
        elif kind in (KIND_METHOD, KIND_FUNCTION):
            if parent and parent == current_parent:
                lines.append(f"    ├─ {icon} {kind} {name}  (L{line}-{end_line})")
            elif parent:
                lines.append(f"    ├─ {icon} {kind} {name} (in {parent})  (L{line}-{end_line})")
            else:
                lines.append(f"  {icon} {kind} {name}  (L{line}-{end_line})")
            if sig:
                lines.append(f"       签名: {sig}")
        else:
            indent = "    ├─ " if parent else "  "
            lines.append(f"{indent}{icon} {kind} {name}  (L{line})")

    total_classes = sum(1 for s in symbols if s.get("kind") in (KIND_CLASS, KIND_INTERFACE, KIND_STRUCT))
    total_functions = sum(1 for s in symbols if s.get("kind") in (KIND_FUNCTION, KIND_METHOD))
    lines.append(f"\n  📊 共 {total_classes} 个类型, {total_functions} 个函数/方法")

    return "\n".join(lines), False


def execute_get_function_definition(
    file_path: str,
    function_name: str,
    work_dir: str = "",
) -> tuple[str, bool]:
    if not file_path:
        return "文件路径不能为空", True
    if not function_name:
        return "函数名不能为空", True

    if work_dir and not os.path.isabs(file_path):
        file_path = os.path.join(work_dir, file_path)

    file_path = os.path.abspath(file_path)

    if not os.path.isfile(file_path):
        return f"文件不存在: {file_path}", True

    ext = os.path.splitext(file_path)[1]
    if ext not in SUPPORTED_EXTENSIONS:
        return f"不支持的语言类型: {ext}", True

    language = SUPPORTED_EXTENSIONS[ext]

    try:
        indexer = get_indexer()
        indexer.index_file(file_path, force=True)

        db = get_db()
        symbols = db.get_file_symbols(file_path)

        if not symbols:
            symbols_raw = parse_file_with_treesitter(file_path, language)
            if not symbols_raw:
                return f"文件中未找到任何符号", True
            symbols = [
                {
                    "name": s.name,
                    "kind": s.kind,
                    "signature": s.signature,
                    "line": s.line,
                    "end_line": s.end_line,
                    "parent_name": s.parent_name,
                    "docstring": s.docstring,
                }
                for s in symbols_raw
            ]

    except Exception as e:
        logger.error(f"AST 解析失败 {file_path}: {e}")
        return f"AST 解析失败: {str(e)}", True

    matches = []
    for sym in symbols:
        if sym.get("name") == function_name and sym.get("kind") in (KIND_FUNCTION, KIND_METHOD):
            matches.append(sym)

    if not matches:
        fuzzy = [s for s in symbols if function_name.lower() in s.get("name", "").lower()
                 and s.get("kind") in (KIND_FUNCTION, KIND_METHOD)]
        if fuzzy:
            names = [f"{s['name']} (L{s['line']})" for s in fuzzy[:5]]
            return (
                f"未找到名为「{function_name}」的函数/方法。"
                f"相似名称: {', '.join(names)}"
            ), True
        all_names = [s["name"] for s in symbols if s.get("kind") in (KIND_FUNCTION, KIND_METHOD)]
        if all_names:
            return (
                f"未找到名为「{function_name}」的函数/方法。"
                f"该文件中的函数/方法: {', '.join(all_names[:20])}"
            ), True
        return f"文件中没有任何函数/方法", True

    if len(matches) > 1:
        lines = [f"⚠️ 找到 {len(matches)} 个名为「{function_name}」的函数/方法（重载/多类同名）:\n"]
        for i, m in enumerate(matches):
            parent = f" (in {m['parent_name']})" if m.get("parent_name") else ""
            lines.append(f"  [{i+1}] {m['kind']} {function_name}{parent} @ L{m['line']}-{m['end_line']}")
        lines.append(f"\n默认返回第一个匹配:\n")

    target = matches[0]
    start_line = target["line"]
    end_line = target["end_line"]
    parent = target.get("parent_name", "")
    kind = target.get("kind", "function")
    sig = target.get("signature", "")

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
    except Exception as e:
        return f"读取文件失败: {e}", True

    if start_line < 1 or start_line > len(all_lines):
        return f"行号超出范围: L{start_line}", True

    if end_line <= start_line:
        end_line = _infer_end_line(all_lines, start_line, language)

    actual_end = min(end_line, len(all_lines))
    code_lines = all_lines[start_line - 1:actual_end]
    code = "".join(code_lines)

    if len(code) > 8000:
        code = code[:8000] + f"\n... [截断，完整代码共 {len(code)} 字符]"

    parent_info = f" (in {parent})" if parent else ""
    header = f"🔍 {kind} {function_name}{parent_info} @ {os.path.basename(file_path)}:L{start_line}-{end_line}"
    if sig:
        header += f"\n   签名: {sig}"

    result = f"{header}\n\n```{language}\n{code}\n```"

    return result, False


AST_CODE_STRUCTURE_TOOL_DEFINITION_OPENAI = {
    "type": "function",
    "function": {
        "name": "get_code_structure",
        "description": (
            "获取文件的代码结构（AST 级别）。返回该文件中所有的类名、函数名、方法名及其签名和行号。"
            "比 grep 精准 100 倍——只返回真正的代码结构，不会匹配注释或字符串。"
            "当你想了解一个文件有哪些类和函数时，优先使用此工具，而不是 grep。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件路径，如 'main.py' 或 'src/app.js'",
                },
            },
            "required": ["file_path"],
        },
    },
}

AST_CODE_STRUCTURE_TOOL_DEFINITION_ANTHROPIC = {
    "name": "get_code_structure",
    "description": (
        "获取文件的代码结构（AST 级别）。返回该文件中所有的类名、函数名、方法名及其签名和行号。"
        "比 grep 精准 100 倍——只返回真正的代码结构，不会匹配注释或字符串。"
        "当你想了解一个文件有哪些类和函数时，优先使用此工具，而不是 grep。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "文件路径，如 'main.py' 或 'src/app.js'",
            },
        },
        "required": ["file_path"],
    },
}

AST_FUNCTION_DEFINITION_TOOL_DEFINITION_OPENAI = {
    "type": "function",
    "function": {
        "name": "get_function_definition",
        "description": (
            "精准获取函数/方法的完整代码实现。基于 AST 定位，直接返回函数体代码块。"
            "当你需要查看某个函数的具体实现时，优先使用此工具，而不是 grep + file_read 手动拼凑。"
            "支持重载检测——如果存在多个同名函数，会列出所有匹配项。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件路径，如 'main.py' 或 'src/app.js'",
                },
                "function_name": {
                    "type": "string",
                    "description": "函数或方法名，如 'connect', 'handle_request'",
                },
            },
            "required": ["file_path", "function_name"],
        },
    },
}

AST_FUNCTION_DEFINITION_TOOL_DEFINITION_ANTHROPIC = {
    "name": "get_function_definition",
    "description": (
        "精准获取函数/方法的完整代码实现。基于 AST 定位，直接返回函数体代码块。"
        "当你需要查看某个函数的具体实现时，优先使用此工具，而不是 grep + file_read 手动拼凑。"
        "支持重载检测——如果存在多个同名函数，会列出所有匹配项。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "文件路径",
            },
            "function_name": {
                "type": "string",
                "description": "函数或方法名",
            },
        },
        "required": ["file_path", "function_name"],
    },
}
