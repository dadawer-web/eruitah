"""
Eruitah 智能编程沙盒 - Grep 正则搜索工具

本模块从 Claude Code 的 GrepTool (TypeScript) 重写而来。
核心功能：全库正则搜索代码，支持 ripgrep (rg) 加速回退到 grep。

参考源码: claude-code-rev/src/tools/GrepTool/GrepTool.ts

GrepTool 在原版 Agent 中的定位是"感知工具"——
Agent 通过它搜索代码中的函数定义、变量引用、错误模式等。
"""

import subprocess
import shutil
import re
import os
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================================
# 常量定义
# ============================================================================

# 最大匹配行数，防止搜索结果撑爆 Token
# 对应 TS 源码中的 maxResultSizeChars 和输出截断逻辑
MAX_MATCH_LINES = 200

# 每行最大显示字符数
MAX_LINE_LENGTH = 500

# 截断提示
TRUNCATION_NOTICE = "\n... [搜索结果已截断，共 {total} 行匹配，仅显示前 {shown} 行] ..."


# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class GrepMatch:
    """
    单行匹配结果

    对应 TS 源码中 ripgrep 输出的单行数据:
        { file_path, line_number, line_text }
    """
    # 文件路径（相对路径）
    file_path: str
    # 行号
    line_number: int
    # 匹配的行内容
    line_text: str


@dataclass
class GrepResult:
    """
    Grep 搜索结果

    对应 TS 源码 GrepTool 的 outputSchema
    """
    # 匹配行列表
    matches: list[GrepMatch] = None
    # 是否被截断
    truncated: bool = False
    # 匹配总行数（截断前）
    total_matches: int = 0
    # 使用的搜索引擎（"rg" 或 "grep"）
    engine_used: str = ""
    # 错误信息
    error: str = ""

    def __post_init__(self):
        if self.matches is None:
            self.matches = []


# ============================================================================
# 搜索引擎检测
# ============================================================================

def _detect_grep_engine() -> str:
    """
    检测系统可用的搜索引擎

    优先级: ripgrep (rg) > GNU grep
    ripgrep 比 grep 快 10-100 倍，且默认支持 .gitignore

    Returns:
        "rg" 或 "grep"
    """
    if shutil.which("rg"):
        return "rg"
    if shutil.which("grep"):
        return "grep"
    return ""


# ============================================================================
# ripgrep 执行器 - 对应 TS 源码中调用 rg 的逻辑
# ============================================================================

def _grep_with_ripgrep(
    pattern: str,
    work_dir: str,
    file_pattern: Optional[str] = None,
    case_insensitive: bool = False,
    max_results: int = MAX_MATCH_LINES,
) -> GrepResult:
    """
    使用 ripgrep (rg) 执行搜索

    对应 TS 源码中通过子进程调用 rg 的逻辑。
    ripgrep 的优势:
    - 默认尊重 .gitignore
    - 自动跳过隐藏文件和二进制文件
    - 速度极快（Rust 实现，多线程）
    - 原生支持行号输出

    Args:
        pattern: 正则表达式模式
        work_dir: 搜索根目录
        file_pattern: 文件过滤模式（如 "*.py"）
        case_insensitive: 是否忽略大小写
        max_results: 最大返回行数

    Returns:
        GrepResult: 搜索结果
    """
    # 构建 rg 命令
    # --line-number: 显示行号
    # --no-heading: 不显示文件头
    # --color=never: 禁用颜色
    # --max-count: 限制每个文件的匹配数
    cmd = [
        "rg",
        "--line-number",
        "--no-heading",
        "--color=never",
        "--max-count", str(max_results),
    ]

    if case_insensitive:
        cmd.append("-i")

    if file_pattern:
        cmd.extend(["--glob", file_pattern])

    cmd.extend([
        "--regexp", pattern,
        work_dir,
    ])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return GrepResult(error="搜索超时（30秒），请缩小搜索范围或使用更精确的模式")
    except FileNotFoundError:
        return GrepResult(error="ripgrep (rg) 未安装")

    # rg 退出码: 0=有匹配, 1=无匹配, 2=错误
    if result.returncode == 1:
        return GrepResult(matches=[], engine_used="rg")
    if result.returncode == 2:
        return GrepResult(error=f"ripgrep 错误: {result.stderr.strip()}")

    # 解析输出
    return _parse_grep_output(result.stdout, work_dir, "rg", max_results)


# ============================================================================
# GNU grep 执行器 - ripgrep 不可用时的回退方案
# ============================================================================

