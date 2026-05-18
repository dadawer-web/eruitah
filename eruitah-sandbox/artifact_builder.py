"""
Eruitah 智能编程沙盒 - 构建产物打包 & 执行环境判定

核心能力:
  1. generate_artifacts() — 遍历沙盒工作区，将代码文件打包为 WebContainer VFS JSON
  2. detect_execution_env() — 根据项目文件特征判定执行环境 (webcontainer / docker / native)

VFS 格式 (兼容 StackBlitz WebContainer):
{
  "index.js": { "file": { "contents": "..." } },
  "package.json": { "file": { "contents": "..." } },
  "src": {
    "directory": {
      "App.vue": { "file": { "contents": "..." } }
    }
  }
}
"""

import os
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

WEBCONTAINER_INDICATORS = {
    "package.json",
    "vite.config.js",
    "vite.config.ts",
    "vite.config.mjs",
    "next.config.js",
    "next.config.mjs",
    "nuxt.config.js",
    "nuxt.config.ts",
    "angular.json",
    "svelte.config.js",
    ".vue",
    ".jsx",
    ".tsx",
    "index.html",
    "tsconfig.json",
}

DOCKER_INDICATORS = {
    "CMakeLists.txt",
    "Makefile",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "Cargo.toml",
    "go.mod",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    ".java",
    ".cpp",
    ".c",
    ".h",
    ".rs",
    ".go",
    ".py",
}

IGNORED_DIRS = {
    "node_modules",
    ".git",
    "__pycache__",
    ".next",
    ".nuxt",
    "dist",
    "build",
    ".cache",
    ".agent_memory",
    ".vscode",
    ".idea",
    "target",
    "vendor",
    "venv",
    ".venv",
    "env",
    ".env",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "coverage",
    ".coverage",
    "htmlcov",
}

IGNORED_FILES = {
    ".DS_Store",
    "Thumbs.db",
    ".gitkeep",
    "*.pyc",
    "*.pyo",
    "*.so",
    "*.dylib",
    "*.dll",
    "*.exe",
    "*.o",
    "*.a",
    "*.wasm",
    "*.lock",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lockb",
}

MAX_FILE_SIZE = 512 * 1024

TEXT_EXTENSIONS = {
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".vue", ".svelte", ".astro",
    ".html", ".htm", ".css", ".scss", ".sass", ".less", ".styl",
    ".json", ".json5", ".jsonc",
    ".md", ".mdx", ".txt", ".csv", ".yaml", ".yml", ".toml",
    ".py", ".pyi", ".pyx",
    ".java", ".kt", ".kts", ".groovy",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".cxx",
    ".rs", ".go", ".rb", ".php",
    ".sh", ".bash", ".zsh", ".fish",
    ".sql", ".graphql", ".gql",
    ".xml", ".svg",
    ".env", ".env.local", ".env.development", ".env.production",
    ".gitignore", ".dockerignore", ".editorconfig", ".prettierrc", ".eslintrc",
    ".babelrc", ".babelrc.js", ".babelrc.json",
    ".conf", ".cfg", ".ini", ".properties",
    ".Dockerfile",
    ".wasm",
}

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".avif",
    ".mp3", ".mp4", ".wav", ".ogg", ".flac", ".aac",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
}


def _should_ignore_dir(dirname: str) -> bool:
    return dirname in IGNORED_DIRS or dirname.startswith(".")


def _should_ignore_file(filename: str) -> bool:
    if filename in IGNORED_FILES:
        return True
    for pattern in IGNORED_FILES:
        if pattern.startswith("*") and filename.endswith(pattern[1:]):
            return True
    return False


def _is_text_file(filepath: str) -> bool:
    _, ext = os.path.splitext(filepath)
    ext = ext.lower()
    if ext in TEXT_EXTENSIONS:
        return True
    if ext in BINARY_EXTENSIONS:
        return False
    basename = os.path.basename(filepath)
    no_ext_files = {
        "Makefile", "Dockerfile", "Vagrantfile", "Gemfile",
        "Rakefile", "Procfile", "Berksfile", "Brewfile",
        "LICENSE", "README", "CHANGELOG", "CONTRIBUTING",
    }
    if basename in no_ext_files:
        return True
    if basename.startswith(".env") or basename.startswith(".git"):
        return True
    try:
        with open(filepath, 'rb') as f:
            chunk = f.read(8192)
        return b'\x00' not in chunk
    except Exception:
        return False


def _read_file_content(filepath: str) -> Optional[str]:
    try:
        size = os.path.getsize(filepath)
        if size > MAX_FILE_SIZE:
            logger.debug(f"跳过大文件: {filepath} ({size} bytes)")
            return None
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except Exception as e:
        logger.debug(f"读取文件失败: {filepath} - {e}")
        return None


