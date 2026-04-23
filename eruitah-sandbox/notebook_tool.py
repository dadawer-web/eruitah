import json
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

MAX_CELL_SOURCE_LENGTH = 5000

def read_notebook(workspace_dir: str, path: str) -> tuple[str, bool]:
    full_path = os.path.join(workspace_dir, path)
    
    if not os.path.exists(full_path):
        return f"文件不存在: {path}", True
    
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            nb = json.load(f)
    except json.JSONDecodeError as e:
        return f"Notebook JSON 解析失败: {str(e)}", True
    except Exception as e:
        return f"读取 Notebook 失败: {str(e)}", True
    
    cells = nb.get('cells', [])
    if not cells:
        return "Notebook 为空", False
    
    output_lines = [f"Notebook: {path}", f"共 {len(cells)} 个 Cell\n"]
    
    for i, cell in enumerate(cells):
        cell_type = cell.get('cell_type', 'unknown')
        source = cell.get('source', '')
        
        if isinstance(source, list):
            source = ''.join(source)
        
        source = source.strip()
        if len(source) > MAX_CELL_SOURCE_LENGTH:
            source = source[:MAX_CELL_SOURCE_LENGTH] + "\n... [Cell 源码过长已截断]"
        
        if not source:
            source = "(空)"
        
        output_lines.append(f"--- Cell [{i}] ({cell_type}) ---")
        output_lines.append(source)
        output_lines.append("")
    
    result = '\n'.join(output_lines)
    if len(result) > 30000:
        result = result[:30000] + "\n... [Notebook 内容过长已截断]"
    
    return result, False

def edit_notebook_cell(workspace_dir: str, path: str, cell_index: int, new_code: str) -> tuple[str, bool]:
    full_path = os.path.join(workspace_dir, path)
    
    if not os.path.exists(full_path):
        return f"文件不存在: {path}", True
    
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            nb = json.load(f)
    except json.JSONDecodeError as e:
        return f"Notebook JSON 解析失败: {str(e)}", True
    except Exception as e:
        return f"读取 Notebook 失败: {str(e)}", True
    
    cells = nb.get('cells', [])
    if cell_index < 0 or cell_index >= len(cells):
        return f"Cell 索引 {cell_index} 超出范围 (0-{len(cells)-1})", True
    
    cell = cells[cell_index]
    old_source = cell.get('source', '')
    if isinstance(old_source, list):
        old_source = ''.join(old_source)
    
    if '\n' in new_code:
        cell['source'] = new_code.splitlines(True)
        if not cell['source'][-1].endswith('\n'):
            cell['source'][-1] += '\n'
    else:
        cell['source'] = new_code + '\n'
    
    cell['outputs'] = []
    cell['execution_count'] = None
    
    try:
        with open(full_path, 'w', encoding='utf-8') as f:
            json.dump(nb, f, ensure_ascii=False, indent=1)
    except Exception as e:
        return f"写入 Notebook 失败: {str(e)}", True
    
    return f"Cell [{cell_index}] 更新成功", False

def add_notebook_cell(workspace_dir: str, path: str, cell_type: str = "code", cell_index: Optional[int] = None, source: str = "") -> tuple[str, bool]:
    full_path = os.path.join(workspace_dir, path)
    
    if not os.path.exists(full_path):
        return f"文件不存在: {path}", True
    
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            nb = json.load(f)
    except json.JSONDecodeError as e:
        return f"Notebook JSON 解析失败: {str(e)}", True
    except Exception as e:
        return f"读取 Notebook 失败: {str(e)}", True
    
    new_cell = {
        "cell_type": cell_type,
        "source": source + '\n' if source else '',
        "metadata": {},
    }
    
    if cell_type == "code":
        new_cell["execution_count"] = None
        new_cell["outputs"] = []
    elif cell_type == "markdown":
        pass
    
    cells = nb.get('cells', [])
    if cell_index is not None and 0 <= cell_index <= len(cells):
        cells.insert(cell_index, new_cell)
        position_desc = f"位置 {cell_index}"
    else:
        cells.append(new_cell)
        position_desc = f"末尾 (索引 {len(cells)-1})"
    
    nb['cells'] = cells
    
    try:
        with open(full_path, 'w', encoding='utf-8') as f:
            json.dump(nb, f, ensure_ascii=False, indent=1)
    except Exception as e:
        return f"写入 Notebook 失败: {str(e)}", True
    
    return f"新 {cell_type} Cell 添加成功，{position_desc}", False

def execute_notebook_tool(action: str, **kwargs) -> tuple[str, bool]:
    workspace_dir = kwargs.get("workspace_dir", ".")
    path = kwargs.get("path", "")
    
    if not path:
        return "Notebook 文件路径不能为空", True
    
    if action == "read":
        return read_notebook(workspace_dir, path)
    elif action == "edit_cell":
        cell_index = kwargs.get("cell_index")
        new_code = kwargs.get("new_code", "")
        if cell_index is None:
            return "cell_index 不能为空", True
        return edit_notebook_cell(workspace_dir, path, int(cell_index), new_code)
    elif action == "add_cell":
        cell_type = kwargs.get("cell_type", "code")
        cell_index = kwargs.get("cell_index")
        source = kwargs.get("source", "")
        return add_notebook_cell(workspace_dir, path, cell_type, cell_index, source)
    else:
        return f"未知 Notebook 操作: {action}", True

NOTEBOOK_TOOL_DEFINITION_OPENAI = {
    "type": "function",
    "function": {
        "name": "notebook_tool",
        "description": "Jupyter Notebook 原生手术刀（读取、编辑 Cell、添加 Cell）",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "操作类型：read, edit_cell, add_cell",
                    "enum": ["read", "edit_cell", "add_cell"]
                },
                "path": {
                    "type": "string",
                    "description": "Notebook 文件路径（.ipynb）"
                },
                "cell_index": {
                    "type": "integer",
                    "description": "Cell 索引号（edit_cell 必填，add_cell 可选）"
                },
                "new_code": {
                    "type": "string",
                    "description": "新的 Cell 代码内容（edit_cell 必填）"
                },
                "cell_type": {
                    "type": "string",
                    "description": "Cell 类型（add_cell 可选，默认 code）",
                    "enum": ["code", "markdown"]
                },
                "source": {
                    "type": "string",
                    "description": "新 Cell 的源码内容（add_cell 可选）"
                }
            },
            "required": ["action", "path"]
        }
    }
}

NOTEBOOK_TOOL_DEFINITION_ANTHROPIC = {
    "name": "notebook_tool",
    "description": "Jupyter Notebook 原生手术刀（读取、编辑 Cell、添加 Cell）",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作类型：read, edit_cell, add_cell",
                "enum": ["read", "edit_cell", "add_cell"]
            },
            "path": {
                "type": "string",
                "description": "Notebook 文件路径（.ipynb）"
            },
            "cell_index": {
                "type": "integer",
                "description": "Cell 索引号（edit_cell 必填，add_cell 可选）"
            },
            "new_code": {
                "type": "string",
                "description": "新的 Cell 代码内容（edit_cell 必填）"
            },
            "cell_type": {
                "type": "string",
                "description": "Cell 类型（add_cell 可选，默认 code）",
                "enum": ["code", "markdown"]
            },
            "source": {
                "type": "string",
                "description": "新 Cell 的源码内容（add_cell 可选）"
            }
        },
        "required": ["action", "path"]
    }
}
