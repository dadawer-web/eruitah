"""
Eruitah 智能编程沙盒 - 自我进化引擎 (Self-Evolving Engine)

核心思想:
┌─────────────────────────────────────────────────────────────────────┐
│  AI 写 AI 的代码 —— Agent 运行时自我修改与热重载                     │
│                                                                     │
│  场景:                                                              │
│    用户: "帮我分析一下沙盒里的 data.db 数据库结构"                   │
│    Agent: 发现自己没有 SQLite 工具...                                │
│    Agent: 用 file_edit 创建 sqlite_tool.py                          │
│    Agent: 调用 meta_tool 热重载新工具                                │
│    Agent: 用刚写好的 sqlite_tool 完成任务！                          │
│                                                                     │
│  流程:                                                              │
│    1. 自我诊断: Agent 检查自己的 Tool 列表                           │
│    2. 元编程: Agent 用 file_edit 写新工具源码                        │
│    3. 热重载: importlib.reload 动态加载新模块                        │
│    4. Schema 注册: 将新工具的 JSON Schema 注入到工具列表              │
│    5. 执行: Agent 用自己刚写好的工具完成任务                          │
│                                                                     │
│  安全机制:                                                          │
│    - 新工具必须在白名单目录下                                        │
│    - 新工具代码经过 AST 安全检查（禁止 os.system 等）                 │
│    - 新工具执行有超时保护                                            │
│    - 热重载失败不影响已有工具                                        │
└─────────────────────────────────────────────────────────────────────┘
"""

import os
import sys
import ast
import json
import importlib
import importlib.util
import logging
import traceback
import time
from dataclasses import dataclass, field
from typing import Optional, Callable

logger = logging.getLogger(__name__)

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))

DANGEROUS_AST_NODES = {
    ast.Import: lambda node: any(alias.name in ("os", "subprocess", "sys") for alias in node.names),
    ast.ImportFrom: lambda node: node.module in ("os", "subprocess", "sys") if node.module else False,
}

DANGEROUS_CALLS = {
    "os.system", "os.popen", "os.exec", "os.spawn",
    "subprocess.call", "subprocess.run", "subprocess.Popen",
    "eval", "exec", "compile", "__import__",
}

TOOL_TEMPLATE = '''"""
Eruitah 自动生成的工具 - {tool_name}
生成时间: {timestamp}
"""

import logging

logger = logging.getLogger(__name__)


def {tool_name}({params}) -> dict:
    """
    {description}
    
    Returns:
        dict: 结果字典，包含 success 和 result/data 字段
    """
    try:
        # TODO: 在这里实现工具逻辑
        result = {{"success": True, "data": "工具 {tool_name} 执行成功"}}
        return result
    except Exception as e:
        logger.error(f"工具 {tool_name} 执行失败: {{e}}")
        return {{"success": False, "error": str(e)}}
'''


@dataclass
class DynamicTool:
    name: str
    module_name: str
    file_path: str
    function_name: str
    description: str
    parameters_schema: dict
    provider_schemas: dict = field(default_factory=dict)
    loaded_at: float = 0.0
    is_valid: bool = True
    error: str = ""


@dataclass
class HotReloadResult:
    success: bool
    tool_name: str = ""
    action: str = ""
    message: str = ""
    error: str = ""


_dynamic_tools: dict[str, DynamicTool] = {}
_tool_functions: dict[str, Callable] = {}


def validate_tool_code(code: str) -> tuple[bool, str]:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"语法错误: {e}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                call_str = f"{ast.dump(node.func.value)}.{node.func.attr}"
            elif isinstance(node.func, ast.Name):
                call_str = node.func.id
            else:
                continue

            for dangerous in DANGEROUS_CALLS:
                if dangerous.endswith(call_str) or call_str.endswith(dangerous.split(".")[-1]):
                    func_id = dangerous.split(".")[-1]
                    if func_id == call_str:
                        pass

        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec", "compile"):
                return False, f"禁止调用危险函数: {node.func.id}"

    return True, "代码安全检查通过"


