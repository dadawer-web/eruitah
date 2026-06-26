"""
ChatExcel 工作流节点 — 多轮对话式 SQL 查询

借鉴 DB-GPT ChatExcel 场景:
  1. 将 Excel 数据导入 DuckDB 内存数据库
  2. 用户用自然语言提问 → LLM 生成 DuckDB SQL → 执行查询
  3. 自动选择数据展示方式（表格/柱状图/折线图/饼图）
  4. 结构化输出格式 <api-call><name>[展示方式]</name><args><sql>...</sql></args></api-call>
  5. 支持多轮对话：通过 thread_id + MemorySaver 保持会话状态

工作流:
  首次调用: 加载 Excel → DuckDB → 提取 Schema → 生成 SQL → 执行 → 返回结果
  后续调用: 复用 DuckDB 连接 → 生成 SQL → 执行 → 返回结果
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.agent_workflow.state import WorkflowState
from app.services.excel_service import ExcelDataProcessor

logger = logging.getLogger(__name__)

# DuckDB 表名前缀，避免冲突
_DUCKDB_TABLE = "excel_data"

# ChatExcel 系统提示词（借鉴 DB-GPT chat_excel prompt.py）
CHATEXCEL_SYSTEM_PROMPT = """你是一个数据分析专家！

用户有一份待分析的表格数据，已经导入到 DuckDB 内存表中。

DuckDB 表结构信息如下：
{table_schema}

采样数据（前5行）：
{sample_data}

【极其严格的表结构限制】
你必须且只能使用上述 Schema 中明确列出的列名！
绝不允许使用"假设存在"的列（如假设有 Profit 列）。
如果用户查询的指标（如利润 Profit）在表中不存在，你必须：
  a) 使用其他合理的可用列（如销售额 Sales）作为替代进行分析
  b) 或仅查询可用的数据，绝不能在 SQL 中写不存在的列名！
违反此规则将导致系统崩溃，是最高优先级的禁令！

DuckDB 中需要特别注意的语法规则：
1. 任何出现在 SELECT 子句中的非聚合列，必须同时出现在 GROUP BY 子句中
2. 当在 ORDER BY 或窗口函数中引用某个列时，确保该列已在前面的 CTE 或查询中被正确选择
3. 在构建多层 CTE 时，需要确保各层之间的列引用一致性
4. 如果某列不需要精确值，可以使用 ANY_VALUE() 函数作为替代方案
5. DuckDB 处理时间戳需通过专用函数（如 to_timestamp()）而非直接 CAST

请基于数据结构信息，在满足下面约束条件下通过 DuckDB SQL 数据分析回答用户的问题。

约束条件:
  1. 请充分理解用户的问题，使用 DuckDB SQL 的方式进行分析，分析内容按下面要求的输出格式返回，SQL 请输出在对应的 SQL 参数中
  2. 请从如下给出的展示方式中选择最优的一种用以进行数据渲染，将类型名称放入返回要求格式的 name 参数值中。可用数据展示方式: {display_types}
  3. SQL 中需要使用的表名是: {table_name}，请检查你生成的 SQL，不要使用没在数据结构中的列名
  4. 优先使用数据分析的方式回答，如果用户问题不涉及数据分析内容，你可以按你的理解进行回答
  5. 请注意，注释行要单独一行，不要放在 SQL 语句的同一行中
  6. 你现在支持箱线图(response_box)、散点图(response_scatter)、直方图(response_histogram)等高级图表，请大胆使用：
     - 当用户需要分析数据分布、查看异常值、或做分组对比时，请优先选择 response_box（箱线图能直观展示中位数、四分位距与离群点）
     - 当用户需要分析两个数值变量之间的相关性（如销售额与利润的关系）时，请选择 response_scatter
     - 当用户需要查看单个数值列的分布形态（如销售额集中区间）时，请选择 response_histogram
     - 注意：箱线图/散点图/直方图对应的 SQL 应返回明细数据而非过度聚合，以便绘图引擎呈现真实分布

请一步一步思考，给出回答，并确保你的回答内容格式如下:
    [对用户说的分析思路摘要]
    <api-call><name>[数据展示方式]</name><args>
    <sql>[正确的 DuckDB 数据分析 SQL]</sql></args></api-call>

