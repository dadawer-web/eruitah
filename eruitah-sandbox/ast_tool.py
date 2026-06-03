"""
Eruitah 智能编程沙盒 - AST 代码结构工具 (v2)

对齐 Understand-Anything python-extractor.ts 的提取深度:
┌─────────────────────────────────────────────────────────────────────┐
│  v1: 只提取 class/function/method 名称 + 行号                       │
│  v2: 完整提取 definitions / calls / imports 三大维度                │
│                                                                     │
│  definitions: 类(含方法/属性)、函数(含参数/返回值)、起止行号         │
│  calls:       函数调用关系 (caller → callee + 行号)                 │
│  imports:     导入模块 (source + specifiers + 行号)                 │
│                                                                     │
│  两个工具的分工:                                                    │
│    get_code_structure:  "这个文件里有什么？" (鸟瞰图)               │
│    get_function_definition: "这个函数怎么实现的？" (精准打击)       │
└─────────────────────────────────────────────────────────────────────┘
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".jsx": "javascript",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".cs": "c_sharp",
}

_ts_language_cache = {}


def _get_ts_language(language: str):
    if language in _ts_language_cache:
        return _ts_language_cache[language]

    try:
        import tree_sitter
    except ImportError:
        _ts_language_cache[language] = None
        return None

    lang_module = None
    try:
        if language == "python":
            import tree_sitter_python as tsp
            lang_module = tsp.language()
        elif language == "c":
            import tree_sitter_c as tsp
            lang_module = tsp.language()
        elif language == "cpp":
            import tree_sitter_cpp as tsp
            lang_module = tsp.language()
        elif language == "java":
            import tree_sitter_java as tsp
            lang_module = tsp.language()
        elif language == "javascript":
            import tree_sitter_javascript as tsp
            lang_module = tsp.language()
        elif language == "typescript":
            import tree_sitter_typescript as tsp
            lang_module = tsp.language().typescript()
        elif language == "tsx":
            import tree_sitter_typescript as tsp
            lang_module = tsp.language().tsx()
        elif language == "go":
            import tree_sitter_go as tsp
            lang_module = tsp.language()
        elif language == "rust":
            import tree_sitter_rust as tsp
            lang_module = tsp.language()
        elif language == "ruby":
            import tree_sitter_ruby as tsp
            lang_module = tsp.language()
        elif language == "php":
            import tree_sitter_php as tsp
            lang_module = tsp.language()
        elif language == "swift":
            import tree_sitter_swift as tsp
            lang_module = tsp.language()
        elif language == "kotlin":
            import tree_sitter_kotlin as tsp
            lang_module = tsp.language()
        elif language == "c_sharp":
            import tree_sitter_c_sharp as tsp
            lang_module = tsp.language()
    except ImportError:
        logger.debug(f"tree-sitter 语言模块未安装: tree_sitter_{language}")

    if lang_module is not None:
        try:
            ts_lang = tree_sitter.Language(lang_module)
        except Exception:
            ts_lang = lang_module
        _ts_language_cache[language] = ts_lang
    else:
        _ts_language_cache[language] = None

    return _ts_language_cache[language]


def _node_text(node, source: bytes) -> str:
    try:
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
    except Exception:
        return ""


def _find_child(node, child_type: str):
    for child in node.children:
        if child.type == child_type:
            return child
    return None


def _find_children(node, child_type: str):
    return [child for child in node.children if child.type == child_type]


def _child_by_field(node, field_name: str):
    child = node.child_by_field_name(field_name)
    return child


# ============================================================
# Python extractor — 对齐 python-extractor.ts
# ============================================================

def _unwrap_decorated(node):
    if node.type == "decorated_definition":
        inner = _find_child(node, "function_definition")
        if inner is None:
            inner = _find_child(node, "class_definition")
        if inner is not None:
            return inner
    return node


def _extract_python_params(params_node, source: bytes) -> list[str]:
    if params_node is None:
        return []
    params = []
    for child in params_node.children:
        if child.type == "identifier":
            text = _node_text(child, source)
            if text not in ("self", "cls"):
                params.append(text)
        elif child.type in ("typed_parameter", "default_parameter", "typed_default_parameter"):
            ident = _find_child(child, "identifier")
            if ident:
                text = _node_text(ident, source)
                if text not in ("self", "cls"):
                    params.append(text)
        elif child.type == "list_splat_pattern":
            ident = _find_child(child, "identifier")
            if ident:
                params.append("*" + _node_text(ident, source))
        elif child.type == "dictionary_splat_pattern":
            ident = _find_child(child, "identifier")
            if ident:
                params.append("**" + _node_text(ident, source))
    return params


def _extract_python_return_type(node, source: bytes) -> str:
    ret = _child_by_field(node, "return_type")
    if ret:
        return _node_text(ret, source)
    return ""


def _extract_python_function(node, source: bytes, parent_name: str = "") -> dict:
    name_node = _child_by_field(node, "name")
    if not name_node:
        return None
    name = _node_text(name_node, source)
    params_node = _child_by_field(node, "parameters")
    params = _extract_python_params(params_node, source)
    return_type = _extract_python_return_type(node, source)
    start_line = node.start_point[0] + 1
    end_line = node.end_point[0] + 1
    docstring = _extract_python_docstring(node, source)
    kind = "method" if parent_name else "function"
    return {
        "name": name,
        "kind": kind,
        "line": start_line,
        "end_line": end_line,
        "params": params,
        "return_type": return_type,
        "parent_name": parent_name,
        "docstring": docstring,
    }


def _extract_python_docstring(node, source: bytes) -> str:
    body = _child_by_field(node, "body")
    if body:
        for child in body.children:
            if child.type == "expression_statement":
                for expr_child in child.children:
                    if expr_child.type == "string":
                        doc = _node_text(expr_child, source)
                        return doc.strip("\"'").strip()[:500]
    return ""


def _extract_python_class(node, source: bytes) -> dict:
    name_node = _child_by_field(node, "name")
    if not name_node:
        return None
    name = _node_text(name_node, source)
    start_line = node.start_point[0] + 1
    end_line = node.end_point[0] + 1
    methods = []
    properties = []
    body = _child_by_field(node, "body")
    if body:
        for member in body.children:
            inner = _unwrap_decorated(member)
            if inner.type == "function_definition":
                method_name_node = _child_by_field(inner, "name")
                if method_name_node:
                    methods.append(_node_text(method_name_node, source))
            if member.type == "expression_statement":
                assignment = _find_child(member, "assignment")
                if assignment:
                    type_node = _find_child(assignment, "type")
                    name_ident = _find_child(assignment, "identifier")
                    if type_node and name_ident:
                        properties.append(_node_text(name_ident, source))
    return {
        "name": name,
        "kind": "class",
        "line": start_line,
        "end_line": end_line,
        "methods": methods,
        "properties": properties,
        "parent_name": "",
        "docstring": _extract_python_docstring(node, source),
    }


def _extract_python_import(node, source: bytes) -> dict:
    dotted_names = _find_children(node, "dotted_name")
    aliased_imports = _find_children(node, "aliased_import")
    line = node.start_point[0] + 1
    results = []
    for dn in dotted_names:
        results.append({
            "source": _node_text(dn, source),
            "specifiers": [_node_text(dn, source)],
            "line": line,
        })
    for ai in aliased_imports:
        dotted = _find_child(ai, "dotted_name")
        alias = None
        for child in ai.children:
            if child.type == "identifier":
                alias = child
                break
        if dotted:
            alias_text = _node_text(alias, source) if alias else _node_text(dotted, source)
            results.append({
                "source": _node_text(dotted, source),
                "specifiers": [alias_text],
                "line": line,
            })
    return results


def _extract_python_from_import(node, source: bytes) -> dict:
    module_node = _child_by_field(node, "module_name")
    source_name = _node_text(module_node, source) if module_node else ""
    module_node_id = module_node.id if module_node else None
    specifiers = []
    all_dotted = _find_children(node, "dotted_name")
    for dn in all_dotted:
        if dn.id == module_node_id:
            continue
        specifiers.append(_node_text(dn, source))
    aliased_imports = _find_children(node, "aliased_import")
    for ai in aliased_imports:
        alias = None
        for child in ai.children:
            if child.type == "identifier":
                alias = child
                break
        if alias:
            specifiers.append(_node_text(alias, source))
    if _find_child(node, "wildcard_import"):
        specifiers.append("*")
    return {
        "source": source_name,
        "specifiers": specifiers,
        "line": node.start_point[0] + 1,
    }


def _extract_python_calls(root_node, source: bytes) -> list[dict]:
    entries = []
    function_stack = []

    def walk(node):
        pushed = False
        if node.type == "function_definition":
            name_node = _child_by_field(node, "name")
            if name_node:
                function_stack.append(_node_text(name_node, source))
                pushed = True

        if node.type == "call":
            callee = None
            for child in node.children:
                if child.type in ("identifier", "attribute"):
                    callee = child
                    break
            if callee and function_stack:
                entries.append({
                    "caller": function_stack[-1],
                    "callee": _node_text(callee, source),
                    "line": node.start_point[0] + 1,
                })

        for child in node.children:
            walk(child)

        if pushed:
            function_stack.pop()

    walk(root_node)
    return entries


def extract_python_structure(root_node, source: bytes) -> dict:
    definitions = []
    imports = []

    for child in root_node.children:
        inner = _unwrap_decorated(child)

        if inner.type == "function_definition":
            func = _extract_python_function(inner, source)
            if func:
                definitions.append(func)

        elif inner.type == "class_definition":
            cls = _extract_python_class(inner, source)
            if cls:
                definitions.append(cls)
                body = _child_by_field(inner, "body")
                if body:
                    for member in body.children:
                        member_inner = _unwrap_decorated(member)
                        if member_inner.type == "function_definition":
                            method = _extract_python_function(member_inner, source, parent_name=cls["name"])
                            if method:
                                definitions.append(method)

        elif child.type == "import_statement":
            import_entries = _extract_python_import(child, source)
            imports.extend(import_entries)

        elif child.type == "import_from_statement":
            imp = _extract_python_from_import(child, source)
            imports.append(imp)

    calls = _extract_python_calls(root_node, source)

    return {
        "definitions": definitions,
        "calls": calls,
        "imports": imports,
    }


# ============================================================
# JavaScript / TypeScript extractor
# ============================================================

def _extract_js_ts_params(params_node, source: bytes) -> list[str]:
    if params_node is None:
        return []
    params = []
    for child in params_node.children:
        if child.type in ("identifier", "required_parameter", "optional_parameter"):
            ident = _find_child(child, "identifier")
            if ident is None and child.type == "identifier":
                ident = child
            if ident:
                params.append(_node_text(ident, source))
            rest = _find_child(child, "rest_parameter")
            if rest:
                ri = _find_child(rest, "identifier")
                if ri:
                    params.append("..." + _node_text(ri, source))
    return params


def _extract_js_ts_calls(root_node, source: bytes) -> list[dict]:
    entries = []
    function_stack = []

    def walk(node):
        pushed = False
        if node.type in ("function_declaration", "method_definition", "arrow_function", "function"):
            name_node = _child_by_field(node, "name")
            if name_node:
                function_stack.append(_node_text(name_node, source))
                pushed = True
            elif function_stack:
                function_stack.append("<anonymous>")
                pushed = True

        if node.type == "call_expression":
            callee = None
            for child in node.children:
                if child.type in ("identifier", "member_expression"):
                    callee = child
                    break
            if callee and function_stack:
                entries.append({
                    "caller": function_stack[-1],
                    "callee": _node_text(callee, source),
                    "line": node.start_point[0] + 1,
                })

        for child in node.children:
            walk(child)

        if pushed:
            function_stack.pop()

    walk(root_node)
    return entries


def extract_js_ts_structure(root_node, source: bytes) -> dict:
    definitions = []
    imports = []

    def walk(node, parent_name=""):
        if node.type == "function_declaration":
            name_node = _child_by_field(node, "name")
            if name_node:
                params_node = _child_by_field(node, "parameters")
                params = _extract_js_ts_params(params_node, source)
                definitions.append({
                    "name": _node_text(name_node, source),
                    "kind": "method" if parent_name else "function",
                    "line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "params": params,
                    "return_type": "",
                    "parent_name": parent_name,
                    "docstring": "",
                })

        elif node.type == "class_declaration":
            name_node = _child_by_field(node, "name")
            if name_node:
                class_name = _node_text(name_node, source)
                methods = []
                body = _child_by_field(node, "body")
                if body:
                    for child in body.children:
                        if child.type == "method_definition":
                            mn = _child_by_field(child, "name")
                            if mn:
                                methods.append(_node_text(mn, source))
                definitions.append({
                    "name": class_name,
                    "kind": "class",
                    "line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "methods": methods,
                    "properties": [],
                    "parent_name": parent_name,
                    "docstring": "",
                })
                if body:
                    for child in body.children:
                        if child.type == "method_definition":
                            mn = _child_by_field(child, "name")
                            params_node = _child_by_field(child, "parameters")
                            if mn:
                                definitions.append({
                                    "name": _node_text(mn, source),
                                    "kind": "method",
                                    "line": child.start_point[0] + 1,
                                    "end_line": child.end_point[0] + 1,
                                    "params": _extract_js_ts_params(params_node, source),
                                    "return_type": "",
                                    "parent_name": class_name,
                                    "docstring": "",
                                })
                return

        elif node.type == "import_statement":
            source_str = ""
            specifiers = []
            for child in node.children:
                if child.type == "string":
                    source_str = _node_text(child, source).strip("\"'")
                elif child.type == "import_clause":
                    for ic in child.children:
                        if ic.type == "identifier":
                            specifiers.append(_node_text(ic, source))
                        elif ic.type == "named_imports":
                            for ni in ic.children:
                                if ni.type == "import_specifier":
                                    ni_name = _child_by_field(ni, "name")
                                    if ni_name:
                                        specifiers.append(_node_text(ni_name, source))
            if source_str:
                imports.append({
                    "source": source_str,
                    "specifiers": specifiers,
                    "line": node.start_point[0] + 1,
                })

        for child in node.children:
            walk(child, parent_name)

    walk(root_node)
    calls = _extract_js_ts_calls(root_node, source)
    return {"definitions": definitions, "calls": calls, "imports": imports}


# ============================================================
# C / C++ / Java / Go / Rust / C# / etc. generic extractor
# ============================================================

_CLASS_TYPES = {
    "class_definition", "class_declaration", "struct_definition",
    "struct_declaration", "interface_declaration", "enum_declaration",
    "trait_declaration", "impl_item",
}
_FUNC_TYPES = {
    "function_definition", "function_declaration", "method_declaration",
    "method_definition", "constructor_declaration", "destructor_declaration",
    "declaration",
}
_CALL_TYPES = {
    "call_expression", "call",
}
_IMPORT_TYPES = {
    "import_statement", "import_declaration", "use_declaration",
    "include_directive", "require_directive",
}


def _extract_generic_params(node, source: bytes) -> list[str]:
    params_node = _child_by_field(node, "parameters")
    if params_node is None:
        params_node = _child_by_field(node, "parameter_list")
    if params_node is None:
        return []
    params = []
    for child in params_node.children:
        if child.type in ("identifier", "parameter_identifier", "plain_parameter",
                          "parameter", "formal_parameter", "parameter_declaration"):
            ident = _find_child(child, "identifier")
            if ident is None:
                for sc in child.children:
                    if sc.type == "identifier":
                        ident = sc
                        break
            if ident:
                params.append(_node_text(ident, source))
            elif child.type == "identifier":
                params.append(_node_text(child, source))
    return params


def _extract_generic_calls(root_node, source: bytes) -> list[dict]:
    entries = []
    func_stack = []

    def walk(node):
        pushed = False
        if node.type in _FUNC_TYPES:
            name_node = _child_by_field(node, "name")
            if name_node:
                func_stack.append(_node_text(name_node, source))
                pushed = True

        if node.type in _CALL_TYPES:
            callee = None
            for child in node.children:
                if child.type in ("identifier", "field_identifier",
                                  "member_expression", "scoped_identifier",
                                  "scoped_type_identifier", "attribute"):
                    callee = child
                    break
            if callee and func_stack:
                entries.append({
                    "caller": func_stack[-1],
                    "callee": _node_text(callee, source),
                    "line": node.start_point[0] + 1,
                })

        for child in node.children:
            walk(child)

        if pushed:
            func_stack.pop()

    walk(root_node)
    return entries


def extract_generic_structure(root_node, source: bytes, language: str) -> dict:
    definitions = []
    imports = []

    def walk(node, parent_name=""):
        if node.type in _CLASS_TYPES:
            name_node = _child_by_field(node, "name")
            if name_node:
                class_name = _node_text(name_node, source)
                methods = []
                body = _child_by_field(node, "body")
                if body:
                    for child in body.children:
                        if child.type in _FUNC_TYPES:
                            mn = _child_by_field(child, "name")
                            if mn:
                                methods.append(_node_text(mn, source))
                definitions.append({
                    "name": class_name,
                    "kind": "class",
                    "line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "methods": methods,
                    "properties": [],
                    "parent_name": parent_name,
                    "docstring": "",
                })
                if body:
                    for child in body.children:
                        if child.type in _FUNC_TYPES:
                            mn = _child_by_field(child, "name")
                            if mn:
                                definitions.append({
                                    "name": _node_text(mn, source),
                                    "kind": "method",
                                    "line": child.start_point[0] + 1,
                                    "end_line": child.end_point[0] + 1,
                                    "params": _extract_generic_params(child, source),
                                    "return_type": "",
                                    "parent_name": class_name,
                                    "docstring": "",
                                })
                return

        elif node.type in _FUNC_TYPES:
            name_node = _child_by_field(node, "name")
            if name_node:
                definitions.append({
                    "name": _node_text(name_node, source),
                    "kind": "method" if parent_name else "function",
                    "line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "params": _extract_generic_params(node, source),
                    "return_type": "",
                    "parent_name": parent_name,
                    "docstring": "",
                })
                return

        elif node.type in _IMPORT_TYPES:
            import_text = _node_text(node, source)
            name_node = _child_by_field(node, "name")
            source_name = _node_text(name_node, source) if name_node else import_text
            specifiers = []
            for child in node.children:
                if child.type in ("dotted_name", "identifier", "string", "scoped_identifier"):
                    specifiers.append(_node_text(child, source))
            imports.append({
                "source": source_name,
                "specifiers": specifiers if specifiers else [import_text],
                "line": node.start_point[0] + 1,
            })
            return

        for child in node.children:
            walk(child, parent_name)

    walk(root_node)
    calls = _extract_generic_calls(root_node, source)
    return {"definitions": definitions, "calls": calls, "imports": imports}


# ============================================================
# Unified parse entry point
# ============================================================

def parse_source_with_treesitter(source: bytes, language: str) -> dict:
    empty = {"definitions": [], "calls": [], "imports": []}

    try:
        import tree_sitter
    except ImportError:
        return empty

    ts_lang = _get_ts_language(language)
    if ts_lang is None:
        return empty

    try:
        parser = tree_sitter.Parser(ts_lang)
    except TypeError:
        try:
            parser = tree_sitter.Parser()
            parser.language = ts_lang
        except Exception:
            return empty

    try:
        tree = parser.parse(source)
    except Exception as e:
        logger.error(f"tree-sitter parse error: {e}")
        return empty

    root = tree.root_node
    if root.has_error:
        logger.debug(f"source has syntax errors, extracting what we can")

    try:
        if language == "python":
            return extract_python_structure(root, source)
        elif language in ("javascript", "typescript", "tsx", "jsx"):
            return extract_js_ts_structure(root, source)
        else:
            return extract_generic_structure(root, source, language)
    except Exception as e:
        logger.error(f"structure extraction error: {e}")
        return empty


def parse_file_with_treesitter(file_path: str, language: str) -> dict:
    try:
        with open(file_path, "rb") as f:
            source = f.read()
    except Exception as e:
        logger.error(f"read file error {file_path}: {e}")
        return {"definitions": [], "calls": [], "imports": []}

    return parse_source_with_treesitter(source, language)


# ============================================================
# Fallback regex parser (when tree-sitter is not installed)
# ============================================================

def _parse_file_fallback(file_path: str, language: str) -> dict:
    definitions = []
    imports = []

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return {"definitions": definitions, "calls": [], "imports": imports}

    import re

    if language == "python":
        patterns = [
            (re.compile(r"^(\s*)class\s+(\w+)"), "class"),
            (re.compile(r"^(\s*)async\s+def\s+(\w+)"), "function"),
            (re.compile(r"^(\s*)def\s+(\w+)"), "function"),
            (re.compile(r"^import\s+(.+)"), "import"),
            (re.compile(r"^from\s+([\w.]+)\s+import\s+(.+)"), "from_import"),
        ]
    elif language in ("c", "cpp", "java", "c_sharp"):
        patterns = [
            (re.compile(r"^\s*class\s+(\w+)"), "class"),
            (re.compile(r"^\s*struct\s+(\w+)"), "class"),
            (re.compile(r"^\s*interface\s+(\w+)"), "class"),
            (re.compile(r"^\s*enum\s+(\w+)"), "class"),
            (re.compile(r"^\s*(?:virtual\s+|static\s+|inline\s+)*(?:\w+(?:\s*<[^>]*>)?(?:\s*::\s*\w+)*\s+)+(\w+)\s*\("), "function"),
            (re.compile(r"^\s*#\s*include\s+[<\"](.+?)[>\"]"), "import"),
        ]
    elif language in ("javascript", "typescript", "tsx", "jsx"):
        patterns = [
            (re.compile(r"^\s*class\s+(\w+)"), "class"),
            (re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)"), "function"),
            (re.compile(r"^\s*(?:export\s+)?interface\s+(\w+)"), "class"),
            (re.compile(r"^\s*import\s+(.+)"), "import"),
        ]
    else:
        patterns = [
            (re.compile(r"^\s*class\s+(\w+)"), "class"),
            (re.compile(r"^\s*def\s+(\w+)"), "function"),
            (re.compile(r"^\s*function\s+(\w+)"), "function"),
        ]

    for i, line in enumerate(lines, 1):
        for pattern, kind in patterns:
            match = pattern.match(line)
            if not match:
                continue

            if kind == "class":
                name = match.group(1)
                indent = len(line) - len(line.lstrip())
                definitions.append({
                    "name": name,
                    "kind": "class",
                    "line": i,
                    "end_line": i,
                    "methods": [],
                    "properties": [],
                    "parent_name": "",
                    "docstring": "",
                })
            elif kind == "function":
                name = match.group(2) if match.lastindex and match.lastindex >= 2 else match.group(1)
                indent = len(line) - len(line.lstrip())
                parent = ""
                func_kind = "function"
                if indent > 0:
                    for sym in reversed(definitions):
                        if sym["kind"] == "class":
                            parent = sym["name"]
                            func_kind = "method"
                            break
                definitions.append({
                    "name": name,
                    "kind": func_kind,
                    "line": i,
                    "end_line": i,
                    "params": [],
                    "return_type": "",
                    "parent_name": parent,
                    "docstring": "",
                })
            elif kind == "import":
                import_text = match.group(1).strip()
                imports.append({
                    "source": import_text,
                    "specifiers": [import_text],
                    "line": i,
                })
            elif kind == "from_import":
                source_name = match.group(1).strip()
                spec_text = match.group(2).strip()
                specs = [s.strip() for s in spec_text.split(",") if s.strip()]
                imports.append({
                    "source": source_name,
                    "specifiers": specs,
                    "line": i,
                })

    return {"definitions": definitions, "calls": [], "imports": imports}


# ============================================================
# End-line inference (for fallback / incomplete parse)
# ============================================================

def _infer_end_line(lines: list, start_line: int, language: str) -> int:
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


# ============================================================
# Public tool execution functions
# ============================================================

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
        result = parse_file_with_treesitter(file_path, language)
        if not result["definitions"] and not result["imports"]:
            result = _parse_file_fallback(file_path, language)
    except Exception as e:
        logger.error(f"AST 解析失败 {file_path}: {e}")
        try:
            result = _parse_file_fallback(file_path, language)
        except Exception as e2:
            return f"AST 解析失败: {str(e2)}", True

    definitions = result["definitions"]
    calls = result["calls"]
    imports = result["imports"]

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            file_lines = f.readlines()
    except Exception:
        file_lines = []

    for sym in definitions:
        if sym.get("end_line", 0) <= sym.get("line", 0) and file_lines:
            sym["end_line"] = _infer_end_line(file_lines, sym["line"], language)

    lines = [f"📐 {os.path.basename(file_path)} 代码结构 ({language}):\n"]

    kind_icons = {
        "class": "📦",
        "interface": "🔌",
        "struct": "🏗️",
        "function": "⚡",
        "method": "🔧",
        "enum": "📋",
        "trait": "🧩",
    }

    current_parent = None
    for sym in definitions:
        kind = sym.get("kind", "")
        name = sym.get("name", "")
        line = sym.get("line", 0)
        end_line = sym.get("end_line", 0)
        parent = sym.get("parent_name", "")
        params = sym.get("params", [])
        return_type = sym.get("return_type", "")
        doc = sym.get("docstring", "")

        icon = kind_icons.get(kind, "📍")

        if kind == "class":
            methods = sym.get("methods", [])
            properties = sym.get("properties", [])
            lines.append(f"  {icon} class {name}  (L{line}-{end_line})")
            if methods:
                lines.append(f"     方法: {', '.join(methods)}")
            if properties:
                lines.append(f"     属性: {', '.join(properties)}")
            if doc:
                lines.append(f"     文档: {doc[:150]}")
            current_parent = name
        elif kind in ("method", "function"):
            param_str = ", ".join(params) if params else ""
            ret_str = f" -> {return_type}" if return_type else ""
            sig = f"({param_str}){ret_str}"
            if parent and parent == current_parent:
                lines.append(f"    ├─ {icon} {kind} {name}{sig}  (L{line}-{end_line})")
            elif parent:
                lines.append(f"    ├─ {icon} {kind} {name} (in {parent}){sig}  (L{line}-{end_line})")
            else:
                lines.append(f"  {icon} {kind} {name}{sig}  (L{line}-{end_line})")
        else:
            indent = "    ├─ " if parent else "  "
            lines.append(f"{indent}{icon} {kind} {name}  (L{line})")

    if imports:
        lines.append(f"\n  📥 导入:")
        for imp in imports:
            source_name = imp.get("source", "")
            specs = imp.get("specifiers", [])
            imp_line = imp.get("line", 0)
            if specs and specs != [source_name]:
                lines.append(f"    from {source_name} import {', '.join(specs)}  (L{imp_line})")
            else:
                lines.append(f"    import {source_name}  (L{imp_line})")

    if calls:
        lines.append(f"\n  📞 调用关系:")
        for call in calls[:30]:
            caller = call.get("caller", "")
            callee = call.get("callee", "")
            call_line = call.get("line", 0)
            lines.append(f"    {caller} → {callee}  (L{call_line})")
        if len(calls) > 30:
            lines.append(f"    ... 共 {len(calls)} 条调用关系")

    total_classes = sum(1 for s in definitions if s.get("kind") == "class")
    total_functions = sum(1 for s in definitions if s.get("kind") in ("function", "method"))
    total_imports = len(imports)
    total_calls = len(calls)
    lines.append(f"\n  📊 共 {total_classes} 个类型, {total_functions} 个函数/方法, {total_imports} 个导入, {total_calls} 条调用")

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
        result = parse_file_with_treesitter(file_path, language)
        if not result["definitions"]:
            result = _parse_file_fallback(file_path, language)
    except Exception as e:
        logger.error(f"AST 解析失败 {file_path}: {e}")
        try:
            result = _parse_file_fallback(file_path, language)
        except Exception as e2:
            return f"AST 解析失败: {str(e2)}", True

    definitions = result["definitions"]

    matches = []
    for sym in definitions:
        if sym.get("name") == function_name and sym.get("kind") in ("function", "method"):
            matches.append(sym)

    if not matches:
        fuzzy = [s for s in definitions if function_name.lower() in s.get("name", "").lower()
                 and s.get("kind") in ("function", "method")]
        if fuzzy:
            names = [f"{s['name']} (L{s['line']})" for s in fuzzy[:5]]
            return (
                f"未找到名为「{function_name}」的函数/方法。"
                f"相似名称: {', '.join(names)}"
            ), True
        all_names = [s["name"] for s in definitions if s.get("kind") in ("function", "method")]
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
            params = m.get("params", [])
            ret = m.get("return_type", "")
            sig = f"({', '.join(params)}){f' -> {ret}' if ret else ''}"
            lines.append(f"  [{i+1}] {m['kind']} {function_name}{parent}{sig} @ L{m['line']}-{m['end_line']}")
        lines.append(f"\n默认返回第一个匹配:\n")

    target = matches[0]
    start_line = target["line"]
    end_line = target["end_line"]
    parent = target.get("parent_name", "")
    kind = target.get("kind", "function")
    params = target.get("params", [])
    return_type = target.get("return_type", "")

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
    sig = f"({', '.join(params)}){f' -> {return_type}' if return_type else ''}"
    header = f"🔍 {kind} {function_name}{parent_info}{sig} @ {os.path.basename(file_path)}:L{start_line}-{end_line}"

    result = f"{header}\n\n```{language}\n{code}\n```"

    return result, False


# ============================================================
# Tool definitions (OpenAI / Anthropic format)
# ============================================================

AST_CODE_STRUCTURE_TOOL_DEFINITION_OPENAI = {
    "type": "function",
    "function": {
        "name": "get_code_structure",
        "description": (
            "获取文件的代码结构（AST 级别）。返回该文件中所有的类名、函数名、方法名及其签名、行号、"
            "调用关系和导入信息。比 grep 精准 100 倍——只返回真正的代码结构，不会匹配注释或字符串。"
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
        "获取文件的代码结构（AST 级别）。返回该文件中所有的类名、函数名、方法名及其签名、行号、"
        "调用关系和导入信息。比 grep 精准 100 倍——只返回真正的代码结构，不会匹配注释或字符串。"
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
