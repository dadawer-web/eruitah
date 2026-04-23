"""
Eruitah 智能编程沙盒 - Tree-sitter 代码索引引擎

核心思想（来自 Claude Code 的 treeSitterAnalysis.ts + codeIndexing.ts）:
┌─────────────────────────────────────────────────────────────────────┐
│  grep 搜索: 把代码当"字符串" → 同名函数重载、宏定义 → 垃圾结果      │
│                                                                     │
│  Tree-sitter 搜索: 把代码当"树状逻辑结构" → 精准定位语义符号        │
│                                                                     │
│  示例:                                                              │
│    grep "class Session" → 匹配注释、字符串、模板参数... 50+ 结果     │
│    Tree-sitter "class Session" → 只匹配类声明: 3 个精确结果          │
│                                                                     │
│  索引结构 (SQLite):                                                 │
│    ┌──────────────────────────────────────────────────────┐         │
│    │  symbols 表:                                         │         │
│    │    id | file_path | name | kind | signature | line   │         │
│    │    1  | main.cpp  | Session | class | class Session  | 42      │         │
│    │    2  | main.cpp  | connect | method | void connect()| 58      │         │
│    │    3  | utils.py  | helper  | function| def helper() | 15      │         │
│    └──────────────────────────────────────────────────────┘         │
│                                                                     │
│  后台线程: 项目启动时扫描所有文件，建立索引                          │
│  增量更新: 文件修改时只重新解析该文件                                │
└─────────────────────────────────────────────────────────────────────┘

参考源码:
    claude-code-rev/src/utils/bash/treeSitterAnalysis.ts
    claude-code-rev/src/utils/codeIndexing.ts
"""

import os
import json
import sqlite3
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get(
    "ERUITAH_CODE_INDEX_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".code_index.db"),
)

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

KIND_CLASS = "class"
KIND_INTERFACE = "interface"
KIND_STRUCT = "struct"
KIND_FUNCTION = "function"
KIND_METHOD = "method"
KIND_VARIABLE = "variable"
KIND_CONSTANT = "constant"
KIND_IMPORT = "import"
KIND_ENUM = "enum"
KIND_TRAIT = "trait"
KIND_NAMESPACE = "namespace"
KIND_PROPERTY = "property"
KIND_FIELD = "field"


@dataclass
class Symbol:
    file_path: str
    name: str
    kind: str
    signature: str
    line: int
    end_line: int
    language: str
    parent_name: str = ""
    docstring: str = ""


@dataclass
class IndexStats:
    total_files: int = 0
    total_symbols: int = 0
    languages: dict = field(default_factory=dict)
    last_index_time: float = 0.0
    index_duration: float = 0.0