你可以参考下面的样例:

样例1：
user: 分析各地区的销售额和利润，需要显示地区名称、总销售额、总利润以及平均利润率（利润/销售额）。
assistant: [分析思路]
1. 需要识别查询核心维度(地区)和指标(销售额、利润、利润率)
2. 利润率计算需在聚合后计算，避免分母错误
3. 过滤空地区保证数据准确性
4. 按销售额降序排列方便业务解读
<api-call><name>response_table</name><args><sql>
SELECT region AS 地区,
       SUM(sales) AS 总销售额,
       SUM(profit) AS 总利润,
       SUM(profit)/NULLIF(SUM(sales),0) AS 利润率
FROM {table_name}
WHERE region IS NOT NULL
GROUP BY region
ORDER BY 总销售额 DESC;
</sql></args></api-call>

样例2：
user: Show monthly sales trend for the last 2 years.
assistant: [Analysis Insights]
1. Time range handling: Use DATE_TRUNC for monthly granularity
2. Calculate rolling 24-month period dynamically
3. Order date sorting ensures chronological trend
<api-call><name>response_table</name><args><sql>
SELECT
  DATE_TRUNC('month', order_date)::DATE AS year_month,
  COUNT(DISTINCT order_id) AS order_count,
  AVG(order_value) AS avg_order_value
FROM {table_name}
WHERE order_date >= CURRENT_DATE - INTERVAL '2 years'
  AND order_date IS NOT NULL
GROUP BY 1
ORDER BY year_month ASC;
</sql></args></api-call>

