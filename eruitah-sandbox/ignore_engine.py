"""
Eruitah 智能编程沙盒 - 降噪引擎 (Ignore Engine)

防止沙盒在解析大型项目时被第三方依赖、编译产物和缓存文件撑爆内存。
核心能力:
  1. 多语言通用黑名单字典 (覆盖 Node/Python/Java/C++/Go/Rust 等)
  2. 自动黑名单生成器: 根据项目类型自动生成 .eruitahignore
  3. 文件过滤器: 读取 .eruitahignore + .gitignore，过滤掉噪声文件

使用方式:
  from ignore_engine import generate_ignore_file, filter_files

  # 1. 自动生成 .eruitahignore（如果不存在）
  generate_ignore_file("/workspace", framework_type="python")

  # 2. 过滤文件列表
  clean_files = filter_files("/workspace", all_files)
"""

import fnmatch
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════
# 多语言通用黑名单字典
# ══════════════════════════════════════════════════════════

IGNORE_RULES = {
    "general": [
        # VCS & IDE
        ".git",
        ".svn",
        ".hg",
        ".idea",
        ".vscode",
        ".eclipse",
        ".settings",
        "*.swp",
        "*.swo",
        "*~",
        # OS
        ".DS_Store",
        "Thumbs.db",
        "desktop.ini",
        # Logs & Temp
        "*.log",
        "*.tmp",
        "*.temp",
        "*.bak",
        "*.cache",
        # Archives
        "*.zip",
        "*.tar",
        "*.tar.gz",
        "*.tgz",
        "*.rar",
        "*.7z",
        # Binary
        "*.exe",
        "*.dll",
        "*.so",
        "*.dylib",
        "*.bin",
        "*.dat",
        # Eruitah 自身
        ".eruitah_cache",
        ".agent_memory",
        "project_structure.json",
    ],

    "node": [
        # Dependencies
        "node_modules",
        "bower_components",
        ".pnp",
        ".pnp.js",
        # Build output
        "dist",
        "build",
        "out",
        ".output",
        ".nuxt",
        ".next",
        ".svelte-kit",
        ".vercel",
        ".netlify",
        # Framework specific
        ".nuxt",
        ".vuepress/dist",
        ".docusaurus",
        "coverage",
        ".coverage",
        # Cache
        ".npm",
        ".yarn",
        ".yarn/cache",
        ".yarn/unplugged",
        ".yarn/build-state.yml",
        ".yarn/install-state.gz",
        ".pnpm-store",
        ".parcel-cache",
        ".turbo",
        ".eslintcache",
        ".stylelintcache",
        # TypeScript
        "*.tsbuildinfo",
    ],

    "python": [
        # Byte-compiled
        "__pycache__",
        "*.pyc",
        "*.pyo",
        "*.pyd",
        "*.pdb",
        # Virtual environments
        "venv",
        ".venv",
        "env",
        ".env",
        ".conda",
        # Distribution
        "*.egg",
        "*.egg-info",
        "*.whl",
        "dist",
        "build",
        "sdist",
        # Testing
        ".pytest_cache",
        ".coverage",
        "htmlcov",
        ".mypy_cache",
        ".ruff_cache",
        ".pytype",
        # Jupyter
        ".ipynb_checkpoints",
        "*.ipynb_metadata",
        # tox
        ".tox",
        ".nox",
    ],

    "java": [
        # Maven
        "target",
        "*.class",
        "*.jar",
        "*.war",
        "*.ear",
        # Gradle
        ".gradle",
        "build",
        "out",
        # IDE
        ".classpath",
        ".project",
        ".settings",
        "*.iml",
        ".idea",
        # Spring
        ".spring",
    ],

    "cpp": [
        # Build
        "build",
        "cmake-build-debug",
        "cmake-build-release",
        "out",
        # Object files
        "*.o",
        "*.obj",
        "*.so",
        "*.a",
        "*.lib",
        "*.exe",
        "*.out",
        "*.app",
        # CMake
        "CMakeFiles",
        "CMakeCache.txt",
        "cmake_install.cmake",
        "Makefile",
        # Generated
        "*.d",
        "*.pch",
        "*.gch",
        "*.ilk",
        "*.pdb",
    ],

    "go": [
        "vendor",
        "*.test",
        "*.out",
    ],

    "rust": [
        "target",
        "Cargo.lock",
    ],

    "dotnet": [
        "bin",
        "obj",
        "*.dll",
        "*.pdb",
        "*.exe",
    ],
}