def _grep_with_gnu(
    pattern: str,
    work_dir: str,
    file_pattern: Optional[str] = None,
    case_insensitive: bool = False,
    max_results: int = MAX_MATCH_LINES,
) -> GrepResult:
    """
    使用 GNU grep 执行搜索（ripgrep 不可用时的回退方案）

    对应 TS 源码中当 rg 不可用时的降级策略。

    Args:
        pattern: 正则表达式模式
        work_dir: 搜索根目录
        file_pattern: 文件过滤模式（如 "*.py"）
        case_insensitive: 是否忽略大小写
        max_results: 最大返回行数

    Returns:
        GrepResult: 搜索结果
    """
    # 构建 grep 命令
    # -n: 显示行号
    # -E: 扩展正则表达式
    # -r: 递归搜索
    # --exclude-dir: 排除目录
    cmd = [
        "grep",
        "-n",
        "-E",
        "-r",
        "--exclude-dir=.git",
        "--exclude-dir=node_modules",
        "--exclude-dir=__pycache__",
        "--exclude-dir=.venv",
        "--exclude-dir=venv",
        "--exclude-dir=build",
        "--exclude-dir=dist",
        "--exclude-dir=target",
        "--binary-files=without-match",
    ]

    if case_insensitive:
        cmd.append("-i")

    if file_pattern:
        cmd.extend(["--include", file_pattern])

    cmd.extend([
        pattern,
        work_dir,
    ])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return GrepResult(error="搜索超时（60秒），请缩小搜索范围")
    except FileNotFoundError:
        return GrepResult(error="grep 未安装")

    # grep 退出码: 0=有匹配, 1=无匹配, 2=错误
    if result.returncode == 1:
        return GrepResult(matches=[], engine_used="grep")
    if result.returncode == 2:
        return GrepResult(error=f"grep 错误: {result.stderr.strip()}")

    return _parse_grep_output(result.stdout, work_dir, "grep", max_results)


# ============================================================================
# 输出解析 - 统一解析 rg 和 grep 的输出格式
# ============================================================================

def _parse_grep_output(
    output: str,
    work_dir: str,
    engine: str,
    max_results: int,
) -> GrepResult:
    """
    解析 grep/rg 的标准输出

    输出格式（两者一致）:
        文件路径:行号:行内容
        例如: src/main.py:42:def hello():

    Args:
        output: grep/rg 的原始输出
        work_dir: 工作目录（用于生成相对路径）
        engine: 使用的搜索引擎
        max_results: 最大返回行数

    Returns:
        GrepResult: 解析后的搜索结果
    """
    matches = []
    abs_work_dir = os.path.abspath(work_dir)

    for line in output.splitlines():
        if not line.strip():
            continue

        # 解析 "文件路径:行号:行内容" 格式
        # 注意: Windows 路径可能包含冒号（如 C:\），需要特殊处理
        # 策略: 找到第一个 ":数字:" 模式
        match = re.match(r'^(.+?):(\d+):(.*)$', line)
        if not match:
            continue

        file_path = match.group(1)
        line_number = int(match.group(2))
        line_text = match.group(3)

        # 转换为相对路径
        try:
            rel_path = os.path.relpath(file_path, abs_work_dir)
        except ValueError:
            rel_path = file_path

        # 截断过长的行
        if len(line_text) > MAX_LINE_LENGTH:
            line_text = line_text[:MAX_LINE_LENGTH] + "... [行已截断]"

        matches.append(GrepMatch(
            file_path=rel_path,
            line_number=line_number,
            line_text=line_text,
        ))

    total = len(matches)
    truncated = total > max_results

    if truncated:
        matches = matches[:max_results]

    return GrepResult(
        matches=matches,
        truncated=truncated,
        total_matches=total,
        engine_used=engine,
    )


# ============================================================================
# 纯 Python 回退搜索 - 当 rg 和 grep 都不可用时
# ============================================================================

def _grep_with_python(
    pattern: str,
    work_dir: str,
    file_pattern: Optional[str] = None,
    case_insensitive: bool = False,
    max_results: int = MAX_MATCH_LINES,
) -> GrepResult:
    """
    纯 Python 实现的正则搜索（rg 和 grep 都不可用时的最终回退）

    使用 os.walk + re 模块实现，速度较慢但保证可用。

    Args:
        pattern: 正则表达式模式
        work_dir: 搜索根目录
        file_pattern: 文件过滤模式（如 "*.py"），支持 fnmatch 语法
        file_pattern: 文件过滤模式
        case_insensitive: 是否忽略大小写
        max_results: 最大返回行数

    Returns:
        GrepResult: 搜索结果
    """
    import fnmatch

    flags = re.IGNORECASE if case_insensitive else 0
    try:
        regex = re.compile(pattern, flags)
    except re.error as e:
        return GrepResult(error=f"无效的正则表达式: {e}")

    matches = []
    abs_work_dir = os.path.abspath(work_dir)
    ignore_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "build", "dist", "target"}

    for root, dirs, files in os.walk(abs_work_dir):
        # 过滤忽略目录（原地修改 dirs 列表影响 os.walk 的遍历）
        dirs[:] = [d for d in dirs if d not in ignore_dirs]

        for filename in files:
            # 文件模式过滤
            if file_pattern and not fnmatch.fnmatch(filename, file_pattern):
                continue

            file_path = os.path.join(root, filename)
            rel_path = os.path.relpath(file_path, abs_work_dir)

            try:
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    for line_num, line in enumerate(f, 1):
                        if regex.search(line):
                            line_text = line.rstrip()
                            if len(line_text) > MAX_LINE_LENGTH:
                                line_text = line_text[:MAX_LINE_LENGTH] + "... [行已截断]"
                            matches.append(GrepMatch(
                                file_path=rel_path,
                                line_number=line_num,
                                line_text=line_text,
                            ))
                            if len(matches) >= max_results * 2:
                                break
            except (OSError, UnicodeDecodeError):
                continue

            if len(matches) >= max_results * 2:
                break

    total = len(matches)
    truncated = total > max_results
    if truncated:
        matches = matches[:max_results]

    return GrepResult(
        matches=matches,
        truncated=truncated,
        total_matches=total,
        engine_used="python",
    )


