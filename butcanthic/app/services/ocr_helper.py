"""
OCR 辅助模块 - 识别 PDF/Word 中嵌入的图片文字

双引擎架构:
  引擎1: RapidOCR (本地 ONNX Runtime) - 提取文字
  引擎2: 大模型 Vision API - 语义描述 (图表趋势、架构关系、画面含义)

融合格式:
  【图片提取文字】：{ocr_text}
  【图片语义描述】：{vision_text}

并发控制: asyncio.Semaphore 限制 Vision API 并发数
容错: Vision API 报错/超时时仅返回 OCR 文本，不阻塞文档解析
"""

import asyncio
import base64
import io
import logging
import os
from typing import List, Optional

from PIL import Image

logger = logging.getLogger(__name__)

_ocr_engine = None

VISION_CONCURRENCY = 5

VISION_ANALYZE_PROMPT = (
    "你是一个专业的数据与图表分析师。请详细描述这张图片的内容。"
    "重点提取图表数据趋势、架构图组件关系或核心画面含义。"
    "不要转录全部文字，只需总结核心语义。"
)


def _get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _ocr_engine = RapidOCR()
            logger.info("RapidOCR engine initialized")
        except ImportError:
            logger.warning("RapidOCR not installed, OCR functionality disabled")
            _ocr_engine = False
    return _ocr_engine if _ocr_engine is not False else None


def ocr_image(image: Image.Image) -> Optional[str]:
    if image.mode == "RGBA":
        image = image.convert("RGB")
    elif image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    engine = _get_ocr_engine()
    if engine is None:
        return None

    try:
        import numpy as np
        img_array = np.array(image)
        result, _ = engine(img_array)

        if result:
            texts = [line[1] for line in result if line[1] and line[1].strip()]
            if texts:
                ocr_text = "\n".join(texts)
                logger.info(f"OCR extracted {len(texts)} text lines from image")
                return ocr_text
    except Exception as e:
        logger.warning(f"OCR failed: {e}")
    return None


def ocr_image_bytes(image_bytes: bytes) -> Optional[str]:
    try:
        image = Image.open(io.BytesIO(image_bytes))
        return ocr_image(image)
    except Exception as e:
        logger.warning(f"Failed to open image for OCR: {e}")
        return None


def extract_images_from_pdf(pdf_path: str) -> List[Image.Image]:
    images = []
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                if hasattr(page, "images") and page.images:
                    for img_info in page.images:
                        try:
                            x0 = img_info.get("x0", 0)
                            top = img_info.get("top", 0)
                            x1 = img_info.get("x1", 0)
                            bottom = img_info.get("bottom", 0)
                            if (x1 - x0) < 20 or (bottom - top) < 20:
                                continue
                            cropped = page.crop((x0, top, x1, bottom))
                            if cropped and hasattr(cropped, "to_image"):
                                pil_img = cropped.to_image(resolution=200).original
                                images.append(pil_img)
                        except Exception as e:
                            logger.debug(f"Failed to extract image from PDF page: {e}")
    except Exception as e:
        logger.warning(f"Failed to extract images from PDF: {e}")
    return images


def extract_images_from_docx(docx_path: str) -> List[Image.Image]:
    images = []
    try:
        import zipfile
        with zipfile.ZipFile(docx_path, "r") as z:
            for name in z.namelist():
                if name.startswith("word/media/"):
                    try:
                        img_data = z.read(name)
                        img = Image.open(io.BytesIO(img_data))
                        images.append(img)
                    except Exception as e:
                        logger.debug(f"Failed to extract image {name} from DOCX: {e}")
    except Exception as e:
        logger.warning(f"Failed to extract images from DOCX: {e}")
    return images


def _image_to_base64(image: Image.Image, fmt: str = "JPEG", quality: int = 85) -> str:
    if image.mode == "RGBA":
        image = image.convert("RGB")
    elif image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    max_dim = 2048
    w, h = image.size
    if max(w, h) > max_dim:
        ratio = max_dim / max(w, h)
        image = image.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

    buf = io.BytesIO()
    image.save(buf, format=fmt, quality=quality)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


