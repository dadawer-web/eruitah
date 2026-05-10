"""
Eruitah 智能编程沙盒 - 自动化测试闭环 (Auto-Test Feedback Loop)

核心思想（来自 Claude Code 的 Green Check 机制）:
┌─────────────────────────────────────────────────────────────────────┐
│  Claude Code 会自动尝试运行代码并根据报错修复，直到测试用例全部通过。  │
│                                                                     │
│  本模块实现:                                                         │
│  1. 测试工程师角色 - 根据新写的代码自动生成测试                      │
│  2. 测试执行引擎 - 运行测试并收集结果                                │
│  3. 反馈闭环 - 将测试结果反馈给 Agent，驱动修复                      │
│  4. 覆盖率追踪 - 追踪测试覆盖率                                     │
│                                                                     │
│  流程:                                                              │
│  用户: "写一个快速排序"                                              │
│  → Agent 创建 quicksort.py                                          │
│  → 测试工程师自动生成 test_quicksort.py                              │
│  → 执行测试 → ❌ 2/5 失败                                           │
│  → 反馈给 Agent: "测试失败: test_empty_list, test_duplicate"        │
│  → Agent 修复代码                                                   │
│  → 执行测试 → ✅ 5/5 通过                                           │
│  → 前端展示: ██████████ 100% (5/5)                                  │
└─────────────────────────────────────────────────────────────────────┘
"""

import os
import re
import json
import time
import logging
import subprocess
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TestCase:
    name: str
    status: str  # "passed", "failed", "error", "skipped"
    message: str = ""
    duration: float = 0.0


@dataclass
class TestResult:
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    test_cases: list = field(default_factory=list)
    output: str = ""
    duration: float = 0.0
    coverage_percent: float = 0.0

    @property
    def success_rate(self) -> float:
        return (self.passed / self.total * 100) if self.total > 0 else 0.0

    @property
    def all_passed(self) -> bool:
        return self.total > 0 and self.failed == 0 and self.errors == 0


TEST_GENERATION_PROMPT = """你是一个测试工程师。请为以下代码生成全面的单元测试。

要求:
1. 使用 {framework} 框架
2. 覆盖所有公共函数和方法
3. 包含正常输入、边界条件和异常情况
4. 测试文件保存为 {test_file_path}
5. 只输出测试代码，不要输出其他内容

被测代码 ({source_file}):
```{language}
{source_code}
```

请生成测试代码:"""


def detect_test_framework(work_dir: str) -> str:
    """检测项目使用的测试框架"""
    if os.path.exists(os.path.join(work_dir, "pytest.ini")):
        return "pytest"
    if os.path.exists(os.path.join(work_dir, "pyproject.toml")):
        try:
            with open(os.path.join(work_dir, "pyproject.toml")) as f:
                if "pytest" in f.read():
                    return "pytest"
        except Exception:
            pass
    if os.path.exists(os.path.join(work_dir, "pom.xml")):
        return "junit"
    if os.path.exists(os.path.join(work_dir, "package.json")):
        try:
            with open(os.path.join(work_dir, "package.json")) as f:
                pkg = json.load(f)
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                if "jest" in deps:
                    return "jest"
                if "mocha" in deps:
                    return "mocha"
                if "vitest" in deps:
                    return "vitest"
        except Exception:
            pass
    return "pytest"


def get_test_file_path(source_file: str) -> str:
    """根据源文件路径推导测试文件路径"""
    dir_name = os.path.dirname(source_file)
    base_name = os.path.basename(source_file)
    name, ext = os.path.splitext(base_name)

    if ext == ".py":
        test_name = f"test_{name}.py"
        if dir_name:
            test_dir = os.path.join(os.path.dirname(dir_name), "tests")
        else:
            test_dir = "tests"
        return os.path.join(test_dir, test_name)
    elif ext in (".java",):
        test_name = f"{name}Test.java"
        return os.path.join(dir_name, test_name)
    elif ext in (".js", ".ts", ".jsx", ".tsx"):
        test_name = f"{name}.test{ext}"
        return os.path.join(dir_name, test_name)
    else:
        test_name = f"test_{name}{ext}"
        return os.path.join(dir_name, test_name)