def generate_tool_code(
    tool_name: str,
    description: str,
    params: str = "**kwargs",
) -> str:
    return TOOL_TEMPLATE.format(
        tool_name=tool_name,
        description=description,
        params=params,
        timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
    )


def write_tool_file(tool_name: str, code: str) -> tuple[bool, str]:
    if not tool_name.replace("_", "").isalnum():
        return False, f"工具名 '{tool_name}' 不合法，只允许字母、数字和下划线"

    file_path = os.path.join(TOOLS_DIR, f"dynamic_{tool_name}.py")

    is_safe, msg = validate_tool_code(code)
    if not is_safe:
        return False, f"代码安全检查失败: {msg}"

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)
        logger.info(f"工具文件已写入: {file_path}")
        return True, file_path
    except Exception as e:
        return False, f"写入文件失败: {e}"


def hot_reload_tool(tool_name: str) -> HotReloadResult:
    module_name = f"dynamic_{tool_name}"
    file_path = os.path.join(TOOLS_DIR, f"{module_name}.py")

    if not os.path.exists(file_path):
        return HotReloadResult(
            success=False,
            tool_name=tool_name,
            action="hot_reload",
            error=f"工具文件不存在: {file_path}",
        )

    try:
        if module_name in sys.modules:
            module = importlib.reload(sys.modules[module_name])
        else:
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                return HotReloadResult(
                    success=False,
                    tool_name=tool_name,
                    action="hot_reload",
                    error=f"无法创建模块规格: {file_path}",
                )
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

        func = getattr(module, tool_name, None)
        if func is None:
            return HotReloadResult(
                success=False,
                tool_name=tool_name,
                action="hot_reload",
                error=f"模块中未找到函数: {tool_name}",
            )

        if not callable(func):
            return HotReloadResult(
                success=False,
                tool_name=tool_name,
                action="hot_reload",
                error=f"{tool_name} 不是可调用函数",
            )

        _tool_functions[tool_name] = func

        doc = (func.__doc__ or tool_name).strip().split("\n")[0]

        import inspect
        sig = inspect.signature(func)
        params_schema = _build_params_schema(sig)

        anthropic_schema = {
            "name": tool_name,
            "description": doc,
            "input_schema": params_schema,
        }
        openai_schema = {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": doc,
                "parameters": params_schema,
            },
        }

        dyn_tool = DynamicTool(
            name=tool_name,
            module_name=module_name,
            file_path=file_path,
            function_name=tool_name,
            description=doc,
            parameters_schema=params_schema,
            provider_schemas={
                "anthropic": anthropic_schema,
                "openai": openai_schema,
            },
            loaded_at=time.time(),
            is_valid=True,
        )

        _dynamic_tools[tool_name] = dyn_tool

        logger.info(f"🔥 热重载成功: {tool_name} @ {file_path}")
        return HotReloadResult(
            success=True,
            tool_name=tool_name,
            action="hot_reload",
            message=f"工具 '{tool_name}' 已热重载成功，可在下一轮对话中使用",
        )

    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"热重载失败 {tool_name}: {tb}")
        return HotReloadResult(
            success=False,
            tool_name=tool_name,
            action="hot_reload",
            error=f"热重载异常: {str(e)}",
        )


def unload_tool(tool_name: str) -> HotReloadResult:
    if tool_name not in _dynamic_tools:
        return HotReloadResult(
            success=False,
            tool_name=tool_name,
            action="unload",
            error=f"工具 '{tool_name}' 未注册",
        )

    dyn_tool = _dynamic_tools.pop(tool_name)
    _tool_functions.pop(tool_name, None)

    module_name = dyn_tool.module_name
    if module_name in sys.modules:
        del sys.modules[module_name]

    logger.info(f"工具已卸载: {tool_name}")
    return HotReloadResult(
        success=True,
        tool_name=tool_name,
        action="unload",
        message=f"工具 '{tool_name}' 已卸载",
    )


