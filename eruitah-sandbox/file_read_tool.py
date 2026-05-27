"""
Eruitah 智能编程沙盒 - 文件读取工具

本模块从 Claude Code 的 FileReadTool (TypeScript) 重写而来。
核心功能：带行号过滤的文件读取，支持只读取第 M 到 N 行。

参考源码: claude-code-rev/src/tools/FileReadTool/FileReadTool.ts

FileReadTool 在原版 Agent 中的定位是"感知工具"——
Agent 通过它查看文件内容，理解代码结构，再决定如何修改。
关键设计：必须支持行号范围过滤，因为动辄上万行的 C++ 文件
不能全扔给大模型，会撑爆 Token。
"""

import os
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================================
# 常量定义
# ============================================================================

# 单次读取最大行数，防止大文件撑爆 Token
# 对应 TS 源码中的 maxResultSizeChars 和输出截断逻辑
MAX_READ_LINES = 2000

# 单行最大字符数
MAX_LINE_LENGTH = 2000

# 最大可读取文件大小（10 MiB）
MAX_FILE_SIZE = 10 * 1024 * 1024

# 无行号范围时的最大文件行数
# 对应需求："如果文件超过 1000 行且没有指定范围，必须拒绝读取"
MAX_LINES_WITHOUT_RANGE = 1000


# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class FileReadResult:
    """
    文件读取结果

    对应 TS 源码 FileReadTool 的 outputSchema:
        { content: string, lineCount: number, truncated: boolean }
    """
    # 文件内容（带行号前缀）
    content: str = ""
    # 文件总行数
    total_lines: int = 0
    # 实际读取的行数
    lines_read: int = 0
    # 读取的起始行号（1-based）
    start_line: int = 1
    # 读取的结束行号（1-based, inclusive）
    end_line: int = 0
    # 是否被截断
    truncated: bool = False
    # 错误信息
    error: str = ""


# ============================================================================
# 核心函数
# ============================================================================