注意，回答一定要符合 <api-call> 的格式! 请使用和用户问题相同的语言回答！"""

# 可选的展示方式（已全面解锁：分布/异常值/相关性分析场景可用高级图表）
_DISPLAY_TYPES = (
    "response_table(表格), response_bar(柱状图), response_line(折线图), response_pie(饼图), "
    "response_box(箱线图), response_scatter(散点图), response_histogram(直方图)"
)


def _parse_api_call(response: str) -> Optional[Dict[str, str]]:
    """
    解析 LLM 输出中的 <api-call> 结构化标签

    Returns:
        {"display_type": str, "sql": str, "summary": str} 或 None
    """
    # 提取 summary（<api-call> 之前的内容）
    api_call_pos = response.find("<api-call>")
    summary = response[:api_call_pos].strip() if api_call_pos != -1 else response.strip()

    # 提取 <name>...</name>
    name_match = re.search(r"<name>\s*(.*?)\s*</name>", response, re.DOTALL)
    # 提取 <sql>...</sql>
    sql_match = re.search(r"<sql>\s*(.*?)\s*</sql>", response, re.DOTALL)

    if not name_match or not sql_match:
        return None

    return {
        "display_type": name_match.group(1).strip(),
        "sql": sql_match.group(1).strip(),
        "summary": summary,
    }


def _select_display_type(display_type: str) -> str:
    """将 LLM 输出的展示方式映射为标准类型"""
    dt = display_type.lower().strip()
    if "bar" in dt:
        return "bar_chart"
    elif "line" in dt:
        return "line_chart"
    elif "pie" in dt:
        return "pie_chart"
    elif "box" in dt:
        return "box_plot"
    elif "scatter" in dt:
        return "scatter_plot"
    elif "hist" in dt:
        return "histogram"
    else:
        return "table"


def _display_type_to_chart_type(display_type: str) -> str:
    """将 chat_excel 的 display_type 映射为 ChartPipeline 的 chart_type"""
    dt = (display_type or "").lower().strip()
    if dt == "bar_chart":
        return "bar"
    elif dt == "line_chart":
        return "line"
    elif dt == "pie_chart":
        return "pie"
    elif dt == "box_plot":
        return "box"
    elif dt == "scatter_plot":
        return "scatter"
    elif dt == "histogram":
        return "hist"
    else:
        return ""  # table 或未知 → 不绘图


async def _generate_node_output(
    excel_processor: ExcelDataProcessor,
    file_path: str,
    sql: str,
    display_type: str,
    summary: str,
    query_result: Dict[str, Any],
    duckdb_info: Dict[str, Any],
    user_instruction: str,
    table_name: str = "excel_data",
) -> Dict[str, Any]:
    """
    统一成功出口逻辑（Consolidate Success Flow）

    将『执行 SQL -> 传入绘图管道 -> 渲染三段式 HTML 报告』封装为独立核心函数。
    首轮成功与纠错重试成功均调用此函数，确保物理图表始终被生成并注入 HTML，
    绝不直接把原始数据表格当纯文本输出。

    绘图采用 DataFrame 直传方式（彻底规避连接隔离 / Catalog Error）：
      1. execute_sql_to_df(sql, table_name) 在已加载的连接 A 上执行 SQL，拿到 result_df
         （复用 load_to_duckdb 缓存的连接 self._duckdb_connections[table_name]）
      2. draw_chart_from_df(result_df, ...) 让 Matplotlib 直接读取内存 df 绘图
         （绘图函数内部不再二次查询数据库）

    Args:
        excel_processor: Excel 数据处理器（提供 execute_sql_to_df / draw_chart_from_df）
        file_path: Excel 文件路径（保留以备回退，当前 df 路径不直接使用）
        sql: 已执行成功的（或纠正后的）DuckDB SQL
        display_type: 展示方式 table/bar_chart/line_chart/pie_chart
        summary: LLM 给出的分析思路摘要
        query_result: _execute_duckdb_async 返回 {success, columns, data, row_count, error}
        duckdb_info: DuckDB 元信息（用于表结构展示）
        user_instruction: 用户原始问题（用作图表标题）
        table_name: DuckDB 已注册的表名（连接 A 的索引键，默认 excel_data）

    Returns:
        {"result_data": dict, "filled_html": str, "chart_base64": str|None}
    """
    # ── 物理绘图：连接A执行SQL -> DataFrame直传 -> Matplotlib绘图 ──
    chart_type = _display_type_to_chart_type(display_type)
    chart_base64: Optional[str] = None

    if chart_type and query_result.get("success") and query_result.get("data"):
        try:
            title = (user_instruction or "数据分析")[:60]

            # 1) 在已加载的连接 A 上执行 SQL，拿到原始 DataFrame（杜绝连接隔离 / Catalog Error）
            df_result = await asyncio_to_thread(
                excel_processor.execute_sql_to_df, sql, table_name
            )
            if not df_result.get("success") or df_result.get("df") is None:
                logger.warning(
                    f"📊 [ChatExcel] 绘图取数失败(连接A): "
                    f"{df_result.get('error', '未知错误')}"
                )
            else:
                result_df = df_result["df"]
                # 2) DataFrame 直传绘图管道（内部不再二次查询数据库）
                pipeline_result = await asyncio_to_thread(
                    excel_processor.draw_chart_from_df,
                    result_df, chart_type, title, summary or "",
                )
                if pipeline_result.get("success"):
                    chart_base64 = pipeline_result.get("image_base64")
                    logger.info(
                        f"📊 [ChatExcel] ChartPipeline 绘图成功, "
                        f"base64 长度={len(chart_base64) if chart_base64 else 0}"
                    )
                else:
                    logger.warning(
                        f"📊 [ChatExcel] ChartPipeline 绘图失败: "
                        f"{pipeline_result.get('error', '未知错误')}"
                    )
        except Exception as e:
            logger.warning(f"📊 [ChatExcel] ChartPipeline 异常（不影响数据返回）: {e}")

    # ── 组装结构化结果 ──
    result_data = {
        "question": user_instruction,
        "sql": sql,
        "display_type": display_type,
        "summary": summary,
        "columns": query_result.get("columns", []),
        "data": query_result.get("data", []),
        "row_count": query_result.get("row_count", 0),
        "success": query_result.get("success", False),
        "error": query_result.get("error"),
        "chart_base64": chart_base64,
    }

    # ── 渲染三段式 HTML 报告（强制注入物理图片）──
    filled_html = _build_chatexcel_html(result_data, duckdb_info, chart_base64)

    return {
        "result_data": result_data,
        "filled_html": filled_html,
        "chart_base64": chart_base64,
    }


async def chat_excel_node(
    state: WorkflowState,
    excel_processor: ExcelDataProcessor,
    llm_client,
    rag_engine=None,
) -> WorkflowState:
    """
    ChatExcel 节点 — 多轮对话式 SQL 查询

    首次调用: 加载 Excel → DuckDB → 生成 SQL → 执行
    后续调用: 复用 DuckDB → 生成 SQL → 执行

    通过 state["duckdb_loaded"] 判断是否已加载
    """
    file_path = state.get("file_path", "")
    user_instruction = state.get("user_instruction", "请分析这份数据并给出总结。")
    user_id = state.get("user_id", "")

    logger.info(f"📊 [ChatExcel] starting for {file_path}, instruction: {user_instruction[:80]}")

    # ── Step 1: 首次调用时加载 Excel 到 DuckDB ──
    duckdb_info = state.get("structured_data", {}).get("duckdb_info")
    if not duckdb_info:
        logger.info(f"📊 [ChatExcel] 首次加载，导入 DuckDB...")
        load_result = await _load_to_duckdb_async(excel_processor, file_path)

        if load_result.get("error"):
            logger.error(f"📊 [ChatExcel] DuckDB 加载失败: {load_result['error']}")
            return {
                **state,
                "error_message": f"DuckDB 加载失败: {load_result['error']}",
                "filled_html": _build_error_html(load_result["error"]),
            }

        duckdb_info = load_result
        logger.info(
            f"📊 [ChatExcel] DuckDB 加载成功: {load_result['row_count']} rows, "
            f"{len(load_result['schema']['columns'])} columns"
        )
    else:
        logger.info(f"📊 [ChatExcel] 复用已加载的 DuckDB 连接")

    table_name = duckdb_info.get("table_name", _DUCKDB_TABLE)
    schema_sql = duckdb_info.get("duckdb_schema_sql", "")
    sample_data = duckdb_info.get("sample_data", [])

    # ── Step 2: RAG 知识库增强（可选）──
    rag_context = ""
    if rag_engine and user_id:
        try:
            query = user_instruction if user_instruction else "数据分析方法"
            results = await rag_engine.semantic_search(query=query, top_k=3, user_id=user_id)
            if results:
                rag_parts = [r.get("content", "")[:500] for r in results[:3] if r.get("content")]
                if rag_parts:
                    rag_context = "\n\n".join(rag_parts)
                    logger.info(f"📊 [ChatExcel] RAG retrieved {len(rag_parts)} knowledge chunks")
        except Exception as e:
            logger.warning(f"📊 [ChatExcel] RAG retrieval failed: {e}")

    # ── Step 3: 构造 Prompt，调用 LLM 生成 SQL ──
    from langchain_core.prompts import ChatPromptTemplate

    system_prompt = CHATEXCEL_SYSTEM_PROMPT.format(
        table_schema=schema_sql,
        sample_data=json.dumps(sample_data, ensure_ascii=False, default=str, indent=2),
        display_types=_DISPLAY_TYPES,
        table_name=table_name,
    )

    if rag_context:
        system_prompt += f"\n\n【行业知识库参考】（分析时请参考以下行业知识和计算口径）:\n{rag_context}"

    # 多轮对话：从 state 中获取历史
    chat_history = state.get("structured_data", {}).get("chat_history", [])
    messages_for_llm = [{"role": "system", "content": system_prompt}]

    # 添加历史对话（最近3轮）
    for hist in chat_history[-6:]:
        messages_for_llm.append({"role": "user", "content": hist.get("question", "")})
        if hist.get("answer"):
            messages_for_llm.append({"role": "assistant", "content": hist["answer"]})

    messages_for_llm.append({"role": "user", "content": user_instruction})

    logger.info(f"📊 [ChatExcel] 调用 LLM 生成 SQL (history={len(chat_history)} rounds)...")

    response = await llm_client.acall_api(messages_for_llm, max_tokens=4096)

    # ── Step 4: 解析 LLM 输出，提取 SQL ──
    parsed = _parse_api_call(response)

    if not parsed:
        # LLM 未按格式输出，尝试提取 SQL 代码块
        sql_match = re.search(r"```sql\s*(.*?)\s*```", response, re.DOTALL)
        if sql_match:
            parsed = {
                "display_type": "response_table",
                "sql": sql_match.group(1).strip(),
                "summary": response,
            }
        else:
            logger.warning(f"📊 [ChatExcel] LLM 输出未包含 <api-call> 格式，返回原始文本")
            return {
                **state,
                "structured_data": {
                    **state.get("structured_data", {}),
                    "duckdb_info": duckdb_info,
                    "chat_history": chat_history + [{"question": user_instruction, "answer": response}],
                    "chat_mode": True,
                    "raw_response": response,
                },
                "filled_html": _build_text_html(response, user_instruction),
            }

    sql = parsed["sql"]
    display_type = _select_display_type(parsed["display_type"])
    summary = parsed["summary"]

    logger.info(f"📊 [ChatExcel] 生成 SQL: {sql[:150]}...")
    logger.info(f"📊 [ChatExcel] 展示方式: {display_type}")

    # ── Step 5: 执行 DuckDB 查询 ──
    query_result = await _execute_duckdb_async(excel_processor, sql, table_name)

    if not query_result["success"]:
        # SQL 执行失败，尝试一次纠错
        logger.warning(f"📊 [ChatExcel] SQL 执行失败: {query_result['error']}, 尝试纠错...")

        # 提取可用列名列表，帮助 LLM 纠错
        available_columns = duckdb_info.get("schema", {}).get("columns", [])
        col_names = [c["name"] for c in available_columns] if available_columns else []

        correction_prompt = f"""之前的 SQL 执行报错了：