def generate_artifacts(work_dir: str, max_total_size: int = 4 * 1024 * 1024) -> dict:
    """
    遍历沙盒工作区，将所有代码文件打包成 WebContainer VFS JSON。

    Args:
        work_dir: 沙盒工作目录
        max_total_size: VFS 总大小上限（默认 4MB）

    Returns:
        dict: VFS 虚拟文件树
    """
    vfs = {}
    total_size = 0
    file_count = 0

    for root, dirs, files in os.walk(work_dir, topdown=True):
        dirs[:] = [d for d in dirs if not _should_ignore_dir(d)]

        rel_root = os.path.relpath(root, work_dir)
        if rel_root == ".":
            rel_root = ""

        for filename in files:
            if _should_ignore_file(filename):
                continue

            filepath = os.path.join(root, filename)
            rel_path = os.path.join(rel_root, filename) if rel_root else filename
            rel_path = rel_path.replace(os.sep, "/")

            if not _is_text_file(filepath):
                continue

            content = _read_file_content(filepath)
            if content is None:
                continue

            content_size = len(content.encode('utf-8'))
            if total_size + content_size > max_total_size:
                logger.warning(
                    f"VFS 总大小超过 {max_total_size // 1024 // 1024}MB 上限，"
                    f"已打包 {file_count} 个文件，跳过剩余文件"
                )
                break

            parts = rel_path.split("/")
            current = vfs
            for i, part in enumerate(parts[:-1]):
                if part not in current:
                    current[part] = {"directory": {}}
                elif "directory" not in current[part]:
                    current[part] = {"directory": {}}
                current = current[part]["directory"]

            leaf_name = parts[-1]
            current[leaf_name] = {"file": {"contents": content}}
            total_size += content_size
            file_count += 1
        else:
            continue
        break

    logger.info(
        f"📦 VFS 打包完成: {file_count} 个文件, "
        f"总大小 {total_size // 1024}KB"
    )

    return vfs


def detect_execution_env(work_dir: str) -> str:
    """
    根据项目文件特征判定执行环境。

    判定优先级:
      1. webcontainer — 前端项目 (Vue/React/Vite/Next/Nuxt/Angular/Svelte)
      2. docker — 后端/系统项目 (C++/Java/Rust/Go/Python + Dockerfile)
      3. native — 默认回退

    Returns:
        str: "webcontainer" | "docker" | "native"
    """
    all_files = set()
    all_extensions = set()

    for root, dirs, files in os.walk(work_dir, topdown=True):
        dirs[:] = [d for d in dirs if not _should_ignore_dir(d)]
        for f in files:
            all_files.add(f)
            _, ext = os.path.splitext(f)
            if ext:
                all_extensions.add(ext.lower())

    webcontainer_score = 0
    docker_score = 0

    for indicator in WEBCONTAINER_INDICATORS:
        if indicator.startswith("."):
            if indicator in all_extensions:
                webcontainer_score += 2
        elif indicator in all_files:
            webcontainer_score += 3

    for indicator in DOCKER_INDICATORS:
        if indicator.startswith("."):
            if indicator in all_extensions:
                docker_score += 2
        elif indicator in all_files:
            docker_score += 3

    if "package.json" in all_files:
        webcontainer_score += 5
        pkg_path = os.path.join(work_dir, "package.json")
        if os.path.exists(pkg_path):
            try:
                with open(pkg_path, 'r', encoding='utf-8') as f:
                    pkg = json.load(f)
                deps = set(list(pkg.get("dependencies", {}).keys()) + list(pkg.get("devDependencies", {}).keys()))
                frontend_frameworks = {
                    "vue", "react", "react-dom", "next", "nuxt", "@angular/core",
                    "svelte", "vite", "@vitejs/plugin-vue", "@vitejs/plugin-react",
                    "astro", "@remix-run/react", "gatsby",
                }
                if deps & frontend_frameworks:
                    webcontainer_score += 10
            except Exception:
                pass

    if "Dockerfile" in all_files or "docker-compose.yml" in all_files:
        docker_score += 5

    if webcontainer_score > docker_score and webcontainer_score >= 3:
        env = "webcontainer"
    elif docker_score > webcontainer_score and docker_score >= 3:
        env = "docker"
    elif webcontainer_score > 0 and docker_score > 0:
        env = "webcontainer"
    elif webcontainer_score > 0:
        env = "webcontainer"
    elif docker_score > 0:
        env = "docker"
    else:
        env = "native"

    logger.info(
        f"🔍 执行环境判定: {env} "
        f"(webcontainer={webcontainer_score}, docker={docker_score})"
    )

    return env


def build_artifact_payload(work_dir: str) -> dict:
    """
    一站式构建产物打包：检测环境 + 生成 VFS。

    Returns:
        dict: {
            "execution_env": "webcontainer" | "docker" | "native",
            "vfs": { ... },
            "file_count": int,
            "total_size_bytes": int,
        }
    """
    execution_env = detect_execution_env(work_dir)
    vfs = generate_artifacts(work_dir)

    total_size = 0
    file_count = 0

    def _count_vfs(node: dict):
        nonlocal file_count, total_size
        for key, value in node.items():
            if "file" in value:
                file_count += 1
                contents = value["file"].get("contents", "")
                total_size += len(contents.encode('utf-8'))
            elif "directory" in value:
                _count_vfs(value["directory"])

    _count_vfs(vfs)

    return {
        "execution_env": execution_env,
        "vfs": vfs,
        "file_count": file_count,
        "total_size_bytes": total_size,
    }
