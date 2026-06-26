import logging
import os
import re
import json
from datetime import datetime
from typing import Dict, Any, Optional

from app.agent_workflow.state import WorkflowState
from app.services.excel_service import ExcelDataProcessor

logger = logging.getLogger(__name__)

# ============================================================
# Text-to-SQL-to-Chart 两阶段模式
# Step 1: LLM 生成 SQL + chart_type
# Step 2: Python 执行 SQL + 绘图
# Step 3: LLM 基于真实查询结果生成深度分析报告
# ============================================================

# ---------------------------------------------------------------------------
# Step 1 Prompt：仅生成 SQL + chart_type（不含 text_analysis）
# ---------------------------------------------------------------------------

SQL_GENERATION_PROMPT = """你是一个顶级数据战略顾问 (Top-tier Data Strategy Consultant)。
你的任务是根据用户的指令和 Excel Schema，生成一条 DuckDB SQL 查询来获取画图或分析所需的数据。

【Excel Schema】：
{schema}

【你的输出格式】
你必须且只能输出一个 JSON 对象，不要输出任何其他文字或代码块！格式如下：

```json
{{
  "sql": "你的 DuckDB SQL 查询语句",
  "chart_type": "图表类型（pie/bar/line/scatter/hist/box/none）",
  "title": "图表标题（中文）"
}}
```

【字段说明】
- `sql`: DuckDB SQL 查询。表名固定为 `df`（即 SELECT ... FROM df ...）。用于查出画图所需的聚合数据。
- `chart_type`: 必须严格根据用户指令决定！
  - 用户要求『饼图/饼状图/占比图』→ "pie"
  - 用户要求『柱状图/条形图』→ "bar"
  - 用户要求『折线图/趋势图』→ "line"
  - 用户要求『散点图』→ "scatter"
  - 用户要求『直方图/分布图』→ "hist"
  - 用户要求『箱线图』→ "box"
  - 用户没有要求画图，只需文字分析 → "none"
- `title`: 图表的中文标题，简洁概括分析主题。

【SQL 编写规则】
1. 表名固定为 `df`，例如：SELECT Department, COUNT(*) as cnt FROM df GROUP BY Department
2. 对于饼图和柱状图：SQL 应返回 2 列（第1列为分类标签，第2列为数值）。
3. 对于折线图：SQL 应返回 2 列（第1列为 X 轴，第2列为 Y 轴），按 X 轴排序。
4. 对于散点图：SQL 应返回 2 列（X 轴和 Y 轴的数值列）。
5. 对于直方图和箱线图：SQL 应返回 1 列（数值列）。
6. 如果用户没有要求画图（chart_type 为 none），SQL 可以返回任意分析结果。

【绝对红线】
1. 只输出 JSON，不要输出 Python 代码！
2. chart_type 必须严格匹配用户要求的图表类型，不要自行更改！
3. SQL 必须能直接在 DuckDB 中执行，表名为 df。
4. 不要在 JSON 中包含 text_analysis 字段！分析报告将在后续步骤中基于真实数据生成。"""


# ---------------------------------------------------------------------------
# Step 3 Prompt：基于真实查询结果生成深度分析报告
# ---------------------------------------------------------------------------

