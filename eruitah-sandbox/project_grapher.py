"""
Eruitah 智能编程沙盒 - 项目级代码图谱构建器

参考 Understand-Anything graph-builder.ts 的跨文件链接逻辑:
┌─────────────────────────────────────────────────────────────────────┐
│  Phase 1 (SCAN):     遍历工作区所有代码文件，提取 AST 数据          │
│  Phase 2 (REGISTER): 符号表注册 + 创建 File/Class/Function 节点    │
│                      + CONTAINS 边                                 │
│  Phase 3 (RESOLVE):  解析 import → IMPORTS 边                      │
│                      解析 call   → CALLS 边 (跨文件符号匹配)       │
│                      无法解析的外部库调用直接 Drop                  │
│  Phase 4 (OUTPUT):   序列化为 project_structure.json                │
│    {"nodes": [{id, type, name, file_path}],                        │
│     "edges": [{source, target, type}]}                             │
│                                                                    │
│  Node ID 规则:                                                     │
│    File     → "rel/path.py"                                       │
│    Class    → "rel/path.py::ClassName"                             │
│    Function → "rel/path.py::func_name"                             │
│    Method   → "rel/path.py::ClassName.method_name"                 │
└─────────────────────────────────────────────────────────────────────┘
"""

import os
import sys
import json
import re
import logging
from pathlib import Path
from collections import defaultdict

from ignore_engine import generate_ignore_file, filter_files
from graph_cluster import detect_domains
from typing import Optional

logger = logging.getLogger(__name__)

LAYER_PRESETS = {
    "BACKEND_MVC": {
        "description": "后端 MVC / 分层架构项目 (Java/Spring, Python/Django, Go, etc.)",
        "layers": {
            "api": {
                "dir_keywords": {"controller", "api", "router", "web", "endpoint", "rest", "graphql", "gateway", "handler", "action", "resource"},
                "name_patterns": r"(?:^|_)(?:controller|api|router|web|endpoint|resource|gateway"
                                 r"|rest|graphql|grpc|handler|action)"
                                 r"(?:impl|base|abstract|interface)?(?:$|_)",
            },
            "business": {
                "dir_keywords": {"service", "manager", "impl", "processor", "orchestrator", "coordinator", "logic", "engine", "workflow", "usecase", "use_case", "command", "query"},
                "name_patterns": r"(?:^|_)(?:service|manager|impl|handler|processor|orchestrator"
                                 r"|coordinator|logic|engine|workflow|usecase|use_case"
                                 r"|command|query|interactor|executor|provider)"
                                 r"(?:impl|base|abstract|interface)?(?:$|_)",
            },
            "data": {
                "dir_keywords": {"repository", "dao", "mapper", "db", "database", "store", "persistence", "cache", "client", "datasource", "storage"},
                "name_patterns": r"(?:^|_)(?:repository|dao|mapper|db|database|store|persistence"
                                 r"|cache|client|datasource|storage|crud|access)"
                                 r"(?:impl|base|abstract|interface)?(?:$|_)",
            },
            "domain": {
                "dir_keywords": {"entity", "model", "dto", "vo", "domain", "record", "bean", "pojo", "proto", "message"},
                "name_patterns": r"(?:^|_)(?:entity|model|dto|vo|value[_-]?object|aggregate"
                                 r"|domain|record|struct|dataclass|bean|pojo|proto|message)"
                                 r"(?:impl|base|abstract|interface)?(?:$|_)",
            },
            "infrastructure": {
                "dir_keywords": {"config", "util", "helper", "common", "base", "constant", "exception", "middleware", "interceptor", "filter", "aspect", "validator", "converter", "factory", "builder", "adapter"},
                "name_patterns": r"(?:^|_)(?:config|util|helper|common|base|abstract|constant"
                                 r"|exception|error|logger|middleware|interceptor|filter"
                                 r"|aspect|validator|converter|mapper|factory|builder"
                                 r"|singleton|adapter|wrapper|decorator|proxy|serializer)"
                                 r"(?:impl|base|abstract|interface)?(?:$|_)",
            },
        },
        "layer_names": {
            "api": "API 接口层",
            "business": "业务逻辑层",
            "data": "数据访问层",
            "domain": "领域模型层",
            "infrastructure": "基础设施层",
            "unknown": "未分类",
        },
    },
    "FRONTEND": {
        "description": "前端 SPA / 组件化项目 (Vue/React/Angular/Svelte, etc.)",
        "layers": {
            "ui_page": {
                "dir_keywords": {"pages", "views", "screens", "routes", "layouts", "app"},
                "name_patterns": r"(?:^|_)(?:page|view|screen|layout|app|route)"
                                 r"(?:component|container|wrapper)?(?:$|_)",
            },
            "ui_component": {
                "dir_keywords": {"components", "widgets", "ui", "shared", "common", "elements", "atoms", "molecules", "organisms", "templates"},
                "name_patterns": r"(?:^|_)(?:component|widget|card|modal|dialog|drawer|popover"
                                 r"|dropdown|tooltip|badge|avatar|button|input|form"
                                 r"|table|list|grid|menu|tab|accordion|carousel"
                                 r"|skeleton|spinner|progress|alert|toast|notification)"
                                 r"(?:component|wrapper|container)?(?:$|_)",
            },
            "state": {
                "dir_keywords": {"store", "stores", "state", "redux", "pinia", "vuex", "context", "providers", "hooks"},
                "name_patterns": r"(?:^|_)(?:store|use[_]?store|state|reducer|action|selector|dispatch"
                                 r"|provider|context|pinia|vuex|mobx|zustand|recoil|jotai)"
                                 r"(?:store|provider|context)?(?:$|_)",
            },
            "logic": {
                "dir_keywords": {"hooks", "composables", "utils", "helpers", "lib", "libs", "services", "logic", "core"},
                "name_patterns": r"(?:^|_)(?:use[_]|hook|composable|util|helper|format|transform"
                                 r"|validate|parse|calculate|compute|process|handler)"
                                 r"(?:hook|util|helper|service)?(?:$|_)",
            },
            "api_client": {
                "dir_keywords": {"api", "services", "requests", "http", "client", "endpoints", "queries", "mutations"},
                "name_patterns": r"(?:^|_)(?:api|service|request|fetch|axios|http|client|endpoint"
                                 r"|query|mutation|graphql|rest|rpc|swagger)"
                                 r"(?:service|client|handler)?(?:$|_)",
            },
            "infrastructure": {
                "dir_keywords": {"config", "constants", "types", "interfaces", "styles", "assets", "public", "static", "middleware", "plugins"},
                "name_patterns": r"(?:^|_)(?:config|constant|type|interface|style|theme|plugin"
                                 r"|middleware|guard|interceptor|router|i18n|locale)"
                                 r"(?:config|type|style|plugin)?(?:$|_)",
            },
        },
        "layer_names": {
            "ui_page": "页面层",
            "ui_component": "组件层",
            "state": "状态管理层",
            "logic": "逻辑/工具层",
            "api_client": "API 客户端层",
            "infrastructure": "基础设施层",
            "unknown": "未分类",
        },
    },
}