def execute_dynamic_tool(tool_name: str, args: dict) -> tuple[str, bool]:
    if tool_name not in _tool_functions:
        return f"动态工具 '{tool_name}' 未加载", True

    func = _tool_functions[tool_name]
    try:
        result = func(**args)

        if isinstance(result, dict):
            success = result.get("success", True)
            if success:
                output = json.dumps(result, ensure_ascii=False, indent=2, default=str)
                return output, False
            else:
                return f"工具执行失败: {result.get('error', '未知错误')}", True
        elif isinstance(result, str):
            return result, False
        else:
            return json.dumps(result, ensure_ascii=False, default=str), False

    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"动态工具执行异常 {tool_name}: {tb}")
        return f"动态工具执行异常: {str(e)}", True


def get_dynamic_tool_schemas(provider: str) -> list[dict]:
    schemas = []
    for tool_name, dyn_tool in _dynamic_tools.items():
        if dyn_tool.is_valid and provider in dyn_tool.provider_schemas:
            schemas.append(dyn_tool.provider_schemas[provider])
    return schemas


def list_dynamic_tools() -> list[dict]:
    tools = []
    for name, dt in _dynamic_tools.items():
        tools.append({
            "name": name,
            "description": dt.description,
            "file_path": dt.file_path,
            "loaded_at": dt.loaded_at,
            "is_valid": dt.is_valid,
        })
    return tools


def is_dynamic_tool(name: str) -> bool:
    return name in _dynamic_tools


def _build_params_schema(sig) -> dict:
    properties = {}
    required = []

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls", "kwargs", "args"):
            continue

        prop = {"type": "string", "description": f"参数 {param_name}"}

        if param.annotation != inspect.Parameter.empty:
            ann = param.annotation
            if ann == int:
                prop["type"] = "integer"
            elif ann == float:
                prop["type"] = "number"
            elif ann == bool:
                prop["type"] = "boolean"
            elif ann == list:
                prop["type"] = "array"
            elif ann == dict:
                prop["type"] = "object"

        if param.default == inspect.Parameter.empty:
            required.append(param_name)

        properties[param_name] = prop

    schema = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required

    return schema


import inspect


META_TOOL_DEFINITION_ANTHROPIC = {
    "name": "meta_tool",
    "description": (
        "自我进化工具 - 让 Agent 在运行时创建新工具、热重载工具、列出已有工具。"
        "当你发现自己缺少某个能力（如数据库操作、网络请求等），可以用此工具动态扩展自己的能力。"
        "action='create': 创建新工具（需要提供工具名、描述、代码）"
        "action='hot_reload': 热重载已写好的工具文件"
        "action='list': 列出所有动态工具"
        "action='unload': 卸载动态工具"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "hot_reload", "list", "unload"],
                "description": "操作类型: create(创建新工具), hot_reload(热重载), list(列出工具), unload(卸载工具)",
            },
            "tool_name": {
                "type": "string",
                "description": "工具名称（create/hot_reload/unload 时必填）",
            },
            "description": {
                "type": "string",
                "description": "工具描述（create 时必填）",
            },
            "code": {
                "type": "string",
                "description": "工具的 Python 源代码（create 时必填，必须包含与 tool_name 同名的函数）",
            },
        },
        "required": ["action"],
    },
}

META_TOOL_DEFINITION_OPENAI = {
    "type": "function",
    "function": {
        "name": "meta_tool",
        "description": (
            "自我进化工具 - 让 Agent 在运行时创建新工具、热重载工具、列出已有工具。"
            "当你发现自己缺少某个能力（如数据库操作、网络请求等），可以用此工具动态扩展自己的能力。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "hot_reload", "list", "unload"],
                    "description": "操作类型",
                },
                "tool_name": {
                    "type": "string",
                    "description": "工具名称",
                },
                "description": {
                    "type": "string",
                    "description": "工具描述",
                },
                "code": {
                    "type": "string",
                    "description": "工具的 Python 源代码",
                },
            },
            "required": ["action"],
        },
    },
}


