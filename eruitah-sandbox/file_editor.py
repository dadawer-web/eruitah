"""
Eruitah 智能编程沙盒 - 文件编辑器

本模块从 Claude Code 的 FileEditTool (TypeScript) 重写而来，保留了核心编辑逻辑：
1. SEARCH/REPLACE 模式 - 局部替换而非全文件覆写
2. 唯一性校验 - old_string 必须在文件中唯一匹配（除非 replace_all=True）
3. 引号规范化 - 处理弯引号与直引号的差异
4. 文件不存在/匹配失败的异常处理

参考源码: claude-code-rev/src/tools/FileEditTool/FileEditTool.ts
         claude-code-rev/src/tools/FileEditTool/utils.ts
"""

import os
import re
import difflib
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================================
# 常量定义
# ============================================================================

# 最大可编辑文件大小（1 GiB），对应 TS 源码 MAX_EDIT_FILE_SIZE
MAX_EDIT_FILE_SIZE = 1024 * 1024 * 1024

# 弯引号常量 - 对应 TS 源码中的 LEFT/RIGHT_SINGLE/CURLY_QUOTE
# Claude 无法输出弯引号，但文件中可能存在弯引号，需要规范化处理
LEFT_SINGLE_CURLY_QUOTE = '\u2018'   # '
RIGHT_SINGLE_CURLY_QUOTE = '\u2019'  # '
LEFT_DOUBLE_CURLY_QUOTE = '\u201c'   # "
RIGHT_DOUBLE_CURLY_QUOTE = '\u201d'  # "


# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class EditResult:
    """
    文件编辑结果，对齐 TS 源码中的 FileEditOutput

    对应源码:
        outputSchema = z.object({
            filePath: z.string(),
            oldString: z.string(),
            newString: z.string(),
            ...
        })
    """
    # 是否编辑成功
    success: bool = True
    # 编辑的文件路径
    file_path: str = ""
    # 实际被替换的旧文本（可能经过引号规范化）
    actual_old_string: str = ""
    # 新文本
    new_string: str = ""
    # 错误信息（失败时）
    error: str = ""
    # diff 补丁（用于前端展示变更）
    diff_patch: str = ""
    # 是否是新建文件
    is_new_file: bool = False


# ============================================================================
# 引号规范化 - 对应 TS 源码 normalizeQuotes() 和 findActualString()
# ============================================================================

def normalize_quotes(text: str) -> str:
    """
    将弯引号规范化为直引号

    对应 TS 源码:
        function normalizeQuotes(str: string): string {
            return str
                .replaceAll(LEFT_SINGLE_CURLY_QUOTE, "'")
                .replaceAll(RIGHT_SINGLE_CURLY_QUOTE, "'")
                .replaceAll(LEFT_DOUBLE_CURLY_QUOTE, '"')
                .replaceAll(RIGHT_DOUBLE_CURLY_QUOTE, '"')
        }

    大模型（如 Claude）输出的是直引号，但文件中可能使用弯引号。
    如果直接用直引号去匹配弯引号文件，会匹配失败。
    因此需要先规范化，再进行匹配。

    Args:
        text: 待规范化的文本

    Returns:
        规范化后的文本（弯引号 -> 直引号）
    """
    return (
        text
        .replace(LEFT_SINGLE_CURLY_QUOTE, "'")
        .replace(RIGHT_SINGLE_CURLY_QUOTE, "'")
        .replace(LEFT_DOUBLE_CURLY_QUOTE, '"')
        .replace(RIGHT_DOUBLE_CURLY_QUOTE, '"')
    )


def find_actual_string(file_content: str, search_string: str) -> Optional[str]:
    """
    在文件内容中查找实际匹配的字符串，处理引号规范化

    对应 TS 源码:
        function findActualString(fileContent, searchString): string | null {
            // 先精确匹配
            if (fileContent.includes(searchString)) return searchString
            // 再用规范化后的版本匹配
            const normalizedSearch = normalizeQuotes(searchString)
            const normalizedFile = normalizeQuotes(fileContent)
            const searchIndex = normalizedFile.indexOf(normalizedSearch)
            if (searchIndex !== -1) {
                return fileContent.substring(searchIndex, searchIndex + searchString.length)
            }
            return null
        }

    这个函数的关键在于: 大模型输出的 search_string 用的是直引号，
    但文件里可能用的是弯引号。我们需要:
    1. 先尝试精确匹配（最快路径）
    2. 精确匹配失败后，对两边都做引号规范化，再匹配
    3. 匹配成功时，返回文件中的原始文本（保留弯引号）

    Args:
        file_content: 文件内容
        search_string: 搜索字符串（来自大模型，可能是直引号）

    Returns:
        文件中实际匹配的字符串，或 None（未找到）
    """
    # 1. 精确匹配 - 最快路径
    if search_string in file_content:
        return search_string

    # 2. 引号规范化后匹配
    normalized_search = normalize_quotes(search_string)
    normalized_file = normalize_quotes(file_content)

    search_index = normalized_file.find(normalized_search)
    if search_index != -1:
        # 返回文件中的原始文本（保留弯引号风格）
        # 对应 TS: return fileContent.substring(searchIndex, searchIndex + searchString.length)
        return file_content[search_index:search_index + len(search_string)]

    return None