def run_python_tests(test_file: str, work_dir: str) -> TestResult:
    """运行 Python 测试"""
    result = TestResult()

    try:
        proc = subprocess.run(
            ["python3", "-m", "pytest", test_file, "-v", "--tb=short", "--no-header"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=work_dir,
        )

        result.output = proc.stdout + proc.stderr

        for line in proc.stdout.splitlines():
            line = line.strip()
            if line.startswith("PASSED") or " PASSED " in line:
                result.passed += 1
                result.total += 1
                name = line.split()[0] if line.split() else "unknown"
                result.test_cases.append(TestCase(name=name, status="passed"))
            elif line.startswith("FAILED") or " FAILED " in line:
                result.failed += 1
                result.total += 1
                name = line.split()[0] if line.split() else "unknown"
                msg = ""
                if "AssertionError" in line:
                    msg = line
                result.test_cases.append(TestCase(name=name, status="failed", message=msg))
            elif line.startswith("ERROR") or " ERROR " in line:
                result.errors += 1
                result.total += 1
                result.test_cases.append(TestCase(name="error", status="error"))

        if result.total == 0:
            for line in proc.stdout.splitlines():
                if "test session starts" in line or "collected" in line:
                    match = re.search(r"collected (\d+) items", line)
                    if match:
                        result.total = int(match.group(1))

    except subprocess.TimeoutExpired:
        result.errors = 1
        result.total = 1
        result.output = "测试执行超时（60秒）"
        result.test_cases.append(TestCase(name="timeout", status="error", message="超时"))
    except FileNotFoundError:
        result.errors = 1
        result.total = 1
        result.output = "pytest 未安装"
        result.test_cases.append(TestCase(name="missing", status="error", message="pytest 未安装"))

    return result


def run_javascript_tests(test_file: str, work_dir: str) -> TestResult:
    """运行 JavaScript 测试"""
    result = TestResult()

    try:
        proc = subprocess.run(
            ["npx", "jest", test_file, "--no-coverage", "--verbose"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=work_dir,
        )

        result.output = proc.stdout + proc.stderr

        for line in proc.stdout.splitlines():
            line = line.strip()
            if "✓" in line or "PASS" in line:
                result.passed += 1
                result.total += 1
            elif "✕" in line or "FAIL" in line:
                result.failed += 1
                result.total += 1

    except subprocess.TimeoutExpired:
        result.errors = 1
        result.total = 1
        result.output = "测试执行超时"
    except FileNotFoundError:
        result.errors = 1
        result.total = 1
        result.output = "jest 未安装"

    return result


def run_tests(test_file: str, work_dir: str = ".") -> TestResult:
    """自动检测并运行测试"""
    ext = os.path.splitext(test_file)[1].lower()

    if ext == ".py":
        return run_python_tests(test_file, work_dir)
    elif ext in (".js", ".jsx", ".ts", ".tsx"):
        return run_javascript_tests(test_file, work_dir)
    else:
        return TestResult(
            total=1,
            errors=1,
            output=f"不支持的测试文件类型: {ext}",
            test_cases=[TestCase(name="unsupported", status="error", message=f"不支持的类型: {ext}")],
        )


def format_test_result(result: TestResult) -> str:
    """格式化测试结果为可读文本"""
    if result.all_passed:
        status_line = f"✅ 全部通过 ({result.passed}/{result.total})"
    else:
        status_line = f"❌ 部分失败 (通过: {result.passed}/{result.total}, 失败: {result.failed}, 错误: {result.errors})"

    bar_filled = int(result.success_rate / 10)
    bar_empty = 10 - bar_filled
    progress_bar = "█" * bar_filled + "░" * bar_empty

    lines = [
        f"🧪 测试结果: {status_line}",
        f"📊 进度: [{progress_bar}] {result.success_rate:.0f}%",
    ]

    if result.test_cases:
        lines.append("\n📋 测试用例:")
        for tc in result.test_cases:
            icon = {"passed": "✅", "failed": "❌", "error": "💥", "skipped": "⏭️"}.get(tc.status, "?")
            msg = f" - {tc.message[:100]}" if tc.message else ""
            lines.append(f"  {icon} {tc.name}{msg}")

    if result.failed > 0 or result.errors > 0:
        lines.append(f"\n📝 详细输出:\n{result.output[:2000]}")

    return "\n".join(lines)


AUTO_TEST_TOOL_DEFINITION_OPENAI = {
    "type": "function",
    "function": {
        "name": "auto_test",
        "description": (
            "自动化测试工具 - 运行测试并反馈结果。"
            "支持多种语言: Python (.py), JavaScript/TypeScript (.js/.ts/.jsx/.tsx), Java (.java) 等。"
            "action='run': 运行指定测试文件"
            "action='generate_and_run': 根据源代码自动生成测试并运行"
            "action='check_coverage': 检查测试覆盖率"
            "action='scan_and_test': 扫描目录下所有代码文件，批量生成并运行测试"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["run", "generate_and_run", "check_coverage", "scan_and_test"],
                    "description": "操作类型",
                },
                "test_file": {
                    "type": "string",
                    "description": "测试文件路径（run 时必填）",
                },
                "source_file": {
                    "type": "string",
                    "description": "源代码文件路径（generate_and_run 时必填）",
                },
                "directory": {
                    "type": "string",
                    "description": "要扫描的目录路径（scan_and_test 时使用）",
                },
            },
            "required": ["action"],
        },
    },
}