def sniff_project_type(root_dir: str) -> str:
    root = Path(root_dir)

    backend_signals = 0
    frontend_signals = 0

    # 具体框架检测标记
    detected_framework = None

    # Java/Spring
    if (root / "pom.xml").is_file() or (root / "build.gradle").is_file() or (root / "build.gradle.kts").is_file():
        detected_framework = "java"
    # Go
    if (root / "go.mod").is_file():
        detected_framework = "go"
    # Rust
    if (root / "Cargo.toml").is_file():
        detected_framework = "rust"
    # C/C++
    if (root / "CMakeLists.txt").is_file() or (root / "Makefile").is_file():
        if not detected_framework:
            detected_framework = "cpp"
    # .NET
    if (root / "*.sln") and not detected_framework:
        for f in root.iterdir():
            if f.suffix == ".sln":
                detected_framework = "dotnet"
                break

    # Node.js / 前端框架
    frontend_marker_files = {"package.json", "tsconfig.json", "vite.config.ts", "vite.config.js",
                              "next.config.js", "next.config.ts", "nuxt.config.ts",
                              "angular.json", "svelte.config.js"}
    for marker in frontend_marker_files:
        if (root / marker).is_file():
            detected_framework = "node"
            break

    # Python (检查 pyproject.toml, setup.py, requirements.txt, manage.py)
    python_markers = {"pyproject.toml", "setup.py", "requirements.txt", "Pipfile", "manage.py", "django_settings.py"}
    for marker in python_markers:
        if (root / marker).is_file():
            if not detected_framework:
                detected_framework = "python"
            break

    backend_marker_files = {"pom.xml", "build.gradle", "build.gradle.kts", "Cargo.toml", "go.mod", "settings.gradle", "ivy.xml", "Makefile"}

    for marker in backend_marker_files:
        if (root / marker).is_file():
            backend_signals += 3

    for marker in frontend_marker_files:
        if (root / marker).is_file():
            frontend_signals += 3

    backend_exts = {".java", ".kt", ".go", ".rs", ".py", ".rb", ".php", ".cs", ".swift"}
    frontend_exts = {".vue", ".jsx", ".tsx", ".svelte"}

    backend_file_count = 0
    frontend_file_count = 0

    try:
        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext in backend_exts:
                    backend_file_count += 1
                elif ext in frontend_exts:
                    frontend_file_count += 1
                if backend_file_count + frontend_file_count > 500:
                    break
            if backend_file_count + frontend_file_count > 500:
                break
    except Exception:
        pass

    backend_signals += backend_file_count
    frontend_signals += frontend_file_count

    # 如果没有通过标记文件检测到框架，通过文件扩展名推断
    if not detected_framework:
        if backend_file_count > frontend_file_count:
            # 根据主要后端扩展名推断
            if backend_file_count > 0:
                detected_framework = "python"  # 默认后端
        elif frontend_file_count > 0:
            detected_framework = "node"

    # 存储具体框架类型供 ignore_engine 使用
    sniff_project_type._last_detected_framework = detected_framework or "auto"

    if frontend_signals > backend_signals:
        return "FRONTEND"
    if backend_signals > frontend_signals:
        return "BACKEND_MVC"

    if frontend_file_count > 0 and backend_file_count == 0:
        return "FRONTEND"
    if backend_file_count > 0 and frontend_file_count == 0:
        return "BACKEND_MVC"

    return "BACKEND_MVC"


