"""
Eruitah 智能编程沙盒 - 语义搜索工具 (Semantic Search Tool)

核心思想:
┌─────────────────────────────────────────────────────────────────────┐
│  GrepTool → 搜关键字 → 噪音太多                                    │
│  SemanticSearchTool → 搜语义符号 → 精准定位                         │
│                                                                     │
│  支持的查询类型:                                                    │
│    - symbol_search: 按名称搜索符号（类、函数、变量等）               │
│    - definition_search: 查找定义位置                                │
│    - hierarchy_search: 查找继承关系（子类/父类）                    │
│    - reference_search: 查找引用位置                                 │
│    - file_outline: 获取文件的符号大纲                               │
│    - project_overview: 获取项目整体符号概览                         │
│                                                                     │
│  大模型使用方式:                                                    │
│    semantic_search(query="class Session", kind="class")             │
│    semantic_search(query="connect", kind="method", parent="Session")│
│    semantic_search(query="outline", file_path="main.py")            │
│    semantic_search(query="overview")                                │
└─────────────────────────────────────────────────────────────────────┘

参考源码:
    claude-code-rev/src/utils/bash/treeSitterAnalysis.ts
    claude-code-rev/src/utils/codeIndexing.ts
"""

import json
import logging
from dataclasses import dataclass
from typing import Optional

from tree_sitter_index import (
    get_indexer,
    get_db,
    CodeIndexer,
    CodeIndexDB,
    Symbol,
    KIND_CLASS,
    KIND_INTERFACE,
    KIND_STRUCT,
    KIND_FUNCTION,
    KIND_METHOD,
    KIND_VARIABLE,
    KIND_CONSTANT,
    KIND_ENUM,
    KIND_TRAIT,
    KIND_NAMESPACE,
    KIND_PROPERTY,
    KIND_FIELD,
    SUPPORTED_EXTENSIONS,
)

logger = logging.getLogger(__name__)

VALID_KINDS = {
    "class", "interface", "struct", "function", "method",
    "variable", "constant", "enum", "trait", "namespace",
    "property", "field",
}


@dataclass
class SemanticSearchResult:
    success: bool
    results: list = None
    total: int = 0
    truncated: bool = False
    error: str = ""

    def __post_init__(self):
        if self.results is None:
            self.results = []


def semantic_search(
    query: str,
    kind: Optional[str] = None,
    file_path: Optional[str] = None,
    parent_name: Optional[str] = None,
    language: Optional[str] = None,
    project_dir: Optional[str] = None,
    limit: int = 50,
) -> SemanticSearchResult:
    try:
        if project_dir:
            indexer = get_indexer()
            indexer.index_project(project_dir)

        db = get_db()

        if query == "outline" and file_path:
            return _file_outline(db, file_path)

        if query == "overview":
            return _project_overview(db)

        if query == "hierarchy":
            return _hierarchy_search(db, kind or "class", parent_name or query)

        effective_kind = kind if kind in VALID_KINDS else None

        results = db.search_symbols(
            name=query,
            kind=effective_kind,
            file_path=file_path,
            parent_name=parent_name,
            language=language,
            limit=limit + 1,
        )

        truncated = len(results) > limit
        if truncated:
            results = results[:limit]

        formatted = []
        for r in results:
            entry = {
                "name": r["name"],
                "kind": r["kind"],
                "file": r["file_path"],
                "line": r["line"],
                "signature": r.get("signature", ""),
            }
            if r.get("parent_name"):
                entry["parent"] = r["parent_name"]
            if r.get("docstring"):
                entry["docstring"] = r["docstring"][:200]
            formatted.append(entry)

        return SemanticSearchResult(
            success=True,
            results=formatted,
            total=len(formatted),
            truncated=truncated,
        )

    except Exception as e:
        logger.error(f"语义搜索失败: {e}")
        return SemanticSearchResult(success=False, error=str(e))


