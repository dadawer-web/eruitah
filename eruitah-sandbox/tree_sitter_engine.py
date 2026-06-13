"""
Eruitah 多语言 AST 解析引擎 —— 基于 Tree-Sitter

支持语言:
  - Python (.py)
  - Java (.java)
  - C/C++ (.c, .cpp, .cc, .cxx, .h, .hpp)

核心能力:
  - ParserFactory: 根据文件后缀动态加载对应语言的 Parser
  - UniversalExtractor: 统一提取类名、函数名、方法名
  - extract_symbols(): 一行调用，返回扁平符号列表
"""

import os
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from tree_sitter import Language, Parser, Node, Query, QueryCursor

logger = logging.getLogger(__name__)


def _make_language(lang_obj):
    """
    兼容 tree-sitter 多版本的 Language 构造。

    tree-sitter >= 0.22: lang_module.language() 直接返回 Language 对象，
                         再次 Language() 包装会抛出 TypeError (PyCapsule)。
    tree-sitter < 0.22:  lang_module.language() 返回 PyCapsule，需要 Language() 包装。

    策略：先尝试 Language() 包装，失败则直接使用原对象。
    """
    try:
        return Language(lang_obj)
    except TypeError:
        return lang_obj

# ════════════════════════════════════════════════════════════════
# 语言注册表
# ════════════════════════════════════════════════════════════════

_LANGUAGE_REGISTRY: Dict[str, dict] = {}


def _init_registry():
    """懒加载语言注册表"""
    if _LANGUAGE_REGISTRY:
        return

    # Python
    try:
        import tree_sitter_python as tspython
        py_lang = _make_language(tspython.language())
        _LANGUAGE_REGISTRY["python"] = {
            "language": py_lang,
            "extensions": {".py"},
            "class_types": {"class_definition"},
            "function_types": {"function_definition"},
            # Python 方法就是 function_definition，在 class 内部
            "method_types": {"function_definition"},
        }
    except ImportError:
        logger.warning("tree-sitter-python 未安装，Python 解析不可用")

    # Java
    try:
        import tree_sitter_java as tsjava
        java_lang = _make_language(tsjava.language())
        _LANGUAGE_REGISTRY["java"] = {
            "language": java_lang,
            "extensions": {".java"},
            "class_types": {"class_declaration", "interface_declaration", "enum_declaration", "record_declaration"},
            "function_types": {"method_declaration"},
            "method_types": {"method_declaration"},
            # Java 特殊：构造方法
            "constructor_types": {"constructor_declaration"},
        }
    except ImportError:
        logger.warning("tree-sitter-java 未安装，Java 解析不可用")

    # C/C++
    try:
        import tree_sitter_cpp as tscpp
        cpp_lang = _make_language(tscpp.language())
        _LANGUAGE_REGISTRY["cpp"] = {
            "language": cpp_lang,
            "extensions": {".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hxx"},
            "class_types": {"class_specifier", "struct_specifier"},
            "function_types": {"function_definition"},
            "method_types": {"function_definition"},  # C++ 方法也是 function_definition，在 class 内部
            # C++ 特殊：声明与定义分离
            "declaration_types": {"declaration"},
        }
    except ImportError:
        logger.warning("tree-sitter-cpp 未安装，C/C++ 解析不可用")


# ════════════════════════════════════════════════════════════════
# ParserFactory
# ════════════════════════════════════════════════════════════════

class ParserFactory:
    """根据文件后缀动态创建对应语言的 Parser"""

    _parser_cache: Dict[str, Parser] = {}

    @classmethod
    def get_parser(cls, file_path: str) -> Optional[Parser]:
        """
        根据文件路径后缀返回对应的 Parser 实例（带缓存）

        Args:
            file_path: 文件路径，如 "src/main.py"

        Returns:
            Parser 实例，或不支持的语言返回 None
        """
        _init_registry()

        ext = os.path.splitext(file_path)[1].lower()
        lang_name = cls._ext_to_lang(ext)
        if not lang_name:
            return None

        if lang_name not in cls._parser_cache:
            lang_info = _LANGUAGE_REGISTRY.get(lang_name)
            if not lang_info:
                return None
            parser = Parser(lang_info["language"])
            cls._parser_cache[lang_name] = parser

        return cls._parser_cache[lang_name]

    @classmethod
    def get_language_info(cls, file_path: str) -> Optional[dict]:
        """根据文件路径后缀返回语言配置信息"""
        _init_registry()
        ext = os.path.splitext(file_path)[1].lower()
        lang_name = cls._ext_to_lang(ext)
        if not lang_name:
            return None
        return _LANGUAGE_REGISTRY.get(lang_name)

    @classmethod
    def get_language_name(cls, file_path: str) -> Optional[str]:
        """根据文件路径后缀返回语言名称"""
        _init_registry()
        ext = os.path.splitext(file_path)[1].lower()
        return cls._ext_to_lang(ext)

    @staticmethod
    def _ext_to_lang(ext: str) -> Optional[str]:
        """文件后缀 → 语言名称映射"""
        for lang_name, info in _LANGUAGE_REGISTRY.items():
            if ext in info["extensions"]:
                return lang_name
        return None

    @classmethod
    def supported_extensions(cls) -> set:
        """返回所有支持的文件后缀"""
        _init_registry()
        exts = set()
        for info in _LANGUAGE_REGISTRY.values():
            exts.update(info["extensions"])
        return exts

    @classmethod
    def _get_language_object(cls, lang_name: str) -> Optional[Language]:
        """根据语言名称返回 Language 对象（用于 Query 构造）"""
        _init_registry()
        info = _LANGUAGE_REGISTRY.get(lang_name)
        if not info:
            return None
        return info.get("language")