def _compile_preset_rules(preset_name: str) -> tuple[dict, list[tuple]]:
    preset = LAYER_PRESETS[preset_name]
    dir_keywords = {}
    name_rules = []

    for layer, cfg in preset["layers"].items():
        dir_keywords[layer] = cfg["dir_keywords"]
        pattern = re.compile(cfg["name_patterns"], re.IGNORECASE)
        name_rules.append((layer, pattern))

    return dir_keywords, name_rules


def detect_layer(node_id: str, node_type: str, name: str, file_path: str,
                 preset_name: str = "BACKEND_MVC",
                 dir_keywords: dict = None,
                 name_rules: list = None) -> str:
    if dir_keywords is None or name_rules is None:
        dir_keywords, name_rules = _compile_preset_rules(preset_name)

    rel_path = file_path
    parts = Path(rel_path).with_suffix("").parts
    dir_parts = parts[:-1] if len(parts) > 1 else []
    file_stem = parts[-1] if parts else ""

    for layer, keywords in dir_keywords.items():
        for dp in dir_parts:
            if dp.lower() in keywords:
                return layer

    for layer, pattern in name_rules:
        if pattern.search(name):
            return layer

    for layer, pattern in name_rules:
        if pattern.search(file_stem):
            return layer

    if node_type == "File":
        for layer, keywords in dir_keywords.items():
            for dp in dir_parts:
                if dp.lower() in keywords:
                    return layer

    return "unknown"

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

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
    ".next", ".nuxt", "target", "bin", "obj", ".idea", ".vscode",
    ".checkpoints", ".eruitah_cache", ".theseus", ".theseus_backups",
    ".user_data", "audio_cache", "chroma_db",
}

PYTHON_STDLIB_TOP_LEVEL = {
    "abc", "aifc", "argparse", "array", "ast", "asynchat", "asyncio",
    "asyncore", "atexit", "audioop", "base64", "bdb", "binascii",
    "binhex", "bisect", "builtins", "bz2", "calendar", "cgi", "cgitb",
    "chunk", "cmath", "cmd", "code", "codecs", "codeop", "collections",
    "colorsys", "compileall", "concurrent", "configparser", "contextlib",
    "contextvars", "copy", "copyreg", "cProfile", "crypt", "csv",
    "ctypes", "curses", "dataclasses", "datetime", "dbm", "decimal",
    "difflib", "dis", "distutils", "doctest", "email", "encodings",
    "enum", "errno", "faulthandler", "fcntl", "filecmp", "fileinput",
    "fnmatch", "formatter", "fractions", "ftplib", "functools", "gc",
    "getopt", "getpass", "gettext", "glob", "grp", "gzip", "hashlib",
    "heapq", "hmac", "html", "http", "idlelib", "imaplib", "imghdr",
    "imp", "importlib", "inspect", "io", "ipaddress", "itertools",
    "json", "keyword", "lib2to3", "linecache", "locale", "logging",
    "lzma", "mailbox", "mailcap", "marshal", "math", "mimetypes",
    "mmap", "modulefinder", "multiprocessing", "netrc", "nis", "nntplib",
    "numbers", "operator", "optparse", "os", "ossaudiodev", "parser",
    "pathlib", "pdb", "pickle", "pickletools", "pipes", "pkgutil",
    "platform", "plistlib", "poplib", "posix", "posixpath", "pprint",
    "profile", "pstats", "pty", "pwd", "py_compile", "pyclbr",
    "pydoc", "queue", "quopri", "random", "re", "readline", "reprlib",
    "resource", "rlcompleter", "runpy", "sched", "secrets", "select",
    "selectors", "shelve", "shlex", "shutil", "signal", "site",
    "smtpd", "smtplib", "sndhdr", "socket", "socketserver", "spwd",
    "sqlite3", "ssl", "stat", "statistics", "string", "stringprep",
    "struct", "subprocess", "sunau", "symtable", "sys", "sysconfig",
    "syslog", "tabnanny", "tarfile", "telnetlib", "tempfile", "termios",
    "test", "textwrap", "threading", "time", "timeit", "tkinter",
    "token", "tokenize", "trace", "traceback", "tracemalloc", "tty",
    "turtle", "turtledemo", "types", "typing", "unicodedata", "unittest",
    "urllib", "uu", "uuid", "venv", "warnings", "wave", "weakref",
    "webbrowser", "winreg", "winsound", "wsgiref", "xdrlib", "xml",
    "xmlrpc", "zipapp", "zipfile", "zipimport", "zlib",
    "_thread", "__future__",
}