# 框架类型 → 规则集合的映射
FRAMEWORK_RULE_MAP = {
    "python": ["general", "python"],
    "node": ["general", "node"],
    "javascript": ["general", "node"],
    "typescript": ["general", "node"],
    "react": ["general", "node"],
    "vue": ["general", "node"],
    "next": ["general", "node"],
    "nuxt": ["general", "node"],
    "java": ["general", "java"],
    "spring": ["general", "java"],
    "cpp": ["general", "cpp"],
    "c": ["general", "cpp"],
    "go": ["general", "go"],
    "rust": ["general", "rust"],
    "dotnet": ["general", "dotnet"],
    "csharp": ["general", "dotnet"],
    # 未知类型：使用通用规则 + 所有语言规则的最大并集
    "auto": ["general", "python", "node", "java", "cpp", "go", "rust", "dotnet"],
}


# ══════════════════════════════════════════════════════════
# 自动黑名单生成器
# ══════════════════════════════════════════════════════════

def generate_ignore_file(workspace_dir: str, framework_type: str = "auto") -> Optional[str]:
    """
    检查工作区下是否存在 .eruitahignore。
    如果不存在，根据 framework_type 自动生成一份。

    Args:
        workspace_dir: 工作区根目录
        framework_type: 项目类型 (python/node/java/cpp/go/rust/auto 等)

    Returns:
        生成的 .eruitahignore 文件路径，或 None（如果已存在）
    """
    ignore_path = os.path.join(workspace_dir, ".eruitahignore")

    if os.path.isfile(ignore_path):
        logger.debug(f".eruitahignore 已存在: {ignore_path}")
        return None

    # 获取规则集合
    rule_keys = FRAMEWORK_RULE_MAP.get(framework_type, FRAMEWORK_RULE_MAP["auto"])

    # 合并去重
    all_rules = []
    seen = set()
    for key in rule_keys:
        rules = IGNORE_RULES.get(key, [])
        for rule in rules:
            if rule not in seen:
                seen.add(rule)
                all_rules.append(rule)

    # 写入文件
    lines = [
        "# Eruitah 智能降噪引擎 - 自动生成",
        f"# 项目类型: {framework_type}",
        f"# 规则来源: {', '.join(rule_keys)}",
        "#",
        "# 此文件用于过滤项目扫描时的噪声文件（依赖、编译产物、缓存等）",
        "# 你可以手动编辑此文件来添加或移除规则",
        "",
    ]

    for key in rule_keys:
        rules = IGNORE_RULES.get(key, [])
        if rules:
            lines.append(f"# ── {key} ──")
            for rule in rules:
                lines.append(rule)
            lines.append("")

    content = "\n".join(lines)

    try:
        with open(ignore_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"📝 已生成 .eruitahignore ({len(all_rules)} 条规则, 类型={framework_type}): {ignore_path}")
        return ignore_path
    except Exception as e:
        logger.warning(f"生成 .eruitahignore 失败: {e}")
        return None


# ══════════════════════════════════════════════════════════
# 文件过滤器
# ══════════════════════════════════════════════════════════

def _parse_ignore_file(filepath: str) -> list[str]:
    """解析 ignore 文件，返回有效规则列表"""
    rules = []
    if not os.path.isfile(filepath):
        return rules
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # 跳过空行和注释
                if not line or line.startswith("#"):
                    continue
                # 去除尾部空格和转义空格
                line = line.rstrip()
                if line.endswith("\\ "):
                    line = line[:-2] + " "
                rules.append(line)
    except Exception as e:
        logger.warning(f"读取 ignore 文件失败 {filepath}: {e}")
    return rules


def _is_ignored(
    rel_path: str,
    rules: list[str],
) -> bool:
    """
    判断一个相对路径是否被 ignore 规则命中。

    匹配逻辑（兼容 .gitignore 语义）:
      1. 规则以 / 结尾 → 只匹配目录
      2. 规则以 / 开头 → 只匹配根目录
      3. 规则包含 / → 匹配完整相对路径
      4. 其他 → 匹配任意层级的文件名或路径片段
      5. 规则以 ! 开头 → 取反（排除之前被忽略的文件）
    """
    # 分离目录规则和文件规则
    is_dir_rule = rel_path.endswith("/") or os.path.isdir(rel_path) if os.path.exists(rel_path) else False

    result = False
    for rule in rules:
        # 取反规则
        if rule.startswith("!"):
            negate_rule = rule[1:]
            if _match_pattern(rel_path, negate_rule):
                result = False
            continue

        if _match_pattern(rel_path, rule):
            result = True

    return result