REPORT_GENERATION_PROMPT = """你是一个顶级数据战略顾问 (Top-tier Data Strategy Consultant)。
你需要基于真实的 SQL 查询结果，撰写一份深度的数据分析报告。

【用户原始需求】
{instruction}

【图表类型】
{chart_type_desc}

【核心分析依据：真实查询数据】
以下是你刚才编写的 SQL 在系统中执行后，得出的真实准确的数据结果（Markdown 格式）：

{result_data}

【严格指令】
你的所有分析、看板指标、数据对比，必须 100% 基于上述真实查询结果！
绝对禁止使用『假设』、『例如』、『预期』等词汇来捏造不存在的数据！
如果你提供的数据不在上述结果中，该次分析将被判定为严重失败。

【重要：图表已由系统自动生成】
系统已经根据上述查询结果自动生成了可视化图表（{chart_type_desc}）。
你只需输出文字分析结论！绝对不要在报告中重复输出原始数据表！
绝对不要建议前端去渲染图表——图表已嵌入报告中！

【你的输出格式】
请直接输出分析报告正文（纯文本，可使用 Markdown 格式），不要输出 JSON 或代码块！
不要在报告开头加 ``` 标记！

请先判断当前数据集所属的业务领域（如电商、人力资源、学术教育、金融、医疗、制造等），然后严格按以下四部分输出深度洞察：

🧠 【分析推演过程】（不少于 200 字）
在输出最终结论前，你必须先写出完整的思考推演链路：
- 数据反映了什么核心现象？
- 这个现象在该行业/领域内通常是由什么因素引起的？
- 如果持续发展，可能会造成什么长远影响？
- 有哪些数据异常点需要特别关注？
这一步是你的思维缓冲带，帮助你深入思考后再输出结论。禁止跳过！

📊 【核心数据看板】（不少于 150 字）
不仅要提炼极值点，还必须包含以下硬性维度：
- 核心极值指标及其具体数值
- 该极值占总体总量的百分比
- 与平均值/中位数的偏差倍数
- 数据整体健康度评级（优/良/中/差）及判定依据

🔍 【多维业务剖析】（不少于 500 字）
禁止概括性陈述！必须至少从 3 个不同的专业视角分别展开细致讨论：
- 每个视角必须独立成段，有明确的小标题
- 每项分析必须用具体的数字作为论据支撑（如"该指标较均值偏离了X倍"）
- 必须结合该数据所属领域的行业常识和业务逻辑
- 视角示例（根据领域自行选择最相关的）：商业场景→供应链/用户心理/竞品环境；教育场景→知识点难度/题型分布/学生认知盲区；金融场景→宏观经济/行业周期/政策影响

💡 【战略行动指南】（不少于 400 字）
必须给出至少 4 条具有可执行性的具体建议。每条建议必须包含以下三个要素：
- 『具体行动项』：描述要做什么，由谁负责，在什么时间框架内完成
- 『预期可解决的问题』：该行动直接针对上述剖析中的哪个具体问题
- 『潜在的执行风险与防范措施』：实施中可能遇到的障碍及应对方案

【文本报告绝对禁令】
1. 严禁在报告正文中直接贴出、打印或复述原始的 SQL 查询结果表格（如 "--- SQL 查询结果 ---" 或带有列名的原始数据对齐块）。
2. 严禁敷衍了事只写1-2句话！你是顶级数据战略顾问，必须给出有深度、有洞察、有建议的专业报告。
3. 你的文本分析必须是对 SQL 执行结果的深度进化，而不是 SQL 结果的复制粘贴。
4. 每个板块的字数下限是硬性要求，未达标将被判定为任务失败！

⚠️ 【审计警告】大语言模型审计系统将对你的输出进行长度和深度检测。如果任何一个板块流于表面、内容流于宽泛或字数未达标，该次任务将被判定为失败，并扣除系统信用分。请务必展现你作为资深行业专家的最高分析水准。"""


# ---------------------------------------------------------------------------
# 图表类型检测（从用户指令中提取意图，用于验证 LLM 输出）
# ---------------------------------------------------------------------------

_CHART_KEYWORD_MAP = [
    ("scatter", ["散点图", "散点", "scatter", "scatter plot", "scatterplot"]),
    ("line",    ["折线图", "折线", "趋势图", "line chart", "line plot"]),
    ("pie",     ["饼图", "饼状图", "占比图", "pie chart", "pie"]),
    ("bar",     ["柱状图", "条形图", "柱形图", "bar chart", "bar plot"]),
    ("hist",    ["直方图", "分布图", "histogram", "hist"]),
    ("box",     ["箱线图", "箱形图", "box plot", "boxplot"]),
]

_CHART_NAME_MAP = {
    "scatter": "散点图", "line": "折线图", "pie": "饼图",
    "bar": "柱状图", "hist": "直方图", "box": "箱线图", "none": "无图表",
}


def _detect_chart_type(instruction: str) -> Optional[str]:
    """从用户指令中检测图表类型。返回 'scatter'/'line'/'pie'/'bar'/'hist'/'box' 或 None。"""
    text = instruction.lower()
    for chart_type, keywords in _CHART_KEYWORD_MAP:
        for kw in keywords:
            if kw in instruction or kw in text:
                return chart_type
    return None