def _file_outline(db: CodeIndexDB, file_path: str) -> SemanticSearchResult:
    symbols = db.get_file_symbols(file_path)

    formatted = []
    for s in symbols:
        indent = ""
        if s["kind"] in (KIND_METHOD, KIND_FIELD, KIND_PROPERTY):
            indent = "  "
        if s.get("parent_name"):
            indent = "  "

        entry = {
            "kind": s["kind"],
            "name": s["name"],
            "file": s["file_path"],
            "line": s["line"],
            "signature": s.get("signature", ""),
        }
        if s.get("parent_name"):
            entry["parent"] = s["parent_name"]
        formatted.append(entry)

    return SemanticSearchResult(
        success=True,
        results=formatted,
        total=len(formatted),
    )


def _project_overview(db: CodeIndexDB) -> SemanticSearchResult:
    stats = db.get_stats()

    class_symbols = db.search_symbols(kind=KIND_CLASS, limit=30)
    interface_symbols = db.search_symbols(kind=KIND_INTERFACE, limit=20)
    function_symbols = db.search_symbols(kind=KIND_FUNCTION, limit=20)

    overview = {
        "total_files": stats.total_files,
        "total_symbols": stats.total_symbols,
        "languages": stats.languages,
        "top_classes": [
            {"name": s["name"], "file": s["file_path"], "line": s["line"]}
            for s in class_symbols
        ],
        "top_interfaces": [
            {"name": s["name"], "file": s["file_path"], "line": s["line"]}
            for s in interface_symbols
        ],
        "top_functions": [
            {"name": s["name"], "file": s["file_path"], "line": s["line"]}
            for s in function_symbols
        ],
    }

    return SemanticSearchResult(
        success=True,
        results=[overview],
        total=1,
    )


def _hierarchy_search(db: CodeIndexDB, kind: str, name: str) -> SemanticSearchResult:
    parent_symbols = db.search_symbols(name=name, kind=kind, limit=10)

    all_results = []
    for parent in parent_symbols:
        parent_entry = {
            "name": parent["name"],
            "kind": parent["kind"],
            "file": parent["file_path"],
            "line": parent["line"],
            "signature": parent.get("signature", ""),
            "children": [],
        }

        children = db.search_symbols(parent_name=parent["name"], limit=50)
        for child in children:
            parent_entry["children"].append({
                "name": child["name"],
                "kind": child["kind"],
                "line": child["line"],
                "signature": child.get("signature", ""),
            })

        all_results.append(parent_entry)

    return SemanticSearchResult(
        success=True,
        results=all_results,
        total=len(all_results),
    )


SEMANTIC_SEARCH_TOOL_DEFINITION_ANTHROPIC = {
    "name": "semantic_search",
    "description": (
        "语义代码搜索工具。基于 Tree-sitter AST 索引，按符号名称、类型、继承关系搜索代码。"
        "比 grep 更精准，不会匹配注释或字符串中的内容。"
        "支持搜索: class, function, method, variable, interface, struct, enum 等。"
        "特殊查询: query='outline' 查看文件大纲, query='overview' 查看项目概览, query='hierarchy' 查看继承关系。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词，或特殊查询: 'outline'(文件大纲), 'overview'(项目概览), 'hierarchy'(继承关系)",
            },
            "kind": {
                "type": "string",
                "enum": list(VALID_KINDS),
                "description": "符号类型过滤: class, function, method, variable 等",
            },
            "file_path": {
                "type": "string",
                "description": "限定搜索的文件路径",
            },
            "parent_name": {
                "type": "string",
                "description": "限定父级符号名称（如搜索某个类的方法）",
            },
            "language": {
                "type": "string",
                "description": "限定编程语言: python, cpp, java, javascript 等",
            },
            "project_dir": {
                "type": "string",
                "description": "项目目录（首次搜索时建立索引）",
            },
        },
        "required": ["query"],
    },
}

