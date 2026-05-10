"""
Eruitah 智能编程沙盒 - Bash 命令执行器

本模块从 Claude Code 的 BashTool (TypeScript) 重写而来，保留了核心安全机制：
1. 危险命令拦截 - 阻止 rm -rf /、恶意命令替换等
2. 超时保护 - 防止命令无限挂起
3. 输出截断 - 防止大模型 Token 爆炸（超过阈值自动截断）
4. 沙箱路径限制 - 限制命令只能在工作目录内操作

参考源码: claude-code-rev/src/tools/BashTool/BashTool.tsx
         claude-code-rev/src/tools/BashTool/bashSecurity.ts
"""

import subprocess
import re
import os
import signal
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================================
# 常量定义 - 对齐 Claude Code 源码中的硬编码值
# ============================================================================

# 默认命令超时时间（毫秒），对应 TS 源码 getDefaultTimeoutMs()
DEFAULT_TIMEOUT_MS = 120_000

# 最大命令超时时间（毫秒），对应 TS 源码 getMaxTimeoutMs()
MAX_TIMEOUT_MS = 600_000

# 输出截断阈值（字符数），防止大模型 Token 爆炸
# 对应 TS 源码 maxResultSizeChars = 30_000，这里我们用更保守的 2000
# 因为用户明确要求"如果输出超过 2000 字符，自动截断"
MAX_OUTPUT_CHARS = 2000

# 截断提示后缀
TRUNCATION_NOTICE = "\n... [输出已截断，共 {total} 字符，仅显示前 {shown} 字符] ..."


# ============================================================================
# 危险命令黑名单 - 对齐 bashSecurity.ts 中的安全校验
# ============================================================================

# 绝对禁止执行的命令模式（匹配即拦截，不进入权限询问流程）
BLOCKED_PATTERNS: list[re.Pattern] = [
    re.compile(r'\brm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?-r[a-zA-Z]*\s+(/|\*\s*$)', re.IGNORECASE),
    re.compile(r'\brm\s+-r[a-zA-Z]*\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?(/|\*\s*$)', re.IGNORECASE),
    re.compile(r'\brm\s+-rf\s+~', re.IGNORECASE),
    re.compile(r'\brm\s+-rf\s+/home', re.IGNORECASE),
    re.compile(r'\brm\s+-rf\s+/etc', re.IGNORECASE),
    re.compile(r'\brm\s+-rf\s+/var', re.IGNORECASE),
    re.compile(r'\bmkfs\b'),
    re.compile(r'\bdd\s+.*of=/dev/'),
    re.compile(r'>\s*/dev/sd[a-z]', re.IGNORECASE),
    re.compile(r'>\s*/dev/sda\b', re.IGNORECASE),
    re.compile(r':\(\)\{\s*:\|:&\s*\};\s*:'),
    re.compile(r'\bchmod\s+777\s+(/|/etc|/usr|/bin|/sbin|/root)\b'),
    re.compile(r'>\s*/etc/passwd\b'),
    re.compile(r'>\s*/etc/shadow\b'),
    re.compile(r'>\s*/etc/sudoers\b'),
    re.compile(r'\breboot\b'),
    re.compile(r'\bshutdown\b'),
    re.compile(r'\binit\s+[06]\b'),
    re.compile(r'\bgit\s+push\s+--force\b'),
    re.compile(r'\bgit\s+push\s+-f\b'),
    re.compile(r'\biptables\s+-F\b'),
    re.compile(r'\bkill\s+-9\s+1\b'),
    re.compile(r'\bmv\s+.*\s+/dev/null\b'),
    re.compile(r'\bformat\s+[A-Z]:', re.IGNORECASE),
]