def _parse_llm_json(response: str) -> Optional[dict]:
    """从 LLM 响应中解析 JSON 输出。支持 ```json 代码块和纯 JSON。"""
    # 尝试提取 ```json ... ``` 代码块
    json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
    if json_match:
        json_str = json_match.group(1).strip()
    else:
        # 尝试提取 ``` ... ``` 代码块
        code_match = re.search(r"```\s*(.*?)\s*```", response, re.DOTALL)
        if code_match:
            json_str = code_match.group(1).strip()
        else:
            # 尝试直接解析整个响应
            json_str = response.strip()

    # 清理：移除可能的前缀文字
    json_start = json_str.find("{")
    if json_start >= 0:
        json_str = json_str[json_start:]
    json_end = json_str.rfind("}")
    if json_end >= 0:
        json_str = json_str[:json_end + 1]

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        logger.warning(f"📊 [DataAgent] JSON 解析失败: {json_str[:200]}...")
        return None


async def process_excel_node(
    state: WorkflowState,
    excel_processor: ExcelDataProcessor,
    llm_client,
    rag_engine=None,
) -> WorkflowState:
    file_path = state.get("file_path", "")
    user_instruction = state.get("user_instruction", "请分析这份数据并给出总结。")
    user_id = state.get("user_id", "")

    # --- 解析追问上下文 ---
    # 如果 user_instruction 包含 【追问】 标记，说明是追问请求
    # 格式: "用户: xxx\nAI助手: xxx\n\n【追问】新的问题"
    chat_history = []
    actual_query = user_instruction
    is_followup = "【追问】" in user_instruction

    if is_followup:
        parts = user_instruction.split("【追问】", 1)
        history_text = parts[0].strip()
        actual_query = parts[1].strip() if len(parts) > 1 else user_instruction

        # 解析历史对话行
        if history_text:
            for line in history_text.split("\n"):
                line = line.strip()
                if line.startswith("用户:") or line.startswith("用户："):
                    content = line.split(":", 1)[1].strip() if ":" in line else line.split("：", 1)[1].strip()
                    chat_history.append({"role": "user", "content": content})
                elif line.startswith("AI助手:") or line.startswith("AI助手："):
                    content = line.split(":", 1)[1].strip() if ":" in line else line.split("：", 1)[1].strip()
                    chat_history.append({"role": "assistant", "content": content})

        logger.info(f"📊 [DataAgent] 追问模式: 历史轮数={len(chat_history)}, 当前问题={actual_query[:50]}")

    logger.info(f"📊 [DataAgent] starting Text-to-SQL-to-Chart (两阶段) for {file_path}")

    # --- RAG 知识检索 ---
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
                    logger.info(f"📊 [DataAgent] RAG retrieved {len(rag_parts)} knowledge chunks")
        except Exception as e:
            logger.warning(f"📊 [DataAgent] RAG retrieval failed: {e}")

    # --- 提取 Schema ---
    schema = await excel_processor.extract_excel_schema(file_path)

    # --- 检测用户图表意图（用于验证 LLM 输出） ---
    detected_chart_type = _detect_chart_type(user_instruction)
    logger.info(f"📊 [DataAgent] 用户图表意图检测: {detected_chart_type or '无明确图表类型'}")

    # ======================================================================
    # Step 1: LLM 生成 SQL + chart_type（不含 text_analysis）
    # ======================================================================
    from langchain_core.prompts import ChatPromptTemplate

    schema_escaped = str(schema).replace("{", "{{").replace("}", "}}")
    sql_prompt_filled = SQL_GENERATION_PROMPT.replace("{schema}", schema_escaped)

    if rag_context:
        rag_escaped = rag_context.replace("{", "{{").replace("}", "}}")
        sql_prompt_filled += "\n\n【行业知识库参考】:\n" + rag_escaped

    # 用户指令中图表类型的强调
    chart_hint = ""
    if detected_chart_type:
        chart_hint = f"\n\n【重要提醒】用户明确要求绘制『{_CHART_NAME_MAP.get(detected_chart_type, detected_chart_type)}』，你的 chart_type 字段必须为 \"{detected_chart_type}\"！"

    sql_prompt_template = ChatPromptTemplate.from_messages([
        ("system", sql_prompt_filled),
        ("user", "用户的分析要求：『{instruction}』{chart_hint}"),
    ])

    max_attempts = 3
    execution_log = []
    sql = ""
    chart_type = "none"
    title = "数据分析"
    error_msg = ""
    llm_json = None
    pipeline_result = None

    for attempt in range(max_attempts):
        logger.info(f"📊 [DataAgent] Step1 第 {attempt + 1} 次尝试（生成 SQL）...")

        if attempt == 0:
            messages = sql_prompt_template.format_messages(
                instruction=actual_query,
                chart_hint=chart_hint.replace("{", "{{").replace("}", "}}"),
            )
            # 追问模式：在 system 和 user 之间插入历史对话
            if chat_history:
                history_msgs = []
                for h in chat_history:
                    if h["role"] == "user":
                        history_msgs.append(("user", f"[历史] {h['content']}"))
                    else:
                        history_msgs.append(("assistant", f"[历史] {h['content']}"))
                # 重建 messages: system + history + user
                messages = [messages[0]] + [
                    ChatPromptTemplate.from_messages([(r, c)]).format_messages()[0]
                    for r, c in history_msgs
                ] + [messages[-1]]
        else:
            correction_template = ChatPromptTemplate.from_messages([
                ("system", sql_prompt_filled),
                ("user", "用户的分析要求：『{instruction}』\n\n【上次执行出错】:\n{error_msg}\n\n请修正你的 JSON 输出。"),
            ])
            messages = correction_template.format_messages(
                instruction=actual_query,
                error_msg=error_msg.replace("{", "{{").replace("}", "}}"),
            )

        response = await llm_client.acall_api(
            [{"role": m.type, "content": m.content} for m in messages],
            max_tokens=2048,
        )

        execution_log.append(f"Step1 尝试 {attempt + 1} LLM 响应:\n{response[:500]}")

        # 解析 LLM JSON 输出
        llm_json = _parse_llm_json(response)
        if not llm_json:
            error_msg = f"LLM 输出不是有效的 JSON。原始响应: {response[:300]}"
            logger.warning(f"📊 [DataAgent] JSON 解析失败，触发重试")
            execution_log.append(f"JSON 解析失败")
            continue

        sql = llm_json.get("sql", "")
        chart_type = llm_json.get("chart_type", "none")
        title = llm_json.get("title", "数据分析")

        # 验证：如果系统检测到用户明确要求了图表类型，强制覆写 LLM 的 chart_type
        # 无论 LLM 返回什么（包括 none），只要用户意图明确，就必须服从
        if detected_chart_type and chart_type != detected_chart_type:
            logger.warning(f"📊 [DataAgent] LLM chart_type={chart_type} 与用户意图 {detected_chart_type} 不符，强制覆写")
            chart_type = detected_chart_type

        if not sql:
            error_msg = "LLM 输出的 JSON 中缺少 sql 字段"
            execution_log.append(f"缺少 sql 字段")
            continue

        # ======================================================================
        # Step 2: Python 执行 SQL + 系统级模板绘图
        # ======================================================================
        logger.info(f"📊 [DataAgent] Step2 执行 SQL + 绘图...")
        pipeline_result = await excel_processor.execute_chart_pipeline(
            file_path=file_path,
            sql=sql,
            chart_type=chart_type if chart_type != "none" else "",
            title=title,
            text_analysis="",  # Step 2 不需要 text_analysis，Step 3 生成
        )

        if pipeline_result["success"]:
            logger.info(f"📊 [DataAgent] SQL+绘图执行成功！chart_type={chart_type}")
            error_msg = ""
            break
        else:
            error_msg = pipeline_result.get("error", "Unknown error")
            logger.warning(f"📊 [DataAgent] 执行失败: {error_msg[:200]}...")
            execution_log.append(f"执行报错:\n{error_msg[:500]}")

    # 如果 Step1/Step2 全部失败，直接返回错误
    if not pipeline_result or not pipeline_result.get("success"):
        preview_html = _build_preview_html({"output": f"分析失败: {error_msg}", "image_base64": None}, schema, user_instruction)
        return {
            **state,
            "generated_code": sql,
            "code_execution_log": execution_log,
            "code_execution_error": error_msg,
            "structured_data": {"success": False, "error": error_msg},
            "output_path": "",
            "error_message": error_msg,
            "filled_html": preview_html,
        }

    # ======================================================================
    # Step 3: LLM 基于真实查询结果生成深度分析报告
    # ======================================================================
    result_markdown = pipeline_result.get("result_markdown", "")
    chart_type_desc = _CHART_NAME_MAP.get(chart_type, chart_type)

    logger.info(f"📊 [DataAgent] Step3 生成深度分析报告（真实数据注入）...")

    report_prompt = REPORT_GENERATION_PROMPT.replace("{instruction}", actual_query)
    report_prompt = report_prompt.replace("{chart_type_desc}", chart_type_desc)
    report_prompt = report_prompt.replace("{result_data}", result_markdown)

    if rag_context:
        report_prompt += f"\n\n【行业知识库参考】:\n{rag_context}"

    text_analysis = ""
    try:
        report_messages = [
            {"role": "system", "content": "你是一个顶级数据战略顾问，擅长基于真实数据撰写深度分析报告。"},
        ]
        # 追问模式：注入历史对话
        if chat_history:
            for h in chat_history:
                report_messages.append({"role": h["role"], "content": f"[历史] {h['content']}"})
        report_messages.append({"role": "user", "content": report_prompt})
        text_analysis = await llm_client.acall_api(
            report_messages,
            max_tokens=8192,
        )
        logger.info(f"📊 [DataAgent] Step3 报告生成成功，长度: {len(text_analysis)}")
        execution_log.append(f"Step3 报告生成成功，长度: {len(text_analysis)}")
    except Exception as e:
        logger.error(f"📊 [DataAgent] Step3 报告生成失败: {e}")
        # 🔑 不再输出原始数据表，改为友好提示（图表仍会由 _build_preview_html 拼接）
        text_analysis = f"⚠️ AI 深度分析报告生成超时，请参考下方图表进行解读。如需文字分析，请尝试追问。"
        execution_log.append(f"Step3 报告生成失败: {e}")

    # 用 Step3 生成的报告替换 pipeline 的 output
    pipeline_result["output"] = text_analysis

    # --- 构建预览 HTML ---
    preview_html = _build_preview_html(pipeline_result, schema, user_instruction)

    structured_data = {
        "analysis_output": text_analysis,
        "has_image": bool(pipeline_result.get("image_base64")),
        "sql": sql,
        "chart_type": detected_chart_type or chart_type,
        "schema": schema,
        "execution_log": execution_log,
        "attempts": len(execution_log),
        "success": True,
    }

    # --- 保存清洗结果 ---
    output_path = _generate_output_path(file_path)
    save_error = ""
    try:
        proc = ExcelDataProcessor()
        save_result = await proc.execute_pandas_code(
            code=f"df.to_excel('{output_path}', index=False)",
            input_path=file_path,
            output_path=output_path,
        )
        if not save_result.get("success"):
            save_error = save_result.get("error", "Unknown save error")
            logger.error(f"📊 [DataAgent] 保存清洗结果失败: {save_error[:200]}")
    except Exception as e:
        save_error = str(e)
        logger.error(f"📊 [DataAgent] 保存清洗结果异常: {e}", exc_info=True)

    logger.info(f"📊 [DataAgent] completed, has_chart={bool(pipeline_result.get('image_base64'))}, report_len={len(text_analysis)}")

    return {
        **state,
        "generated_code": sql,
        "code_execution_log": execution_log,
        "code_execution_error": error_msg or save_error,
        "structured_data": structured_data,
        "output_path": output_path,
        "error_message": save_error,
        "filled_html": preview_html,
    }