# ════════════════════════════════════════════════════════════════
# UniversalExtractor
# ════════════════════════════════════════════════════════════════

class UniversalExtractor:
    """
    多语言统一符号提取器

    遍历 Tree-Sitter AST，提取类名、函数名、方法名，
    返回统一的扁平符号列表。
    """

    def __init__(self):
        _init_registry()
        self.queries_dir = Path(__file__).parent / "queries"
        self._route_queries: Dict[str, Query] = {}
        self._load_route_queries()

    def extract_symbols(self, filepath: str, code_content: str) -> Dict:
        """
        提取文件中的所有符号（定义 + 调用 + 路由）

        Args:
            filepath: 文件路径（用于判断语言）
            code_content: 文件内容字符串

        Returns:
            字典，包含:
              - definitions: 定义符号列表 [{name, kind, line, parent}, ...]
              - calls: 调用符号列表 [{name, kind, line, caller}, ...]
              - routes: 路由信息列表 [{method, path, handler, line}, ...]
        """
        lang_info = ParserFactory.get_language_info(filepath)
        if not lang_info:
            return {"definitions": [], "calls": [], "routes": []}

        parser = ParserFactory.get_parser(filepath)
        if not parser:
            return {"definitions": [], "calls": [], "routes": []}

        try:
            tree = parser.parse(code_content.encode("utf-8"))
        except Exception as e:
            logger.warning(f"Tree-Sitter 解析失败 [{filepath}]: {e}")
            return {"definitions": [], "calls": [], "routes": []}

        lang_name = ParserFactory.get_language_name(filepath)

        # 根据语言选择提取策略
        if lang_name == "python":
            return self._extract_python(tree, lang_info)
        elif lang_name == "java":
            return self._extract_java(tree, lang_info)
        elif lang_name == "cpp":
            return self._extract_cpp(tree, lang_info)
        else:
            return self._extract_generic(tree, lang_info)

    def extract_symbols_flat(self, filepath: str, code_content: str) -> List[str]:
        """
        提取符号并返回扁平字符串列表

        Returns:
            如 ['class ChatServer', 'function start', 'method send_msg']
        """
        result = self.extract_symbols(filepath, code_content)
        defs = result.get("definitions", [])
        return [f"{s['kind']} {s['name']}" for s in defs]

    # ── Query 加载 ──

    _ROUTE_QUERY_FILES = {
        "java": "java_spring.scm",
        "python": "python_fastapi.scm",
    }

    def _load_route_queries(self):
        """预加载路由查询脚本 (.scm)"""
        for lang_name, filename in self._ROUTE_QUERY_FILES.items():
            query_str = self._load_query(filename)
            if not query_str:
                continue
            try:
                lang_obj = ParserFactory._get_language_object(lang_name)
                if lang_obj:
                    self._route_queries[lang_name] = Query(lang_obj, query_str)
                    logger.debug(f"已加载路由查询: {filename}")
            except Exception as e:
                logger.warning(f"加载路由查询失败 {filename}: {e}")

    def _load_query(self, filename: str) -> Optional[str]:
        """读取 .scm 查询文件内容"""
        filepath = self.queries_dir / filename
        if not filepath.exists():
            logger.debug(f"查询文件不存在: {filepath}")
            return None
        try:
            return filepath.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"读取查询文件失败 {filepath}: {e}")
            return None

    def _extract_routes_via_query(self, tree, lang_name: str) -> List[Dict]:
        """
        使用 Tree-Sitter Query API 从 .scm 文件提取路由信息。
        返回 [{"method", "path", "handler", "line"}, ...]
        """
        query = self._route_queries.get(lang_name)
        if not query:
            return []

        routes = []
        try:
            cursor = QueryCursor(query)
            matches = cursor.matches(tree.root_node)

            for pattern_idx, captures_dict in matches:
                # 从 captures 中提取各字段
                annotation_name = ""
                http_method = ""
                method_name = ""
                function_name = ""
                route_line = 0

                for capture_name, nodes in captures_dict.items():
                    if not nodes:
                        continue
                    text = nodes[0].text.decode("utf-8")
                    node_line = nodes[0].start_point[0] + 1

                    if capture_name == "annotation_name":
                        annotation_name = text
                        route_line = node_line
                    elif capture_name == "http_method":
                        http_method = text.lower()
                        route_line = node_line
                    elif capture_name == "method_name":
                        method_name = text
                    elif capture_name == "function_name":
                        function_name = text

                # 确定 HTTP 方法和路径
                handler = function_name or method_name
                if not handler:
                    continue

                # 从注解名推导 HTTP 方法 (Java)
                if annotation_name and not http_method:
                    http_method = self._annotation_to_http_method(annotation_name)

                if not http_method:
                    continue

                # 提取路径: 需要回到 AST 中找 string_literal/string
                path = self._extract_route_path(tree, lang_name, handler)

                routes.append({
                    "method": http_method.upper(),
                    "path": path or "/",
                    "handler": handler,
                    "line": route_line,
                })

        except Exception as e:
            logger.debug(f"Query 路由提取失败 [{lang_name}]: {e}")

        return routes

    @staticmethod
    def _annotation_to_http_method(annotation_name: str) -> str:
        """从 Java 注解名推导 HTTP 方法"""
        mapping = {
            "GetMapping": "GET",
            "PostMapping": "POST",
            "PutMapping": "PUT",
            "DeleteMapping": "DELETE",
            "PatchMapping": "PATCH",
            "RequestMapping": "ANY",
        }
        return mapping.get(annotation_name, "")

    def _extract_route_path(self, tree, lang_name: str, handler: str) -> str:
        """从 AST 中提取路由路径字符串"""
        if lang_name == "python":
            return self._extract_python_route_path(tree, handler)
        elif lang_name == "java":
            return self._extract_java_route_path(tree, handler)
        return ""

    @staticmethod
    def _extract_python_route_path(tree, handler: str) -> str:
        """从 Python AST 中提取装饰器里的路径字符串"""
        def _walk(node):
            if node.type == "decorated_definition":
                # 找到 function_definition 中的 handler 名
                func_name = ""
                decorator_node = None
                for child in node.children:
                    if child.type == "function_definition":
                        for sub in child.children:
                            if sub.type == "identifier":
                                func_name = sub.text.decode("utf-8")
                                break
                    elif child.type == "decorator":
                        decorator_node = child

                if func_name == handler and decorator_node:
                    # 在 decorator 中找 string 参数
                    for desc in _find_all_descendants(decorator_node):
                        if desc.type == "string":
                            text = desc.text.decode("utf-8")
                            if len(text) >= 2 and text[0] in ('"', "'"):
                                return text[1:-1]
            for child in node.children:
                result = _walk(child)
                if result:
                    return result
            return ""

        def _find_all_descendants(node):
            yield node
            for child in node.children:
                yield from _find_all_descendants(child)

        return _walk(tree.root_node)

    @staticmethod
    def _extract_java_route_path(tree, handler: str) -> str:
        """从 Java AST 中提取注解里的路径字符串"""
        def _walk(node):
            if node.type == "method_declaration":
                # 找到方法名
                method_name = ""
                for child in node.children:
                    if child.type == "identifier":
                        method_name = child.text.decode("utf-8")
                        break
                if method_name != handler:
                    for child in node.children:
                        result = _walk(child)
                        if result:
                            return result
                    return ""

                # 找到 annotation 中的 string_literal
                for child in node.children:
                    if child.type == "modifiers":
                        for mod in child.children:
                            if mod.type in ("annotation", "marker_annotation"):
                                for desc in _find_all_descendants(mod):
                                    if desc.type == "string_literal":
                                        text = desc.text.decode("utf-8")
                                        if len(text) >= 2 and text[0] == '"':
                                            return text[1:-1]
                                    elif desc.type == "element_value_pair":
                                        children = desc.children
                                        if len(children) >= 3:
                                            key = children[0].text.decode("utf-8")
                                            if key in ("value", "path"):
                                                val = children[2]
                                                if val.type == "string_literal":
                                                    t = val.text.decode("utf-8")
                                                    if len(t) >= 2 and t[0] == '"':
                                                        return t[1:-1]
                return ""

            for child in node.children:
                result = _walk(child)
                if result:
                    return result
            return ""

        def _find_all_descendants(node):
            yield node
            for child in node.children:
                yield from _find_all_descendants(child)

        return _walk(tree.root_node)

    # ── Python 提取 ──

    def _extract_python(self, tree, lang_info: dict) -> Dict:
        """Python 符号提取：definitions (class, function) + calls (call) + routes (via Query)"""
        definitions = []
        calls = []
        class_types = lang_info["class_types"]
        func_types = lang_info["function_types"]
        seen_calls = set()  # 防重: (caller, callee)

        def _get_current_function(call_line: int) -> str:
            """根据调用行号，找到最近的函数/方法名作为 caller"""
            best = ""
            for d in definitions:
                if d["kind"] in ("function", "method") and d["line"] <= call_line:
                    if not best or d["line"] > best_line:
                        best = d["name"]
                        best_line = d["line"]
            return best

        def _walk(node: Node, parent_class: str = ""):
            if node.type in class_types:
                name = self._get_name(node)
                if name:
                    definitions.append({
                        "name": name,
                        "kind": "class",
                        "line": node.start_point[0] + 1,
                        "parent": "",
                    })
                    for child in node.children:
                        _walk(child, parent_class=name)
                    return

            # 处理 decorated_definition
            if node.type == "decorated_definition":
                func_name = ""
                for child in node.children:
                    if child.type in func_types:
                        func_name = self._get_name(child) or ""
                        kind = "method" if parent_class else "function"
                        if func_name:
                            definitions.append({
                                "name": func_name,
                                "kind": kind,
                                "line": child.start_point[0] + 1,
                                "parent": parent_class,
                            })
                        break
                for child in node.children:
                    if child.type not in func_types:
                        _walk(child, parent_class)
                return

            if node.type in func_types:
                name = self._get_name(node)
                if name:
                    kind = "method" if parent_class else "function"
                    definitions.append({
                        "name": name,
                        "kind": kind,
                        "line": node.start_point[0] + 1,
                        "parent": parent_class,
                    })

            # 提取函数调用: call 节点
            if node.type == "call":
                callee = self._get_python_call_name(node)
                if callee:
                    call_line = node.start_point[0] + 1
                    caller = _get_current_function(call_line)
                    dedup_key = (caller, callee)
                    if dedup_key not in seen_calls:
                        seen_calls.add(dedup_key)
                        calls.append({
                            "name": callee,
                            "kind": "call",
                            "line": call_line,
                            "caller": caller,
                        })

            for child in node.children:
                _walk(child, parent_class)

        _walk(tree.root_node)

        # 使用 Query API 提取路由（替代硬编码装饰器遍历）
        routes = self._extract_routes_via_query(tree, "python")

        return {"definitions": definitions, "calls": calls, "routes": routes}

    # ── Java 提取 ──

    def _extract_java(self, tree, lang_info: dict) -> Dict:
        """Java 符号提取：definitions + calls + routes (via Query)"""
        definitions = []
        calls = []
        class_types = lang_info["class_types"]
        func_types = lang_info["function_types"]
        constructor_types = lang_info.get("constructor_types", set())
        seen_calls = set()

        def _get_current_method(call_line: int) -> str:
            """根据调用行号，找到最近的方法名作为 caller"""
            best = ""
            best_line = 0
            for d in definitions:
                if d["kind"] in ("method", "constructor") and d["line"] <= call_line:
                    if d["line"] > best_line:
                        best = d["name"]
                        best_line = d["line"]
            return best

        def _walk(node: Node, parent_class: str = ""):
            if node.type in class_types:
                name = self._get_name(node)
                if name:
                    kind = "class"
                    if node.type == "interface_declaration":
                        kind = "interface"
                    elif node.type == "enum_declaration":
                        kind = "enum"
                    elif node.type == "record_declaration":
                        kind = "record"
                    definitions.append({
                        "name": name,
                        "kind": kind,
                        "line": node.start_point[0] + 1,
                        "parent": "",
                    })
                    for child in node.children:
                        _walk(child, parent_class=name)
                    return

            if node.type in func_types:
                name = self._get_name(node)
                if name:
                    definitions.append({
                        "name": name,
                        "kind": "method",
                        "line": node.start_point[0] + 1,
                        "parent": parent_class,
                    })

            if node.type in constructor_types:
                name = self._get_name(node)
                if name:
                    definitions.append({
                        "name": name,
                        "kind": "constructor",
                        "line": node.start_point[0] + 1,
                        "parent": parent_class,
                    })

            # 提取方法调用: method_invocation
            if node.type == "method_invocation":
                callee = self._get_java_method_call_name(node)
                if callee:
                    call_line = node.start_point[0] + 1
                    caller = _get_current_method(call_line)
                    dedup_key = (caller, callee)
                    if dedup_key not in seen_calls:
                        seen_calls.add(dedup_key)
                        calls.append({
                            "name": callee,
                            "kind": "call",
                            "line": call_line,
                            "caller": caller,
                        })

            # 提取对象创建: new ClassName()
            elif node.type == "object_creation_expression":
                name = self._get_name(node)
                if name:
                    call_line = node.start_point[0] + 1
                    caller = _get_current_method(call_line)
                    dedup_key = (caller, f"new {name}")
                    if dedup_key not in seen_calls:
                        seen_calls.add(dedup_key)
                        calls.append({
                            "name": name,
                            "kind": "constructor_call",
                            "line": call_line,
                            "caller": caller,
                        })

            for child in node.children:
                _walk(child, parent_class)

        _walk(tree.root_node)

        # 使用 Query API 提取路由（替代硬编码注解遍历）
        routes = self._extract_routes_via_query(tree, "java")

        return {"definitions": definitions, "calls": calls, "routes": routes}

    # ── C++ 提取 ──

    def _extract_cpp(self, tree, lang_info: dict) -> Dict:
        """C/C++ 符号提取：definitions + calls (call_expression)"""
        definitions = []
        calls = []
        class_types = lang_info["class_types"]
        func_types = lang_info["function_types"]
        seen_calls = set()

        def _get_current_function(call_line: int) -> str:
            """根据调用行号，找到最近的函数/方法名作为 caller"""
            best = ""
            best_line = 0
            for d in definitions:
                if d["kind"] in ("function", "method", "constructor") and d["line"] <= call_line:
                    if d["line"] > best_line:
                        best = d["name"]
                        best_line = d["line"]
            return best

        def _walk(node: Node, parent_class: str = ""):
            if node.type in class_types:
                name = self._get_name(node)
                if name:
                    kind = "class" if node.type == "class_specifier" else "struct"
                    definitions.append({
                        "name": name,
                        "kind": kind,
                        "line": node.start_point[0] + 1,
                        "parent": "",
                    })
                    for child in node.children:
                        _walk(child, parent_class=name)
                    return

            if node.type in func_types:
                name = self._get_cpp_function_name(node)
                if name:
                    kind = "method" if parent_class else "function"
                    definitions.append({
                        "name": name,
                        "kind": kind,
                        "line": node.start_point[0] + 1,
                        "parent": parent_class,
                    })

            elif node.type == "field_declaration" and parent_class:
                func_decl = self._find_child_by_type(node, "function_declarator")
                if func_decl:
                    name = self._get_cpp_declarator_name(func_decl)
                    if name:
                        definitions.append({
                            "name": name,
                            "kind": "method",
                            "line": node.start_point[0] + 1,
                            "parent": parent_class,
                        })

            elif node.type == "declaration" and parent_class:
                func_decl = self._find_child_by_type(node, "function_declarator")
                if func_decl:
                    name = self._get_cpp_declarator_name(func_decl)
                    if name:
                        dest = self._find_child_by_type(func_decl, "destructor_name")
                        kind = "destructor" if dest else "constructor"
                        definitions.append({
                            "name": name,
                            "kind": kind,
                            "line": node.start_point[0] + 1,
                            "parent": parent_class,
                        })

            # 提取函数调用: call_expression
            if node.type == "call_expression":
                callee = self._get_cpp_call_name(node)
                if callee:
                    call_line = node.start_point[0] + 1
                    caller = _get_current_function(call_line)
                    dedup_key = (caller, callee)
                    if dedup_key not in seen_calls:
                        seen_calls.add(dedup_key)
                        calls.append({
                            "name": callee,
                            "kind": "call",
                            "line": call_line,
                            "caller": caller,
                        })

            for child in node.children:
                _walk(child, parent_class)

        _walk(tree.root_node)
        return {"definitions": definitions, "calls": calls, "routes": []}

    def _get_cpp_function_name(self, node: Node) -> Optional[str]:
        """
        C++ 函数名提取比较复杂：
        - 普通函数: int foo() → name 在 declarator → function_declarator → identifier
        - 类方法: void Server::start() → name 在 declarator → function_declarator → qualified_identifier
        - 运算符重载: operator== → 特殊处理
        """
        # 找 declarator 子节点
        declarator = self._find_child_by_type(node, "function_declarator")
        if not declarator:
            # 尝试找 pointer_declarator > function_declarator
            ptr_decl = self._find_child_by_type(node, "pointer_declarator")
            if ptr_decl:
                declarator = self._find_child_by_type(ptr_decl, "function_declarator")

        if not declarator:
            return None

        return self._get_cpp_declarator_name(declarator)

    @staticmethod
    def _get_cpp_declarator_name(declarator: Node) -> Optional[str]:
        """从 C++ function_declarator 节点提取函数名"""
        # 1. 简单标识符
        ident = UniversalExtractor._find_child_by_type_static(declarator, "identifier")
        if ident:
            return ident.text.decode("utf-8")

        # 2. 限定标识符 (ClassName::method_name)
        qualified = UniversalExtractor._find_child_by_type_static(declarator, "qualified_identifier")
        if qualified:
            return qualified.text.decode("utf-8")

        # 3. 字段标识符 (类内部方法声明)
        field_ident = UniversalExtractor._find_child_by_type_static(declarator, "field_identifier")
        if field_ident:
            return field_ident.text.decode("utf-8")

        # 4. 运算符重载
        op_ident = UniversalExtractor._find_child_by_type_static(declarator, "operator_name")
        if op_ident:
            return op_ident.text.decode("utf-8")

        # 5. 析构函数
        dest = UniversalExtractor._find_child_by_type_static(declarator, "destructor_name")
        if dest:
            return dest.text.decode("utf-8")

        return None

    @staticmethod
    def _find_child_by_type_static(node: Node, child_type: str) -> Optional[Node]:
        """静态版本的 _find_child_by_type"""
        for child in node.children:
            if child.type == child_type:
                return child
        return None

    # ── 通用提取（fallback）──

    def _extract_generic(self, tree, lang_info: dict) -> Dict:
        """通用符号提取：合并所有已知类型进行匹配（无调用提取）"""
        definitions = []
        class_types = lang_info.get("class_types", set())
        func_types = lang_info.get("function_types", set())

        def _walk(node: Node, parent_class: str = ""):
            if node.type in class_types:
                name = self._get_name(node)
                if name:
                    definitions.append({
                        "name": name,
                        "kind": "class",
                        "line": node.start_point[0] + 1,
                        "parent": "",
                    })
                    for child in node.children:
                        _walk(child, parent_class=name)
                    return

            if node.type in func_types:
                name = self._get_name(node)
                if name:
                    kind = "method" if parent_class else "function"
                    definitions.append({
                        "name": name,
                        "kind": kind,
                        "line": node.start_point[0] + 1,
                        "parent": parent_class,
                    })

            for child in node.children:
                _walk(child, parent_class)

        _walk(tree.root_node)
        return {"definitions": definitions, "calls": [], "routes": []}

    # ── 辅助方法 ──

    @staticmethod
    def _get_name(node: Node) -> Optional[str]:
        """
        从 AST 节点提取名称。
        大多数语言的名称在第一个 identifier 类型的子节点中。
        C++ 的 class_specifier 使用 type_identifier。
        """
        for child in node.children:
            if child.type in ("identifier", "name", "type_identifier"):
                return child.text.decode("utf-8")
        # 递归查找
        for child in node.children:
            name = UniversalExtractor._get_name(child)
            if name:
                return name
        return None

    @staticmethod
    def _find_child_by_type(node: Node, child_type: str) -> Optional[Node]:
        """查找指定类型的直接子节点"""
        for child in node.children:
            if child.type == child_type:
                return child
        return None

    # ── 调用名称提取辅助方法 ──

    @staticmethod
    def _get_python_call_name(node: Node) -> Optional[str]:
        """
        从 Python call 节点提取被调用的函数名。
        call 节点的第一个子节点是调用目标:
          - identifier: foo() → "foo"
          - attribute: obj.method() → "obj.method"
        """
        if not node.children:
            return None
        first = node.children[0]
        if first.type == "identifier":
            return first.text.decode("utf-8")
        elif first.type == "attribute":
            # obj.method() → 提取完整属性链
            return first.text.decode("utf-8")
        return None

    @staticmethod
    def _get_java_method_call_name(node: Node) -> Optional[str]:
        """
        从 Java method_invocation 节点提取方法名。
        method_invocation 结构: object.method(args)
          - 第一个子节点通常是 object
          - 后面跟着 . 和 identifier
        简化处理: 提取最后一个 identifier 子节点作为方法名
        """
        # 方法名在最后一个 identifier 子节点
        identifiers = [c for c in node.children if c.type == "identifier"]
        if identifiers:
            return identifiers[-1].text.decode("utf-8")
        return None

    @staticmethod
    def _get_cpp_call_name(node: Node) -> Optional[str]:
        """
        从 C++ call_expression 节点提取被调用的函数名。
        call_expression 结构:
          - identifier: foo() → "foo"
          - qualified_identifier: Server::start() → "Server::start"
          - field_expression: obj.method() → "obj.method"
          - 也可以是更复杂的表达式
        """
        if not node.children:
            return None
        first = node.children[0]
        if first.type == "identifier":
            return first.text.decode("utf-8")
        elif first.type == "qualified_identifier":
            return first.text.decode("utf-8")
        elif first.type == "field_expression":
            return first.text.decode("utf-8")
        # 嵌套 call_expression 等复杂情况，跳过
        return None

    # ── 路由解析辅助方法 ──

    # Python HTTP 方法关键词
    _PYTHON_HTTP_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}

    @classmethod
    def _parse_python_route_decorator(cls, decorator_node: Node, func_name: str) -> Optional[Dict]:
        """
        从 Python 装饰器节点提取路由信息。
        支持模式:
          @app.get("/api/users")
          @router.post("/api/users/{id}")
          @app.put("/api/items")
          @app.delete("/api/items/{id}")
          @app.api_route("/api/any", methods=["GET"])
        装饰器 AST: decorator → call → attribute (app.get) + argument_list
        """
        # 找到 call 子节点
        call_node = None
        for child in decorator_node.children:
            if child.type == "call":
                call_node = child
                break
        if not call_node:
            return None

        # 提取 HTTP 方法和装饰器名
        http_method = ""
        first_child = call_node.children[0] if call_node.children else None
        if not first_child:
            return None

        if first_child.type == "attribute":
            # app.get, router.post 等
            attr_text = first_child.text.decode("utf-8")
            parts = attr_text.rsplit(".", 1)
            method_key = parts[-1].lower() if len(parts) > 1 else ""
            if method_key in cls._PYTHON_HTTP_METHODS:
                http_method = method_key.upper()
            elif method_key == "api_route":
                http_method = "ANY"
            elif method_key == "route":
                # Flask: @app.route("/path", methods=["GET", "POST"])
                http_method = "ANY"
            else:
                return None
        elif first_child.type == "identifier":
            # 简写: @get("/path") (少见)
            name = first_child.text.decode("utf-8").lower()
            if name in cls._PYTHON_HTTP_METHODS:
                http_method = name.upper()
            else:
                return None
        else:
            return None

        # 提取路径字符串: 第一个 string 参数
        path = cls._extract_first_string_arg(call_node)
        if not path:
            return None

        return {
            "method": http_method,
            "path": path,
            "handler": func_name,
            "line": decorator_node.start_point[0] + 1,
        }

    # Java Spring 路由注解映射
    _JAVA_ROUTE_ANNOTATIONS = {
        "GetMapping": "GET",
        "PostMapping": "POST",
        "PutMapping": "PUT",
        "DeleteMapping": "DELETE",
        "PatchMapping": "PATCH",
        "RequestMapping": "ANY",
    }

    @classmethod
    def _parse_java_route_annotation(cls, annotation_node: Node, method_name: str) -> Optional[Dict]:
        """
        从 Java 注解节点提取路由信息。
        支持模式:
          @GetMapping("/api/users")
          @PostMapping("/api/users/{id}")
          @RequestMapping(value = "/api/users", method = RequestMethod.GET)
          @RequestMapping("/api/users")
        注解 AST: marker_annotation/annotation → name (identifier/scoped_type_identifier) + argument_list
        """
        # 提取注解名
        annotation_name = ""
        for child in annotation_node.children:
            if child.type in ("identifier", "scoped_type_identifier", "type_identifier"):
                annotation_name = child.text.decode("utf-8")
                break
            elif child.type == "name":
                # 有些情况下 name 节点包含 identifier
                for sub in child.children:
                    if sub.type == "identifier":
                        annotation_name = sub.text.decode("utf-8")
                        break
                if annotation_name:
                    break

        if not annotation_name:
            return None

        # 检查是否是路由注解
        http_method = cls._JAVA_ROUTE_ANNOTATIONS.get(annotation_name)
        if not http_method:
            return None

        # 提取路径: 从 annotation_argument_list 中找 string_literal
        path = ""
        arg_list = None
        for child in annotation_node.children:
            if child.type == "annotation_argument_list":
                arg_list = child
                break

        if arg_list:
            # 优先找 value= 或 path= 赋值
            for arg in arg_list.children:
                if arg.type == "string_literal":
                    path = cls._clean_java_string(arg.text.decode("utf-8"))
                    break
                elif arg.type == "assignment_expression":
                    # value = "/api/users" 或 path = "/api/users"
                    left = arg.child_by_field_name("left")
                    right = arg.child_by_field_name("right")
                    if left and right and left.text.decode("utf-8") in ("value", "path"):
                        if right.type == "string_literal":
                            path = cls._clean_java_string(right.text.decode("utf-8"))
                            break
                elif arg.type == "element_value_pair":
                    # Java 注解参数: value = "/health" 或 path = "/health"
                    children = arg.children
                    if len(children) >= 3:
                        key = children[0].text.decode("utf-8")
                        if key in ("value", "path"):
                            val_node = children[2]
                            if val_node.type == "string_literal":
                                path = cls._clean_java_string(val_node.text.decode("utf-8"))
                                break

        if not path:
            return None

        # 如果是 RequestMapping，尝试从 method= 提取具体 HTTP 方法
        if annotation_name == "RequestMapping" and arg_list:
            for arg in arg_list.children:
                if arg.type == "assignment_expression":
                    left = arg.child_by_field_name("left")
                    right = arg.child_by_field_name("right")
                    if left and left.text.decode("utf-8") == "method":
                        right_text = right.text.decode("utf-8")
                        if "GET" in right_text:
                            http_method = "GET"
                        elif "POST" in right_text:
                            http_method = "POST"
                        elif "PUT" in right_text:
                            http_method = "PUT"
                        elif "DELETE" in right_text:
                            http_method = "DELETE"
                        elif "PATCH" in right_text:
                            http_method = "PATCH"
                elif arg.type == "element_value_pair":
                    children = arg.children
                    if len(children) >= 3 and children[0].text.decode("utf-8") == "method":
                        right_text = children[2].text.decode("utf-8")
                        if "GET" in right_text:
                            http_method = "GET"
                        elif "POST" in right_text:
                            http_method = "POST"
                        elif "PUT" in right_text:
                            http_method = "PUT"
                        elif "DELETE" in right_text:
                            http_method = "DELETE"
                        elif "PATCH" in right_text:
                            http_method = "PATCH"

        return {
            "method": http_method,
            "path": path,
            "handler": method_name,
            "line": annotation_node.start_point[0] + 1,
        }

    @staticmethod
    def _extract_first_string_arg(call_node: Node) -> str:
        """从 call 节点的参数列表中提取第一个 string 参数的值"""
        for child in call_node.children:
            if child.type == "argument_list":
                for arg in child.children:
                    if arg.type == "string":
                        text = arg.text.decode("utf-8")
                        # 去掉引号: "path" 或 'path'
                        if len(text) >= 2 and text[0] in ('"', "'") and text[-1] == text[0]:
                            return text[1:-1]
                        return text
                    elif arg.type == "concatenated_string":
                        # f-string 或拼接字符串
                        return arg.text.decode("utf-8").strip('"').strip("'")
                break
        return ""

    @staticmethod
    def _clean_java_string(s: str) -> str:
        """清理 Java 字符串字面量: 去掉引号"""
        if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
            return s[1:-1]
        return s