# ============================================================================
# Diff 补丁生成 - 对应 TS 源码 getPatchForEdit() / getPatchFromContents()
# ============================================================================

def generate_diff_patch(
    file_path: str,
    old_content: str,
    new_content: str,
    context_lines: int = 4,
) -> str:
    """
    生成 unified diff 格式的补丁，用于前端展示变更

    对应 TS 源码:
        getPatchFromContents({ filePath, oldContent, newContent })

    使用 Python 标准库 difflib.unified_diff 生成补丁，
    与 TS 源码中使用 jsdiff 库的 structuredPatch 功能等价。

    Args:
        file_path: 文件路径（用于 diff 头部信息）
        old_content: 修改前的文件内容
        new_content: 修改后的文件内容
        context_lines: 上下文行数，对应 TS 源码中的 CONTEXT_LINES = 4

    Returns:
        unified diff 格式的补丁字符串
    """
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    diff_lines = list(difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{os.path.basename(file_path)}",
        tofile=f"b/{os.path.basename(file_path)}",
        n=context_lines,
    ))

    return "".join(diff_lines)


# ============================================================================
# 核心编辑函数 - 对应 TS 源码 FileEditTool.call()
# ============================================================================

def edit_file(
    file_path: str,
    search_text: str,
    replace_text: str,
    replace_all: bool = False,
    session_id: str = None,
    turn: int = 0,
) -> EditResult:
    """
    文件编辑核心函数 - SEARCH/REPLACE 模式

    对应 TS 源码 FileEditTool.call() 的核心逻辑:
    1. 读取文件 -> 2. 查找匹配 -> 3. 唯一性校验 -> 4. 执行替换 -> 5. 写回文件 -> 6. 生成 diff

    工作原理（SEARCH/REPLACE 模式）:
    ┌─────────────────────────────────────────────────────┐
    │  大模型输出:                                         │
    │    search_text:  "def hello():"                      │
    │    replace_text: "def hello(name):"                  │
    │                                                     │
    │  文件内容:                                           │
    │    1: def hello():                                   │
    │    2:     print("world")                             │
    │                                                     │
    │  替换后:                                             │
    │    1: def hello(name):                               │
    │    2:     print("world")                             │
    └─────────────────────────────────────────────────────┘

    Args:
        file_path: 文件路径（相对或绝对）
        search_text: 要查找的文本（SEARCH 部分）
        replace_text: 要替换为的文本（REPLACE 部分）
        replace_all: 是否替换所有匹配（默认只替换第一个）

    Returns:
        EditResult: 编辑结果，包含成功/失败、diff 补丁等信息

    Example:
        >>> result = edit_file(
        ...     "/path/to/main.py",
        ...     "def hello():",
        ...     "def hello(name):"
        ... )
        >>> if result.success:
        ...     print("编辑成功!")
        ...     print(result.diff_patch)
    """
    # ------------------------------------------------------------------
    # 路径规范化 - 对应 TS 源码 expandPath(file_path)
    # ------------------------------------------------------------------
    abs_file_path = os.path.abspath(os.path.expanduser(file_path))

    # ------------------------------------------------------------------
    # 第一步: 读取文件 - 对应 TS 源码 readFileForEdit()
    # ------------------------------------------------------------------
    is_new_file = not os.path.exists(abs_file_path)

    if is_new_file:
        # 文件不存在的情况
        # 对应 TS 源码: if (fileContent === null) { ... }
        if search_text == "":
            # search_text 为空 + 文件不存在 = 创建新文件
            # 对应 TS: "Empty old_string on nonexistent file means new file creation — valid"
            file_content = ""
        else:
            # 文件不存在且 search_text 非空 -> 错误
            return EditResult(
                success=False,
                file_path=file_path,
                error=f"文件不存在: {abs_file_path}。如果需要创建新文件，请将 search_text 设为空字符串。",
            )
    else:
        # 文件存在 - 修改前自动备份
        if session_id:
            try:
                from session_storage import get_storage
                storage = get_storage()
                storage.save_file_snapshot(session_id, turn, abs_file_path, "edit")
            except Exception as e:
                logger.warning(f"文件快照保存失败: {e}")
        
        # 文件存在 - 检查大小
        file_size = os.path.getsize(abs_file_path)
        if file_size > MAX_EDIT_FILE_SIZE:
            return EditResult(
                success=False,
                file_path=file_path,
                error=f"文件过大 ({file_size} 字节)，最大可编辑 {MAX_EDIT_FILE_SIZE} 字节。",
            )

        # 读取文件内容
        try:
            with open(abs_file_path, 'r', encoding='utf-8') as f:
                file_content = f.read()
        except UnicodeDecodeError:
            # 尝试其他编码 - 对应 TS 源码中的 detectFileEncoding
            try:
                with open(abs_file_path, 'r', encoding='latin-1') as f:
                    file_content = f.read()
            except Exception as e:
                return EditResult(
                    success=False,
                    file_path=file_path,
                    error=f"无法读取文件: {e}",
                )
        except Exception as e:
            return EditResult(
                success=False,
                file_path=file_path,
                error=f"无法读取文件: {e}",
            )

    # ------------------------------------------------------------------
    # 第二步: 处理空文件 + 空 search_text 的情况
    # 对应 TS 源码: "Empty file with empty old_string is valid"
    # ------------------------------------------------------------------
    if search_text == "":
        if file_content.strip() != "" and not is_new_file:
            # 文件非空但 search_text 为空 -> 不能"创建"已存在的非空文件
            return EditResult(
                success=False,
                file_path=file_path,
                error="文件已存在且非空，无法使用空 search_text 创建。",
            )
        # 创建新文件或替换空文件
        new_content = replace_text
    else:
        # ------------------------------------------------------------------
        # 第三步: 查找匹配 - 对应 TS 源码 findActualString()
        # ------------------------------------------------------------------
        actual_old_string = find_actual_string(file_content, search_text)

        if actual_old_string is None:
            # 匹配失败 - 提供有用的错误信息
            # 对应 TS 源码: "String to replace not found in file"
            return EditResult(
                success=False,
                file_path=file_path,
                error=(
                    f"未在文件中找到匹配的文本。\n"
                    f"搜索文本: {search_text[:200]}{'...' if len(search_text) > 200 else ''}\n"
                    f"提示: 请确保 search_text 与文件中的内容完全一致（包括缩进和空格）。"
                ),
            )

        # ------------------------------------------------------------------
        # 第四步: 唯一性校验 - 对应 TS 源码中的 matches 检查
        # ------------------------------------------------------------------
        if not replace_all:
            # 计算匹配次数
            match_count = file_content.count(actual_old_string)

            if match_count > 1:
                # 多处匹配但 replace_all=False -> 需要更多上下文来唯一标识
                # 对应 TS: "Found N matches of the string to replace, but replace_all is false"
                return EditResult(
                    success=False,
                    file_path=file_path,
                    error=(
                        f"在文件中找到 {match_count} 处匹配，但 replace_all=False。\n"
                        f"请提供更多上下文使匹配唯一，或设置 replace_all=True 替换所有匹配。"
                    ),
                )

        # ------------------------------------------------------------------
        # 第五步: 执行替换 - 对应 TS 源码 applyEditToFile()
        # ------------------------------------------------------------------
        if replace_all:
            # 替换所有匹配
            new_content = file_content.replace(actual_old_string, replace_text)
        else:
            # 只替换第一个匹配
            new_content = file_content.replace(actual_old_string, replace_text, 1)

        # 检查替换是否真的改变了内容
        # 对应 TS: "if (updatedFile === previousContent) { throw new Error('String not found') }"
        if new_content == file_content:
            return EditResult(
                success=False,
                file_path=file_path,
                error="替换后内容未发生变化（search_text 和 replace_text 可能等价）。",
            )

    # ------------------------------------------------------------------
    # 第六步: 确保目标目录存在 - 对应 TS 源码 fs.mkdir(dirname())
    # ------------------------------------------------------------------
    dir_name = os.path.dirname(abs_file_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    # ------------------------------------------------------------------
    # 第七步: 写回文件 - 对应 TS 源码 writeTextContent()
    # ------------------------------------------------------------------
    try:
        with open(abs_file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
    except Exception as e:
        return EditResult(
            success=False,
            file_path=file_path,
            error=f"写入文件失败: {e}",
        )

    # ------------------------------------------------------------------
    # 第八步: 生成 diff 补丁 - 对应 TS 源码 getPatchForEdit()
    # ------------------------------------------------------------------
    diff_patch = generate_diff_patch(abs_file_path, file_content, new_content)

    return EditResult(
        success=True,
        file_path=file_path,
        actual_old_string=search_text if search_text == "" else (actual_old_string or search_text),
        new_string=replace_text,
        diff_patch=diff_patch,
        is_new_file=is_new_file,
    )


def execute_file_edit(file_path: str, search_text: str, replace_text: str, work_dir: str = ".") -> tuple[str, bool]:
    """执行文件编辑（供 agent_runner 调用）"""
    try:
        # 切换到工作目录
        original_dir = os.getcwd()
        os.chdir(work_dir)
        
        result = edit_file(file_path, search_text, replace_text)
        
        os.chdir(original_dir)
        
        if result.success:
            if result.is_new_file:
                return f"文件创建成功: {result.file_path}", False
            else:
                return f"文件编辑成功: {result.file_path}\n\n{result.diff_patch}", False
        else:
            return result.error, True
    except Exception as e:
        return f"文件编辑失败: {str(e)}", True
