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
import os
from dataclasses import dataclass
from typing import Optional

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

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


SEMANTIC_SEARCH_CODE_TOOL_DEFINITION_OPENAI = {
    "type": "function",
    "function": {
        "name": "semantic_search_code",
        "description": (
            "Codebase RAG 语义代码搜索 - 用自然语言描述你想找的功能，返回最相关的代码片段。"
            "适用于：不确定某个功能在哪个文件、需要理解业务逻辑、在大型项目中定位代码。"
            "示例查询：'数据库连接初始化'、'用户认证逻辑'、'错误处理中间件'、'配置文件加载'。"
            "如果你知道极其确切的函数名或变量名，使用 grep 进行精准搜索。"
            "如果你不确定功能在哪里，优先使用此工具。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "自然语言描述你想找的功能，如 '数据库连接初始化'、'用户登录验证'、'文件上传处理'",
                },
                "top_k": {
                    "type": "integer",
                    "description": "返回最相关的结果数量（默认 3，最多 10）",
                },
                "project_dir": {
                    "type": "string",
                    "description": "项目目录路径（可选，默认为当前工作目录）",
                },
            },
            "required": ["query"],
        },
    },
}

SEMANTIC_SEARCH_CODE_TOOL_DEFINITION_ANTHROPIC = {
    "name": "semantic_search_code",
    "description": (
        "Codebase RAG 语义代码搜索 - 用自然语言描述你想找的功能，返回最相关的代码片段。"
        "适用于：不确定某个功能在哪个文件、需要理解业务逻辑、在大型项目中定位代码。"
        "如果你知道极其确切的函数名或变量名，使用 grep 进行精准搜索。"
        "如果你不确定功能在哪里，优先使用此工具。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "自然语言描述你想找的功能，如 '数据库连接初始化'、'用户登录验证'",
            },
            "top_k": {
                "type": "integer",
                "description": "返回最相关的结果数量（默认 3，最多 10）",
            },
            "project_dir": {
                "type": "string",
                "description": "项目目录路径（可选）",
            },
        },
        "required": ["query"],
    },
}


