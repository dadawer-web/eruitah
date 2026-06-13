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
import hashlib
import logging
from pathlib import Path
from collections import defaultdict

from ignore_engine import generate_ignore_file, filter_files
from graph_cluster import detect_domains
from tree_sitter_engine import UniversalExtractor, _extract_imports
from typing import Optional

logger = logging.getLogger(__name__)


def compute_file_hash(filepath: str) -> str:
    """计算文件的 SHA-256 哈希指纹，用于增量缓存比对"""
    sha256 = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
    except (IOError, OSError):
        return ""
    return sha256.hexdigest()


# ================================================================
# 框架级探针: 导入包名 → 架构层级映射
# ================================================================
FRAMEWORK_SIGNATURES = {
    # ── API 接口层 ──
    "api": {
        "flask", "fastapi", "django.urls", "django.views", "django.http",
        "spring.web", "express", "gin", "koa", "hapi", "restify",
        "falcon", "bottle", "tornado.web", "aiohttp", "sanic",
        "starlette", "uvicorn", "gunicorn", "werkzeug",
        "grpc", "protobuf", "thrift",
        "django.rest_framework", "rest_framework",
        "flask_restful", "flask_restx", "flask_api",
        "swagger", "openapi",
    },
    # ── 数据访问层 ──
    "data": {
        "sqlalchemy", "django.db", "pymongo", "motor",
        "mybatis", "hibernate", "jpa", "jdbc",
        "redis", "redis_store", "aioredis", "redis-py",
        "sqlmodel", "tortoise", "orm", "peewee", "pony",
        "alembic", "flyway", "liquibase",
        "psycopg2", "pymysql", "sqlite3", "cx_Oracle",
        "elasticsearch", "elasticapm",
        "cassandra", "dynamodb", "firebase",
        "prisma", "sequelize", "typeorm", "mongoose", "knex",
        "sql", "database", "db", "repository", "dao",
    },
    # ── 基础设施层 ──
    "infrastructure": {
        "logging", "loguru", "structlog", "sentry_sdk",
        "celery", "dramatiq", "rq", "huey",
        "kafka", "confluent_kafka", "pika", "aio_pika", "rabbitmq",
        "docker", "kubernetes", "k8s",
        "config", "dotenv", "pydantic", "dynaconf",
        "prometheus_client", "opentelemetry", "jaeger",
        "consul", "etcd", "zookeeper",
        "boto3", "botocore", "google.cloud", "azure",
        "cron", "apscheduler", "schedule",
        "httpx", "requests", "aiohttp",
    },
    # ── UI 展示层 ──
    "ui": {
        "react", "vue", "angular", "svelte", "solid_js",
        "html", "jinja2", "template", "mako", "chameleon",
        "django.template", "flask.templating",
        "tkinter", "pyqt", "pyside", "kivy",
        "next", "nuxt", "gatsby", "remix",
        "ant_design", "element_ui", "vuetify", "material_ui",
        "tailwind", "bootstrap", "sass", "less", "css",
        "storybook",
    },
    # ── 状态管理 / 消息 ──
    "state": {
        "redux", "vuex", "pinia", "mobx", "zustand", "recoil", "jotai",
        "xstate", "effector", "overmind",
        "event_emitter", "events", "blinker",
    },
    # ── 测试 ──
    "test": {
        "pytest", "unittest", "mock", "pytest_mock",
        "jest", "mocha", "chai", "sinon", "cypress", "playwright", "selenium",
        "testing", "test",
    },
}