class ProjectGrapher:
    def __init__(self, root_dir: str, preset: str = None):
        self.root_dir = os.path.abspath(root_dir)
        self.nodes = []
        self.edges = []
        self._node_ids = set()
        self._edge_keys = set()

        self._file_analyses = {}
        self._symbol_table = defaultdict(list)
        self._file_index = {}
        self._import_map = defaultdict(list)
        self._dropped_calls = 0

        if preset is None:
            preset = sniff_project_type(self.root_dir)
        self.preset = preset
        self._dir_keywords, self._name_rules = _compile_preset_rules(preset)
        logger.info(f"项目类型嗅探: {preset} — {LAYER_PRESETS[preset]['description']}")

    def _rel(self, fp: str) -> str:
        return os.path.relpath(fp, self.root_dir)

    def _make_file_id(self, fp: str) -> str:
        return self._rel(fp)

    def _make_def_id(self, fp: str, name: str, parent_name: str = "", kind: str = "") -> str:
        rel = self._rel(fp)
        if parent_name and kind == "method":
            return f"{rel}::{parent_name}.{name}"
        return f"{rel}::{name}"

    # 允许进入图谱的节点类型（禁止目录/文件夹节点）
    VALID_NODE_TYPES = {"File", "Class", "Interface", "Function", "Method"}

    def _add_node(self, node_id: str, node_type: str, name: str, file_path: str, **extra):
        # 严格过滤：只允许代码实体节点，禁止目录/文件夹节点
        if node_type not in self.VALID_NODE_TYPES:
            logger.debug(f"跳过非代码节点: type={node_type}, name={name}, id={node_id}")
            return
        if node_id in self._node_ids:
            return
        self._node_ids.add(node_id)
        node = {"id": node_id, "type": node_type, "name": name, "file_path": file_path}
        node["layer"] = detect_layer(node_id, node_type, name, file_path,
                                     dir_keywords=self._dir_keywords,
                                     name_rules=self._name_rules)
        node.update(extra)
        self.nodes.append(node)

    def _add_edge(self, source: str, target: str, edge_type: str):
        key = f"{edge_type}|{source}|{target}"
        if key in self._edge_keys:
            return
        self._edge_keys.add(key)
        self.edges.append({"source": source, "target": target, "type": edge_type})

    # ================================================================
    # Phase 1: Scan files
    # ================================================================

    def scan_files(self) -> list[str]:
        code_files = []
        for dirpath, dirnames, filenames in os.walk(self.root_dir):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
            for fname in filenames:
                ext = os.path.splitext(fname)[1]
                if ext in SUPPORTED_EXTENSIONS:
                    full_path = os.path.join(dirpath, fname)
                    code_files.append(full_path)
        return code_files

    # ================================================================
    # Phase 2: Extract AST data per file
    # ================================================================

    def extract_all(self, file_paths: list[str]):
        try:
            from ast_tool import parse_file_with_treesitter, _parse_file_fallback
        except ImportError:
            logger.error("无法导入 ast_tool，请确保 ast_tool.py 在同一目录下")
            return

        for fp in file_paths:
            ext = os.path.splitext(fp)[1]
            language = SUPPORTED_EXTENSIONS.get(ext, "")
            if not language:
                continue

            try:
                result = parse_file_with_treesitter(fp, language)
                if not result["definitions"] and not result["imports"]:
                    result = _parse_file_fallback(fp, language)
            except Exception as e:
                logger.debug(f"解析失败 {fp}: {e}")
                try:
                    result = _parse_file_fallback(fp, language)
                except Exception:
                    result = {"definitions": [], "calls": [], "imports": []}

            self._file_analyses[fp] = result

    # ================================================================
    # Phase 3: Build symbol table & file index
    # ================================================================

    def build_symbol_table(self):
        for fp, analysis in self._file_analyses.items():
            rel = self._rel(fp)
            module_path = self._file_to_module(rel)
            self._file_index[module_path] = fp

            parent_dir_module = self._dir_to_module(os.path.dirname(rel))
            if parent_dir_module and parent_dir_module not in self._file_index:
                self._file_index[parent_dir_module] = os.path.dirname(fp)

            for defn in analysis["definitions"]:
                name = defn.get("name", "")
                kind = defn.get("kind", "")
                parent_name = defn.get("parent_name", "")
                if name and kind in ("function", "method", "class"):
                    self._symbol_table[name].append({
                        "file": fp,
                        "kind": kind,
                        "line": defn.get("line", 0),
                        "parent_name": parent_name,
                    })

    def _file_to_module(self, rel_path: str) -> str:
        parts = Path(rel_path).with_suffix("").parts
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts)

    def _dir_to_module(self, rel_dir: str) -> str:
        if not rel_dir or rel_dir == ".":
            return ""
        return rel_dir.replace(os.sep, ".")

    # ================================================================
    # Phase 4: Resolve imports → project-internal files
    # ================================================================

    def resolve_imports(self):
        for fp, analysis in self._file_analyses.items():
            language = SUPPORTED_EXTENSIONS.get(os.path.splitext(fp)[1], "")
            for imp in analysis.get("imports", []):
                source = imp.get("source", "")
                specifiers = imp.get("specifiers", [])
                resolved = self._resolve_import(fp, source, language)
                if resolved:
                    self._import_map[fp].append({
                        "resolved_file": resolved,
                        "source": source,
                        "specifiers": specifiers,
                    })

    def _resolve_import(self, from_file: str, source: str, language: str) -> Optional[str]:
        if not source:
            return None

        if language == "python":
            return self._resolve_python_import(from_file, source)
        elif language in ("javascript", "typescript", "tsx", "jsx"):
            return self._resolve_js_ts_import(from_file, source)
        elif language in ("c", "cpp"):
            return self._resolve_c_cpp_import(from_file, source)
        elif language == "go":
            return self._resolve_go_import(from_file, source)
        elif language == "java":
            return self._resolve_java_import(from_file, source)
        elif language == "rust":
            return self._resolve_rust_import(from_file, source)
        return None

    def _resolve_python_import(self, from_file: str, source: str) -> Optional[str]:
        if source.startswith("."):
            return self._resolve_python_relative(from_file, source)

        top = source.split(".")[0]
        if top in PYTHON_STDLIB_TOP_LEVEL:
            return None

        candidates = [source]
        parts = source.split(".")
        for i in range(len(parts) - 1, 0, -1):
            candidates.append(".".join(parts[:i]))

        for candidate in candidates:
            if candidate in self._file_index:
                resolved = self._file_index[candidate]
                if os.path.isfile(resolved):
                    return resolved

            module_path = candidate.replace(".", os.sep)
            for ext in (".py", os.sep + "__init__.py"):
                probe = os.path.join(self.root_dir, module_path + ext)
                if os.path.isfile(probe):
                    return probe

        return None

    def _resolve_python_relative(self, from_file: str, source: str) -> Optional[str]:
        dots = 0
        for ch in source:
            if ch == ".":
                dots += 1
            else:
                break

        remainder = source.lstrip(".")
        from_dir = os.path.dirname(from_file)

        for _ in range(dots - 1):
            from_dir = os.path.dirname(from_dir)

        if remainder:
            probe_py = os.path.join(from_dir, remainder.replace(".", os.sep) + ".py")
            if os.path.isfile(probe_py):
                return probe_py
            probe_init = os.path.join(from_dir, remainder.replace(".", os.sep), "__init__.py")
            if os.path.isfile(probe_init):
                return probe_init
        else:
            probe_init = os.path.join(from_dir, "__init__.py")
            if os.path.isfile(probe_init):
                return probe_init

        return None

    def _resolve_js_ts_import(self, from_file: str, source: str) -> Optional[str]:
        if not source.startswith("."):
            return None

        from_dir = os.path.dirname(from_file)
        base = os.path.normpath(os.path.join(from_dir, source))

        for ext in ("", ".js", ".jsx", ".ts", ".tsx"):
            probe = base + ext
            if os.path.isfile(probe):
                return probe

        for index in ("index.js", "index.jsx", "index.ts", "index.tsx"):
            probe = os.path.join(base, index)
            if os.path.isfile(probe):
                return probe

        return None

    def _resolve_c_cpp_import(self, from_file: str, source: str) -> Optional[str]:
        stripped = source.strip("\"'<>")
        from_dir = os.path.dirname(from_file)

        for search_dir in [from_dir, os.path.join(self.root_dir, "include"),
                           os.path.join(self.root_dir, "src"), self.root_dir]:
            probe = os.path.join(search_dir, stripped)
            if os.path.isfile(probe):
                return probe

        return None

    def _resolve_go_import(self, from_file: str, source: str) -> Optional[str]:
        go_mod = self._find_go_mod()
        if not go_mod:
            return None

        mod_dir = os.path.dirname(go_mod)
        try:
            with open(go_mod, "r") as f:
                for line in f:
                    if line.startswith("module "):
                        module_name = line.split()[1].strip()
                        if source.startswith(module_name):
                            rel = source[len(module_name):].lstrip("/")
                            probe = os.path.join(mod_dir, rel)
                            if os.path.isdir(probe):
                                return probe
                        break
        except Exception:
            pass

        return None

    def _resolve_java_import(self, from_file: str, source: str) -> Optional[str]:
        parts = source.split(".")
        for ext in (".java",):
            rel = os.sep.join(parts) + ext
            for search_dir in [os.path.join(self.root_dir, "src"),
                               os.path.join(self.root_dir, "src", "main", "java"),
                               self.root_dir]:
                probe = os.path.join(search_dir, rel)
                if os.path.isfile(probe):
                    return probe
        return None

    def _resolve_rust_import(self, from_file: str, source: str) -> Optional[str]:
        if source.startswith("crate::"):
            remainder = source[7:].replace("::", os.sep)
            for root_file in ["src/lib.rs", "src/main.rs"]:
                crate_root = os.path.join(self.root_dir, root_file)
                if os.path.isfile(crate_root):
                    if not remainder:
                        return crate_root
                    probe = os.path.join(self.root_dir, "src", remainder + ".rs")
                    if os.path.isfile(probe):
                        return probe
                    probe = os.path.join(self.root_dir, "src", remainder, "mod.rs")
                    if os.path.isfile(probe):
                        return probe
        return None

    def _find_go_mod(self) -> Optional[str]:
        current = self.root_dir
        while current != os.path.dirname(current):
            probe = os.path.join(current, "go.mod")
            if os.path.isfile(probe):
                return probe
            current = os.path.dirname(current)
        return None

    # ================================================================
    # Phase 5: Build graph (nodes + edges)
    # ================================================================

    def build_graph(self):
        for fp, analysis in self._file_analyses.items():
            self._register_file_nodes_and_contains(fp, analysis)

        self._build_import_edges()
        self._build_cross_file_call_edges()

    def _register_file_nodes_and_contains(self, fp: str, analysis: dict):
        file_id = self._make_file_id(fp)
        basename = os.path.basename(fp)
        self._add_node(file_id, "File", basename, fp)

        for defn in analysis.get("definitions", []):
            name = defn.get("name", "")
            kind = defn.get("kind", "")
            parent_name = defn.get("parent_name", "")
            if not name:
                continue

            if kind == "class":
                node_type = "Class"
                node_id = self._make_def_id(fp, name, parent_name="", kind="class")
            elif kind in ("function", "method"):
                node_type = "Function"
                node_id = self._make_def_id(fp, name, parent_name=parent_name, kind=kind)
            else:
                continue

            extra = {}
            line = defn.get("line", 0)
            end_line = defn.get("end_line", 0)
            if line:
                extra["line"] = line
            if end_line:
                extra["end_line"] = end_line
            if parent_name:
                extra["parent"] = parent_name
            params = defn.get("params", [])
            if params:
                extra["params"] = params
            return_type = defn.get("return_type", "")
            if return_type:
                extra["return_type"] = return_type

            self._add_node(node_id, node_type, name, fp, **extra)
            self._add_edge(file_id, node_id, "CONTAINS")

        for call in analysis.get("calls", []):
            caller = call.get("caller", "")
            if not caller:
                continue
            caller_id = self._make_def_id(fp, caller)
            if caller_id not in self._node_ids:
                self._add_node(caller_id, "Function", caller, fp)
                self._add_edge(file_id, caller_id, "CONTAINS")

    def _build_import_edges(self):
        for fp, imports in self._import_map.items():
            file_id = self._make_file_id(fp)
            for imp in imports:
                resolved = imp["resolved_file"]
                target_id = self._make_file_id(resolved)
                if target_id in self._node_ids:
                    self._add_edge(file_id, target_id, "IMPORTS")

    def _build_cross_file_call_edges(self):
        for fp, analysis in self._file_analyses.items():
            imported_symbols = self._get_imported_symbols(fp)

            for call in analysis.get("calls", []):
                caller = call.get("caller", "")
                callee_raw = call.get("callee", "")

                if not caller or not callee_raw:
                    continue

                callee_name = callee_raw.split(".")[-1]

                if callee_name in imported_symbols:
                    targets = imported_symbols[callee_name]
                    for target in targets:
                        target_file = target["file"]
                        target_kind = target.get("kind", "function")
                        target_parent = target.get("parent_name", "")
                        if target_file == fp:
                            continue
                        caller_id = self._make_def_id(fp, caller)
                        callee_id = self._make_def_id(
                            target_file, callee_name,
                            parent_name=target_parent, kind=target_kind,
                        )
                        if callee_id in self._node_ids:
                            self._add_edge(caller_id, callee_id, "CALLS")
                else:
                    self._dropped_calls += 1

    def _get_imported_symbols(self, fp: str) -> dict:
        result = defaultdict(list)

        for imp in self._import_map.get(fp, []):
            resolved_file = imp["resolved_file"]
            specifiers = imp.get("specifiers", [])

            if resolved_file in self._file_analyses:
                target_defs = self._file_analyses[resolved_file].get("definitions", [])
                exported = {}
                for defn in target_defs:
                    name = defn.get("name", "")
                    kind = defn.get("kind", "")
                    if name and kind in ("function", "method", "class"):
                        exported[name] = defn

                if specifiers == ["*"]:
                    for name, defn in exported.items():
                        result[name].append({
                            "file": resolved_file,
                            "kind": defn["kind"],
                            "parent_name": defn.get("parent_name", ""),
                        })
                else:
                    for spec in specifiers:
                        if spec in exported:
                            result[spec].append({
                                "file": resolved_file,
                                "kind": exported[spec]["kind"],
                                "parent_name": exported[spec].get("parent_name", ""),
                            })

            source = imp.get("source", "")
            source_top = source.split(".")[-1]
            if source_top and source_top != source:
                if source_top in self._symbol_table:
                    for sym in self._symbol_table[source_top]:
                        if sym["file"] != fp:
                            result[source_top].append({
                                "file": sym["file"],
                                "kind": sym["kind"],
                                "parent_name": sym.get("parent_name", ""),
                            })

        return dict(result)

    # ================================================================
    # Phase 6: Serialize
    # ================================================================

    def to_dict(self) -> dict:
        layers = defaultdict(list)
        for node in self.nodes:
            layer = node.get("layer", "unknown")
            layers[layer].append(node["id"])

        preset_cfg = LAYER_PRESETS.get(self.preset, LAYER_PRESETS["BACKEND_MVC"])
        layer_names = preset_cfg.get("layer_names", {})

        layer_list = []
        for layer_id, node_ids in sorted(layers.items()):
            layer_list.append({
                "id": layer_id,
                "name": layer_names.get(layer_id, layer_id),
                "nodeIds": node_ids,
            })

        return {
            "nodes": self.nodes,
            "edges": self.edges,
            "layers": layer_list,
            "preset": self.preset,
        }

    def write_json(self, output_path: Optional[str] = None, modified_file_paths: Optional[list] = None):
        if output_path is None:
            output_path = os.path.join(self.root_dir, "project_structure.json")

        new_graph = self.to_dict()

        # ── Diff Integration: 读取旧图谱，计算变更影响 ──
        old_graph = None
        if os.path.exists(output_path):
            try:
                with open(output_path, "r", encoding="utf-8") as f:
                    old_graph = json.load(f)
                logger.info(f"读取到旧图谱: {len(old_graph.get('nodes', []))} 节点, {len(old_graph.get('edges', []))} 边")
            except Exception as e:
                logger.warning(f"读取旧图谱失败，跳过 Diff 计算: {e}")
                old_graph = None

        if old_graph is not None:
            try:
                from graph_diff import calculate_graph_diff
                final_graph = calculate_graph_diff(old_graph, new_graph, modified_file_paths)
                summary = final_graph.get("diff_summary", {})
                change_count = summary.get("added_nodes", 0) + summary.get("deleted_nodes", 0) + summary.get("modified_nodes", 0)
                logger.info(f"📊 图谱 Diff 计算完成，发现 {change_count} 个修改点 "
                            f"(+{summary.get('added_nodes', 0)} -{summary.get('deleted_nodes', 0)} "
                            f"~{summary.get('modified_nodes', 0)} ⚡{summary.get('impacted_nodes', 0)} "
                            f"爆炸半径: {summary.get('blast_radius', 0)})")
                # 保留 layers 和 preset 信息
                final_graph["layers"] = new_graph.get("layers", [])
                final_graph["preset"] = new_graph.get("preset", "")
            except ImportError:
                logger.warning("graph_diff 模块未找到，跳过 Diff 计算，直接写入新图谱")
                final_graph = new_graph
            except Exception as e:
                logger.warning(f"Diff 计算异常，回退到直接写入: {e}")
                final_graph = new_graph
        else:
            final_graph = new_graph
            logger.info("无旧图谱，跳过 Diff 计算")

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(final_graph, f, indent=2, ensure_ascii=False)

        logger.info(f"项目图谱已写入: {output_path}")
        logger.info(f"  节点数: {len(final_graph.get('nodes', []))}")
        logger.info(f"  边数: {len(final_graph.get('edges', []))}")
        if self._dropped_calls:
            logger.info(f"  Drop 外部调用: {self._dropped_calls} 条")

        layer_counts = defaultdict(int)
        for node in final_graph.get("nodes", []):
            layer_counts[node.get("layer", "unknown")] += 1
        if layer_counts:
            logger.info("  架构分层:")
            for layer, count in sorted(layer_counts.items()):
                logger.info(f"    {layer}: {count} 个节点")

        return output_path

    # ================================================================
    # Main entry point
    # ================================================================

    def run(self, output_path: Optional[str] = None, modified_file_paths: Optional[list] = None) -> dict:
        logger.info(f"开始构建项目图谱: {self.root_dir}")

        # ── Phase 1: 扫描文件 ──
        raw_file_paths = self.scan_files()
        logger.info(f"🔍 智能降噪引擎启动: 扫描到 {len(raw_file_paths)} 个原始文件...")

        # ── 降噪过滤: 生成 .eruitahignore + 过滤噪声文件 ──
        # 使用嗅探器检测到的具体框架类型（java/python/node/cpp/go/rust）
        fw_type = getattr(sniff_project_type, '_last_detected_framework', None) or "auto"

        generate_ignore_file(self.root_dir, framework_type=fw_type)
        file_paths = filter_files(self.root_dir, raw_file_paths)

        if len(file_paths) < len(raw_file_paths):
            removed = len(raw_file_paths) - len(file_paths)
            logger.info(
                f"🔇 命中黑名单策略 ({fw_type})，已剔除 {removed} 个噪声文件 "
                f"(node_modules, dist, __pycache__ 等)"
            )
            logger.info(
                f"✨ 提纯完成: 仅保留 {len(file_paths)} 个核心业务文件进行 AST 解析！"
            )
        else:
            logger.info(f"扫描到 {len(file_paths)} 个代码文件 (无需降噪过滤)")

        # ── Phase 2: AST 提取 ──
        self.extract_all(file_paths)
        logger.info(f"完成 AST 提取: {len(self._file_analyses)} 个文件")

        # ── Phase 3: 符号表 + 导入解析 ──
        self.build_symbol_table()
        logger.info(f"符号表构建完成: {len(self._symbol_table)} 个符号")

        self.resolve_imports()
        resolved_count = sum(len(v) for v in self._import_map.values())
        logger.info(f"导入解析完成: {resolved_count} 条解析结果")

        # ── Phase 4: 构建图谱 + 社区发现 + Diff + 写入 ──
        self.build_graph()

        # 社区发现: 将紧密连接的节点聚类为业务领域
        self.nodes = detect_domains(self.nodes, self.edges)

        self.write_json(output_path, modified_file_paths=modified_file_paths)
        return self.to_dict()