# 需要警告但可由调用方决定是否放行的命令模式
# 对应 TS 源码中 behavior: 'ask' 的安全检查
WARNED_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\$\('), '命令包含 $() 命令替换，可能执行任意代码'),
    (re.compile(r'`'), '命令包含反引号命令替换，可能执行任意代码'),
    (re.compile(r'\$\{'), '命令包含 ${} 参数替换，可能绕过安全检查'),
    (re.compile(r'\$IFS|\$\{[^}]*IFS'), '命令包含 IFS 变量，可能绕过安全校验'),
    (re.compile(r'/proc/.*?/environ'), '命令尝试读取 /proc/*/environ，可能泄露环境变量中的密钥'),
    (re.compile(r'<(?!<)'), '命令包含输入重定向 (<)，可能读取敏感文件'),
    (re.compile(r'curl\s+.*\|\s*(bash|sh|zsh)'), '命令将网络下载内容管道到 shell 执行，极度危险'),
    (re.compile(r'wget\s+.*\|\s*(bash|sh|zsh)'), '命令将网络下载内容管道到 shell 执行，极度危险'),
    (re.compile(r'\bsudo\s+'), '使用超级用户权限执行命令'),
    (re.compile(r'\brm\s+-rf\s+'), '递归删除操作'),
    (re.compile(r'\bgit\s+reset\s+--hard\b'), 'Git 硬重置，可能丢失未提交的代码'),
    (re.compile(r'\bdocker\s+rm\b'), '删除 Docker 容器'),
    (re.compile(r'\bdocker\s+rmi\b'), '删除 Docker 镜像'),
    (re.compile(r'\bpip\s+uninstall\b'), '卸载 Python 包'),
    (re.compile(r'\bnpm\s+uninstall\b'), '卸载 Node 包'),
    (re.compile(r'\bchmod\s+777\b'), '设置危险权限 777'),
]

# Zsh 危险命令 - 对应 ZSH_DANGEROUS_COMMANDS
ZSH_DANGEROUS_COMMANDS = {
    'zmodload', 'emulate', 'sysopen', 'sysread', 'syswrite',
    'sysseek', 'zpty', 'ztcp', 'zsocket',
}

# 控制字符检测 - 对应 CONTROL_CHAR_RE
CONTROL_CHAR_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')


# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class BashResult:
    """
    Bash 命令执行结果，对齐 TS 源码中的 Out 类型

    对应源码:
        outputSchema = z.object({
            stdout: z.string(),
            stderr: z.string(),
            interrupted: z.boolean(),
            ...
        })
    """
    # 标准输出
    stdout: str = ""
    # 标准错误
    stderr: str = ""
    # 退出码（0 表示成功）
    exit_code: int = 0
    # 是否被超时中断
    interrupted: bool = False
    # 是否被安全策略拦截
    blocked: bool = False
    # 拦截/警告原因
    block_reason: str = ""
    # 是否需要用户确认（警告级命令）
    needs_confirmation: bool = False
    # 原始命令（用于重新执行）
    original_command: str = ""
    # 输出是否被截断
    truncated: bool = False
    # 实际执行耗时（秒）
    elapsed_seconds: float = 0.0


@dataclass
class SecurityCheckResult:
    """安全检查结果，对应 TS 源码中的 PermissionResult"""
    # allow / ask / deny
    behavior: str
    # 原因说明
    message: str = ""


# ============================================================================
# 安全校验函数 - 对齐 bashSecurity.ts
# ============================================================================

