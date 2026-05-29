import logging
import os
import re
from datetime import datetime
from typing import Dict, Any

from app.agent_workflow.state import WorkflowState
from app.services.excel_service import ExcelDataProcessor

logger = logging.getLogger(__name__)

DATA_AGENT_SYSTEM_PROMPT = """你是一个顶级的数据分析师 (Data Analyst Agent)。
你写出的 Python 代码会被直接在沙盒中执行。
环境已经预先为你加载了 `df` (Pandas DataFrame) 代表当前 Excel 数据，并导入了 `pd` 和 `plt` (matplotlib.pyplot)。

【你的任务】：根据用户的指令和以下 Excel Schema，编写 Python 代码进行数据分析、处理或画图。

【输出要求】：
1. 只输出可以执行的纯 Python 代码，不要输出任何多余的解释文字！用 ```python 开头，``` 结束。
2. 需要输出的分析结论，请用 `print()` 打印出来。
3. 如果需要画图，请直接使用 `plt.plot()` 等方法画图，环境会自动捕捉图像，【绝对不要】调用 `plt.show()`。
4. 为了防止中文字体乱码，请在画图前加上：plt.rcParams['font.sans-serif']=['SimHei'] 或使用英文字段。
5. 禁止使用 `plt.show()`，禁止 import os, sys, subprocess 等系统模块。"""


async def process_excel_node(
    state: WorkflowState,
    excel_processor: ExcelDataProcessor,
    llm_client,
    rag_engine=None,
) -> WorkflowState:
    file_path = state.get("file_path", "")
    user_instruction = state.get("user_instruction", "请分析这份数据并给出总结。")
    user_id = state.get("user_id", "")

    logger.info(f"📊 [DataAgent] starting for {file_path}")

    rag_context = ""
    if rag_engine and user_id:
        try:
            query = user_instruction if user_instruction else "数据分析方法"
            results = await rag_engine.semantic_search(query=query, top_k=3, user_id=user_id)
            if results:
                rag_parts = []
                for r in results[:3]:
                    content = r.get("content", "")
                    if content:
                        rag_parts.append(content[:500])
                if rag_parts:
                    rag_context = "\n\n".join(rag_parts)
                    logger.info(f"📊 [DataAgent] RAG retrieved {len(rag_parts)} knowledge chunks for context")
        except Exception as e:
            logger.warning(f"📊 [DataAgent] RAG retrieval failed: {e}")

    schema = await excel_processor.extract_excel_schema(file_path)

    max_attempts = 3
    code = ""
    execution_log = []
    final_result = {}
    error_msg = ""

    from langchain_core.prompts import ChatPromptTemplate

    system_prompt_filled = DATA_AGENT_SYSTEM_PROMPT.replace("{schema}", str(schema))

    if rag_context:
        system_prompt_filled += f"\n\n【行业知识库参考】（写代码时必须参考以下行业知识和计算口径）:\n{rag_context}"

    prompt_template = ChatPromptTemplate.from_messages([
        ("system", system_prompt_filled),
        ("user", "【用户指令】: {instruction}"),
    ])

    for attempt in range(max_attempts):
        logger.info(f"📊 [DataAgent] 第 {attempt + 1} 次尝试生成/修复代码...")

        if attempt == 0:
            messages = prompt_template.format_messages(instruction=user_instruction)
        else:
            correction_template = ChatPromptTemplate.from_messages([
                ("system", system_prompt_filled),
                ("user", "【用户指令】: {instruction}\n\n【刚才执行的代码报错了】:\n{error_msg}\n\n请分析错误原因，并输出修正后的完整 Python 代码。"),
            ])
            messages = correction_template.format_messages(
                instruction=user_instruction,
                error_msg=error_msg,
            )

        response = await llm_client.acall_api(
            [{"role": m.type, "content": m.content} for m in messages],
            max_tokens=4096,
        )

        code_match = re.search(r"```python\s*(.*?)\s*```", response, re.DOTALL)
        code = code_match.group(1).strip() if code_match else response.strip()
        execution_log.append(f"尝试 {attempt + 1} 生成代码:\n{code}")

        result = await excel_processor.execute_python_code(file_path, code)

        if result["success"]:
            logger.info(f"📊 [DataAgent] 代码执行成功！")
            final_result = result
            error_msg = ""
            break
        else:
            error_msg = result.get("error", "Unknown error")
            logger.warning(f"📊 [DataAgent] 代码执行失败，触发纠错机制: {error_msg[:150]}...")
            execution_log.append(f"执行报错:\n{error_msg}")

    preview_html = _build_preview_html(final_result, schema, user_instruction)

    structured_data = {
        "analysis_output": final_result.get("output", ""),
        "image_base64": final_result.get("image_base64"),
        "schema": schema,
        "execution_log": execution_log,
        "attempts": len(execution_log),
        "success": final_result.get("success", False),
    }

    output_path = _generate_output_path(file_path)
    try:
        from app.services.excel_service import ExcelDataProcessor as _EDP
        proc = _EDP()
        save_result = await proc.execute_pandas_code(
            code=code,
            input_path=file_path,
            output_path=output_path,
        )
        if save_result.get("success"):
            output_path = save_result.get("output_path", output_path)
    except Exception as e:
        logger.warning(f"📊 [DataAgent] 保存清洗结果失败: {e}")

    logger.info(f"📊 [DataAgent] completed, success={final_result.get('success', False)}")

    return {
        **state,
        "generated_code": code,
        "code_execution_log": execution_log,
        "code_execution_error": error_msg,
        "structured_data": structured_data,
        "output_path": output_path,
        "error_message": error_msg,
        "filled_html": preview_html,
    }


def _build_preview_html(result: dict, schema: dict, instruction: str) -> str:
    output = result.get("output", "代码未输出任何文本")
    img_b64 = result.get("image_base64")

    html = "<div style='padding: 20px; font-family: sans-serif;'>"
    html += "<h2 style='color: #4f46e5; border-bottom: 2px solid #e5e7eb; padding-bottom: 10px;'>📊 数据分析报告</h2>"
    html += f"<h4 style='color: #6b7280; margin-top: 20px;'>💡 AI 分析结论:</h4>"
    html += f"<pre style='background: #1f2937; color: #a5b4fc; padding: 15px; border-radius: 8px; white-space: pre-wrap;'>{output}</pre>"

    if img_b64:
        html += "<h4 style='color: #6b7280; margin-top: 20px;'>📈 可视化图表:</h4>"
        html += f"<img src='data:image/png;base64,{img_b64}' style='max-width: 100%; border-radius: 8px; border: 1px solid #e5e7eb;' />"

    html += "</div>"
    return html


def _generate_output_path(input_path: str) -> str:
    base = input_path.rsplit(".", 1)[0]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join("temp_workspace", "output")
    os.makedirs(output_dir, exist_ok=True)
    filename = os.path.basename(f"{base}_cleaned_{timestamp}.xlsx")
    return os.path.join(output_dir, filename)