class CodeIndexDB:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS symbols (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                name TEXT NOT NULL,
                kind TEXT NOT NULL,
                signature TEXT,
                line INTEGER NOT NULL,
                end_line INTEGER,
                language TEXT,
                parent_name TEXT DEFAULT '',
                docstring TEXT DEFAULT '',
                updated_at REAL
            );

            CREATE TABLE IF NOT EXISTS file_index (
                file_path TEXT PRIMARY KEY,
                language TEXT,
                mtime REAL,
                symbol_count INTEGER DEFAULT 0,
                indexed_at REAL
            );

            CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
            CREATE INDEX IF NOT EXISTS idx_symbols_kind ON symbols(kind);
            CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_path);
            CREATE INDEX IF NOT EXISTS idx_symbols_name_kind ON symbols(name, kind);
        """)
        conn.commit()

    def upsert_symbols(self, file_path: str, symbols: list[Symbol], language: str, mtime: float):
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM symbols WHERE file_path = ?", (file_path,))

            for sym in symbols:
                conn.execute(
                    """INSERT INTO symbols (file_path, name, kind, signature, line, end_line, language, parent_name, docstring, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (sym.file_path, sym.name, sym.kind, sym.signature, sym.line, sym.end_line,
                     sym.language, sym.parent_name, sym.docstring, time.time()),
                )

            conn.execute(
                """INSERT OR REPLACE INTO file_index (file_path, language, mtime, symbol_count, indexed_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (file_path, language, mtime, len(symbols), time.time()),
            )

            conn.commit()
        except Exception as e:
            logger.error(f"写入索引失败 {file_path}: {e}")
            conn.rollback()

    def remove_file(self, file_path: str):
        conn = self._get_conn()
        conn.execute("DELETE FROM symbols WHERE file_path = ?", (file_path,))
        conn.execute("DELETE FROM file_index WHERE file_path = ?", (file_path,))
        conn.commit()

    def search_symbols(
        self,
        name: Optional[str] = None,
        kind: Optional[str] = None,
        file_path: Optional[str] = None,
        parent_name: Optional[str] = None,
        language: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        conn = self._get_conn()

        conditions = []
        params = []

        if name:
            conditions.append("name LIKE ?")
            params.append(f"%{name}%")
        if kind:
            conditions.append("kind = ?")
            params.append(kind)
        if file_path:
            conditions.append("file_path LIKE ?")
            params.append(f"%{file_path}%")
        if parent_name:
            conditions.append("parent_name LIKE ?")
            params.append(f"%{parent_name}%")
        if language:
            conditions.append("language = ?")
            params.append(language)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        query = f"SELECT * FROM symbols WHERE {where_clause} ORDER BY file_path, line LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_file_symbols(self, file_path: str) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM symbols WHERE file_path = ? ORDER BY line",
            (file_path,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_stats(self) -> IndexStats:
        conn = self._get_conn()
        total_files = conn.execute("SELECT COUNT(*) FROM file_index").fetchone()[0]
        total_symbols = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]

        lang_rows = conn.execute(
            "SELECT language, COUNT(*) as cnt FROM symbols GROUP BY language"
        ).fetchall()
        languages = {row["language"]: row["cnt"] for row in lang_rows}

        last_time = conn.execute(
            "SELECT MAX(indexed_at) FROM file_index"
        ).fetchone()[0] or 0.0

        return IndexStats(
            total_files=total_files,
            total_symbols=total_symbols,
            languages=languages,
            last_index_time=last_time,
        )

    def needs_reindex(self, file_path: str, mtime: float) -> bool:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT mtime FROM file_index WHERE file_path = ?",
            (file_path,),
        ).fetchone()
        if row is None:
            return True
        return row["mtime"] < mtime

    def close(self):
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None


def parse_file_with_treesitter(file_path: str, language: str) -> list[Symbol]:
    try:
        import tree_sitter
    except ImportError:
        return _parse_file_fallback(file_path, language)

    try:
        lang_module = _get_tree_sitter_language(language)
        if lang_module is None:
            return _parse_file_fallback(file_path, language)

        parser = tree_sitter.Parser(lang_module)

        with open(file_path, "rb") as f:
            source = f.read()

        tree = parser.parse(source)
        root = tree.root_node

        symbols = []
        _extract_symbols(root, source, file_path, language, symbols, "")
        return symbols

    except Exception as e:
        logger.error(f"Tree-sitter 解析失败 {file_path}: {e}")
        return _parse_file_fallback(file_path, language)


def _get_tree_sitter_language(language: str):
    try:
        if language == "python":
            import tree_sitter_python as tsp
            return tsp.language()
        elif language in ("c",):
            import tree_sitter_c as tsp
            return tsp.language()
        elif language == "cpp":
            import tree_sitter_cpp as tsp
            return tsp.language()
        elif language == "java":
            import tree_sitter_java as tsp
            return tsp.language()
        elif language == "javascript":
            import tree_sitter_javascript as tsp
            return tsp.language()
        elif language == "typescript":
            import tree_sitter_typescript as tsp
            return tsp.language().typescript()
        elif language == "tsx":
            import tree_sitter_typescript as tsp
            return tsp.language().tsx()
        elif language == "go":
            import tree_sitter_go as tsp
            return tsp.language()
        elif language == "rust":
            import tree_sitter_rust as tsp
            return tsp.language()
        elif language == "ruby":
            import tree_sitter_ruby as tsp
            return tsp.language()
        elif language == "php":
            import tree_sitter_php as tsp
            return tsp.language()
        elif language == "swift":
            import tree_sitter_swift as tsp
            return tsp.language()
        elif language == "kotlin":
            import tree_sitter_kotlin as tsp
            return tsp.language()
        elif language == "c_sharp":
            import tree_sitter_c_sharp as tsp
            return tsp.language()
        else:
            return None
    except ImportError:
        logger.debug(f"Tree-sitter 语言模块未安装: tree_sitter_{language}")
        return None


KIND_MAP = {
    "class_declaration": KIND_CLASS,
    "class_definition": KIND_CLASS,
    "interface_declaration": KIND_INTERFACE,
    "struct_declaration": KIND_STRUCT,
    "struct_definition": KIND_STRUCT,
    "function_declaration": KIND_FUNCTION,
    "function_definition": KIND_FUNCTION,
    "method_declaration": KIND_METHOD,
    "method_definition": KIND_METHOD,
    "variable_declaration": KIND_VARIABLE,
    "variable_declarator": KIND_VARIABLE,
    "assignment": KIND_VARIABLE,
    "constant_declaration": KIND_CONSTANT,
    "import_declaration": KIND_IMPORT,
    "import_statement": KIND_IMPORT,
    "enum_declaration": KIND_ENUM,
    "trait_declaration": KIND_TRAIT,
    "namespace_declaration": KIND_NAMESPACE,
    "property_declaration": KIND_PROPERTY,
    "field_definition": KIND_FIELD,
    "decorated_definition": None,
}


def _extract_symbols(node, source: bytes, file_path: str, language: str, symbols: list, parent_name: str):
    kind = KIND_MAP.get(node.type)

    if kind is not None:
        name = _get_node_name(node, source, language)
        if name:
            signature = _get_signature(node, source)
            docstring = _get_docstring(node, source, language)

            sym = Symbol(
                file_path=file_path,
                name=name,
                kind=kind,
                signature=signature,
                line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                language=language,
                parent_name=parent_name,
                docstring=docstring,
            )
            symbols.append(sym)

            for child in node.children:
                _extract_symbols(child, source, file_path, language, symbols, name)
            return

    for child in node.children:
        _extract_symbols(child, source, file_path, language, symbols, parent_name)


def _get_node_name(node, source: bytes, language: str) -> str:
    name_field = node.child_by_field_name("name")
    if name_field:
        return source[name_field.start_byte:name_field.end_byte].decode("utf-8", errors="replace")

    for child in node.children:
        if child.type in ("identifier", "property_identifier", "type_identifier", "name"):
            return source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")

    return ""


def _get_signature(node, source: bytes) -> str:
    first_line_start = source.rfind(b"\n", 0, node.start_byte) + 1
    first_line_end = source.find(b"\n", node.start_byte)
    if first_line_end == -1:
        first_line_end = len(source)

    first_line = source[first_line_start:first_line_end].decode("utf-8", errors="replace").strip()

    if len(first_line) > 200:
        first_line = first_line[:200] + "..."

    return first_line


def _get_docstring(node, source: bytes, language: str) -> str:
    if language == "python":
        body = node.child_by_field_name("body")
        if body:
            for child in body.children:
                if child.type == "expression_statement":
                    for expr_child in child.children:
                        if expr_child.type == "string":
                            doc = source[expr_child.start_byte:expr_child.end_byte].decode("utf-8", errors="replace")
                            return doc.strip("\"'").strip()[:500]
    return ""


def _parse_file_fallback(file_path: str, language: str) -> list[Symbol]:
    symbols = []

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return symbols

    import re

    if language == "python":
        patterns = [
            (re.compile(r"^(\s*)class\s+(\w+)"), KIND_CLASS),
            (re.compile(r"^(\s*)def\s+(\w+)"), KIND_FUNCTION),
            (re.compile(r"^(\s*)async\s+def\s+(\w+)"), KIND_FUNCTION),
        ]
    elif language in ("c", "cpp", "java", "c_sharp"):
        patterns = [
            (re.compile(r"^\s*class\s+(\w+)"), KIND_CLASS),
            (re.compile(r"^\s*struct\s+(\w+)"), KIND_STRUCT),
            (re.compile(r"^\s*interface\s+(\w+)"), KIND_INTERFACE),
            (re.compile(r"^\s*enum\s+(\w+)"), KIND_ENUM),
            (re.compile(r"^\s*(?:virtual\s+|static\s+|inline\s+)*(?:\w+(?:\s*<[^>]*>)?(?:\s*::\s*\w+)*\s+)+(\w+)\s*\("), KIND_FUNCTION),
        ]
    elif language in ("javascript", "typescript", "tsx", "jsx"):
        patterns = [
            (re.compile(r"^\s*class\s+(\w+)"), KIND_CLASS),
            (re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)"), KIND_FUNCTION),
            (re.compile(r"^\s*(?:const|let|var)\s+(\w+)\s*="), KIND_VARIABLE),
            (re.compile(r"^\s*(?:export\s+)?interface\s+(\w+)"), KIND_INTERFACE),
        ]
    else:
        patterns = [
            (re.compile(r"^\s*class\s+(\w+)"), KIND_CLASS),
            (re.compile(r"^\s*def\s+(\w+)"), KIND_FUNCTION),
            (re.compile(r"^\s*function\s+(\w+)"), KIND_FUNCTION),
        ]

    for i, line in enumerate(lines, 1):
        for pattern, kind in patterns:
            match = pattern.match(line)
            if match:
                name = match.group(match.lastindex or 1)
                indent = len(line) - len(line.lstrip())
                parent = ""
                if indent > 0 and kind in (KIND_FUNCTION, KIND_METHOD):
                    for sym in reversed(symbols):
                        if sym.kind in (KIND_CLASS, KIND_STRUCT, KIND_INTERFACE):
                            parent = sym.name
                            kind = KIND_METHOD
                            break

                symbols.append(Symbol(
                    file_path=file_path,
                    name=name,
                    kind=kind,
                    signature=line.strip()[:200],
                    line=i,
                    end_line=i,
                    language=language,
                    parent_name=parent,
                ))
                break

    return symbols


class CodeIndexer:
    def __init__(self, db: Optional[CodeIndexDB] = None):
        self.db = db or CodeIndexDB()
        self._indexing = False
        self._thread: Optional[threading.Thread] = None

    def index_project(self, project_dir: str, force: bool = False):
        project_dir = os.path.abspath(project_dir)
        if not os.path.isdir(project_dir):
            logger.error(f"项目目录不存在: {project_dir}")
            return

        start_time = time.time()
        total_files = 0
        total_symbols = 0

        for root, dirs, files in os.walk(project_dir):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in (
                "node_modules", "__pycache__", ".git", "venv", ".venv",
                "build", "dist", "target", ".tox", ".mypy_cache",
            )]

            for filename in files:
                ext = os.path.splitext(filename)[1]
                if ext not in SUPPORTED_EXTENSIONS:
                    continue

                file_path = os.path.join(root, filename)
                try:
                    mtime = os.path.getmtime(file_path)
                except OSError:
                    continue

                if not force and not self.db.needs_reindex(file_path, mtime):
                    continue

                language = SUPPORTED_EXTENSIONS[ext]
                symbols = parse_file_with_treesitter(file_path, language)
                self.db.upsert_symbols(file_path, symbols, language, mtime)

                total_files += 1
                total_symbols += len(symbols)

        duration = time.time() - start_time
        logger.info(
            f"索引完成: {total_files} 文件, {total_symbols} 符号, 耗时 {duration:.2f}s"
        )

    def index_project_async(self, project_dir: str, force: bool = False):
        if self._indexing:
            logger.info("索引正在进行中，跳过")
            return

        def _worker():
            self._indexing = True
            try:
                self.index_project(project_dir, force)
            finally:
                self._indexing = False

        self._thread = threading.Thread(target=_worker, daemon=True)
        self._thread.start()

    def index_file(self, file_path: str, force: bool = True):
        file_path = os.path.abspath(file_path)
        if not os.path.isfile(file_path):
            return

        ext = os.path.splitext(file_path)[1]
        if ext not in SUPPORTED_EXTENSIONS:
            return

        language = SUPPORTED_EXTENSIONS[ext]
        mtime = os.path.getmtime(file_path)

        if not force and not self.db.needs_reindex(file_path, mtime):
            return

        symbols = parse_file_with_treesitter(file_path, language)
        self.db.upsert_symbols(file_path, symbols, language, mtime)
        logger.info(f"文件索引更新: {file_path} ({len(symbols)} 符号)")

    @property
    def is_indexing(self) -> bool:
        return self._indexing


SUPPORTED_EXTENSIONS = SUPPORTED_EXTENSIONS


_global_indexer: Optional[CodeIndexer] = None
_global_db: Optional[CodeIndexDB] = None


def get_indexer() -> CodeIndexer:
    global _global_indexer, _global_db
    if _global_indexer is None:
        _global_db = CodeIndexDB()
        _global_indexer = CodeIndexer(_global_db)
    return _global_indexer


def get_db() -> CodeIndexDB:
    global _global_db
    if _global_db is None:
        _global_db = CodeIndexDB()
    return _global_db


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("Eruitah Tree-sitter 代码索引引擎测试")
    print("=" * 60)

    indexer = get_indexer()

    test_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"\n--- 索引项目: {test_dir} ---")
    indexer.index_project(test_dir)

    db = get_db()
    stats = db.get_stats()
    print(f"\n索引统计:")
    print(f"  文件数: {stats.total_files}")
    print(f"  符号数: {stats.total_symbols}")
    print(f"  语言分布: {stats.languages}")

    print(f"\n--- 搜索: 名为 'run_agent' 的符号 ---")
    results = db.search_symbols(name="run_agent")
    for r in results:
        print(f"  {r['kind']}: {r['name']} @ {r['file_path']}:{r['line']}")
        print(f"    签名: {r['signature'][:100]}")

    print(f"\n--- 搜索: 所有 class ---")
    results = db.search_symbols(kind=KIND_CLASS)
    for r in results[:10]:
        print(f"  class {r['name']} @ {r['file_path']}:{r['line']}")