AUTO_TEST_TOOL_DEFINITION_ANTHROPIC = {
    "name": "auto_test",
    "description": (
        "自动化测试工具 - 运行测试并反馈结果，驱动代码修复闭环。"
        "支持多种语言: Python (.py), JavaScript/TypeScript (.js/.ts/.jsx/.tsx), Java (.java) 等。"
        "可以根据源代码自动生成测试，运行并反馈结果给 Agent。"
        "scan_and_test 动作可扫描目录下所有代码文件，批量生成并运行测试。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["run", "generate_and_run", "check_coverage", "scan_and_test"],
                "description": "操作类型",
            },
            "test_file": {
                "type": "string",
                "description": "测试文件路径",
            },
            "source_file": {
                "type": "string",
                "description": "源代码文件路径",
            },
            "directory": {
                "type": "string",
                "description": "要扫描的目录路径",
            },
        },
        "required": ["action"],
    },
}


def execute_auto_test(action: str, test_file: str = "", source_file: str = "", directory: str = "", work_dir: str = ".") -> tuple[str, bool]:
    """执行自动化测试工具"""
    if action == "run":
        if not test_file:
            return "必须提供 test_file 参数", True

        abs_test = os.path.join(work_dir, test_file) if not os.path.isabs(test_file) else test_file
        if not os.path.exists(abs_test):
            return f"测试文件不存在: {test_file}", True

        result = run_tests(abs_test, work_dir)
        output = format_test_result(result)
        return output, not result.all_passed

    elif action == "generate_and_run":
        if not source_file:
            return "必须提供 source_file 参数", True

        abs_source = os.path.join(work_dir, source_file) if not os.path.isabs(source_file) else source_file
        if not os.path.exists(abs_source):
            return f"源文件不存在: {source_file}", True

        test_path = get_test_file_path(source_file)
        framework = detect_test_framework(work_dir)

        try:
            with open(abs_source, 'r', encoding='utf-8') as f:
                source_code = f.read()
        except Exception as e:
            return f"读取源文件失败: {e}", True

        ext = os.path.splitext(source_file)[1].lower()
        language_map = {".py": "python", ".js": "javascript", ".ts": "typescript", ".java": "java"}
        language = language_map.get(ext, "unknown")

        prompt = TEST_GENERATION_PROMPT.format(
            framework=framework,
            test_file_path=test_path,
            source_file=source_file,
            source_code=source_code[:3000],
            language=language,
        )

        return (
            f"📝 测试生成提示已准备。\n"
            f"源文件: {source_file}\n"
            f"测试文件: {test_path}\n"
            f"框架: {framework}\n"
            f"语言: {language}\n\n"
            f"请使用 file_edit 工具创建测试文件 {test_path}，然后使用 auto_test(action='run', test_file='{test_path}') 运行测试。\n\n"
            f"测试生成参考提示:\n{prompt[:500]}...",
            False,
        )

    elif action == "scan_and_test":
        scan_dir = os.path.join(work_dir, directory) if directory and not os.path.isabs(directory) else (directory or work_dir)
        
        if not os.path.exists(scan_dir):
            return f"目录不存在: {directory or work_dir}", True

        supported_extensions = {'.py', '.js', '.ts', '.jsx', '.tsx', '.java'}
        code_files = []
        
        for root, dirs, files in os.walk(scan_dir):
            dirs[:] = [d for d in dirs if d not in {'node_modules', '__pycache__', '.git', 'venv', 'dist', 'build', 'tests'}]
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in supported_extensions:
                    code_files.append(os.path.join(root, f))

        if not code_files:
            return f"在目录 {scan_dir} 中未找到支持的代码文件。\n支持的文件类型: Python (.py), JavaScript (.js/.jsx), TypeScript (.ts/.tsx), Java (.java)", True

        results = []
        for source_file in code_files:
            rel_path = os.path.relpath(source_file, work_dir)
            test_path = get_test_file_path(rel_path)
            ext = os.path.splitext(source_file)[1].lower()
            language_map = {".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".jsx": "React JSX", ".tsx": "React TSX", ".java": "Java"}
            language = language_map.get(ext, "unknown")
            results.append(f"  - {rel_path} ({language}) → 测试文件: {test_path}")

        return (
            f"📂 扫描完成，找到 {len(code_files)} 个代码文件:\n" +
            "\n".join(results) +
            f"\n\n💡 请逐个使用 auto_test(action='generate_and_run', source_file='文件路径') 为每个文件生成测试。\n"
            f"支持的测试框架: pytest (Python), jest/vitest/mocha (JS/TS), junit (Java)",
            False,
        )

    elif action == "check_coverage":
        try:
            proc = subprocess.run(
                ["python3", "-m", "pytest", "--cov=.", "--cov-report=term-missing", "--no-header", "-q"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=work_dir,
            )
            return f"📊 覆盖率报告:\n{proc.stdout[:2000]}", False
        except FileNotFoundError:
            return "pytest-cov 未安装，请运行: pip install pytest-cov", True
        except subprocess.TimeoutExpired:
            return "覆盖率检查超时", True
        except Exception as e:
            return f"覆盖率检查失败: {e}", True

    else:
        return f"未知操作: {action}", True


RUN_AUTO_TEST_TOOL_DEFINITION_OPENAI = {
    "type": "function",
    "function": {
        "name": "run_auto_test",
        "description": (
            "TDD 自愈测试引擎 - 修改代码后立即运行测试，报错则自动修复，直到全绿。"
            "这是你修改代码后必须调用的工具！不要在修改完代码后直接告诉用户任务完成，"
            "必须先调用此工具验证代码正确性。\n"
            "test_command 示例：\n"
            "- Python: 'pytest' 或 'python3 -m pytest test_xxx.py'\n"
            "- C/C++: 'make test' 或 './run_tests'\n"
            "- Node.js: 'npm test' 或 'npx jest'\n"
            "- 通用: 'make test' 或任何构建系统的测试命令"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "test_command": {
                    "type": "string",
                    "description": "测试命令，如 'pytest'、'make test'、'npm test'。如果不填，系统会自动检测。",
                },
                "test_file": {
                    "type": "string",
                    "description": "指定测试文件路径（可选），如 'tests/test_main.py'。不填则运行所有测试。",
                },
            },
            "required": [],
        },
    },
}

RUN_AUTO_TEST_TOOL_DEFINITION_ANTHROPIC = {
    "name": "run_auto_test",
    "description": (
        "TDD 自愈测试引擎 - 修改代码后立即运行测试，报错则自动修复，直到全绿。"
        "这是你修改代码后必须调用的工具！不要在修改完代码后直接告诉用户任务完成，"
        "必须先调用此工具验证代码正确性。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "test_command": {
                "type": "string",
                "description": "测试命令，如 'pytest'、'make test'、'npm test'。如果不填，系统会自动检测。",
            },
            "test_file": {
                "type": "string",
                "description": "指定测试文件路径（可选）。不填则运行所有测试。",
            },
        },
        "required": [],
    },
}


