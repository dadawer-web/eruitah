"""
Node 1: ExtractContext - 标记化文档意图识别
Step 1: 剥离 Base64 图片数据
Step 2a: 处理表格空缺 — 在空 <td> 中插入 [[ANS_N]]
Step 2b: 处理段落问答题 — 在问题段落后动态插入答题区 [[ANS_N]]
Step 2c: 处理填空题 — 替换占位符为 [[ANS_N]]
Step 3: 生成 placeholder_map 供后续 Fill 节点使用
"""

import logging
import re
from typing import Any, Dict, List

from bs4 import BeautifulSoup, Tag

from app.agent_workflow.state import WorkflowState

logger = logging.getLogger(__name__)

QA_PATTERN = re.compile(
    r'(?i)(简述|什么是|如何|为什么|分析|区别|答[:：]|请写出|请说明|请解释|计算|画出|论述|说明|解释|列举|比较|阐述|评价|讨论|定义|描述|证明|推导|[\?？]\s*$|^\s*\d+[\.、\)]|_{3,}|\(\s{2,}\)|（\s{2,}）)',
)

FILL_BLANK_PATTERN = re.compile(
    r'(?:_{3,}|_{2,}_|（\s{2,}）|\(\s{2,}\)|【\s*】|\[\s*\]|待填|待定|TBD)',
    re.IGNORECASE,
)

PLACEHOLDER_CELL_PATTERNS = [
    re.compile(r'^_{2,}$'),
    re.compile(r'^-{2,}$'),
    re.compile(r'^\.{3,}$'),
    re.compile(r'^[\(（]\s*[\)）]$'),
    re.compile(r'^[\[\【]\s*[\]】]$'),
    re.compile(r'^\*{2,}$'),
    re.compile(r'^[/\\]{2,}$'),
    re.compile(r'^待[填定写]$'),
    re.compile(r'^TBD$', re.IGNORECASE),
    re.compile(r'^N/?A$', re.IGNORECASE),
    re.compile(r'^无$'),
    re.compile(r'^空$'),
    re.compile(r'^—+$'),
    re.compile(r'^~+$'),
]


def _is_empty_cell(text: str) -> bool:
    if not text:
        return True
    stripped = text.strip()
    if len(stripped) == 0:
        return True
    if stripped in ("/", "-", "\\", "—", "–", "…", "·"):
        return True
    for pattern in PLACEHOLDER_CELL_PATTERNS:
        if pattern.match(stripped):
            return True
    return False


def _is_inside_table(tag: Tag) -> bool:
    parent = tag.parent
    while parent:
        if parent.name == "table":
            return True
        parent = parent.parent
    return False