def _match_pattern(rel_path: str, pattern: str) -> bool:
    """
    匹配单个规则。支持 .gitignore 风格的通配符。
    """
    # 处理目录限定规则 (以 / 结尾)
    dir_only = pattern.endswith("/")
    if dir_only:
        pattern = pattern[:-1]

    # 处理根目录限定 (以 / 开头)
    root_only = pattern.startswith("/")
    if root_only:
        pattern = pattern[1:]

    # 如果规则包含 /，匹配完整路径
    if "/" in pattern:
        if root_only:
            # 从根开始匹配
            return fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(rel_path, pattern + "/**")
        else:
            # 任意位置匹配
            return (fnmatch.fnmatch(rel_path, pattern) or
                    fnmatch.fnmatch(rel_path, "*/" + pattern) or
                    fnmatch.fnmatch(rel_path, pattern + "/**") or
                    fnmatch.fnmatch(rel_path, "*/" + pattern + "/**"))
    else:
        # 不含 / 的规则：匹配任意层级的文件名
        basename = os.path.basename(rel_path)
        if fnmatch.fnmatch(basename, pattern):
            return True
        # 也匹配路径中的任意目录段
        parts = rel_path.replace("\\", "/").split("/")
        for part in parts:
            if fnmatch.fnmatch(part, pattern):
                return True
        # 匹配完整路径
        return fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(rel_path, "*/" + pattern + "/*")


def filter_files(workspace_dir: str, file_list: list[str]) -> list[str]:
    """
    读取 .eruitahignore 和 .gitignore，过滤文件列表。

    Args:
        workspace_dir: 工作区根目录
        file_list: 待过滤的文件路径列表（相对路径或绝对路径）

    Returns:
        过滤后的纯业务代码文件列表
    """
    if not file_list:
        return []

    # 读取规则
    rules = []
    eruitahignore = os.path.join(workspace_dir, ".eruitahignore")
    gitignore = os.path.join(workspace_dir, ".gitignore")

    rules.extend(_parse_ignore_file(eruitahignore))
    rules.extend(_parse_ignore_file(gitignore))

    # 如果没有任何规则，使用通用规则兜底
    if not rules:
        rules = IGNORE_RULES["general"][:]
        logger.debug("无 ignore 文件，使用通用黑名单兜底")

    # 过滤
    kept = []
    ignored_count = 0
    for filepath in file_list:
        # 统一为相对路径
        if os.path.isabs(filepath):
            try:
                rel_path = os.path.relpath(filepath, workspace_dir)
            except ValueError:
                rel_path = filepath
        else:
            rel_path = filepath

        # 规范化路径分隔符
        rel_path = rel_path.replace("\\", "/")

        if _is_ignored(rel_path, rules):
            ignored_count += 1
        else:
            kept.append(filepath)

    if ignored_count > 0:
        logger.info(f"🔇 降噪过滤: {len(file_list)} → {len(kept)} 文件 (过滤掉 {ignored_count} 个噪声文件)")

    return kept


def get_ignore_stats(workspace_dir: str, file_list: list[str]) -> dict:
    """
    分析文件列表中被过滤的文件类型分布，用于调试和日志。

    Returns:
        {
            "total": 总文件数,
            "kept": 保留文件数,
            "ignored": 过滤文件数,
            "ignored_categories": {
                "node_modules": 123,
                "__pycache__": 45,
                ...
            }
        }
    """
    rules = []
    eruitahignore = os.path.join(workspace_dir, ".eruitahignore")
    gitignore = os.path.join(workspace_dir, ".gitignore")
    rules.extend(_parse_ignore_file(eruitahignore))
    rules.extend(_parse_ignore_file(gitignore))

    if not rules:
        rules = IGNORE_RULES["general"][:]

    kept = 0
    ignored = 0
    categories = {}

    for filepath in file_list:
        if os.path.isabs(filepath):
            try:
                rel_path = os.path.relpath(filepath, workspace_dir)
            except ValueError:
                rel_path = filepath
        else:
            rel_path = filepath

        rel_path = rel_path.replace("\\", "/")

        if _is_ignored(rel_path, rules):
            ignored += 1
            # 分类统计
            parts = rel_path.split("/")
            for part in parts:
                for category in ["node_modules", "__pycache__", ".git", "dist", "build",
                                  "target", "venv", ".venv", "coverage", ".pytest_cache",
                                  ".gradle", "cmake-build-debug", "vendor", ".next", ".nuxt"]:
                    if fnmatch.fnmatch(part, category) or fnmatch.fnmatch(part, category + "*"):
                        categories[category] = categories.get(category, 0) + 1
                        break
        else:
            kept += 1

    return {
        "total": len(file_list),
        "kept": kept,
        "ignored": ignored,
        "ignored_categories": categories,
    }