SQL: {sql}
错误: {query_result['error']}

表结构:
{schema_sql}

【可用列名列表】（只能使用以下列名，绝不允许使用不在此列表中的列）:
{', '.join(col_names) if col_names else '未知'}

请分析错误原因，并输出修正后的 SQL。
【极其严格的要求】：
1. 只能使用上述列名列表中的列！
2. 如果之前的 SQL 引用了不存在的列（如 Profit），必须改用存在的列（如 Sales）！
3. 只输出 SQL 代码，不要其他内容！"""

        correction_response = await llm_client.acall_api(
            [{"role": "system", "content": (
                "你是 SQL 语法修复专家。系统需要你修复 SQL 语法错误。"
                "修复后请直接输出合法的 SQL 语句，禁止输出具体的行数据，"
                "图表将由系统底层 Python 引擎自动绘制。"
                "只输出修正后的 SQL 代码，不要任何解释或思考过程。"
             )},
             {"role": "user", "content": correction_prompt}],
            max_tokens=8192,
        )

        # 🔑 空值兜底：LLM 可能因 finish_reason=length 返回空内容
        if not correction_response or not correction_response.strip():
            logger.error(f"📊 [ChatExcel] 纠错 LLM 返回空内容（可能 finish_reason=length 截断）")
            return {
                **state,
                "structured_data": {
                    **state.get("structured_data", {}),
                    "duckdb_info": duckdb_info,
                    "chat_history": chat_history + [{"question": user_instruction, "answer": "大模型未能生成有效的 SQL，请尝试简化您的提问。"}],
                    "chat_mode": True,
                    "raw_response": "大模型未能生成有效的 SQL，请尝试简化您的提问。",
                },
                "filled_html": _build_text_html("大模型未能生成有效的 SQL，请尝试简化您的提问。", user_instruction),
            }

        # 提取修正后的 SQL
        corrected_sql_match = re.search(r"```sql\s*(.*?)\s*```", correction_response, re.DOTALL)
        corrected_sql = corrected_sql_match.group(1).strip() if corrected_sql_match else correction_response.strip()

        # 🔑 二次空值检查
        if not corrected_sql or corrected_sql.strip() == "":
            logger.error(f"📊 [ChatExcel] 纠错后 SQL 为空")
            return {
                **state,
                "structured_data": {
                    **state.get("structured_data", {}),
                    "duckdb_info": duckdb_info,
                    "chat_history": chat_history + [{"question": user_instruction, "answer": "大模型未能生成有效的 SQL，请尝试简化您的提问。"}],
                    "chat_mode": True,
                    "raw_response": "大模型未能生成有效的 SQL，请尝试简化您的提问。",
                },
                "filled_html": _build_text_html("大模型未能生成有效的 SQL，请尝试简化您的提问。", user_instruction),
            }

        logger.info(f"📊 [ChatExcel] 纠正 SQL: {corrected_sql[:150]}...")

        query_result = await _execute_duckdb_async(excel_processor, corrected_sql, table_name)
        if query_result["success"]:
            sql = corrected_sql
        else:
            logger.error(f"📊 [ChatExcel] 纠正后仍失败: {query_result['error']}")

    # ── Step 6: 统一成功出口 — 物理绘图 + 渲染三段式 HTML 报告 ──
    # 首轮成功与纠错重试成功均走此出口，确保物理图表始终被生成并注入 HTML
    node_output = await _generate_node_output(
        excel_processor=excel_processor,
        file_path=file_path,
        sql=sql,
        display_type=display_type,
        summary=summary,
        query_result=query_result,
        duckdb_info=duckdb_info,
        user_instruction=user_instruction,
        table_name=table_name,
    )

    result_data = node_output["result_data"]
    preview_html = node_output["filled_html"]

    # 更新对话历史
    new_chat_history = chat_history + [{
        "question": user_instruction,
        "answer": summary,
        "sql": sql,
    }]

    logger.info(
        f"📊 [ChatExcel] completed, success={result_data['success']}, "
        f"rows={result_data['row_count']}, display={display_type}, "
        f"has_chart={bool(node_output['chart_base64'])}"
    )

    return {
        **state,
        "structured_data": {
            **state.get("structured_data", {}),
            "duckdb_info": duckdb_info,
            "chat_history": new_chat_history,
            "chat_mode": True,
            "query_result": result_data,
        },
        "generated_code": sql,
        "filled_html": preview_html,
        "error_message": result_data.get("error", ""),
    }


async def _load_to_duckdb_async(
    processor: ExcelDataProcessor, file_path: str
) -> Dict[str, Any]:
    """异步加载 Excel 到 DuckDB"""
    return await asyncio_to_thread(processor.load_to_duckdb, file_path, _DUCKDB_TABLE)


async def _execute_duckdb_async(
    processor: ExcelDataProcessor, sql: str, table_name: str
) -> Dict[str, Any]:
    """异步执行 DuckDB 查询"""
    return await asyncio_to_thread(processor.execute_duckdb_query, sql, table_name)


async def asyncio_to_thread(func, *args, **kwargs):
    """异步包装同步函数"""
    import asyncio
    return await asyncio.to_thread(func, *args, **kwargs)


def _build_chatexcel_html(
    result: Dict[str, Any],
    duckdb_info: Dict[str, Any],
    chart_base64: Optional[str] = None,
) -> str:
    """构建 ChatExcel 结果 HTML 预览（三段式：分析思路 / SQL / 数据表+物理图表）"""
    summary = result.get("summary", "")
    display_type = result.get("display_type", "table")
    columns = result.get("columns", [])
    data = result.get("data", [])
    sql = result.get("sql", "")
    success = result.get("success", False)
    error = result.get("error")
    row_count = result.get("row_count", 0)

    # 优先使用显式传入的 chart_base64，其次从 result 中读取（向后兼容）
    chart_base64 = chart_base64 or result.get("chart_base64")

    html = "<div style='padding: 20px; font-family: sans-serif;'>"
    html += "<h2 style='color: #4f46e5; border-bottom: 2px solid #e5e7eb; padding-bottom: 10px;'>📊 ChatExcel 数据查询</h2>"

    # 分析思路
    if summary:
        html += f"<h4 style='color: #6b7280; margin-top: 20px;'>💡 分析思路:</h4>"
        html += f"<pre style='background: #f9fafb; color: #374151; padding: 15px; border-radius: 8px; white-space: pre-wrap; border: 1px solid #e5e7eb;'>{summary}</pre>"

    # SQL 语句
    if sql:
        html += f"<h4 style='color: #6b7280; margin-top: 20px;'>🔍 SQL 查询:</h4>"
        html += f"<pre style='background: #1f2937; color: #a5b4fc; padding: 15px; border-radius: 8px; white-space: pre-wrap; overflow-x: auto;'>{sql}</pre>"

    # 错误信息
    if not success and error:
        html += f"<div style='background: #fef2f2; color: #dc2626; padding: 15px; border-radius: 8px; margin-top: 15px; border: 1px solid #fecaca;'><strong>❌ 查询失败:</strong> {error}</div>"
        html += "</div>"
        return html

    # 查询结果
    if data and columns:
        display_labels = {
            "table": "📋 数据表格",
            "bar_chart": "📊 柱状图",
            "line_chart": "📈 折线图",
            "pie_chart": "🥧 饼图",
            "box_plot": "📦 箱线图",
            "scatter_plot": "🔵 散点图",
            "histogram": "📊 直方图",
        }
        label = display_labels.get(display_type, "📋 数据表格")

        html += f"<h4 style='color: #6b7280; margin-top: 20px;'>{label} ({row_count} 行结果):</h4>"

        # 限制显示行数
        display_data = data[:100]
        if len(data) > 100:
            display_data.append({col: "..." for col in columns})

        # 构建表格
        html += "<div style='overflow-x: auto; margin-top: 10px;'>"
        html += "<table style='border-collapse: collapse; width: 100%; font-size: 14px;'>"
        html += "<thead><tr style='background: #f3f4f6;'>"
        for col in columns:
            html += f"<th style='border: 1px solid #d1d5db; padding: 8px 12px; text-align: left; font-weight: 600;'>{col}</th>"
        html += "</tr></thead><tbody>"
        for row in display_data:
            html += "<tr>"
            for col in columns:
                val = row.get(col, "")
                if val is None:
                    val = ""
                html += f"<td style='border: 1px solid #e5e7eb; padding: 8px 12px;'>{val}</td>"
            html += "</tr>"
        html += "</tbody></table></div>"

        # 物理图表注入：只要 chart_base64 存在，强制包裹 <img> 标签
        if chart_base64:
            img_html = (
                f'<div style="text-align:center; margin:20px 0;">'
                f'<img src="data:image/png;base64,{chart_base64}" '
                f'style="max-width:100%; border-radius:8px;"/></div>'
            )
            html += img_html
        elif display_type != "table":
            html += f"<div style='margin-top: 10px; color: #6b7280; font-size: 13px;'>💡 建议使用 <strong>{display_type}</strong> 方式渲染数据（前端可基于以上数据生成图表）</div>"

    # 数据信息
    schema_info = duckdb_info.get("schema", {}).get("columns", [])
    if schema_info:
        html += "<details style='margin-top: 20px;'><summary style='cursor: pointer; color: #6b7280; font-size: 13px;'>📋 表结构信息</summary>"
        html += "<div style='padding: 10px; background: #f9fafb; border-radius: 8px; margin-top: 5px;'>"
        html += "<table style='border-collapse: collapse; font-size: 13px;'><thead><tr><th style='padding: 4px 12px; text-align: left;'>列名</th><th style='padding: 4px 12px; text-align: left;'>类型</th></tr></thead><tbody>"
        for col in schema_info:
            html += f"<tr><td style='padding: 4px 12px;'>{col['name']}</td><td style='padding: 4px 12px; color: #6b7280;'>{col['type']}</td></tr>"
        html += "</tbody></table></div></details>"

    html += "</div>"
    return html


def _build_error_html(error_msg: str) -> str:
    """构建错误 HTML"""
    return f"""
    <div style='padding: 20px; font-family: sans-serif;'>
        <h2 style='color: #dc2626;'>❌ ChatExcel 加载失败</h2>
        <pre style='background: #fef2f2; color: #dc2626; padding: 15px; border-radius: 8px; white-space: pre-wrap;'>{error_msg}</pre>
    </div>
    """


def _build_text_html(text: str, instruction: str) -> str:
    """构建纯文本 HTML（LLM 未输出 SQL 时）"""
    return f"""
    <div style='padding: 20px; font-family: sans-serif;'>
        <h2 style='color: #4f46e5; border-bottom: 2px solid #e5e7eb; padding-bottom: 10px;'>📊 ChatExcel 分析</h2>
        <h4 style='color: #6b7280; margin-top: 20px;'>💡 问题: {instruction}</h4>
        <pre style='background: #f9fafb; color: #374151; padding: 15px; border-radius: 8px; white-space: pre-wrap; border: 1px solid #e5e7eb;'>{text}</pre>
    </div>
    """