def check_command_security(command: str, work_dir: str = ".") -> SecurityCheckResult:
    """
    对命令进行安全校验，对应 TS 源码 bashCommandIsSafe_DEPRECATED()

    校验流程:
    1. 控制字符检测 - 对应 CONTROL_CHAR_RE
    2. 绝对禁止模式匹配 - 对应 BLOCKED_PATTERNS
    3. 命令替换检测 - 对应 validateDangerousPatterns
    4. IFS 注入检测 - 对应 validateIFSInjection
    5. /proc 访问检测 - 对应 validateProcEnvironAccess
    6. Zsh 危险命令检测 - 对应 validateZshDangerousCommands
    7. 路径越权检测 - 限制在工作目录内

    Args:
        command: 待执行的 shell 命令
        work_dir: 允许操作的工作目录（沙箱边界）

    Returns:
        SecurityCheckResult: behavior='allow' 放行, 'ask' 需确认, 'deny' 拒绝
    """
    # 1. 控制字符检测 - 对应 TS 源码 CONTROL_CHAR_RE
    # 非打印控制字符可能被 bash 静默丢弃但混淆我们的校验器
    if CONTROL_CHAR_RE.search(command):
        return SecurityCheckResult(
            behavior='deny',
            message='命令包含非打印控制字符，可能用于绕过安全检查'
        )

    # 2. 绝对禁止模式 - 匹配即拦截，不可覆盖
    for pattern in BLOCKED_PATTERNS:
        if pattern.search(command):
            return SecurityCheckResult(
                behavior='deny',
                message=f'命令匹配危险模式，已被安全策略拦截'
            )

    # 3. 警告级模式 - 对应 TS 中 behavior: 'ask' 的检查
    # 在自动化场景下，我们默认拒绝这些模式；交互场景可由调用方决定
    for pattern, message in WARNED_PATTERNS:
        if pattern.search(command):
            return SecurityCheckResult(
                behavior='ask',
                message=message
            )

    # 4. Zsh 危险命令检测 - 对应 validateZshDangerousCommands
    # 提取基础命令名（跳过环境变量赋值和前缀修饰符）
    tokens = command.strip().split()
    base_cmd = ""
    precommand_modifiers = {'command', 'builtin', 'noglob', 'nocorrect'}
    for token in tokens:
        # 跳过环境变量赋值 (VAR=value)
        if re.match(r'^[A-Za-z_]\w*=', token):
            continue
        # 跳过前缀修饰符
        if token in precommand_modifiers:
            continue
        base_cmd = token
        break

    if base_cmd in ZSH_DANGEROUS_COMMANDS:
        return SecurityCheckResult(
            behavior='deny',
            message=f'命令使用 Zsh 危险命令 "{base_cmd}"，可绕过安全检查'
        )

    # fc -e 检测 - 可通过编辑器执行任意命令
    if base_cmd == 'fc' and re.search(r'\s-\S*e', command.strip()):
        return SecurityCheckResult(
            behavior='deny',
            message="命令使用 'fc -e'，可通过编辑器执行任意命令"
        )

    # 5. 路径越权检测 - 确保命令操作在工作目录范围内
    # 提取命令中出现的路径参数，检查是否越界
    abs_work_dir = os.path.abspath(work_dir)
    path_patterns = [
        re.compile(r'(?:^|\s)(/[^\s;|&><]+)'),
        re.compile(r'(?:^|\s)(\./[^\s;|&><]+)'),
        re.compile(r'(?:^|\s)(~/[^\s;|&><]+)'),
    ]
    for p in path_patterns:
        for match in p.finditer(command):
            path = match.group(1)
            # 展开路径
            expanded = os.path.abspath(os.path.expanduser(path))
            # 允许 /tmp 和 /dev/null 等安全路径
            safe_prefixes = ['/tmp', '/dev/null', '/dev/zero', '/dev/urandom', '/proc/self/fd']
            if any(expanded.startswith(sp) for sp in safe_prefixes):
                continue
            # 检查是否在工作目录内
            if not expanded.startswith(abs_work_dir):
                return SecurityCheckResult(
                    behavior='ask',
                    message=f'命令访问路径 "{path}" 超出工作目录范围'
                )

    return SecurityCheckResult(behavior='allow', message='命令通过安全检查')


# ============================================================================
# 输出截断 - 对应 TS 源码中的 truncate() 和 EndTruncatingAccumulator
# ============================================================================

def truncate_output(output: str, max_chars: int = MAX_OUTPUT_CHARS) -> tuple[str, bool]:
    """
    截断输出以防止大模型 Token 爆炸

    对应 TS 源码:
        - maxResultSizeChars = 30_000 (BashTool)
        - EndTruncatingAccumulator 类
        - truncate() 函数 (utils/format.ts)

    策略: 保留头部内容 + 截断提示，因为头部通常包含最有用的信息
    （如编译错误的第一行、命令执行结果的摘要等）

    Args:
        output: 原始输出字符串
        max_chars: 最大字符数

    Returns:
        (截断后的输出, 是否发生了截断)
    """
    if len(output) <= max_chars:
        return output, False

    truncated = output[:max_chars]
    notice = TRUNCATION_NOTICE.format(
        total=len(output),
        shown=max_chars
    )
    return truncated + notice, True


# ============================================================================
# 核心 Bash 执行器 - 对应 TS 源码 BashTool.call() + runShellCommand()
# ============================================================================