# ============================================================================
# 核心入口函数
# ============================================================================

def grep_search(
    pattern: str,
    work_dir: str = ".",
    file_pattern: Optional[str] = None,
    case_insensitive: bool = False,
    max_results: int = MAX_MATCH_LINES,
) -> GrepResult:
    """
    全库正则搜索 - 核心入口函数

    对应 TS 源码 GrepTool.call() 的核心逻辑:
    1. 检测可用搜索引擎（rg > grep > python）
    2. 执行搜索
    3. 解析结果
    4. 截断输出防止 Token 爆炸

    搜索引擎优先级:
    - ripgrep (rg): 最快，默认尊重 .gitignore
    - GNU grep: 次选，需要手动排除目录
    - Python re: 最终回退，速度较慢但保证可用

    Args:
        pattern: 正则表达式模式
        work_dir: 搜索根目录
        file_pattern: 文件过滤模式（如 "*.py"、"*.cpp"）
        case_insensitive: 是否忽略大小写
        max_results: 最大返回匹配行数

    Returns:
        GrepResult: 搜索结果

    Example:
        >>> result = grep_search("def hello", work_dir="/home/user/project", file_pattern="*.py")
        >>> for m in result.matches:
        ...     print(f"{m.file_path}:{m.line_number}: {m.line_text}")
    """
    abs_work_dir = os.path.abspath(work_dir)

    if not os.path.isdir(abs_work_dir):
        return GrepResult(error=f"搜索目录不存在: {abs_work_dir}")

    # 验证正则表达式
    try:
        re.compile(pattern)
    except re.error as e:
        return GrepResult(error=f"无效的正则表达式 '{pattern}': {e}")

    # ------------------------------------------------------------------
    # 按优先级选择搜索引擎
    # ------------------------------------------------------------------
    engine = _detect_grep_engine()

    if engine == "rg":
        result = _grep_with_ripgrep(
            pattern=pattern,
            work_dir=abs_work_dir,
            file_pattern=file_pattern,
            case_insensitive=case_insensitive,
            max_results=max_results,
        )
    elif engine == "grep":
        result = _grep_with_gnu(
            pattern=pattern,
            work_dir=abs_work_dir,
            file_pattern=file_pattern,
            case_insensitive=case_insensitive,
            max_results=max_results,
        )
    else:
        # 最终回退: 纯 Python 实现
        result = _grep_with_python(
            pattern=pattern,
            work_dir=abs_work_dir,
            file_pattern=file_pattern,
            case_insensitive=case_insensitive,
            max_results=max_results,
        )

    # 如果搜索无结果，给出优雅的错误提示
    if not result.error and not result.matches:
        result.error = (
            f"未找到匹配 '{pattern}' 的内容。\n"
            f"建议:\n"
            f"  1. 检查正则表达式是否正确\n"
            f"  2. 尝试使用 case_insensitive=True 忽略大小写\n"
            f"  3. 使用 file_pattern 限制搜索文件类型（如 '*.py'）\n"
            f"  4. 扩大搜索目录范围"
        )

    return result


def execute_grep(pattern: str, path: str = ".") -> tuple[str, bool]:
    """执行 grep 搜索（供 agent_runner 调用）"""
    try:
        result = grep_search(pattern, work_dir=path)
        
        if result.error:
            return result.error, True
        else:
            output = f"Grep 搜索 '{pattern}' 完成\n使用引擎: {result.engine_used}\n找到 {result.total_matches} 个匹配"
            if result.truncated:
                output += f"，仅显示前 {MAX_MATCH_LINES} 个"
            output += "\n\n"
            
            for match in result.matches:
                output += f"{match.file_path}:{match.line_number}: {match.line_text}\n"
            
            return output, False
    except Exception as e:
        return f"Grep 搜索失败: {str(e)}", True