def build_project_graph(root_dir: str, output_path: Optional[str] = None, preset: str = None, modified_file_paths: Optional[list] = None) -> dict:
    grapher = ProjectGrapher(root_dir, preset=preset)
    return grapher.run(output_path, modified_file_paths=modified_file_paths)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    output = sys.argv[2] if len(sys.argv) > 2 else None
    preset_arg = sys.argv[3] if len(sys.argv) > 3 else None

    result = build_project_graph(root, output, preset=preset_arg)

    node_types = defaultdict(int)
    edge_types = defaultdict(int)
    for n in result["nodes"]:
        node_types[n["type"]] += 1
    for e in result["edges"]:
        edge_types[e["type"]] += 1

    print(f"\n📊 项目图谱统计 (Preset: {result.get('preset', 'N/A')}):")
    print(f"  节点: {len(result['nodes'])}")
    for t, c in sorted(node_types.items()):
        print(f"    {t}: {c}")
    print(f"  边: {len(result['edges'])}")
    for t, c in sorted(edge_types.items()):
        print(f"    {t}: {c}")

    layer_counts = defaultdict(int)
    for n in result["nodes"]:
        layer_counts[n.get("layer", "unknown")] += 1
    if layer_counts:
        print(f"  架构分层:")
        for layer, count in sorted(layer_counts.items()):
            print(f"    {layer}: {count}")