async def extract_context(state: WorkflowState) -> WorkflowState:
    html = state.get("current_html", "")
    file_path = state.get("file_path", "")
    file_type = state.get("file_type", "")

    logger.info(f"ExtractContext: received HTML with length={len(html)}")

    doc_images = []
    if file_type == "docx" and file_path:
        try:
            from app.services.docx_parser import DocxParser
            parser = DocxParser()
            result = await parser.extract_text_with_images(file_path)
            doc_images = result.get("images", [])
            if doc_images:
                logger.info(f"ExtractContext: extracted {len(doc_images)} images from DOCX for vision pipeline")
        except Exception as e:
            logger.warning(f"ExtractContext: image extraction failed: {e}")

    if not html:
        logger.warning("ExtractContext: empty HTML input, triggering circuit breaker")
        return {
            **state,
            "empty_fields": [],
            "field_semantics": {},
            "has_fields_to_fill": False,
            "placeholder_map": {},
            "image_store": {},
            "error_message": "HTML 内容为空，无法提取表格字段",
        }

    from app.services.document_service import strip_images_from_html
    html, image_store = strip_images_from_html(html)

    if "data:image" in html:
        logger.warning("ExtractContext: base64 images still present after stripping! Force removing...")
        html = re.sub(r'src="data:image/[^"]*"', 'src=""', html)

    if image_store:
        logger.info(f"ExtractContext: stripped {len(image_store)} base64 images")

    soup = BeautifulSoup(html, "html.parser")

    ans_idx = 0
    placeholder_map: Dict[str, Any] = {}

    # ── Step 2a: 处理表格空缺 ──
    tables = soup.find_all("table")
    if tables:
        logger.info(f"ExtractContext: found {len(tables)} table(s) in HTML")
        for table in tables:
            header_map = _build_header_map(table)
            for row in table.find_all("tr"):
                col_offset = 0
                for cell in row.find_all(["td", "th"]):
                    text = cell.get_text(strip=True)
                    colspan = int(cell.get("colspan", 1))
                    if cell.name == "td" and _is_empty_cell(text):
                        header = header_map.get(str(col_offset), f"col_{col_offset}")
                        context = _get_row_context(row)
                        tag = f"[[ANS_{ans_idx}]]"
                        cell.clear()
                        cell.append(tag)
                        placeholder_map[tag] = {
                            "type": "table_empty",
                            "header": header,
                            "context": context,
                            "original_text": text,
                        }
                        ans_idx += 1
                    col_offset += colspan

    # ── Step 2b: 处理段落问答题 ──
    paragraphs = soup.find_all(["p", "li", "div", "h1", "h2", "h3", "h4", "h5", "h6"])
    for p in paragraphs:
        if _is_inside_table(p):
            continue

        text = p.get_text(strip=True)
        if not text:
            continue

        if QA_PATTERN.search(text):
            tag = f"[[ANS_{ans_idx}]]"
            new_p = soup.new_tag(
                "p",
                style="color: blue; font-weight: bold;",
            )
            new_p.string = f"[AI智能解答]：{tag}"
            p.insert_after(new_p)
            placeholder_map[tag] = {
                "type": "qa",
                "question": text[:300],
            }
            logger.info(f"[雷达探测] 发现非表格问题: {text[:20]}... 已锁定占位符 [[ANS_{ans_idx}]]")
            ans_idx += 1
            continue

        if FILL_BLANK_PATTERN.search(text):
            tag = f"[[ANS_{ans_idx}]]"
            inner = str(p)
            inner = FILL_BLANK_PATTERN.sub(
                f'<span style="color: #2563eb; font-weight: bold;">{tag}</span>',
                inner,
                count=1,
            )
            p.replace_with(BeautifulSoup(inner, "html.parser"))
            placeholder_map[tag] = {
                "type": "fill_blank",
                "surrounding_text": text[:200],
            }
            ans_idx += 1
            logger.debug(f"  FillBlank intent: tag={tag}, text={text[:80]}...")

    has_fields_to_fill = ans_idx > 0

    table_empty_count = sum(1 for v in placeholder_map.values() if v["type"] == "table_empty")
    qa_count = sum(1 for v in placeholder_map.values() if v["type"] == "qa")
    fb_count = sum(1 for v in placeholder_map.values() if v["type"] == "fill_blank")

    logger.info(
        f"文档分析完毕，发现表格空缺: {table_empty_count > 0}, "
        f"发现问答/填空意图: {qa_count > 0 or fb_count > 0} "
        f"(table_empty={table_empty_count}, qa={qa_count}, fill_blank={fb_count})"
    )

    if not has_fields_to_fill:
        logger.warning("ExtractContext: no actionable intent found, triggering circuit breaker")
        return {
            **state,
            "empty_fields": [],
            "field_semantics": {},
            "has_fields_to_fill": False,
            "placeholder_map": {},
            "image_store": image_store,
            "doc_images": doc_images,
            "error_message": "文档中未发现需要处理的空缺、问答或填空",
        }

    tagged_html = str(soup)

    logger.info(f"成功提取文档结构，总计标记 {len(placeholder_map)} 个占位符，HTML长度: {len(tagged_html)}")

    return {
        **state,
        "current_html": tagged_html,
        "empty_fields": list(placeholder_map.values()),
        "field_semantics": {},
        "has_fields_to_fill": True,
        "placeholder_map": placeholder_map,
        "image_store": image_store,
        "doc_images": doc_images,
        "error_message": "",
        "current_progress": 15,
        "current_action": f"文档分析完毕，发现 {len(placeholder_map)} 个待处理项",
    }


def _build_header_map(table: Tag) -> Dict[str, str]:
    header_map: Dict[str, str] = {}
    for row_idx, row in enumerate(table.find_all("tr")):
        col_offset = 0
        for cell in row.find_all(["th", "td"]):
            text = cell.get_text(strip=True)
            colspan = int(cell.get("colspan", 1))
            if row_idx == 0 or cell.name == "th":
                for c in range(colspan):
                    col_key = str(col_offset + c)
                    if col_key not in header_map:
                        header_map[col_key] = text
            col_offset += colspan
    return header_map


def _get_row_context(row: Tag) -> str:
    parts = []
    for cell in row.find_all(["td", "th"]):
        text = cell.get_text(strip=True)
        if not _is_empty_cell(text):
            parts.append(text)
    return " | ".join(parts) if parts else ""