SEMANTIC_SEARCH_TOOL_DEFINITION_OPENAI = {
    "type": "function",
    "function": {
        "name": "semantic_search",
        "description": (
            "语义代码搜索工具。基于 Tree-sitter AST 索引，按符号名称、类型、继承关系搜索代码。"
            "比 grep 更精准，不会匹配注释或字符串中的内容。"
            "支持搜索: class, function, method, variable, interface, struct, enum 等。"
            "特殊查询: query='outline' 查看文件大纲, query='overview' 查看项目概览, query='hierarchy' 查看继承关系。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词，或特殊查询: 'outline', 'overview', 'hierarchy'",
                },
                "kind": {
                    "type": "string",
                    "enum": list(VALID_KINDS),
                    "description": "符号类型过滤",
                },
                "file_path": {
                    "type": "string",
                    "description": "限定搜索的文件路径",
                },
                "parent_name": {
                    "type": "string",
                    "description": "限定父级符号名称",
                },
                "language": {
                    "type": "string",
                    "description": "限定编程语言",
                },
                "project_dir": {
                    "type": "string",
                    "description": "项目目录",
                },
            },
            "required": ["query"],
        },
    },
}


def format_semantic_results(result: SemanticSearchResult) -> str:
    if not result.success:
        return f"语义搜索失败: {result.error}"

    if not result.results:
        return "未找到匹配的符号"

    if len(result.results) == 1 and isinstance(result.results[0], dict) and "total_files" in result.results[0]:
        overview = result.results[0]
        lines = [
            f"📊 项目概览:",
            f"  文件数: {overview['total_files']}",
            f"  符号数: {overview['total_symbols']}",
            f"  语言: {', '.join(f'{k}({v})' for k, v in overview['languages'].items())}",
        ]
        if overview.get("top_classes"):
            lines.append(f"\n  主要类:")
            for cls in overview["top_classes"][:10]:
                lines.append(f"    - {cls['name']} @ {cls['file']}:{cls['line']}")
        return "\n".join(lines)

    lines = [f"语义搜索结果 ({result.total} 个符号){' [截断]' if result.truncated else ''}:"]
    for r in result.results:
        if "children" in r:
            lines.append(f"  📦 {r['kind']} {r['name']} @ {r['file']}:{r['line']}")
            lines.append(f"     签名: {r['signature'][:100]}")
            for child in r.get("children", []):
                lines.append(f"     ├─ {child['kind']} {child['name']} :{child['line']}")
        else:
            kind_icon = {
                "class": "📦", "interface": "🔌", "struct": "🏗️",
                "function": "⚡", "method": "🔧", "variable": "📌",
                "constant": "🔒", "enum": "📋", "trait": "🧩",
            }.get(r.get("kind", ""), "📍")

            parent_str = f" (in {r['parent']})" if r.get("parent") else ""
            lines.append(
                f"  {kind_icon} {r['kind']} {r['name']}{parent_str} @ {r['file']}:{r['line']}"
            )
            if r.get("signature"):
                lines.append(f"     签名: {r['signature'][:100]}")
            if r.get("docstring"):
                lines.append(f"     文档: {r['docstring'][:100]}")

    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("Eruitah 语义搜索工具测试")
    print("=" * 60)

    test_dir = os.path.dirname(os.path.abspath(__file__))

    print("\n--- 项目概览 ---")
    result = semantic_search("overview", project_dir=test_dir)
    print(format_semantic_results(result))

    print("\n--- 搜索 class ---")
    result = semantic_search("", kind="class", project_dir=test_dir)
    print(format_semantic_results(result))

    print("\n--- 搜索 run_agent ---")
    result = semantic_search("run_agent", project_dir=test_dir)
    print(format_semantic_results(result))

    print("\n--- 文件大纲 ---")
    result = semantic_search("outline", file_path=os.path.join(test_dir, "agent_runner.py"), project_dir=test_dir)
    print(format_semantic_results(result))