# ════════════════════════════════════════════════════════════════
# 便捷函数
# ════════════════════════════════════════════════════════════════

_extractor = UniversalExtractor()


def extract_symbols(filepath: str, code_content: str) -> Dict:
    """
    便捷函数：提取文件中的符号（定义 + 调用）

    Args:
        filepath: 文件路径
        code_content: 文件内容

    Returns:
        {"definitions": [...], "calls": [...]}
    """
    return _extractor.extract_symbols(filepath, code_content)


def extract_symbols_flat(filepath: str, code_content: str) -> List[str]:
    """
    便捷函数：提取符号并返回扁平字符串列表

    Returns:
        如 ['class ChatServer', 'function start', 'method send_msg']
    """
    return _extractor.extract_symbols_flat(filepath, code_content)


# ════════════════════════════════════════════════════════════════
# 兼容适配器：对接 project_grapher.py 的 {definitions, calls, imports} 格式
# ════════════════════════════════════════════════════════════════

def parse_file_with_treesitter_v2(filepath: str, language: str = "") -> dict:
    """
    兼容 project_grapher.py 的解析接口。

    返回格式与 ast_tool.parse_file_with_treesitter 完全一致:
    {
        "definitions": [{"name", "kind", "line", "end_line", "parent_name", ...}],
        "calls": [{"caller", "callee", "line"}],
        "imports": [{"source", "specifiers", "line"}]
    }

    Args:
        filepath: 文件路径
        language: 语言名称（可选，会根据文件后缀自动判断）
    """
    empty = {"definitions": [], "calls": [], "imports": []}

    # 检查是否为支持的语言
    lang_info = ParserFactory.get_language_info(filepath)
    if not lang_info:
        return empty

    # 读取文件内容
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            code_content = f.read()
    except Exception as e:
        logger.warning(f"文件读取失败 {filepath}: {e}")
        return empty

    # 使用 Tree-Sitter 提取符号（定义 + 调用）
    result = _extractor.extract_symbols(filepath, code_content)
    raw_definitions = result.get("definitions", [])
    raw_calls = result.get("calls", [])
    raw_routes = result.get("routes", [])

    # 转换为 definitions 格式
    definitions = []
    for sym in raw_definitions:
        defn = {
            "name": sym["name"],
            "kind": sym["kind"],
            "line": sym["line"],
            "end_line": sym["line"],
            "parent_name": sym.get("parent", ""),
        }
        if sym["kind"] == "class":
            defn["methods"] = []
            defn["properties"] = []
            defn["docstring"] = ""
        elif sym["kind"] in ("function", "method"):
            defn["params"] = []
            defn["return_type"] = ""
            defn["docstring"] = ""
        elif sym["kind"] == "constructor":
            defn["params"] = []
            defn["return_type"] = ""
            defn["docstring"] = ""
        definitions.append(defn)

    # 转换为 calls 格式
    calls = []
    for call in raw_calls:
        calls.append({
            "caller": call.get("caller", ""),
            "callee": call["name"],
            "line": call["line"],
        })

    # 提取 imports
    imports = _extract_imports(filepath, code_content)

    return {"definitions": definitions, "calls": calls, "imports": imports, "routes": raw_routes}