def _build_preview_html(result: dict, schema: dict, instruction: str) -> str:
    output = result.get("output", "代码未输出任何文本")
    img_b64 = result.get("image_base64")

    html = "<div style='padding: 20px; font-family: sans-serif;'>"
    html += "<h2 style='color: #4f46e5; border-bottom: 2px solid #e5e7eb; padding-bottom: 10px;'>📊 数据分析报告</h2>"
    html += f"<h4 style='color: #6b7280; margin-top: 20px;'>💡 AI 分析结论:</h4>"
    html += f"<pre style='background: #1f2937; color: #a5b4fc; padding: 15px; border-radius: 8px; white-space: pre-wrap;'>{output}</pre>"

    # 🔑 图表始终拼接：只要 image_base64 存在就强制渲染 <img>
    if img_b64:
        html += "<h4 style='color: #6b7280; margin-top: 20px;'>📈 可视化图表:</h4>"
        html += (
            f"<div style='margin-top:20px; text-align:center;'>"
            f"<img src='data:image/png;base64,{img_b64}' "
            f"style='max-width:100%; border-radius:8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); border: 1px solid #e5e7eb;' />"
            f"</div>"
        )

    html += "</div>"
    return html


def _generate_output_path(input_path: str) -> str:
    base = input_path.rsplit(".", 1)[0]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join("temp_workspace", "output")
    os.makedirs(output_dir, exist_ok=True)
    filename = os.path.basename(f"{base}_cleaned_{timestamp}.xlsx")
    return os.path.join(output_dir, filename)