def execute_run_auto_test(
    test_command: str = "",
    test_file: str = "",
    work_dir: str = ".",
) -> tuple[str, bool]:
    """
    TDD 自愈引擎核心 - 运行测试并返回结构化结果

    返回格式:
    - 测试通过: [Test Passed] 所有测试用例通过！
    - 测试失败: [Test Failed] 自动测试失败，请根据以下报错信息分析原因并调用 file_edit 进行修复：
                  {error_logs}
    """
    if not test_command:
        framework = detect_test_framework(work_dir)
        if framework == "pytest":
            if test_file:
                test_command = f"python3 -m pytest {test_file} -v --tb=short"
            else:
                test_command = "python3 -m pytest -v --tb=short"
        elif framework == "jest":
            if test_file:
                test_command = f"npx jest {test_file} --no-coverage --verbose"
            else:
                test_command = "npx jest --no-coverage"
        elif framework == "vitest":
            test_command = "npx vitest run"
        elif framework == "mocha":
            test_command = "npx mocha"
        elif framework == "junit":
            test_command = "mvn test"
        else:
            if test_file:
                test_command = f"python3 -m pytest {test_file} -v --tb=short"
            else:
                test_command = "python3 -m pytest -v --tb=short"

    logger.info(f"🧪 TDD 自愈引擎启动: {test_command} (cwd={work_dir})")

    try:
        proc = subprocess.run(
            test_command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=work_dir,
        )

        full_output = proc.stdout + proc.stderr

        if proc.returncode == 0:
            summary_lines = full_output.strip().split("\n")[-5:]
            summary = "\n".join(summary_lines)
            return (
                f"[Test Passed] ✅ 所有测试用例通过！\n\n"
                f"测试命令: {test_command}\n"
                f"退出码: {proc.returncode}\n\n"
                f"测试摘要:\n{summary}",
                False,
            )
        else:
            all_lines = full_output.strip().split("\n")
            error_tail = "\n".join(all_lines[-50:])

            failed_tests = []
            for line in all_lines:
                stripped = line.strip()
                if "FAILED" in stripped or "FAIL:" in stripped:
                    failed_tests.append(stripped)
                elif "AssertionError" in stripped or "AssertionError" in stripped:
                    failed_tests.append(stripped)
                elif "Error:" in stripped and "0 errors" not in stripped:
                    failed_tests.append(stripped)

            failed_summary = ""
            if failed_tests:
                failed_summary = "\n失败的测试:\n" + "\n".join(failed_tests[:10])

            return (
                f"[Test Failed] ❌ 自动测试失败，请根据以下报错信息分析原因并调用 file_edit 进行修复：\n\n"
                f"测试命令: {test_command}\n"
                f"退出码: {proc.returncode}\n"
                f"{failed_summary}\n\n"
                f"详细报错（最后 50 行）:\n{error_tail}",
                True,
            )

    except subprocess.TimeoutExpired:
        return (
            "[Test Failed] ❌ 测试执行超时（120秒）。\n"
            "可能原因：测试中存在死循环或等待输入。请检查代码逻辑。",
            True,
        )
    except Exception as e:
        return (
            f"[Test Failed] ❌ 测试执行异常: {str(e)}\n"
            f"请检查测试命令是否正确: {test_command}",
            True,
        )
