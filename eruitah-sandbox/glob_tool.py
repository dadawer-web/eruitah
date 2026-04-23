"""
Eruitah 智能编程沙盒 - Glob 文件模式匹配工具

本模块从 Claude Code 的 GlobTool (TypeScript) 重写而来。
核心功能：基于 glob 模式快速查找文件路径，支持 ** 递归匹配。

参考源码: claude-code-rev/src/tools/GlobTool/GlobTool.ts

GlobTool 在原版 Agent 中的定位是"感知工具"——
Agent 通过它发现项目中有哪些文件，再决定读取或编辑哪些。
"""

import os
import glob as globlib
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================================
# 常量定义
# ============================================================================

# 最大返回文件数，防止匹配到海量文件时撑爆 Token
# 对应 TS 源码中 maxResultSizeChars 和输出截断逻辑
MAX_RESULTS = 200

# 默认忽略的目录模式 - 对应 TS 源码中的 ignore 模式
# 这些目录通常包含大量生成文件，对 AI 没有参考价值
DEFAULT_IGNORE_PATTERNS = [
    "node_modules",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".idea",
    ".vscode",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "target",
    ".gradle",
    ".mvn",
]


# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class GlobResult:
    """
    Glob 查找结果

    对应 TS 源码 GlobTool 的 outputSchema:
        { files: string[], truncated: boolean }
    """
    # 匹配到的文件路径列表
    files: list[str] = None
    # 是否被截断（结果超过 MAX_RESULTS）
    truncated: bool = False
    # 匹配总数（截断前）
    total_matches: int = 0
    # 错误信息
    error: str = ""

    def __post_init__(self):
        if self.files is None:
            self.files = []


# ============================================================================
# 核心函数
# ============================================================================

def glob_search(
    pattern: str,
    work_dir: str = ".",
    ignore_patterns: Optional[list[str]] = None,
    max_results: int = MAX_RESULTS,
) -> GlobResult:
    """
    基于 glob 模式查找文件

    对应 TS 源码 GlobTool.call() 的核心逻辑:
    1. 解析 glob 模式
    2. 遍历目录树匹配
    3. 过滤忽略目录
    4. 截断结果防止 Token 爆炸

    支持的 glob 模式:
    - *: 匹配任意文件名（不含路径分隔符）
    - **: 递归匹配任意层目录
    - ?: 匹配单个字符
    - [abc]: 匹配括号内任意字符
    - [0-9]: 匹配范围内字符

    Args:
        pattern: glob 模式，如 "**/*.py"、"src/**/*.ts"
        work_dir: 搜索根目录
        ignore_patterns: 要忽略的目录名列表
        max_results: 最大返回结果数

    Returns:
        GlobResult: 查找结果

    Example:
        >>> result = glob_search("**/*.py", work_dir="/home/user/project")
        >>> for f in result.files:
        ...     print(f)
    """
    abs_work_dir = os.path.abspath(work_dir)

    if not os.path.isdir(abs_work_dir):
        return GlobResult(error=f"工作目录不存在: {abs_work_dir}")

    # 合并忽略模式
    ignores = set(ignore_patterns or []) | set(DEFAULT_IGNORE_PATTERNS)

    # ------------------------------------------------------------------
    # 第一步: 使用 Python glob 库执行匹配
    # 对应 TS 源码中的 glob(pattern, { cwd, ignore })
    # ------------------------------------------------------------------
    try:
        # 构建完整路径模式
        if os.path.isabs(pattern):
            full_pattern = pattern
        else:
            full_pattern = os.path.join(abs_work_dir, pattern)

        # 使用 glob.glob 的 recursive=True 支持 ** 模式
        # 对应 TS 源码中 glob 模块的匹配逻辑
        matched_paths = globlib.glob(full_pattern, recursive=True)
    except Exception as e:
        return GlobResult(error=f"Glob 匹配异常: {e}")

    # ------------------------------------------------------------------
    # 第二步: 过滤忽略目录和非常规文件
    # 对应 TS 源码中的 ignore 模式过滤
    # ------------------------------------------------------------------
    filtered_files = []
    for path in matched_paths:
        # 只保留文件（排除目录）
        if not os.path.isfile(path):
            continue

        # 检查路径中是否包含忽略的目录
        # 例如 /project/node_modules/foo.js 应被过滤
        rel_path = os.path.relpath(path, abs_work_dir)
        path_parts = rel_path.split(os.sep)

        should_ignore = False
        for part in path_parts:
            if part in ignores:
                should_ignore = True
                break

        if should_ignore:
            continue

        # 返回相对路径（对齐 TS 源码的行为：返回相对于 cwd 的路径）
        filtered_files.append(rel_path)

    # ------------------------------------------------------------------
    # 第三步: 排序和截断
    # 对应 TS 源码中的输出截断逻辑
    # ------------------------------------------------------------------
    # 按路径排序，保证结果确定性
    filtered_files.sort()

    total_matches = len(filtered_files)

    if len(filtered_files) > max_results:
        truncated = True
        filtered_files = filtered_files[:max_results]
    else:
        truncated = False

    return GlobResult(
        files=filtered_files,
        truncated=truncated,
        total_matches=total_matches,
    )


def execute_glob(pattern: str, work_dir: str = ".") -> tuple[str, bool]:
    """执行 glob 搜索（供 agent_runner 调用）"""
    try:
        result = glob_search(pattern, work_dir)
        
        if result.error:
            return result.error, True
        else:
            output = f"Glob 搜索 '{pattern}' 完成\n找到 {result.total_matches} 个文件"
            if result.truncated:
                output += f"，仅显示前 {MAX_RESULTS} 个"
            output += "\n\n"
            output += "\n".join(result.files)
            return output, False
    except Exception as e:
        return f"Glob 搜索失败: {str(e)}", True