class _VectorEngine:
    """
    动态双轨制向量搜索引擎

    三级降级策略：
    1. API 模式（EMBEDDING_MODE=api）：调用 OpenAI 兼容 Embedding API，零本地内存
    2. Local 模式（EMBEDDING_MODE=local）：加载 sentence-transformers 本地模型
    3. 纯 Lexical 降级：两者都不可用时，自动回退到纯关键词搜索

    环境变量配置：
    - EMBEDDING_MODE: "api" | "local" | "auto"（默认 auto，优先 API）
    - EMBEDDING_API_URL: Embedding API 地址
    - EMBEDDING_API_KEY: API 密钥
    - EMBEDDING_MODEL: 模型名称
    - EMBEDDING_DIMENSIONS: 向量维度（API 模式需要）
    - ERUITAH_EMBEDDING_MODEL: 本地模型名称（Local 模式）
    """

    def __init__(self):
        self._encoder = None
        self._embeddings_matrix = None
        self._symbol_ids = []
        self._symbol_texts = []
        self._indexed_project = None
        self._mode = None
        self._api_dim = None

    @property
    def mode(self) -> str:
        if self._mode is None:
            self._mode = self._detect_mode()
        return self._mode

    @property
    def available(self) -> bool:
        return self.mode in ("api", "local")

    def _detect_mode(self) -> str:
        preferred = os.environ.get("EMBEDDING_MODE", "auto").lower()

        if preferred == "api":
            if self._check_api_available():
                logger.info("🔍 Embedding 模式: API (用户指定)")
                return "api"
            logger.warning("⚠️ EMBEDDING_MODE=api 但 API 不可用，尝试降级到 local")
            if self._check_local_available():
                return "local"
            return "lexical"

        if preferred == "local":
            if self._check_local_available():
                logger.info("🔍 Embedding 模式: Local (用户指定)")
                return "local"
            logger.warning("⚠️ EMBEDDING_MODE=local 但 sentence-transformers 未安装，降级到 lexical")
            return "lexical"

        if preferred == "auto":
            if self._check_api_available():
                logger.info("🔍 Embedding 模式: API (auto 优先)")
                return "api"
            if self._check_local_available():
                logger.info("🔍 Embedding 模式: Local (API 不可用，降级)")
                return "local"
            logger.info("🔍 Embedding 模式: Lexical Only (API 和 Local 均不可用)")
            return "lexical"

        logger.warning(f"⚠️ 未知 EMBEDDING_MODE={preferred}，降级到 lexical")
        return "lexical"

    def _check_api_available(self) -> bool:
        api_key = os.environ.get("EMBEDDING_API_KEY", "")
        api_url = os.environ.get("EMBEDDING_API_URL", "") or os.environ.get("EMBEDDING_BASE_URL", "")
        return bool(api_key and api_url)

    def _check_local_available(self) -> bool:
        try:
            import sentence_transformers
            import numpy
            return True
        except ImportError:
            return False

    def _get_api_dim(self) -> int:
        if self._api_dim is not None:
            return self._api_dim
        dim = int(os.environ.get("EMBEDDING_DIMENSIONS", "0"))
        if dim > 0:
            self._api_dim = dim
            return dim
        model = os.environ.get("EMBEDDING_MODEL", "")
        if "3-small" in model:
            self._api_dim = 1536
        elif "3-large" in model:
            self._api_dim = 3072
        elif "ada-002" in model:
            self._api_dim = 1536
        elif "bge-m3" in model:
            self._api_dim = 1024
        elif "bge-large" in model:
            self._api_dim = 1024
        elif "bge-base" in model:
            self._api_dim = 768
        elif "bge-small" in model:
            self._api_dim = 384
        elif "text2vec" in model:
            self._api_dim = 768
        else:
            self._api_dim = 1024
        return self._api_dim

    def _encode_via_api(self, texts: list[str]) -> 'numpy.ndarray':
        import numpy as np
        import requests

        base_url = os.environ.get("EMBEDDING_API_URL", "") or os.environ.get("EMBEDDING_BASE_URL", "")
        api_key = os.environ.get("EMBEDDING_API_KEY", "")
        model = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-m3")

        if base_url.endswith("/embeddings"):
            api_url = base_url
        elif base_url.endswith("/v1"):
            api_url = base_url + "/embeddings"
        else:
            api_url = base_url.rstrip("/") + "/v1/embeddings"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        batch_size = 64
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            payload = {
                "input": batch,
                "model": model,
            }

            try:
                resp = requests.post(
                    api_url,
                    headers=headers,
                    json=payload,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()["data"]
                data.sort(key=lambda x: x["index"])
                for item in data:
                    all_embeddings.append(item["embedding"])
            except requests.exceptions.RequestException as e:
                logger.error(f"❌ Embedding API 调用失败 (batch {i}): {e}")
                dim = self._get_api_dim()
                for _ in batch:
                    all_embeddings.append([0.0] * dim)

        return np.array(all_embeddings, dtype=np.float32)

    def _encode_via_local(self, texts: list[str]) -> 'numpy.ndarray':
        import numpy as np

        if self._encoder is None:
            from sentence_transformers import SentenceTransformer
            model_name = os.environ.get(
                "ERUITAH_EMBEDDING_MODEL",
                "shibing624/text2vec-base-chinese",
            )
            logger.info(f"🔄 加载本地向量模型: {model_name}...")
            self._encoder = SentenceTransformer(model_name)
            logger.info(f"✅ 本地向量模型加载完成")

        embeddings = self._encoder.encode(texts, show_progress_bar=False, batch_size=64)
        return np.array(embeddings, dtype=np.float32)

    def _encode(self, texts: list[str]) -> 'numpy.ndarray':
        if self.mode == "api":
            return self._encode_via_api(texts)
        elif self.mode == "local":
            return self._encode_via_local(texts)
        else:
            import numpy as np
            return np.zeros((len(texts), 1), dtype=np.float32)

    def build_index(self, symbols: list[dict], project_dir: str):
        if not self.available:
            return

        if self._indexed_project == project_dir and self._embeddings_matrix is not None:
            return

        import numpy as np

        texts = []
        ids = []
        for sym in symbols:
            parts = []
            name = sym.get("name", "")
            kind = sym.get("kind", "")
            sig = sym.get("signature", "")
            doc = sym.get("docstring", "")
            parent = sym.get("parent_name", "")
            fpath = sym.get("file_path", "")

            if kind in ("class", "interface"):
                parts.append(f"class {name}")
            elif kind in ("function", "method"):
                parts.append(f"function {name}")
            else:
                parts.append(f"{kind} {name}")

            if parent:
                parts.append(f"in {parent}")
            if sig:
                parts.append(sig)
            if doc:
                parts.append(doc[:300])
            if fpath:
                parts.append(f"file: {fpath}")

            text = " ".join(parts)
            if len(text.strip()) > 5:
                texts.append(text)
                ids.append(f"{fpath}:{sym.get('line', 0)}:{name}")

        if not texts:
            return

        logger.info(f"🔄 构建 {len(texts)} 个代码块的向量索引 (mode={self.mode})...")
        embeddings = self._encode(texts)

        if embeddings.shape[0] == 0:
            return

        self._embeddings_matrix = embeddings

        norms = np.linalg.norm(self._embeddings_matrix, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        self._embeddings_matrix = self._embeddings_matrix / norms

        self._symbol_ids = ids
        self._symbol_texts = texts
        self._indexed_project = project_dir
        logger.info(f"✅ 向量索引构建完成: {len(ids)} 个代码块 (mode={self.mode})")

    def search(self, query: str, top_k: int = 20) -> list[tuple[str, float]]:
        if not self.available or self._embeddings_matrix is None:
            return []

        import numpy as np

        query_embeddings = self._encode([query])
        query_vec = query_embeddings[0]
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            return []
        query_vec = query_vec / query_norm

        similarities = (self._embeddings_matrix @ query_vec.T).flatten()

        top_indices = np.argsort(similarities)[::-1][:top_k]

        results = []
        for idx in top_indices:
            if idx < len(self._symbol_ids):
                results.append((self._symbol_ids[idx], float(similarities[idx])))

        return results


_vector_engine = _VectorEngine()


def _rrf_fuse(
    channel_a: list[tuple[str, float]],
    channel_b: list[tuple[str, float]],
    k: int = 60,
) -> list[tuple[str, float]]:
    """
    RRF (Reciprocal Rank Fusion) 倒数排名融合算法

    公式: Score = 1/(k + rank_A) + 1/(k + rank_B)
    不看绝对分数，只看排名，完美中和两种引擎的评分偏差。
    """
    rrf_scores = {}

    for rank, (item_id, _score) in enumerate(channel_a):
        rrf_scores[item_id] = rrf_scores.get(item_id, 0.0) + 1.0 / (k + rank + 1)

    for rank, (item_id, _score) in enumerate(channel_b):
        rrf_scores[item_id] = rrf_scores.get(item_id, 0.0) + 1.0 / (k + rank + 1)

    fused = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    return fused


def _extract_keywords(query: str) -> list[str]:
    """从自然语言查询中提取搜索关键词"""
    import re

    stop_words = {
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
        "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
        "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那",
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "can", "shall", "to", "of", "in", "for",
        "on", "with", "at", "by", "from", "as", "into", "through", "during",
        "before", "after", "above", "below", "between", "out", "off", "over",
        "under", "again", "further", "then", "once", "and", "but", "or",
        "not", "no", "nor", "so", "if", "than", "too", "very", "just",
        "about", "up", "all", "each", "both", "few", "more", "most",
        "other", "some", "such", "only", "own", "same", "how", "what",
        "which", "who", "when", "where", "why", "this", "that", "these",
        "those", "i", "me", "my", "we", "our", "you", "your", "he", "him",
        "his", "she", "her", "it", "its", "they", "them", "their",
    }

    tech_synonyms = {
        "数据库": ["database", "db", "sql", "postgres", "mysql", "sqlite", "mongo"],
        "连接": ["connect", "connection", "conn", "link", "pool"],
        "初始化": ["init", "initialize", "setup", "bootstrap", "constructor"],
        "配置": ["config", "configuration", "setting", "option", "preference"],
        "认证": ["auth", "authenticate", "login", "token", "session", "credential"],
        "授权": ["authorize", "permission", "role", "access", "privilege"],
        "路由": ["route", "router", "endpoint", "path", "url"],
        "中间件": ["middleware", "interceptor", "filter", "handler"],
        "缓存": ["cache", "redis", "memcache", "lru"],
        "日志": ["log", "logger", "logging", "trace", "debug"],
        "错误": ["error", "exception", "fault", "fail", "crash"],
        "处理": ["handle", "handler", "process", "manage", "deal"],
        "请求": ["request", "req", "http", "api", "call"],
        "响应": ["response", "resp", "reply", "result", "return"],
        "用户": ["user", "account", "member", "profile"],
        "文件": ["file", "document", "path", "io", "read", "write"],
        "上传": ["upload", "file_upload", "multipart", "attachment"],
        "下载": ["download", "export", "stream"],
        "测试": ["test", "spec", "mock", "fixture", "assert"],
        "搜索": ["search", "find", "query", "lookup", "filter"],
        "创建": ["create", "new", "add", "insert", "make", "build"],
        "删除": ["delete", "remove", "destroy", "drop", "erase"],
        "更新": ["update", "modify", "edit", "change", "patch", "put"],
        "查询": ["query", "search", "find", "select", "get", "fetch"],
        "验证": ["validate", "verify", "check", "confirm", "assert"],
        "加密": ["encrypt", "crypto", "hash", "cipher", "ssl", "tls"],
        "解密": ["decrypt", "decode", "unseal"],
        "序列化": ["serialize", "marshal", "encode", "json", "pickle"],
        "反序列化": ["deserialize", "unmarshal", "decode", "parse"],
        "线程": ["thread", "async", "concurrent", "parallel", "lock", "mutex"],
        "网络": ["network", "http", "tcp", "udp", "socket", "websocket"],
        "消息": ["message", "msg", "event", "notify", "queue", "pubsub"],
        "定时": ["cron", "schedule", "timer", "interval", "periodic"],
        "监控": ["monitor", "metric", "health", "status", "heartbeat"],
        "部署": ["deploy", "release", "build", "ci", "cd", "pipeline"],
    }

    words = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*|[\u4e00-\u9fff]+', query.lower())

    keywords = []
    for w in words:
        if w in stop_words:
            continue
        keywords.append(w)
        if w in tech_synonyms:
            keywords.extend(tech_synonyms[w])

    camel_parts = re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)', query)
    for part in camel_parts:
        if part.lower() not in stop_words and len(part) > 1:
            keywords.append(part.lower())

    snake_parts = query.replace('-', '_').split('_')
    for part in snake_parts:
        part = part.lower().strip()
        if part and part not in stop_words and len(part) > 1:
            keywords.append(part)

    seen = set()
    unique = []
    for k in keywords:
        k_lower = k.lower()
        if k_lower not in seen:
            seen.add(k_lower)
            unique.append(k_lower)

    return unique if unique else [query.lower()]


def semantic_search_code(
    query: str,
    top_k: int = 3,
    project_dir: Optional[str] = None,
) -> tuple[str, bool]:
    """
    Codebase RAG 混合检索 (Hybrid Search) - RRF 融合管道

    双通道检索 + RRF 融合：
    - 通道 A: FTS5 全文检索 (SQLite MATCH + bm25)
    - 通道 B: 语义向量检索 (Embedding 余弦相似度)
    - RRF 倒数排名融合: Score = 1/(k+rank_A) + 1/(k+rank_B), k=60

    Returns:
        (formatted_result, is_error)
    """
    if not query.strip():
        return "查询不能为空", True

    top_k = max(1, min(top_k, 10))

    try:
        if project_dir:
            indexer = get_indexer()
            indexer.index_project(project_dir)

        db = get_db()

        # 构建向量索引
        all_symbols = db.search_symbols(limit=5000)
        _vector_engine.build_index(all_symbols, project_dir or os.getcwd())

        # 提取关键词用于 FTS5 查询
        keywords = _extract_keywords(query)
        fts_query = " ".join(keywords)
        logger.info(f"🔍 Hybrid Search: query='{query}', fts_query='{fts_query}'")

        # ── 通道 A: FTS5 全文检索 (SQLite MATCH + bm25) ──
        fts_results = db.search_fts(fts_query, limit=20)
        channel_a_ranked = []
        sym_lookup = {}
        for sym, _rank_score in fts_results:
            sym_id = f"{sym.get('file_path', '')}:{sym.get('line', 0)}:{sym.get('name', '')}"
            channel_a_ranked.append((sym_id, _rank_score))
            sym_lookup[sym_id] = sym

        # ── 通道 B: 语义向量检索 (Embedding 余弦相似度) ──
        channel_b_raw = _vector_engine.search(query, top_k=20)
        channel_b_ranked = [(sid, score) for sid, score in channel_b_raw]

        # 补充向量通道的符号到 lookup
        for sid, _vec_score in channel_b_raw:
            if sid not in sym_lookup:
                parts = sid.rsplit(":", 2)
                if len(parts) >= 3:
                    fp, line_str, name = parts[0], parts[1], parts[2]
                    sym_lookup[sid] = {
                        "file_path": fp,
                        "line": int(line_str) if line_str.isdigit() else 0,
                        "name": name,
                        "kind": "unknown",
                        "signature": "",
                        "docstring": "",
                        "parent_name": "",
                    }

        # ── RRF 融合: Score = 1/(k + rank_A) + 1/(k + rank_B), k=60 ──
        if channel_b_ranked:
            fused = _rrf_fuse(channel_a_ranked, channel_b_ranked, k=60)
            search_mode = "Hybrid (FTS5 + Semantic RRF)"
            logger.info(f"🔀 RRF 融合: FTS5 {len(channel_a_ranked)} 条 + Semantic {len(channel_b_ranked)} 条 → {len(fused)} 条")
        elif channel_a_ranked:
            fused = [(sid, score) for sid, score in channel_a_ranked]
            search_mode = "FTS5 Only (向量引擎不可用)"
            logger.info(f"📝 纯 FTS5 搜索: {len(fused)} 条")
        else:
            fused = []
            search_mode = "No Results"

        # ── 取 Top-K 结果 ──
        top_results = []
        for sid, rrf_score in fused[:top_k]:
            sym = sym_lookup.get(sid)
            if sym:
                top_results.append((rrf_score, sym))

        if not top_results:
            fallback_result = semantic_search(
                query=query,
                project_dir=project_dir,
                limit=top_k,
            )
            if fallback_result.results:
                formatted = format_semantic_results(fallback_result)
                return (
                    f"🔍 混合检索未找到高置信度匹配，以下是符号名模糊匹配结果：\n\n{formatted}",
                    False,
                )
            return f"未找到与 '{query}' 相关的代码。建议：\n1. 尝试更具体的关键词\n2. 使用 grep 进行全文搜索\n3. 使用 semantic_search(query='overview') 查看项目结构", False

        lines = [
            f"🔍 Hybrid Search 结果: '{query}' [{search_mode}] (Top {len(top_results)})",
            "=" * 60,
        ]

        for rank, (rrf_score, sym) in enumerate(top_results, 1):
            kind_icon = {
                "class": "📦", "interface": "🔌", "struct": "🏗️",
                "function": "⚡", "method": "🔧", "variable": "📌",
                "constant": "🔒", "enum": "📋", "trait": "🧩",
                "unknown": "❓",
            }.get(sym.get("kind", ""), "📍")

            relevance = "🟢" if rrf_score >= 0.02 else "🟡" if rrf_score >= 0.01 else "🔴"
            parent_str = f" (in {sym['parent_name']})" if sym.get("parent_name") else ""

            lines.append(f"\n{relevance} #{rank} [RRF={rrf_score:.4f}] {kind_icon} {sym.get('kind', '?')} {sym.get('name', '?')}{parent_str}")
            lines.append(f"   📄 文件: {sym.get('file_path', '?')}:{sym.get('line', 0)}")

            if sym.get("signature"):
                lines.append(f"   ✍️ 签名: {sym['signature'][:150]}")

            if sym.get("docstring"):
                lines.append(f"   📝 文档: {sym['docstring'][:200]}")

            try:
                fp = sym.get("file_path", "")
                if not os.path.isabs(fp) and project_dir:
                    fp = os.path.join(project_dir, fp)
                if os.path.exists(fp):
                    with open(fp, "r", encoding="utf-8", errors="replace") as f:
                        all_lines = f.readlines()
                    sym_line = sym.get("line", 0)
                    start = max(0, sym_line - 1 - 3)
                    end = min(len(all_lines), sym_line - 1 + 15)
                    snippet = "".join(all_lines[start:end])
                    lines.append(f"   💻 代码片段:")
                    for i, code_line in enumerate(snippet.split("\n"), start=start + 1):
                        marker = " →" if i == sym_line else "  "
                        lines.append(f"     {marker} {i:4d} | {code_line}")
            except Exception:
                pass

        return "\n".join(lines), False

    except Exception as e:
        logger.error(f"Hybrid Search 失败: {e}")
        return f"语义搜索失败: {str(e)}", True


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