# 构建反向查找表: top_level_package → layer (加速匹配)
_FRAMEWORK_LOOKUP = {}
for _layer, _packages in FRAMEWORK_SIGNATURES.items():
    for _pkg in _packages:
        _FRAMEWORK_LOOKUP[_pkg] = _layer
        # 也注册顶层包名 (如 "django.db" → 同时注册 "django")
        top = _pkg.split(".")[0]
        if top not in _FRAMEWORK_LOOKUP:
            _FRAMEWORK_LOOKUP[top] = _layer


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
    "C_CPP_NATIVE": {
        "description": "C/C++ 原生工程 (CMake/Makefile 构建, Socket/系统编程, etc.)",
        "layers": {
            "entry": {
                "dir_keywords": {"src", "app", "main", "bin", "cmd"},
                "name_patterns": r"(?:^|_)(?:main|app|entry|start|init)"
                                 r"(?:impl|base|abstract)?(?:$|_)",
            },
            "network": {
                "dir_keywords": {"net", "network", "socket", "tcp", "udp", "http", "server", "client", "connection", "io", "epoll", "select"},
                "name_patterns": r"(?:^|_)(?:server|client|socket|connection|listener"
                                 r"|acceptor|connector|channel|session|epoll|poll"
                                 r"|tcp|udp|http|request|response|handler)"
                                 r"(?:impl|base|abstract)?(?:$|_)",
            },
            "core": {
                "dir_keywords": {"core", "engine", "logic", "processor", "service", "manager", "dispatcher", "event", "loop", "reactor"},
                "name_patterns": r"(?:^|_)(?:engine|processor|service|manager|dispatcher"
                                 r"|handler|worker|scheduler|reactor|loop|event"
                                 r"|task|job|timer|clock|thread|pool)"
                                 r"(?:impl|base|abstract)?(?:$|_)",
            },
            "data": {
                "dir_keywords": {"data", "model", "entity", "proto", "message", "buffer", "packet", "codec", "serialize", "db", "store"},
                "name_patterns": r"(?:^|_)(?:model|entity|message|packet|buffer"
                                 r"|frame|proto|codec|serializer|parser|db"
                                 r"|store|repository|dao|record|payload)"
                                 r"(?:impl|base|abstract)?(?:$|_)",
            },
            "infrastructure": {
                "dir_keywords": {"util", "helper", "common", "base", "config", "constant", "include", "lib", "third_party", "vendor", "external", "debug", "log", "test"},
                "name_patterns": r"(?:^|_)(?:util|helper|common|base|config|constant"
                                 r"|logger|log|error|exception|singleton|factory"
                                 r"|builder|adapter|wrapper|lock|mutex|atomic)"
                                 r"(?:impl|base|abstract)?(?:$|_)",
            },
        },
        "layer_names": {
            "entry": "入口层",
            "network": "网络通信层",
            "core": "核心逻辑层",
            "data": "数据/协议层",
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
    """项目类型嗅探，优先级: 特定构建文件 > 代码文件后缀比例 > 文件夹名称"""
    root = Path(root_dir)

    # ── 第一优先级: 特定构建文件 / 包管理文件 ──
    # 这些标记文件能唯一确定项目类型，优先级最高

    # Java/Spring
    if (root / "pom.xml").is_file() or (root / "build.gradle").is_file() or (root / "build.gradle.kts").is_file():
        sniff_project_type._last_detected_framework = "java"
        return "BACKEND_MVC"

    # C/C++ 原生: CMakeLists.txt / Makefile 是强信号
    if (root / "CMakeLists.txt").is_file() or (root / "Makefile").is_file():
        sniff_project_type._last_detected_framework = "cpp"
        return "C_CPP_NATIVE"

    # Go
    if (root / "go.mod").is_file():
        sniff_project_type._last_detected_framework = "go"
        return "BACKEND_MVC"

    # Rust
    if (root / "Cargo.toml").is_file():
        sniff_project_type._last_detected_framework = "rust"
        return "BACKEND_MVC"

    # .NET
    for f in root.iterdir():
        if f.suffix == ".sln":
            sniff_project_type._last_detected_framework = "dotnet"
            return "BACKEND_MVC"

    # Node.js / 前端框架
    frontend_marker_files = {"package.json", "tsconfig.json", "vite.config.ts", "vite.config.js",
                              "next.config.js", "next.config.ts", "nuxt.config.ts",
                              "angular.json", "svelte.config.js"}
    for marker in frontend_marker_files:
        if (root / marker).is_file():
            sniff_project_type._last_detected_framework = "node"
            return "FRONTEND"

    # Python
    python_markers = {"pyproject.toml", "setup.py", "requirements.txt", "Pipfile", "manage.py", "django_settings.py"}
    for marker in python_markers:
        if (root / marker).is_file():
            sniff_project_type._last_detected_framework = "python"
            return "BACKEND_MVC"

    # ── 第二优先级: 代码文件后缀比例 ──
    # 构建文件缺失时，通过扫描源文件后缀推断项目类型

    cpp_exts = {".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hxx", ".hh"}
    backend_exts = {".java", ".kt", ".go", ".rs", ".py", ".rb", ".php", ".cs", ".swift"}
    frontend_exts = {".vue", ".jsx", ".tsx", ".svelte"}

    cpp_file_count = 0
    backend_file_count = 0
    frontend_file_count = 0

    try:
        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext in cpp_exts:
                    cpp_file_count += 1
                elif ext in backend_exts:
                    backend_file_count += 1
                elif ext in frontend_exts:
                    frontend_file_count += 1
                if cpp_file_count + backend_file_count + frontend_file_count > 500:
                    break
            if cpp_file_count + backend_file_count + frontend_file_count > 500:
                break
    except Exception:
        pass

    total_code_files = cpp_file_count + backend_file_count + frontend_file_count

    # C/C++ 文件占主导 → C_CPP_NATIVE
    if total_code_files > 0 and cpp_file_count > backend_file_count and cpp_file_count > frontend_file_count:
        sniff_project_type._last_detected_framework = "cpp"
        return "C_CPP_NATIVE"

    # 前端文件占主导 → FRONTEND
    if frontend_file_count > cpp_file_count and frontend_file_count > backend_file_count:
        sniff_project_type._last_detected_framework = "node"
        return "FRONTEND"

    # 后端文件占主导 → BACKEND_MVC
    if backend_file_count > 0:
        sniff_project_type._last_detected_framework = "python"
        return "BACKEND_MVC"

    # ── 第三优先级: 兜底默认 ──
    sniff_project_type._last_detected_framework = "auto"
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
                 name_rules: list = None,
                 imports_list: list = None) -> str:
    if dir_keywords is None or name_rules is None:
        dir_keywords, name_rules = _compile_preset_rules(preset_name)

    # ── 第一优先级: 框架探针嗅探 (Framework-Aware Probe) ──
    if imports_list:
        for imp_source in imports_list:
            if not imp_source:
                continue
            # 精确匹配: "django.db" → data
            if imp_source in _FRAMEWORK_LOOKUP:
                return _FRAMEWORK_LOOKUP[imp_source]
            # 逐级向上匹配: "django.db.models" → "django.db" → "django"
            parts = imp_source.split(".")
            for i in range(len(parts), 0, -1):
                prefix = ".".join(parts[:i])
                if prefix in _FRAMEWORK_LOOKUP:
                    return _FRAMEWORK_LOOKUP[prefix]

    # ── 第二优先级: 目录关键词 + 命名约定 fallback ──
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

    # ── 兜底: unknown ──
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

        # ── SQLite 本地数据库引擎 ──
        self._cache_dir = os.path.join(self.root_dir, ".eruitah_cache")
        os.makedirs(self._cache_dir, exist_ok=True)
        self._db_path = os.path.join(self._cache_dir, "codegraph.db")
        self._conn = self._init_db()
        self._cache_hits = 0
        self._cache_misses = 0

        # ── 语义向量缓存 ──
        self._node_embeddings = {}  # { node_id: [float, ...] }
        self._vector_engine = None

        if preset is None:
            preset = sniff_project_type(self.root_dir)
        self.preset = preset
        self._dir_keywords, self._name_rules = _compile_preset_rules(preset)
        logger.info(f"项目类型嗅探: {preset} — {LAYER_PRESETS[preset]['description']}")

    def _init_db(self):
        """初始化 SQLite 数据库，创建表结构"""
        import sqlite3
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row  # 支持按列名访问
        conn.execute("PRAGMA journal_mode=WAL")  # WAL 模式，提升并发性能
        conn.execute("PRAGMA synchronous=NORMAL")
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    path TEXT PRIMARY KEY,
                    hash TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    symbols TEXT,
                    ai_summary TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS nodes (
                    id TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    name TEXT,
                    layer TEXT,
                    symbols TEXT,
                    ai_summary TEXT,
                    embedding TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS edges (
                    source TEXT NOT NULL,
                    target TEXT NOT NULL,
                    type TEXT NOT NULL,
                    detail TEXT DEFAULT '',
                    PRIMARY KEY (source, target, type)
                )
            """)
            # 平滑升级: 为旧表增加 detail 字段
            try:
                conn.execute("ALTER TABLE edges ADD COLUMN detail TEXT DEFAULT ''")
            except Exception:
                pass  # 字段已存在
            conn.execute("CREATE INDEX IF NOT EXISTS idx_nodes_file_path ON nodes(file_path)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_nodes_embedding ON nodes(embedding)")

            # ── FTS5 全文索引 ──
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
                    node_id UNINDEXED,
                    name,
                    ai_summary,
                    symbols
                )
            """)
            # 插入同步触发器
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS nodes_ai AFTER INSERT ON nodes BEGIN
                    INSERT INTO nodes_fts(rowid, node_id, name, ai_summary, symbols)
                    VALUES (new.rowid, new.id, new.name, new.ai_summary, new.symbols);
                END
            """)
            # 删除同步触发器
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS nodes_ad AFTER DELETE ON nodes BEGIN
                    DELETE FROM nodes_fts WHERE rowid = old.rowid;
                END
            """)
            # 更新同步触发器
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS nodes_au AFTER UPDATE ON nodes BEGIN
                    DELETE FROM nodes_fts WHERE rowid = old.rowid;
                    INSERT INTO nodes_fts(rowid, node_id, name, ai_summary, symbols)
                    VALUES (new.rowid, new.id, new.name, new.ai_summary, new.symbols);
                END
            """)
            # 将现有数据灌入 FTS5 索引（仅首次创建时需要）
            try:
                existing_count = conn.execute("SELECT count(*) FROM nodes_fts").fetchone()[0]
                nodes_count = conn.execute("SELECT count(*) FROM nodes").fetchone()[0]
                if existing_count == 0 and nodes_count > 0:
                    conn.execute("""
                        INSERT INTO nodes_fts(rowid, node_id, name, ai_summary, symbols)
                        SELECT rowid, id, name, ai_summary, symbols FROM nodes
                    """)
                    logger.info(f"FTS5 索引初始化: 已灌入 {nodes_count} 条记录")
            except Exception as e:
                logger.debug(f"FTS5 现有数据灌入跳过: {e}")
        logger.info(f"SQLite 数据库初始化完成: {self._db_path}")
        return conn

    def _db_get_file_hash(self, file_path: str) -> str | None:
        """查询文件缓存哈希，命中返回哈希值，否则返回 None"""
        row = self._conn.execute("SELECT hash FROM files WHERE path = ?", (file_path,)).fetchone()
        return row["hash"] if row else None

    def _db_get_cached_file_data(self, file_path: str) -> dict | None:
        """获取文件的完整缓存数据 (symbols, calls, imports)"""
        row = self._conn.execute(
            "SELECT hash, symbols, ai_summary FROM files WHERE path = ?",
            (file_path,)
        ).fetchone()
        if not row:
            return None
        result = {"hash": row["hash"]}
        if row["symbols"]:
            try:
                result["symbols"] = json.loads(row["symbols"])
            except (json.JSONDecodeError, TypeError):
                result["symbols"] = []
        else:
            result["symbols"] = []
        result["ai_summary"] = row["ai_summary"] or ""
        return result

    # 代码文件后缀集合，用于缓存防毒化判断
    _CODE_EXTENSIONS = set(SUPPORTED_EXTENSIONS.keys())

    def _db_upsert_file(self, file_path: str, file_hash: str, symbols: list = None,
                        calls: list = None, imports: list = None, ai_summary: str = ""):
        """写入/更新文件记录（含缓存防毒化：代码文件 0 符号不缓存）"""
        from datetime import datetime

        # ── 缓存防毒化: 代码文件提取到 0 个符号时，不写入缓存 ──
        # 这样下次扫描时缓存未命中，会强制重新 AST 解析
        ext = os.path.splitext(file_path)[1].lower()
        if ext in self._CODE_EXTENSIONS and not symbols:
            logger.debug(f"缓存防毒化: 跳过写入空符号缓存 {file_path}")
            return

        symbols_json = json.dumps(symbols or [], ensure_ascii=False)
        # 同时存储 calls 和 imports 在 symbols 字段中（兼容旧逻辑）
        combined = {
            "symbols": symbols or [],
            "calls": calls or [],
            "imports": imports or [],
        }
        combined_json = json.dumps(combined, ensure_ascii=False)
        with self._conn:
            self._conn.execute(
                """INSERT OR REPLACE INTO files (path, hash, updated_at, symbols, ai_summary)
                   VALUES (?, ?, ?, ?, ?)""",
                (file_path, file_hash, datetime.utcnow().isoformat(), combined_json, ai_summary)
            )

    def _db_upsert_nodes(self, nodes: list):
        """批量写入/更新节点记录"""
        if not nodes:
            return
        with self._conn:
            for n in nodes:
                nid = n.get("id", "")
                fp = n.get("file_path", "")
                name = n.get("name", "")
                layer = n.get("layer", "")
                symbols_json = json.dumps(n.get("data", {}).get("symbols", []), ensure_ascii=False)
                ai_summary = ""
                embedding_json = ""
                # 检查是否有 embedding
                if nid in self._node_embeddings:
                    embedding_json = json.dumps(self._node_embeddings[nid])
                self._conn.execute(
                    """INSERT OR REPLACE INTO nodes (id, file_path, name, layer, symbols, ai_summary, embedding)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (nid, fp, name, layer, symbols_json, ai_summary, embedding_json)
                )

    def _db_upsert_edges(self, edges: list):
        """批量写入/更新边记录"""
        if not edges:
            return
        with self._conn:
            # 先清空旧边
            self._conn.execute("DELETE FROM edges")
            for e in edges:
                self._conn.execute(
                    """INSERT OR REPLACE INTO edges (source, target, type, detail)
                       VALUES (?, ?, ?, ?)""",
                    (e.get("source", ""), e.get("target", ""), e.get("type", ""), e.get("detail", ""))
                )

    def _db_update_embeddings(self):
        """将内存中的 embeddings 更新到 SQLite"""
        if not self._node_embeddings:
            return
        with self._conn:
            for nid, emb in self._node_embeddings.items():
                emb_json = json.dumps(emb) if isinstance(emb, list) else ""
                self._conn.execute(
                    "UPDATE nodes SET embedding = ? WHERE id = ?",
                    (emb_json, nid)
                )

    def _db_close(self):
        """关闭数据库连接"""
        if self._conn:
            self._conn.close()
            self._conn = None

    def _ensure_db_conn(self):
        """确保数据库连接存活（断线重连）"""
        if self._conn is None:
            self._conn = self._init_db()

    def update_single_file(self, filepath: str):
        """
        实时局部热更新：仅针对单个文件执行增量更新
        适用于 watchdog 监听到文件变更后的即时响应
        """
        self._ensure_db_conn()

        ext = os.path.splitext(filepath)[1]
        language = SUPPORTED_EXTENSIONS.get(ext, "")
        if not language:
            return

        # ── Step 1: 计算最新 Hash ──
        current_hash = compute_file_hash(filepath)
        if not current_hash:
            logger.debug(f"文件读取失败，跳过: {filepath}")
            return

        # ── Step 2: 查 SQLite，Hash 没变则直接 return ──
        cached_hash = self._db_get_file_hash(filepath)
        if cached_hash == current_hash:
            return

        # ── Step 3: 使用 Tree-Sitter UniversalExtractor 提取多语言符号 ──
        logger.info(f"[⚡ 实时脉冲] 检测到变更: {filepath}")

        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                code_content = f.read()
        except Exception as e:
            logger.warning(f"文件读取失败 {filepath}: {e}")
            return

        try:
            extractor = UniversalExtractor()
            extract_result = extractor.extract_symbols(filepath, code_content)
            raw_symbols = extract_result.get("definitions", [])
            raw_calls = extract_result.get("calls", [])
            raw_routes = extract_result.get("routes", [])
            imports_list = _extract_imports(filepath, code_content)

            # 转换为 definitions 格式供图谱构建使用
            definitions = []
            for sym in raw_symbols:
                defn = {
                    "name": sym["name"],
                    "kind": sym["kind"],
                    "line": sym["line"],
                    "end_line": sym["line"],
                    "parent_name": sym.get("parent", ""),
                }
                definitions.append(defn)

            # 转换为 calls 格式
            calls = []
            for call in raw_calls:
                calls.append({
                    "caller": call.get("caller", ""),
                    "callee": call["name"],
                    "line": call["line"],
                })

            result = {
                "definitions": definitions,
                "calls": calls,
                "imports": imports_list,
                "_raw_symbols": raw_symbols,
                "_raw_calls": raw_calls,
                "_raw_routes": raw_routes,
            }
        except Exception as e:
            logger.debug(f"Tree-Sitter 解析失败 {filepath}: {e}")
            result = {"definitions": [], "calls": [], "imports": [], "_raw_symbols": [], "_raw_calls": [], "_raw_routes": []}

        # ── Step 4: 更新内存中的 _file_analyses ──
        self._file_analyses[filepath] = result

        # ── Step 5: 更新符号表（仅该文件的符号）──
        rel = self._rel(filepath)
        module_path = self._file_to_module(rel)
        self._file_index[module_path] = filepath

        # 先清理该文件的旧符号
        for sym_name in list(self._symbol_table.keys()):
            self._symbol_table[sym_name] = [
                s for s in self._symbol_table[sym_name] if s["file"] != filepath
            ]
            if not self._symbol_table[sym_name]:
                del self._symbol_table[sym_name]

        # 重新注册该文件的符号
        for defn in result.get("definitions", []):
            name = defn.get("name", "")
            kind = defn.get("kind", "")
            parent_name = defn.get("parent_name", "")
            if name and kind in ("function", "method", "class"):
                self._symbol_table[name].append({
                    "file": filepath,
                    "kind": kind,
                    "line": defn.get("line", 0),
                    "parent_name": parent_name,
                })

        # ── Step 6: 重新解析该文件的导入 ──
        self._import_map[filepath] = []
        for imp in result.get("imports", []):
            source = imp.get("source", "")
            if not source:
                continue
            resolved = self._file_index.get(source) or self._file_index.get(source + ".__init__")
            self._import_map[filepath].append({
                "source": source,
                "specifiers": imp.get("specifiers", []),
                "resolved_file": resolved,
            })

        # ── Step 7: 重建该文件的图谱节点 ──
        # 先删除该文件的旧节点
        old_node_ids = set()
        for n in self.nodes:
            if n.get("file_path") == filepath:
                old_node_ids.add(n["id"])
        self.nodes = [n for n in self.nodes if n.get("file_path") != filepath]
        self.edges = [e for e in self.edges if e["source"] not in old_node_ids and e["target"] not in old_node_ids]
        self._node_ids -= old_node_ids

        # 重新添加该文件的节点
        raw_symbols = result.get("_raw_symbols", [])
        raw_calls = result.get("_raw_calls", [])
        self._register_file_node(filepath, symbols=raw_symbols, calls=raw_calls)
        for defn in result.get("definitions", []):
            name = defn.get("name", "")
            kind = defn.get("kind", "")
            parent_name = defn.get("parent_name", "")
            if not name:
                continue
            if kind in ("class", "struct", "enum", "record"):
                node_id = self._make_def_id(filepath, name)
                self._add_node(node_id, "Class", name, filepath)
            elif kind == "interface":
                node_id = self._make_def_id(filepath, name)
                self._add_node(node_id, "Interface", name, filepath)
            elif kind in ("method", "constructor", "destructor") and parent_name:
                node_id = self._make_def_id(filepath, name, parent_name, kind)
                self._add_node(node_id, "Method", name, filepath)
            elif kind == "function":
                node_id = self._make_def_id(filepath, name)
                self._add_node(node_id, "Function", name, filepath)

        # 重建该文件的 CONTAINS 和 CALLS 边
        self._build_file_contains_edges(filepath)
        self._build_file_calls_edges(filepath)

        # ── Step 8: 重新执行社区发现 ──
        try:
            self.nodes = detect_domains(self.nodes, self.edges)
            for n in self.nodes:
                if 'cluster_id' in n:
                    if 'data' not in n:
                        n['data'] = {}
                    n['data']['cluster_id'] = n['cluster_id']
                    if 'cluster_name' in n:
                        n['data']['cluster_name'] = n['cluster_name']
        except Exception as e:
            logger.debug(f"社区发现失败: {e}")

        # ── Step 9: 生成该文件新节点的 Embedding ──
        self._init_vector_engine()
        if self._vector_engine is not None:
            texts = []
            node_ids = []
            for node in self.nodes:
                if node.get("file_path") != filepath:
                    continue
                nid = node.get("id", "")
                if nid in self._node_embeddings:
                    continue
                label = node.get("name", "")
                ntype = node.get("type", "")
                layer = node.get("layer", "")
                parts = [f"{ntype} {label}"]
                if layer:
                    parts.append(f"layer: {layer}")
                parts.append(f"file: {self._rel(filepath)}")
                text = " ".join(parts)
                if len(text.strip()) > 3:
                    texts.append(text)
                    node_ids.append(nid)
            if texts:
                try:
                    embeddings = self._vector_engine._encode(texts)
                    for i, nid in enumerate(node_ids):
                        if i < len(embeddings):
                            self._node_embeddings[nid] = embeddings[i].tolist()
                    self._db_update_embeddings()
                except Exception as e:
                    logger.debug(f"Embedding 生成失败: {e}")

        # ── Step 10: 写入 SQLite ──
        self._db_upsert_file(
            file_path=filepath,
            file_hash=current_hash,
            symbols=result.get("definitions", []),
            calls=result.get("calls", []),
            imports=result.get("imports", []),
        )
        self._db_upsert_nodes(self.nodes)
        self._db_upsert_edges(self.edges)

        # ── Step 11: 写入 project_structure.json ──
        output_path = os.path.join(self.root_dir, "project_structure.json")
        try:
            final_graph = self.to_dict()
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(final_graph, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"写入 JSON 失败: {e}")

        logger.info(f"[⚡ 实时脉冲] 增量更新完毕: {filepath}")

    def _register_file_node(self, filepath: str, symbols: list = None, calls: list = None):
        """注册单个文件节点，symbols 为高清符号表，calls 为调用表（写入 nodes 表）"""
        file_id = self._make_file_id(filepath)
        file_imports = self._file_analyses.get(filepath, {}).get("imports", [])
        imports_list = [imp.get("source", "") for imp in file_imports if imp.get("source")]
        layer = detect_layer(file_id, "File", os.path.basename(filepath), filepath,
                             dir_keywords=self._dir_keywords,
                             name_rules=self._name_rules,
                             imports_list=imports_list)
        extra = {}
        if symbols:
            extra["data"] = {"symbols": symbols}
        if calls:
            if "data" not in extra:
                extra["data"] = {}
            extra["data"]["calls"] = calls
        self._add_node(file_id, "File", os.path.basename(filepath), filepath, layer=layer, **extra)

    def _build_file_contains_edges(self, filepath: str):
        """构建单个文件的 CONTAINS 边"""
        file_id = self._make_file_id(filepath)
        analysis = self._file_analyses.get(filepath, {})
        for defn in analysis.get("definitions", []):
            name = defn.get("name", "")
            kind = defn.get("kind", "")
            parent_name = defn.get("parent_name", "")
            if not name:
                continue
            if kind == "class":
                node_id = self._make_def_id(filepath, name)
            elif kind == "method" and parent_name:
                node_id = self._make_def_id(filepath, name, parent_name, kind)
            elif kind == "function":
                node_id = self._make_def_id(filepath, name)
            else:
                continue
            if node_id in self._node_ids:
                self.edges.append({
                    "source": file_id,
                    "target": node_id,
                    "type": "CONTAINS",
                })

    def _build_file_calls_edges(self, filepath: str):
        """构建单个文件的 CALLS / IMPORTS 边"""
        analysis = self._file_analyses.get(filepath, {})
        file_id = self._make_file_id(filepath)

        # IMPORTS 边
        for imp in analysis.get("imports", []):
            source = imp.get("source", "")
            if not source:
                continue
            resolved = self._file_index.get(source) or self._file_index.get(source + ".__init__")
            if resolved:
                target_file_id = self._make_file_id(resolved)
                if target_file_id in self._node_ids and target_file_id != file_id:
                    self.edges.append({
                        "source": file_id,
                        "target": target_file_id,
                        "type": "IMPORTS",
                    })

        # CALLS 边
        for defn in analysis.get("definitions", []):
            name = defn.get("name", "")
            kind = defn.get("kind", "")
            parent_name = defn.get("parent_name", "")
            if kind == "class":
                caller_id = self._make_def_id(filepath, name)
            elif kind == "method" and parent_name:
                caller_id = self._make_def_id(filepath, name, parent_name, kind)
            elif kind == "function":
                caller_id = self._make_def_id(filepath, name)
            else:
                continue

            for call in defn.get("calls", []):
                call_name = call.get("name", "") if isinstance(call, dict) else str(call)
                if not call_name:
                    continue
                candidates = self._symbol_table.get(call_name, [])
                resolved = False
                for cand in candidates:
                    if cand["file"] == filepath and cand.get("parent_name") == parent_name:
                        continue
                    if cand["kind"] == "class":
                        target_id = self._make_def_id(cand["file"], call_name)
                    elif cand["kind"] == "method" and cand.get("parent_name"):
                        target_id = self._make_def_id(cand["file"], call_name, cand["parent_name"], "method")
                    else:
                        target_id = self._make_def_id(cand["file"], call_name)
                    if target_id in self._node_ids:
                        self.edges.append({
                            "source": caller_id,
                            "target": target_id,
                            "type": "CALLS",
                        })
                        resolved = True
                        break
                if not resolved:
                    self._dropped_calls += 1

    def _init_vector_engine(self):
        """懒加载向量引擎（复用 semantic_search_tool._VectorEngine）"""
        if self._vector_engine is not None:
            return
        try:
            from semantic_search_tool import _VectorEngine
            self._vector_engine = _VectorEngine()
            if not self._vector_engine.available:
                logger.info("向量引擎不可用 (API/Local 均未配置)，跳过 Embedding 生成")
                self._vector_engine = None
        except ImportError:
            logger.info("semantic_search_tool 未找到，跳过 Embedding 生成")
            self._vector_engine = None

    def generate_embeddings(self):
        """为所有节点生成语义向量并持久化到 SQLite"""
        self._init_vector_engine()
        if self._vector_engine is None:
            return

        # 从 SQLite 加载已有 embeddings
        rows = self._conn.execute(
            "SELECT id, embedding FROM nodes WHERE embedding IS NOT NULL AND embedding != ''"
        ).fetchall()
        for row in rows:
            try:
                emb = json.loads(row["embedding"])
                if isinstance(emb, list) and len(emb) > 0:
                    self._node_embeddings[row["id"]] = emb
            except (json.JSONDecodeError, TypeError):
                pass
        logger.info(f"SQLite Embeddings 缓存加载: {len(self._node_embeddings)} 条记录")

        # 构建待编码文本：为每个节点拼接摘要文本
        texts = []
        node_ids = []
        for node in self.nodes:
            nid = node.get("id", "")
            # 已有缓存且指纹未变，跳过
            if nid in self._node_embeddings:
                continue
            label = node.get("label", "")
            ntype = node.get("type", "")
            layer = node.get("layer", "")
            fp = node.get("file_path", "")
            # 拼接节点语义描述
            parts = [f"{ntype} {label}"]
            if layer:
                parts.append(f"layer: {layer}")
            if fp:
                parts.append(f"file: {fp}")
            # 从 SQLite 中取 ai_summary
            cached_data = self._db_get_cached_file_data(fp)
            ai_summary = cached_data.get("ai_summary", "") if cached_data else ""
            if ai_summary:
                parts.append(ai_summary[:500])
            # 从符号表补充
            data = node.get("data", {})
            symbols = data.get("symbols", [])
            if symbols:
                sym_names = [s.get("name", "") for s in symbols if s.get("name")]
                parts.append("symbols: " + ", ".join(sym_names[:20]))
            text = " ".join(parts)
            if len(text.strip()) > 3:
                texts.append(text)
                node_ids.append(nid)

        if not texts:
            logger.info("所有节点 Embedding 已缓存，无需重新生成")
            return

        logger.info(f"🔄 生成 {len(texts)} 个节点的语义向量 (mode={self._vector_engine.mode})...")
        try:
            embeddings = self._vector_engine._encode(texts)
            for i, nid in enumerate(node_ids):
                if i < len(embeddings):
                    self._node_embeddings[nid] = embeddings[i].tolist()
            logger.info(f"✅ Embedding 生成完成: {len(node_ids)} 个新节点")
            # 实时写入 SQLite
            self._db_update_embeddings()
        except Exception as e:
            logger.warning(f"Embedding 生成失败: {e}")

    def _rel(self, fp: str) -> str:
        return os.path.relpath(fp, self.root_dir)

    def _make_file_id(self, fp: str) -> str:
        return self._rel(fp)

    def _make_def_id(self, fp: str, name: str, parent_name: str = "", kind: str = "") -> str:
        rel = self._rel(fp)
        if parent_name and kind == "method":
            return f"{rel}::{parent_name}.{name}"
        return f"{rel}::{name}"

    # 允许进入图谱的节点类型（File 是 CONTAINS/IMPORTS 边的锚点，必须保留）
    VALID_NODE_TYPES = {"File", "Class", "Interface", "Function", "Method", "Route"}

    def _add_node(self, node_id: str, node_type: str, name: str, file_path: str, **extra):
        # 严格过滤：只允许代码实体节点，禁止目录/文件夹节点
        if node_type not in self.VALID_NODE_TYPES:
            logger.debug(f"跳过非代码节点: type={node_type}, name={name}, id={node_id}")
            return
        if node_id in self._node_ids:
            return
        self._node_ids.add(node_id)
        node = {"id": node_id, "type": node_type, "name": name, "file_path": file_path}

        # 提取该文件的导入源列表，用于框架探针嗅探
        file_imports = self._file_analyses.get(file_path, {}).get("imports", [])
        imports_list = [imp.get("source", "") for imp in file_imports if imp.get("source")]

        node["layer"] = detect_layer(node_id, node_type, name, file_path,
                                     dir_keywords=self._dir_keywords,
                                     name_rules=self._name_rules,
                                     imports_list=imports_list)
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
        extractor = UniversalExtractor()

        for fp in file_paths:
            ext = os.path.splitext(fp)[1]
            language = SUPPORTED_EXTENSIONS.get(ext, "")
            if not language:
                continue

            # ── 增量指纹缓存: 计算当前文件哈希 ──
            current_hash = compute_file_hash(fp)
            cached_hash = self._db_get_file_hash(fp)

            if cached_hash and cached_hash == current_hash:
                # 短路机制: 哈希匹配，直接使用 DB 缓存数据
                cached_data = self._db_get_cached_file_data(fp)
                if cached_data:
                    combined = cached_data.get("symbols", {})

                    # ── 缓存防毒化: 代码文件缓存中 0 符号视为无效 ──
                    # 避免因环境异常导致的空结果被反复命中
                    cached_definitions = []
                    if isinstance(combined, dict):
                        cached_definitions = combined.get("symbols", [])
                    else:
                        cached_definitions = cached_data.get("symbols", [])

                    if ext.lower() in self._CODE_EXTENSIONS and not cached_definitions:
                        logger.debug(f"缓存防毒化: 命中空符号缓存，强制重新解析 {fp}")
                        # 不 continue，走到下面的 AST 解析逻辑
                    else:
                        logger.info(f"[INFO] 命中 DB 缓存: 跳过解析 {fp}")
                        if isinstance(combined, dict):
                            self._file_analyses[fp] = {
                                "definitions": combined.get("symbols", []),
                                "calls": combined.get("calls", []),
                                "imports": combined.get("imports", []),
                                "_raw_symbols": combined.get("symbols", []),
                            }
                        else:
                            self._file_analyses[fp] = {
                                "definitions": cached_data.get("symbols", []),
                                "calls": [],
                                "imports": [],
                                "_raw_symbols": cached_data.get("symbols", []),
                            }
                        self._cache_hits += 1
                        continue

            # ── 缓存未命中: 使用 Tree-Sitter UniversalExtractor 提取 ──
            self._cache_misses += 1

            try:
                with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                    code_content = f.read()
            except Exception as e:
                logger.warning(f"文件读取失败 {fp}: {e}")
                continue

            try:
                extract_result = extractor.extract_symbols(fp, code_content)
                raw_symbols = extract_result.get("definitions", [])
                raw_calls = extract_result.get("calls", [])
                raw_routes = extract_result.get("routes", [])
                imports_list = _extract_imports(fp, code_content)

                # 转换为 definitions 格式供图谱构建使用
                definitions = []
                for sym in raw_symbols:
                    defn = {
                        "name": sym["name"],
                        "kind": sym["kind"],
                        "line": sym["line"],
                        "end_line": sym["line"],
                        "parent_name": sym.get("parent", ""),
                    }
                    definitions.append(defn)

                # 转换为 calls 格式
                calls = []
                for call in raw_calls:
                    calls.append({
                        "caller": call.get("caller", ""),
                        "callee": call["name"],
                        "line": call["line"],
                    })

                result = {
                    "definitions": definitions,
                    "calls": calls,
                    "imports": imports_list,
                    "_raw_symbols": raw_symbols,
                    "_raw_calls": raw_calls,
                    "_raw_routes": raw_routes,
                }
            except Exception as e:
                logger.debug(f"Tree-Sitter 解析失败 {fp}: {e}")
                result = {"definitions": [], "calls": [], "imports": [], "_raw_symbols": [], "_raw_calls": [], "_raw_routes": []}

            self._file_analyses[fp] = result

            # ── 将最新解析结果写入 SQLite ──
            self._db_upsert_file(
                file_path=fp,
                file_hash=current_hash,
                symbols=result.get("definitions", []),
                calls=result.get("calls", []),
                imports=result.get("imports", []),
            )

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
        # Java import 如 com.example.provider.controller.ProviderController
        # 需要找到对应的 .java 文件，支持多模块 Maven/Gradle 项目
        parts = source.split(".")
        rel = os.sep.join(parts) + ".java"

        # 策略1: 利用已有的 _file_analyses，直接用文件名匹配
        # 这是最可靠的方式，因为所有被解析的文件都在 _file_analyses 中
        class_name = parts[-1] if parts else ""
        if class_name:
            for fp in self._file_analyses:
                basename = os.path.basename(fp)
                if basename == class_name + ".java":
                    # 验证包路径匹配
                    package_dir = os.sep.join(parts[:-1])
                    if fp.replace(os.sep, "/").endswith(package_dir.replace(".", "/") + "/" + basename):
                        return fp
            # 第二轮：宽松匹配（仅类名一致）
            candidates = []
            for fp in self._file_analyses:
                if os.path.basename(fp) == class_name + ".java":
                    candidates.append(fp)
            if len(candidates) == 1:
                return candidates[0]
            elif len(candidates) > 1:
                # 多个同名类，选择包路径最匹配的
                package_path = "/".join(parts[:-1])
                for c in candidates:
                    if package_path in c.replace(os.sep, "/"):
                        return c
                return candidates[0]

        # 策略2: 递归搜索所有 src/main/java 目录（多模块项目）
        # 缓存 java_roots 避免每次调用都 walk 整个目录树
        if not hasattr(self, '_java_roots_cache'):
            java_roots = []
            for dirpath, dirnames, filenames in os.walk(self.root_dir):
                if dirpath.endswith(os.sep.join(["src", "main", "java"])) or \
                   dirpath.endswith("/src/main/java"):
                    java_roots.append(dirpath)
                for d in list(dirnames):
                    candidate = os.path.join(dirpath, d, "src", "main", "java")
                    if os.path.isdir(candidate) and candidate not in java_roots:
                        java_roots.append(candidate)
            if not java_roots:
                java_roots = [self.root_dir]
            self._java_roots_cache = java_roots

        for java_root in self._java_roots_cache:
            probe = os.path.join(java_root, rel)
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
        self.resolve_symbol_edges()
        self.build_route_nodes_and_edges()

    def build_route_nodes_and_edges(self):
        """
        构建路由虚拟节点和 routes_to 边。
        遍历所有文件的 routes 列表，为每个 API 路由创建虚拟节点，
        并将路由指向其 handler 函数。
        """
        for fp, analysis in self._file_analyses.items():
            routes = analysis.get("_raw_routes", [])
            if not routes:
                continue

            file_id = self._make_file_id(fp)

            for route in routes:
                method = route.get("method", "ANY")
                path = route.get("path", "")
                handler = route.get("handler", "")

                if not path:
                    continue

                # 生成路由虚拟节点 ID
                route_id = f"[Route] {method} {path}"
                route_name = f"{method} {path}"

                # 添加路由虚拟节点
                self._add_node(
                    route_id,
                    "Route",
                    route_name,
                    fp,
                    layer="api_route",
                )

                # 查找 handler 对应的节点 ID
                handler_id = None
                # 优先查找 File::handler 格式
                for node in self.nodes:
                    if node.get("name") == handler and node.get("file_path") == fp:
                        handler_id = node["id"]
                        break

                # 如果找不到精确的 handler 节点，指向文件
                if not handler_id:
                    handler_id = file_id

                # 添加 routes_to 边
                self._add_edge(route_id, handler_id, "routes_to")

    def resolve_symbol_edges(self):
        """
        全局符号解析器：遍历所有文件的 calls 列表，
        将被调用的符号名与全局 nodes 表中的 definitions 匹配，
        生成 symbol_call 类型的精细边。

        边格式:
          source: 调用方文件 ID
          target: 定义方文件 ID
          type: "symbol_call"
          detail: "bind_port, listen" (具体调用的符号名，逗号分隔)
        """
        # 1. 构建全局符号索引: symbol_name → [file_id, ...]
        symbol_index = defaultdict(list)
        for node in self.nodes:
            if node.get("type") == "File":
                syms = node.get("data", {}).get("symbols", [])
                for sym in syms:
                    name = sym.get("name", "")
                    if name:
                        symbol_index[name].append(node["id"])

        # 2. 遍历所有文件的 calls，按 (source_file, target_file) 聚合
        symbol_edges = defaultdict(set)  # (source, target) → {callee_name, ...}
        for node in self.nodes:
            if node.get("type") != "File":
                continue
            source_id = node["id"]
            calls = node.get("data", {}).get("calls", [])
            for call in calls:
                callee_name = call.get("name", "")
                if not callee_name:
                    continue
                # 简化 callee_name: 取最后一段 (obj.method → method, Server::start → start)
                simple_name = callee_name.split(".")[-1].split("::")[-1]
                # 在全局符号索引中查找定义方
                for target_id in symbol_index.get(simple_name, []):
                    if target_id != source_id:  # 排除文件内部调用
                        symbol_edges[(source_id, target_id)].add(simple_name)

        # 3. 生成 symbol_call 边
        for (source, target), callee_names in symbol_edges.items():
            detail = ", ".join(sorted(callee_names))
            self._add_edge(source, target, "symbol_call")
            # 将 detail 写入对应的边
            for edge in self.edges:
                if edge["source"] == source and edge["target"] == target and edge["type"] == "symbol_call":
                    edge["detail"] = detail
                    break

    def _register_file_nodes_and_contains(self, fp: str, analysis: dict):
        file_id = self._make_file_id(fp)
        basename = os.path.basename(fp)

        # 将高清符号表和调用表附加到 File 节点，写入 nodes 表
        raw_symbols = analysis.get("_raw_symbols", [])
        raw_calls = analysis.get("_raw_calls", [])
        file_extra = {}
        if raw_symbols:
            file_extra["data"] = {"symbols": raw_symbols}
        if raw_calls:
            if "data" not in file_extra:
                file_extra["data"] = {}
            file_extra["data"]["calls"] = raw_calls
        self._add_node(file_id, "File", basename, fp, **file_extra)

        for defn in analysis.get("definitions", []):
            name = defn.get("name", "")
            kind = defn.get("kind", "")
            parent_name = defn.get("parent_name", "")
            if not name:
                continue

            if kind in ("class", "struct", "enum", "record"):
                node_type = "Class"
                node_id = self._make_def_id(fp, name, parent_name="", kind="class")
            elif kind == "interface":
                node_type = "Interface"
                node_id = self._make_def_id(fp, name, parent_name="", kind="interface")
            elif kind in ("method", "constructor", "destructor"):
                node_type = "Method"
                node_id = self._make_def_id(fp, name, parent_name=parent_name, kind=kind)
            elif kind == "function":
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

        # ── Diff Integration: 强制禁用旧图谱缓存，避免垃圾节点回注 ──
        old_graph = None
        # if os.path.exists(output_path):
        #     try:
        #         with open(output_path, "r", encoding="utf-8") as f:
        #             old_graph = json.load(f)
        #         logger.info(f"读取到旧图谱: {len(old_graph.get('nodes', []))} 节点, {len(old_graph.get('edges', []))} 边")
        #     except Exception as e:
        #         logger.warning(f"读取旧图谱失败，跳过 Diff 计算: {e}")
        #         old_graph = None
        logger.info("旧图谱缓存已禁用，强制使用 100% 净化后的新节点")

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

        # ── 持久化到 SQLite ──
        self._db_upsert_nodes(final_graph.get("nodes", []))
        self._db_upsert_edges(final_graph.get("edges", []))

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
        if self._cache_hits > 0 or self._cache_misses > 0:
            total = self._cache_hits + self._cache_misses
            hit_rate = (self._cache_hits / total * 100) if total > 0 else 0
            logger.info(f"⚡ 指纹缓存: 命中 {self._cache_hits}/{total} ({hit_rate:.0f}%), "
                        f"跳过 {self._cache_hits} 次 AST 解析 + LLM 调用")

        # ── Phase 3: 符号表 + 导入解析 ──
        self.build_symbol_table()
        logger.info(f"符号表构建完成: {len(self._symbol_table)} 个符号")

        self.resolve_imports()
        resolved_count = sum(len(v) for v in self._import_map.values())
        logger.info(f"导入解析完成: {resolved_count} 条解析结果")

        # ── Phase 4: 构建图谱 + 社区发现 + Diff + 写入 ──
        self.build_graph()

        # 社区发现: 将紧密连接的节点聚类为业务领域
        try:
            self.nodes = detect_domains(self.nodes, self.edges)
            # 强制双写：将 cluster_id 复制到 node['data'] 中，确保前端框架绝对能读到
            for n in self.nodes:
                if 'cluster_id' in n:
                    if 'data' not in n:
                        n['data'] = {}
                    n['data']['cluster_id'] = n['cluster_id']
                    if 'cluster_name' in n:
                        n['data']['cluster_name'] = n['cluster_name']
            logger.info(f"社区发现完成: {len(set(n.get('cluster_id', '') for n in self.nodes))} 个领域")
        except Exception as e:
            logger.error(f"聚类算法调用失败: {e}")

        # ── Phase 5: 语义向量生成 ──
        self.generate_embeddings()

        self.write_json(output_path, modified_file_paths=modified_file_paths)
        self._db_close()
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