def execute_bash(
    command: str,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    work_dir: str = ".",
    env: Optional[dict] = None,
    allow_warnings: bool = False,
) -> BashResult:
    """
    执行 Bash 命令，核心入口函数

    对应 TS 源码 BashTool.call() 的核心逻辑:
    1. 安全校验 -> 2. 执行命令 -> 3. 处理超时 -> 4. 截断输出 -> 5. 返回结果

    Args:
        command: 要执行的 shell 命令
        timeout_ms: 超时时间（毫秒），默认 120 秒
        work_dir: 工作目录（沙箱边界），默认当前目录
        env: 额外的环境变量
        allow_warnings: 是否允许警告级命令执行（对应 ask -> allow 的升级）

    Returns:
        BashResult: 执行结果，包含 stdout/stderr/exit_code 等信息

    Example:
        >>> result = execute_bash("ls -la", work_dir="/home/user/project")
        >>> print(result.stdout)
        >>> print(result.exit_code)
    """
    import time

    # ------------------------------------------------------------------
    # 第一步: 安全校验 - 对应 TS 源码 bashToolHasPermission()
    # ------------------------------------------------------------------
    security_result = check_command_security(command, work_dir)

    if security_result.behavior == 'deny':
        logger.warning(f"🚫 命令被安全策略拦截: {command} -> {security_result.message}")
        return BashResult(
            blocked=True,
            block_reason=f"[Security Alert] 尝试执行毁灭性命令，系统已强行拦截！原因: {security_result.message}",
            exit_code=-1,
        )

    if security_result.behavior == 'ask' and not allow_warnings:
        logger.warning(f"命令需要确认: {command} -> {security_result.message}")
        return BashResult(
            blocked=True,
            block_reason=security_result.message,
            needs_confirmation=True,
            original_command=command,
            exit_code=-1,
        )

    # ------------------------------------------------------------------
    # 第二步: 超时参数校验 - 对应 TS 源码中的 timeout 校验
    # ------------------------------------------------------------------
    # 确保 timeout_ms 是整数
    try:
        timeout_ms = int(timeout_ms)
    except (ValueError, TypeError):
        timeout_ms = DEFAULT_TIMEOUT_MS
    
    timeout_ms = min(timeout_ms, MAX_TIMEOUT_MS)
    timeout_seconds = timeout_ms / 1000.0

    # ------------------------------------------------------------------
    # 第三步: 执行命令 - 对应 TS 源码 exec() + Shell.ts
    # ------------------------------------------------------------------
    start_time = time.time()

    # 构建执行环境
    exec_env = os.environ.copy()
    if env:
        exec_env.update(env)

    # 确保工作目录存在
    abs_work_dir = os.path.abspath(work_dir)
    os.makedirs(abs_work_dir, exist_ok=True)

    try:
        # 使用 subprocess.Popen 执行命令
        # 对应 TS 源码中的 exec(command, abortController.signal, 'bash', {...})
        #
        # 关键参数说明:
        # - shell=True: 通过 /bin/bash 执行，支持管道等 shell 特性
        # - cwd: 限制在工作目录内
        # - stdout/stderr: PIPE 捕获输出
        # - start_new_session=True: 创建新进程组，便于超时后 kill 整组
        process = subprocess.Popen(
            command,
            shell=True,
            cwd=abs_work_dir,
            env=exec_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            # 创建新的进程组，使超时 kill 时能杀掉整个进程树
            # 对应 TS 源码中 abortController 的进程管理
            start_new_session=True,
        )

        try:
            # 等待命令完成，带超时
            # 对应 TS 源码中的 timeoutMs 参数
            stdout_bytes, stderr_bytes = process.communicate(timeout=timeout_seconds)
            exit_code = process.returncode
            interrupted = False

        except subprocess.TimeoutExpired:
            # ------------------------------------------------------------------
            # 第四步: 超时处理 - 对应 TS 源码中的 onTimeout 回调
            # ------------------------------------------------------------------
            logger.warning(f"命令超时 ({timeout_ms}ms): {command}")

            # 先尝试优雅终止 (SIGTERM)
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass

            # 等待 3 秒让进程清理
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                # 强制杀死 (SIGKILL) - 对应 TS 源码中的 abort
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    pass
                process.wait()

            # 收集已产生的输出
            stdout_bytes = process.stdout.read() if process.stdout else b""
            stderr_bytes = process.stderr.read() if process.stderr else b""
            exit_code = -1
            interrupted = True

    except Exception as e:
        # 执行异常（如命令不存在）
        # 对应 TS 源码中的 ShellError / isENOENT 处理
        elapsed = time.time() - start_time
        return BashResult(
            stdout="",
            stderr=str(e),
            exit_code=-1,
            interrupted=False,
            elapsed_seconds=elapsed,
        )

    elapsed = time.time() - start_time

    # ------------------------------------------------------------------
    # 第五步: 解码输出 - 对应 TS 源码中的 encoding 检测
    # ------------------------------------------------------------------
    try:
        stdout = stdout_bytes.decode('utf-8', errors='replace')
    except Exception:
        stdout = stdout_bytes.decode('latin-1', errors='replace')

    try:
        stderr = stderr_bytes.decode('utf-8', errors='replace')
    except Exception:
        stderr = stderr_bytes.decode('latin-1', errors='replace')

    # 去除尾部空白（对齐 TS 源码 .trimEnd()）
    stdout = stdout.rstrip()
    stderr = stderr.rstrip()

    # ------------------------------------------------------------------
    # 第六步: 输出截断 - 对应 TS 源码 EndTruncatingAccumulator
    # ------------------------------------------------------------------
    stdout, stdout_truncated = truncate_output(stdout, MAX_OUTPUT_CHARS)
    stderr, stderr_truncated = truncate_output(stderr, MAX_OUTPUT_CHARS)

    # ------------------------------------------------------------------
    # 第七步: 构建返回结果 - 对应 TS 源码 mapToolResultToToolResultBlockParam
    # ------------------------------------------------------------------
    # 如果有错误退出码，追加退出码信息到 stdout
    # 对应 TS 源码: if (result.code !== 0) { stdoutAccumulator.append(`Exit code ${result.code}`) }
    if exit_code != 0 and not interrupted:
        stdout += f"\nExit code {exit_code}"

    return BashResult(
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        interrupted=interrupted,
        truncated=stdout_truncated or stderr_truncated,
        elapsed_seconds=elapsed,
    )