async def _vision_analyze_image(image: Image.Image, ai_client, semaphore: asyncio.Semaphore) -> str:
    if ai_client is None:
        return ""

    try:
        b64 = _image_to_base64(image)
    except Exception as e:
        logger.warning(f"Vision: image base64 encoding failed: {e}")
        return ""

    async with semaphore:
        try:
            vision_text = await asyncio.wait_for(
                ai_client.analyze_image(b64, VISION_ANALYZE_PROMPT),
                timeout=60,
            )
            if vision_text:
                logger.info(f"Vision: semantic description obtained ({len(vision_text)} chars)")
                return vision_text
            return ""
        except asyncio.TimeoutError:
            logger.warning("Vision: API call timed out (60s), skipping")
            return ""
        except Exception as e:
            logger.warning(f"Vision: API call failed: {e}")
            return ""


async def _process_single_image(
    idx: int,
    image: Image.Image,
    ai_client,
    semaphore: asyncio.Semaphore,
) -> Optional[str]:
    ocr_text = ocr_image(image)

    vision_text = ""
    if ai_client is not None:
        try:
            vision_text = await _vision_analyze_image(image, ai_client, semaphore)
        except Exception as e:
            logger.warning(f"Vision analysis failed for image {idx + 1}: {e}")

    parts = []
    if ocr_text:
        parts.append(f"【图片提取文字】：{ocr_text}")
    if vision_text:
        parts.append(f"【图片语义描述】：{vision_text}")

    if parts:
        header = f"[图片{idx + 1}]"
        return f"{header}\n" + "\n".join(parts)

    return None


async def _process_images_batch(
    images: List[Image.Image],
    ai_client=None,
) -> List[str]:
    if not images:
        return []

    semaphore = asyncio.Semaphore(VISION_CONCURRENCY)

    tasks = [
        _process_single_image(idx, img, ai_client, semaphore)
        for idx, img in enumerate(images)
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    texts = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.warning(f"Image {i + 1} processing failed: {result}")
            ocr_text = ocr_image(images[i])
            if ocr_text:
                texts.append(f"[图片{i + 1}]\n【图片提取文字】：{ocr_text}")
        elif result is not None:
            texts.append(result)

    return texts


def ocr_pdf_images(pdf_path: str) -> Optional[str]:
    images = extract_images_from_pdf(pdf_path)
    if not images:
        return None

    all_texts = []
    for i, img in enumerate(images):
        text = ocr_image(img)
        if text:
            all_texts.append(f"[图片{i + 1} OCR文本]\n{text}")

    if all_texts:
        logger.info(f"OCR: extracted text from {len(all_texts)}/{len(images)} images in PDF")
        return "\n\n".join(all_texts)
    return None


def ocr_docx_images(docx_path: str) -> Optional[str]:
    images = extract_images_from_docx(docx_path)
    if not images:
        return None

    all_texts = []
    for i, img in enumerate(images):
        text = ocr_image(img)
        if text:
            all_texts.append(f"[图片{i + 1} OCR文本]\n{text}")

    if all_texts:
        logger.info(f"OCR: extracted text from {len(all_texts)}/{len(images)} images in DOCX")
        return "\n\n".join(all_texts)
    return None


async def ocr_pdf_images_v2(pdf_path: str, ai_client=None) -> Optional[str]:
    images = extract_images_from_pdf(pdf_path)
    if not images:
        return None

    texts = await _process_images_batch(images, ai_client)

    if texts:
        logger.info(f"Vision-RAG: processed {len(texts)}/{len(images)} images in PDF (OCR+Vision)")
        return "\n\n".join(texts)
    return None


async def ocr_docx_images_v2(docx_path: str, ai_client=None) -> Optional[str]:
    images = extract_images_from_docx(docx_path)
    if not images:
        return None

    texts = await _process_images_batch(images, ai_client)

    if texts:
        logger.info(f"Vision-RAG: processed {len(texts)}/{len(images)} images in DOCX (OCR+Vision)")
        return "\n\n".join(texts)
    return None