def read_file(
    file_path: str,
    start_line: int = 1,
    end_line: Optional[int] = None,
    work_dir: str = ".",
) -> FileReadResult:
    """
    读取文件内容，支持行号范围过滤

    对应 TS 源码 FileReadTool.call() 的核心逻辑:
    1. 读取文件
    2. 按行号范围过滤
    3. 添加行号前缀
    4. 截断过长行
    5. 截断过多行

    行号为 1-based（第一行是第 1 行），与编辑器和 TS 源码保持一致。

    核心安全限制:
    - 文件超过 1000 行且没有指定行号范围时，拒绝读取
    - 最大读取 2000 行
    - 最大读取 10 MiB 文件

    为什么需要行号范围过滤？
    ┌──────────────────────────────────────────────────────────────┐
    │  一个典型的 C++ 头文件可能有 5000+ 行                          │
    │  大模型上下文窗口有限（如 128K Token）                        │
    │  5000 行代码 ≈ 15000 Token                                   │
    │  如果 Agent 只需要看 main() 函数（第 200-250 行）             │
    │  读取全部 5000 行会浪费 97% 的 Token                          │
    │  因此必须支持 "只读第 M 到 N 行"                              │
    └──────────────────────────────────────────────────────────────┘

    Args:
        file_path: 文件路径（相对或绝对）
        start_line: 起始行号（1-based, inclusive），默认第 1 行
        end_line: 结束行号（1-based, inclusive），None 表示到文件末尾
        work_dir: 工作目录（用于解析相对路径）

    Returns:
        FileReadResult: 读取结果，content 中每行带 "行号→" 前缀

    Example:
        >>> # 读取整个文件
        >>> result = read_file("main.py", work_dir="/home/user/project")
        >>>
        >>> # 只读取第 10-20 行
        >>> result = read_file("main.cpp", start_line=10, end_line=20)
        >>>
        >>> # 读取从第 100 行到末尾
        >>> result = read_file("utils.py", start_line=100)
    """
    # ------------------------------------------------------------------
    # 路径解析 - 对应 TS 源码 expandPath()
    # ------------------------------------------------------------------
    if os.path.isabs(file_path):
        abs_file_path = file_path
    else:
        abs_file_path = os.path.abspath(os.path.join(work_dir, file_path))

    # 展开用户目录
    abs_file_path = os.path.expanduser(abs_file_path)

    # ------------------------------------------------------------------
    # 沙盒路径隔离校验
    # ------------------------------------------------------------------
    if work_dir and work_dir != ".":
        try:
            from sandbox_isolation import enforce_sandbox_path
            abs_file_path = enforce_sandbox_path(abs_file_path, work_dir)
        except PermissionError as e:
            return FileReadResult(error=str(e))

    # ------------------------------------------------------------------
    # 文件存在性检查 - 对应 TS 源码 isENOENT 检查
    # ------------------------------------------------------------------
    if not os.path.exists(abs_file_path):
        return FileReadResult(error=f"文件不存在: {file_path}")

    if not os.path.isfile(abs_file_path):
        return FileReadResult(error=f"路径不是文件: {file_path}")

    # ------------------------------------------------------------------
    # 文件大小检查 - 防止读取超大文件
    # ------------------------------------------------------------------
    file_size = os.path.getsize(abs_file_path)
    if file_size > MAX_FILE_SIZE:
        return FileReadResult(
            error=f"文件过大 ({file_size / 1024 / 1024:.1f} MiB)，最大可读取 {MAX_FILE_SIZE / 1024 / 1024:.0f} MiB。请使用 start_line 和 end_line 参数分段读取。"
        )

    # ------------------------------------------------------------------
    # 读取文件内容 - 对应 TS 源码 readFileContent()
    # ------------------------------------------------------------------
    try:
        with open(abs_file_path, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
    except UnicodeDecodeError:
        # 尝试其他编码
        try:
            with open(abs_file_path, 'r', encoding='latin-1') as f:
                all_lines = f.readlines()
        except Exception as e:
            return FileReadResult(error=f"无法读取文件（编码错误）: {e}")
    except PermissionError:
        return FileReadResult(error=f"无权限读取文件: {file_path}")
    except Exception as e:
        return FileReadResult(error=f"读取文件失败: {e}")

    total_lines = len(all_lines)

    # ------------------------------------------------------------------
    # 无行号范围时的行数检查
    # 对应需求："如果文件超过 1000 行且没有指定范围，必须拒绝读取"
    # ------------------------------------------------------------------
    if start_line == 1 and end_line is None:
        if total_lines > MAX_LINES_WITHOUT_RANGE:
            return FileReadResult(
                error=f"文件过大（共 {total_lines} 行），请使用 grep 搜索或指定行号读取。",
                total_lines=total_lines,
            )

    # ------------------------------------------------------------------
    # 行号范围校验
    # ------------------------------------------------------------------
    if start_line < 1:
        start_line = 1

    if end_line is None:
        end_line = total_lines
    elif end_line > total_lines:
        end_line = total_lines

    if start_line > total_lines:
        return FileReadResult(
            error=f"起始行号 {start_line} 超出文件总行数 {total_lines}",
            total_lines=total_lines,
        )

    # ------------------------------------------------------------------
    # 行数截断保护 - 防止读取过多行撑爆 Token
    # 对应 TS 源码中的 maxResultSizeChars 限制
    # ------------------------------------------------------------------
    max_end = start_line + MAX_READ_LINES - 1
    truncated = False
    if end_line > max_end:
        end_line = max_end
        truncated = True

    # ------------------------------------------------------------------
    # 提取目标行并添加行号前缀
    # 对应 TS 源码中 formatFileContent() 的行号格式化
    # ------------------------------------------------------------------
    # 行号前缀宽度: 根据最大行号计算，保证对齐
    # 例如: 总共 1234 行，则行号宽度为 4（"  1→", " 10→", "1234→"）
    line_num_width = len(str(end_line))

    output_lines = []
    for i in range(start_line - 1, end_line):
        line_text = all_lines[i].rstrip('\n\r')

        # 截断过长行
        if len(line_text) > MAX_LINE_LENGTH:
            line_text = line_text[:MAX_LINE_LENGTH] + "... [行已截断]"

        # 添加行号前缀，格式: "  42→line content"
        # 对齐 TS 源码中的 LINE_NUMBER→ 前缀格式
        line_num_str = str(i + 1).rjust(line_num_width)
        output_lines.append(f"{line_num_str}→{line_text}")

    content = "\n".join(output_lines)
    lines_read = end_line - start_line + 1

    return FileReadResult(
        content=content,
        total_lines=total_lines,
        lines_read=lines_read,
        start_line=start_line,
        end_line=end_line,
        truncated=truncated,
    )


def execute_file_read(file_path: str, start_line: Optional[int] = None, end_line: Optional[int] = None, work_dir: str = ".") -> tuple[str, bool]:
    """执行文件读取（供 agent_runner 调用）"""
    try:
        result = read_file(file_path, start_line or 1, end_line, work_dir)
        
        if result.error:
            return result.error, True
        else:
            output = f"文件 {file_path} 读取成功\n总行数: {result.total_lines}, 读取行数: {result.lines_read}\n\n"
            output += result.content
            if result.truncated:
                output += f"\n\n[文件被截断] 仅显示前 {MAX_READ_LINES} 行"
            return output, False
    except Exception as e:
        return f"文件读取失败: {str(e)}", True