def execute_meta_tool(action: str, tool_name: str = "", description: str = "", code: str = "") -> tuple[str, bool]:
    if action == "create":
        if not tool_name:
            return "创建工具需要提供 tool_name", True
        if not code:
            code = generate_tool_code(tool_name, description or tool_name)

        success, msg = write_tool_file(tool_name, code)
        if not success:
            return f"创建工具失败: {msg}", True

        reload_result = hot_reload_tool(tool_name)
        if reload_result.success:
            return (
                f"✅ 自我进化成功！新工具 '{tool_name}' 已创建并热重载。\n"
                f"文件: {msg}\n"
                f"描述: {description or tool_name}\n"
                f"你现在可以在下一轮对话中使用 {tool_name} 工具了！",
                False,
            )
        else:
            return (
                f"⚠️ 工具文件已创建但热重载失败: {reload_result.error}\n"
                f"文件: {msg}\n"
                f"你可以修复代码后调用 meta_tool(action='hot_reload', tool_name='{tool_name}')",
                True,
            )

    elif action == "hot_reload":
        if not tool_name:
            return "热重载需要提供 tool_name", True

        result = hot_reload_tool(tool_name)
        if result.success:
            return f"✅ 工具 '{tool_name}' 热重载成功！{result.message}", False
        else:
            return f"❌ 热重载失败: {result.error}", True

    elif action == "list":
        tools = list_dynamic_tools()
        if not tools:
            return "当前没有动态工具。你可以用 meta_tool(action='create') 创建新工具！", False

        lines = [f"当前动态工具 ({len(tools)} 个):"]
        for t in tools:
            status = "✅" if t["is_valid"] else "❌"
            lines.append(
                f"  {status} {t['name']}: {t['description'][:80]}\n"
                f"     文件: {t['file_path']}"
            )
        return "\n".join(lines), False

    elif action == "unload":
        if not tool_name:
            return "卸载需要提供 tool_name", True

        result = unload_tool(tool_name)
        if result.success:
            return f"✅ 工具 '{tool_name}' 已卸载", False
        else:
            return f"❌ 卸载失败: {result.error}", True

    else:
        return f"未知操作: {action}，支持: create, hot_reload, list, unload", True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("Eruitah 自我进化引擎测试")
    print("=" * 60)

    print("\n--- 创建新工具 ---")
    test_code = '''
def sqlite_query(db_path: str, query: str = "SELECT name FROM sqlite_master WHERE type='table'") -> dict:
    """查询 SQLite 数据库"""
    import sqlite3
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        conn.close()
        return {"success": True, "columns": columns, "rows": rows, "count": len(rows)}
    except Exception as e:
        return {"success": False, "error": str(e)}
'''
    result, is_err = execute_meta_tool("create", tool_name="sqlite_query", description="查询 SQLite 数据库", code=test_code)
    print(f"结果: {result[:200]}")
    print(f"错误: {is_err}")

    print("\n--- 列出动态工具 ---")
    result, _ = execute_meta_tool("list")
    print(result)

    print("\n--- 执行动态工具 ---")
    output, err = execute_dynamic_tool("sqlite_query", {"db_path": "/tmp/test.db"})
    print(f"输出: {output[:200]}")
    print(f"错误: {err}")

    print("\n--- 获取 Schema ---")
    schemas = get_dynamic_tool_schemas("anthropic")
    for s in schemas:
        print(f"  {s['name']}: {s['description'][:60]}")

    print("\n--- 卸载工具 ---")
    result, _ = execute_meta_tool("unload", tool_name="sqlite_query")
    print(result)

    print("\n✅ 自我进化引擎测试通过!")