def _extract_imports(filepath: str, code_content: str) -> list:
    """
    从代码中提取 import 语句（正则补充，覆盖 Python/Java/C++）
    """
    import re

    imports = []
    lang_name = ParserFactory.get_language_name(filepath)
    lines = code_content.split("\n")

    if lang_name == "python":
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            m = re.match(r"^from\s+([\w.]+)\s+import\s+(.+)", stripped)
            if m:
                source = m.group(1)
                specs = [s.strip() for s in m.group(2).split(",") if s.strip()]
                imports.append({"source": source, "specifiers": specs, "line": i})
                continue
            m = re.match(r"^import\s+([\w.]+)", stripped)
            if m:
                source = m.group(1)
                imports.append({"source": source, "specifiers": [source], "line": i})

    elif lang_name == "java":
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            m = re.match(r"^import\s+(?:static\s+)?([\w.]+(?:\.\*)?)\s*;", stripped)
            if m:
                source = m.group(1)
                if source.endswith(".*"):
                    specs = ["*"]
                else:
                    specs = [source.split(".")[-1]]
                imports.append({"source": source, "specifiers": specs, "line": i})

    elif lang_name == "cpp":
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            m = re.match(r'^#\s*include\s+[<"](.+?)[>"]', stripped)
            if m:
                source = m.group(1)
                imports.append({"source": source, "specifiers": [source], "line": i})

    return imports