_COMPILER_ERROR_PATTERNS = [
    re.compile(r'^(.+?):(\d+):(\d+):\s*(?:error|fatal\s+error):\s*(.+)$', re.MULTILINE),
    re.compile(r'^(.+?):(\d+):(\d+):\s*warning:\s*(.+)$', re.MULTILINE),
    re.compile(r'^(.+?):(\d+):(\d+):\s*note:\s*(.+)$', re.MULTILINE),
    re.compile(r'^(.+?):(\d+):\s*(?:error|fatal\s+error):\s*(.+)$', re.MULTILINE),
    re.compile(r'^\s*File\s+"(.+?)",\s*line\s+(\d+)', re.MULTILINE),
    re.compile(r'^(.+?):(\d+):(\d+)\s*-\s*error\s+(.+)$', re.MULTILINE),
    re.compile(r'^(.+?)\((\d+),(\d+)\):\s*error\s+(.+)$', re.MULTILINE),
]


def parse_compiler_errors(stderr: str, work_dir: str = "") -> list:
    if not stderr:
        return []

    diagnostics = []
    seen = set()

    for pattern in _COMPILER_ERROR_PATTERNS:
        for match in pattern.finditer(stderr):
            groups = match.groups()
            file_path = groups[0].strip()
            line_num = int(groups[1])

            col_num = 1
            message = ""
            if len(groups) >= 4 and isinstance(groups[2], str) and groups[2].isdigit():
                col_num = int(groups[2])
                message = groups[3].strip()
            elif len(groups) >= 3:
                message = groups[-1].strip()

            raw = match.group(0).lower()
            if "warning" in raw:
                severity = "warning"
            elif "note" in raw:
                severity = "info"
            else:
                severity = "error"

            if not os.path.isabs(file_path) and work_dir:
                file_path = os.path.join(work_dir, file_path)
            file_path = os.path.abspath(file_path)

            key = f"{file_path}:{line_num}:{col_num}"
            if key not in seen:
                seen.add(key)
                diagnostics.append({
                    "file": file_path,
                    "line": line_num,
                    "column": col_num,
                    "endLine": line_num,
                    "endColumn": col_num + 10,
                    "message": message,
                    "severity": severity,
                })

    return diagnostics