# ════════════════════════════════════════════════════════════════
# 测试入口
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    # ── 内置测试代码 ──
    python_code = '''
class ChatServer:
    """A simple chat server."""

    def __init__(self, host, port):
        self.host = host
        self.port = port

    def start(self):
        """Start the server."""
        pass

    def send_msg(self, client, message):
        """Send a message to a client."""
        pass


def parse_config(path):
    """Parse configuration file."""
    pass


class ConnectionPool:
    def acquire(self):
        pass

    def release(self, conn):
        pass
'''

    java_code = '''
public class ConsumerApplication {
    private final ProviderFeignClient feignClient;

    public ConsumerApplication(ProviderFeignClient feignClient) {
        this.feignClient = feignClient;
    }

    public String callProvider() {
        return feignClient.hello();
    }

    @Override
    public String toString() {
        return "ConsumerApplication";
    }
}

interface ProviderFeignClient {
    String hello();
}

enum Status {
    ACTIVE, INACTIVE
}
'''

    cpp_code = '''
class Server {
public:
    Server(int port);
    ~Server();

    void start();
    void stop();

private:
    int port_;
    ConnectionPool* pool_;
};

struct Config {
    std::string host;
    int port;
};

void initialize(const Config& cfg);
Server* create_server(int port);
'''

    extractor = UniversalExtractor()

    print("=" * 60)
    print("🐍 Python 符号提取")
    print("=" * 60)
    result = extractor.extract_symbols("test.py", python_code)
    for sym in result["definitions"]:
        parent = f" (in {sym['parent']})" if sym["parent"] else ""
        print(f"  L{sym['line']:3d}  {sym['kind']:12s}  {sym['name']}{parent}")
    print(f"  📞 调用: {len(result['calls'])} 个")
    for call in result["calls"]:
        caller = f" (from {call['caller']})" if call["caller"] else ""
        print(f"    L{call['line']:3d}  → {call['name']}{caller}")

    print()
    print("=" * 60)
    print("☕ Java 符号提取")
    print("=" * 60)
    result = extractor.extract_symbols("Test.java", java_code)
    for sym in result["definitions"]:
        parent = f" (in {sym['parent']})" if sym["parent"] else ""
        print(f"  L{sym['line']:3d}  {sym['kind']:12s}  {sym['name']}{parent}")
    print(f"  📞 调用: {len(result['calls'])} 个")
    for call in result["calls"]:
        caller = f" (from {call['caller']})" if call["caller"] else ""
        print(f"    L{call['line']:3d}  → {call['name']}{caller}")

    print()
    print("=" * 60)
    print("⚡ C++ 符号提取")
    print("=" * 60)
    result = extractor.extract_symbols("test.cpp", cpp_code)
    for sym in result["definitions"]:
        parent = f" (in {sym['parent']})" if sym["parent"] else ""
        print(f"  L{sym['line']:3d}  {sym['kind']:12s}  {sym['name']}{parent}")
    print(f"  📞 调用: {len(result['calls'])} 个")
    for call in result["calls"]:
        caller = f" (from {call['caller']})" if call["caller"] else ""
        print(f"    L{call['line']:3d}  → {call['name']}{caller}")

    print()
    print("=" * 60)
    print("📋 扁平符号列表")
    print("=" * 60)
    print("Python:", extractor.extract_symbols_flat("test.py", python_code))
    print("Java:  ", extractor.extract_symbols_flat("Test.java", java_code))
    print("C++:   ", extractor.extract_symbols_flat("test.cpp", cpp_code))

    # ── 测试项目中的真实文件 ──
    print()
    print("=" * 60)
    print("📂 真实文件测试")
    print("=" * 60)

    test_files = [
        os.path.join(os.path.dirname(__file__), "project_grapher.py"),
        os.path.join(os.path.dirname(__file__), "main.py"),
    ]

    # 尝试找一个 Java 文件
    for root, dirs, files in os.walk(os.path.dirname(__file__)):
        for f in files:
            if f.endswith(".java"):
                test_files.append(os.path.join(root, f))
                break
        if any(f.endswith(".java") for f in files):
            break

    for fpath in test_files:
        if not os.path.isfile(fpath):
            continue
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        flat = extract_symbols_flat(fpath, content)
        print(f"\n  {os.path.basename(fpath)} ({len(flat)} symbols):")
        for sym in flat[:15]:
            print(f"    • {sym}")
        if len(flat) > 15:
            print(f"    ... and {len(flat) - 15} more")

    # ── 不支持的文件后缀测试 ──
    print()
    result = extract_symbols("readme.md", "# Hello")
    assert result == {"definitions": [], "calls": [], "routes": []}, f"不支持的文件应返回空字典，但得到: {result}"
    print("✅ 不支持的文件后缀 → 返回空字典")

    print()
    print("🎉 Tree-Sitter 多语言解析引擎测试全部通过！")
