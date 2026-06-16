"""
OCR 辅助模块 - 识别 PDF/Word 中嵌入的图片文字

双引擎架构:
  引擎1: RapidOCR (本地 ONNX Runtime) - 提取文字
  引擎2: 大模型 Vision API - 语义描述 (图表趋势、架构关系、画面含义)

融合格式:
  ![图片描述](image_ref)
  > **图表深度解析**：{vision_caption}

Caption 缓存:
  基于 SHA-256 哈希的内存缓存，同一图片不重复调用 Vision API

并发控制: asyncio.Semaphore 限制 Vision API 并发数
容错: Vision API 报错/超时时仅返回 OCR 文本，不阻塞文档解析
"""

import asyncio
import base64
import gc
import hashlib
import io
import logging
import os
from typing import Dict, Generator, List, Optional, Tuple

from PIL import Image

logger = logging.getLogger(__name__)

_ocr_engine = None

VISION_CONCURRENCY = 5

# ── 图片降级防线：最大边长限制 ──
IMAGE_MAX_DIM = 1024       # 超过此尺寸的图片将被等比例缩放
IMAGE_MAX_RAW_DIM = 4000   # 原始图片宽或高超过此值直接跳过（防 OOM）
IMAGE_MAX_RAW_BYTES = 20 * 1024 * 1024  # 原始图片解压后超过 20MB 直接跳过

# ── Caption 缓存（参考 llm_wiki 的 image-caption-cache，适配内存模式） ──
_caption_cache: Dict[str, str] = {}  # key=SHA-256, value=caption text
_CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "image_caption_cache.json")


def _compute_image_hash(image: Image.Image) -> str:
    """计算图片的 SHA-256 哈希（基于像素数据，非 base64 编码）"""
    if image.mode == "RGBA":
        image = image.convert("RGB")
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=95)
    return hashlib.sha256(buf.getvalue()).hexdigest()


def _load_caption_cache():
    """从磁盘加载 Caption 缓存"""
    global _caption_cache
    try:
        if os.path.exists(_CACHE_FILE):
            import json
            with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                _caption_cache = json.load(f)
            logger.info(f"[CaptionCache] 已加载 {len(_caption_cache)} 条缓存")
    except Exception as e:
        logger.warning(f"[CaptionCache] 加载失败: {e}")
        _caption_cache = {}


def _save_caption_cache():
    """将 Caption 缓存持久化到磁盘"""
    try:
        import json
        os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_caption_cache, f, ensure_ascii=False, indent=2)
        logger.info(f"[CaptionCache] 已保存 {len(_caption_cache)} 条缓存")
    except Exception as e:
        logger.warning(f"[CaptionCache] 保存失败: {e}")


def _get_vision_prompt() -> str:
    """从 PromptManager 加载 vision_caption_system 提示词，降级为内置默认"""
    try:
        from app.core.prompt_manager import PromptManager
        prompt = PromptManager.get_prompt("vision_caption_system")
        if prompt:
            return prompt
    except Exception:
        pass

    # 内置降级提示词
    return (
        "你是一个专业的数据与架构分析师。请分析这张图片。"
        "如果是图表，描述其核心逻辑、数据趋势和节点关系。"
        "如果是普通插图，描述其关键内容。"
        "提取至少3个核心关键词，用逗号分隔。"
        "输出2-4句话，纯文本，不要Markdown格式。"
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


def downscale_image(image: Image.Image, max_dim: int = IMAGE_MAX_DIM) -> Image.Image:
    """等比例缩放图片，确保最大边长不超过 max_dim，降低内存占用"""
    if image.mode == "RGBA":
        image = image.convert("RGB")
    elif image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    w, h = image.size
    if max(w, h) > max_dim:
        ratio = max_dim / max(w, h)
        new_size = (int(w * ratio), int(h * ratio))
        image = image.resize(new_size, Image.LANCZOS)
        logger.debug(f"Image downscaled: {w}x{h} → {new_size[0]}x{new_size[1]}")
    return image


# ── 流式图片提取（生成器模式，逐页/逐图 yield，绝不全量囤积） ──

def iter_images_from_pdf(pdf_path: str) -> Generator[Image.Image, None, None]:
    """
    流式从 PDF 中逐页逐图提取内嵌图片（生成器模式）。

    三层硬性内存防护：
    1. 严禁全文档级高清栅格化 —— 使用 PyMuPDF (fitz) 直接提取内嵌图片字节流，
       绝不调用 to_image / get_pixmap 做页面级栅格化
    2. 逐页读取与清理 —— load_page → 提取 → del page + gc.collect()
    3. 尺寸阈值防护 —— 原始图宽/高 > 4000px 或解压后 > 20MB 直接跳过

    每提取一张图立即降级缩放并 yield，绝不将所有图片囤积在内存中。
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        # 降级到 pdfplumber（低分辨率栅格化，仅作最后兜底）
        logger.warning("[MemoryGuard] PyMuPDF (fitz) 未安装，降级使用 pdfplumber 提取图片（可能占用更多内存）")
        yield from _iter_images_from_pdf_pdfplumber(pdf_path)
        return

    try:
        doc = fitz.open(pdf_path)
        total_pages = doc.page_count
        for page_num in range(total_pages):
            page = doc.load_page(page_num)
            image_list = page.get_images(full=True)

            for img_index, img_info in enumerate(image_list):
                try:
                    xref = img_info[0]
                    base_image = doc.extract_image(xref)
                    if not base_image:
                        continue

                    img_bytes = base_image.get("image")
                    img_width = base_image.get("width", 0)
                    img_height = base_image.get("height", 0)

                    if not img_bytes:
                        continue

                    # ── 防护层 3：尺寸阈值检查 ──
                    if img_width > IMAGE_MAX_RAW_DIM or img_height > IMAGE_MAX_RAW_DIM:
                        logger.warning(
                            f"[MemoryGuard] 跳过超大图片: page={page_num + 1}, "
                            f"img_idx={img_index}, size={img_width}x{img_height} "
                            f"(阈值={IMAGE_MAX_RAW_DIM}px)"
                        )
                        del img_bytes
                        continue

                    if len(img_bytes) > IMAGE_MAX_RAW_BYTES:
                        logger.warning(
                            f"[MemoryGuard] 跳过超大图片字节: page={page_num + 1}, "
                            f"img_idx={img_index}, bytes={len(img_bytes) / 1024 / 1024:.1f}MB "
                            f"(阈值={IMAGE_MAX_RAW_BYTES / 1024 / 1024:.0f}MB)"
                        )
                        del img_bytes
                        continue

                    # 从字节流解码为 PIL Image
                    pil_img = Image.open(io.BytesIO(img_bytes))
                    # 立即加载像素数据（避免 lazy loading 持有字节流引用）
                    pil_img.load()
                    del img_bytes
                    del base_image

                    # 立即降级缩放
                    pil_img = downscale_image(pil_img)
                    yield pil_img
                    del pil_img

                except Exception as e:
                    logger.debug(f"Failed to extract image from PDF page {page_num + 1}, img {img_index}: {e}")

            # ── 防护层 2：每页处理完主动释放 ──
            del page
            del image_list

        doc.close()
        del doc
        gc.collect()

    except Exception as e:
        logger.warning(f"Failed to iter images from PDF (fitz): {e}")


def _iter_images_from_pdf_pdfplumber(pdf_path: str) -> Generator[Image.Image, None, None]:
    """
    pdfplumber 降级提取（仅当 PyMuPDF 不可用时使用）。
    使用低分辨率栅格化（DPI=72），避免内存爆炸。
    """
    try:
        import pdfplumber
        import logging as _logging
        _logging.getLogger("pdfminer").setLevel(_logging.ERROR)
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                if not (hasattr(page, "images") and page.images):
                    continue
                for img_info in page.images:
                    try:
                        x0 = img_info.get("x0", 0)
                        top = img_info.get("top", 0)
                        x1 = img_info.get("x1", 0)
                        bottom = img_info.get("bottom", 0)
                        if (x1 - x0) < 20 or (bottom - top) < 20:
                            continue
                        # 尺寸阈值检查（PDF 坐标单位约 1/72 inch）
                        if (x1 - x0) > IMAGE_MAX_RAW_DIM or (bottom - top) > IMAGE_MAX_RAW_DIM:
                            logger.warning(
                                f"[MemoryGuard] 跳过超大图片区域: page={page_num + 1}, "
                                f"bbox=({x0:.0f},{top:.0f},{x1:.0f},{bottom:.0f})"
                            )
                            continue
                        cropped = page.crop((x0, top, x1, bottom))
                        if cropped and hasattr(cropped, "to_image"):
                            # 低分辨率栅格化：DPI=72（原来 200，降低 2.8x）
                            pil_img = cropped.to_image(resolution=72).original
                            pil_img = downscale_image(pil_img)
                            yield pil_img
                            del pil_img
                            del cropped
                    except Exception as e:
                        logger.debug(f"Failed to extract image from PDF page {page_num}: {e}")
                del page
    except Exception as e:
        logger.warning(f"Failed to iter images from PDF (pdfplumber): {e}")


def iter_images_from_docx(docx_path: str) -> Generator[Image.Image, None, None]:
    """
    流式从 DOCX 中逐图提取图片（生成器模式）。
    每提取一张图立即降级缩放并 yield。
    超大图片直接跳过（防 OOM）。
    """
    try:
        import zipfile
        with zipfile.ZipFile(docx_path, "r") as z:
            for name in z.namelist():
                if not name.startswith("word/media/"):
                    continue
                try:
                    img_data = z.read(name)

                    # 尺寸阈值检查：字节流过大直接跳过
                    if len(img_data) > IMAGE_MAX_RAW_BYTES:
                        logger.warning(
                            f"[MemoryGuard] 跳过超大 DOCX 图片: {name}, "
                            f"bytes={len(img_data) / 1024 / 1024:.1f}MB "
                            f"(阈值={IMAGE_MAX_RAW_BYTES / 1024 / 1024:.0f}MB)"
                        )
                        del img_data
                        continue

                    img = Image.open(io.BytesIO(img_data))
                    # 立即加载像素数据
                    img.load()
                    del img_data

                    # 尺寸阈值检查：宽高过大直接跳过
                    w, h = img.size
                    if w > IMAGE_MAX_RAW_DIM or h > IMAGE_MAX_RAW_DIM:
                        logger.warning(
                            f"[MemoryGuard] 跳过超大 DOCX 图片: {name}, "
                            f"size={w}x{h} (阈值={IMAGE_MAX_RAW_DIM}px)"
                        )
                        del img
                        continue

                    # 立即降级缩放
                    img = downscale_image(img)
                    yield img
                    del img
                except Exception as e:
                    logger.debug(f"Failed to extract image {name} from DOCX: {e}")
    except Exception as e:
        logger.warning(f"Failed to iter images from DOCX: {e}")


# ── 兼容层：旧的全量列表接口（内部调用生成器，仍会一次性加载） ──
# 仅用于不需要流式管控的轻量场景

def extract_images_from_pdf(pdf_path: str) -> List[Image.Image]:
    return list(iter_images_from_pdf(pdf_path))


def extract_images_from_docx(docx_path: str) -> List[Image.Image]:
    return list(iter_images_from_docx(docx_path))


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
    """调用 Vision LLM 生成图片描述，带 SHA-256 缓存"""
    if ai_client is None:
        return ""

    # 计算 SHA-256 哈希，查缓存
    try:
        img_hash = _compute_image_hash(image)
    except Exception as e:
        logger.warning(f"Vision: image hash computation failed: {e}")
        img_hash = None

    if img_hash and img_hash in _caption_cache:
        logger.info(f"[CaptionCache] 命中缓存: {img_hash[:12]}...")
        return _caption_cache[img_hash]

    try:
        b64 = _image_to_base64(image)
    except Exception as e:
        logger.warning(f"Vision: image base64 encoding failed: {e}")
        return ""

    # 使用模板化的提示词
    prompt = _get_vision_prompt()

    async with semaphore:
        try:
            vision_text = await asyncio.wait_for(
                ai_client.analyze_image(b64, prompt),
                timeout=90,
            )
            if vision_text:
                # 清理 LLM 可能的格式化输出
                caption = vision_text.strip()
                if caption.startswith("```"):
                    caption = caption.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

                logger.info(f"Vision: semantic description obtained ({len(caption)} chars)")

                # 写入缓存
                if img_hash:
                    _caption_cache[img_hash] = caption
                    _save_caption_cache()

                return caption
            return ""
        except asyncio.TimeoutError:
            logger.warning("Vision: API call timed out (90s), using placeholder")
            return "[图片解析超时]"
        except Exception as e:
            logger.warning(f"Vision: API call failed: {e}")
            return ""


async def _process_single_image(
    idx: int,
    image: Image.Image,
    ai_client,
    semaphore: asyncio.Semaphore,
    image_ref: str = "",
) -> Optional[str]:
    """
    处理单张图片：OCR + Vision Caption → Markdown 融合格式

    输出格式:
      ![图片描述](image_ref)
      > **图表深度解析**：{caption}
    """
    ocr_text = await asyncio.to_thread(ocr_image, image)

    vision_text = ""
    if ai_client is not None:
        try:
            vision_text = await _vision_analyze_image(image, ai_client, semaphore)
        except Exception as e:
            logger.warning(f"Vision analysis failed for image {idx + 1}: {e}")

    # 构建 Markdown 融合格式
    ref = image_ref or f"image_{idx + 1}"
    alt_text = ""

    if vision_text:
        # 从 caption 中提取第一句作为 alt 文本
        first_sentence = vision_text.split("。")[0].strip()
        if first_sentence and len(first_sentence) > 50:
            first_sentence = first_sentence[:50] + "..."
        alt_text = first_sentence or f"图片{idx + 1}"

    parts = []

    # 图片引用行
    if alt_text:
        parts.append(f"![{alt_text}]({ref})")
    else:
        parts.append(f"![图片{idx + 1}]({ref})")

    # 深度解析引用块
    caption_parts = []
    if ocr_text:
        caption_parts.append(f"提取文字：{ocr_text}")
    if vision_text:
        caption_parts.append(f"深度解析：{vision_text}")

    if caption_parts:
        parts.append(f"> **图表深度解析**：{' | '.join(caption_parts)}")

    if len(parts) > 1 or vision_text:
        return "\n".join(parts)

    # 降级：只有 OCR 文本
    if ocr_text:
        return f"[图片{idx + 1}]\n【图片提取文字】：{ocr_text}"

    return None


async def _process_images_batch(
    images: List[Image.Image],
    ai_client=None,
    image_refs: Optional[List[str]] = None,
) -> List[str]:
    """
    批量处理图片，返回 Markdown 融合格式列表

    Args:
        images: PIL Image 列表
        ai_client: AI 客户端（支持 Vision）
        image_refs: 图片引用路径列表（如 ["media/img1.png", ...]）
    """
    if not images:
        return []

    # 启动时加载缓存
    if not _caption_cache:
        _load_caption_cache()

    semaphore = asyncio.Semaphore(VISION_CONCURRENCY)

    tasks = [
        _process_single_image(
            idx, img, ai_client, semaphore,
            image_ref=(image_refs[idx] if image_refs and idx < len(image_refs) else ""),
        )
        for idx, img in enumerate(images)
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    texts = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.warning(f"Image {i + 1} processing failed: {result}")
            ocr_text = await asyncio.to_thread(ocr_image, images[i])
            if ocr_text:
                ref = image_refs[i] if image_refs and i < len(image_refs) else f"image_{i + 1}"
                texts.append(f"![图片{i + 1}]({ref})\n> **图表深度解析**：提取文字：{ocr_text}")
        elif result is not None:
            texts.append(result)

    return texts


async def process_images_streaming(
    image_iter,
    ai_client=None,
    base_name: str = "",
) -> List[str]:
    """
    流式逐图处理（Streaming Memory Management）：
    从生成器逐张取出图片 → 立即 OCR + Vision 解析 → 追加文本 → del 图片 + gc.collect()

    核心保证：内存中同一时刻最多只有 1 张图片对象 + 1 个 Vision 请求。

    Args:
        image_iter: 图片生成器（iter_images_from_pdf / iter_images_from_docx）
        ai_client: AI 客户端
        base_name: 文件名前缀，用于构建图片引用路径

    Returns:
        Markdown 融合格式文本列表
    """
    if not _caption_cache:
        _load_caption_cache()

    semaphore = asyncio.Semaphore(VISION_CONCURRENCY)
    caption_texts: List[str] = []
    img_idx = 0

    for image in image_iter:
        img_idx += 1
        image_ref = f"media/{base_name}_img{img_idx}.png" if base_name else f"image_{img_idx}"

        try:
            result = await _process_single_image(
                img_idx - 1, image, ai_client, semaphore, image_ref=image_ref,
            )
            if result is not None:
                caption_texts.append(result)
        except Exception as e:
            logger.warning(f"Image {img_idx} streaming processing failed: {e}")
            # 降级：仅 OCR
            try:
                ocr_text = await asyncio.to_thread(ocr_image, image)
                if ocr_text:
                    caption_texts.append(
                        f"![图片{img_idx}]({image_ref})\n> **图表深度解析**：提取文字：{ocr_text}"
                    )
            except Exception:
                pass
        finally:
            # 强制销毁当前图片，释放内存
            del image
            gc.collect()

    if caption_texts:
        logger.info(f"[Vision] 流式处理完成: {img_idx} 张图片, {len(caption_texts)} 条描述")

    return caption_texts


async def process_images_streaming_with_peek(
    peek_images: List[Image.Image],
    remaining_iter,
    ai_client=None,
    base_name: str = "",
    progress_callback=None,
) -> List[str]:
    """
    流式逐图处理（带 peek 预读 + 逐图进度上报）：
    支持已预读的图片列表 + 剩余生成器，每处理完一张图上报进度。

    Args:
        peek_images: 已预读的图片列表（避免生成器丢失第一张）
        remaining_iter: 剩余图片生成器
        ai_client: AI 客户端
        base_name: 文件名前缀
        progress_callback: 进度回调函数 (state, message, percent)
    """
    if not _caption_cache:
        _load_caption_cache()

    semaphore = asyncio.Semaphore(VISION_CONCURRENCY)
    caption_texts: List[str] = []
    img_idx = 0

    # 合并 peek 图片和剩余生成器
    def _combined_iter():
        for img in peek_images:
            yield img
        yield from remaining_iter

    for image in _combined_iter():
        img_idx += 1
        image_ref = f"media/{base_name}_img{img_idx}.png" if base_name else f"image_{img_idx}"

        try:
            result = await _process_single_image(
                img_idx - 1, image, ai_client, semaphore, image_ref=image_ref,
            )
            if result is not None:
                caption_texts.append(result)
                # 逐图上报进度
                if progress_callback:
                    # 尝试从 result 中提取简短描述
                    short_desc = f"第 {img_idx} 张图表"
                    if "深度解析" in result:
                        try:
                            # 提取 ![图片N](ref) 后的描述
                            import re
                            m = re.search(r'\*\*(.+?)\*\*', result)
                            if m:
                                short_desc = f"第 {img_idx} 张『{m.group(1)}』"
                        except Exception:
                            pass
                    progress_callback(
                        'VISION_PROCESSING',
                        f'✨ {short_desc} 解读完成，已成功转化为文本嵌入！',
                        18 + min(img_idx * 3, 12),
                    )
        except Exception as e:
            logger.warning(f"Image {img_idx} streaming processing failed: {e}")
            # 降级：仅 OCR
            try:
                ocr_text = await asyncio.to_thread(ocr_image, image)
                if ocr_text:
                    caption_texts.append(
                        f"![图片{img_idx}]({image_ref})\n> **图表深度解析**：提取文字：{ocr_text}"
                    )
            except Exception:
                pass
        finally:
            # 强制销毁当前图片，释放内存
            del image
            gc.collect()

    if caption_texts:
        logger.info(f"[Vision] 流式处理完成: {img_idx} 张图片, {len(caption_texts)} 条描述")
        if progress_callback:
            progress_callback(
                'VISION_PROCESSING',
                f'👁️ 多模态视觉解析完成！共 {len(caption_texts)} 张图表已转化为语义嵌入',
                28,
            )

    return caption_texts


def ocr_pdf_images(pdf_path: str) -> Optional[str]:
    """流式逐图 OCR（不再全量加载图片列表）"""
    all_texts = []
    for i, img in enumerate(iter_images_from_pdf(pdf_path)):
        try:
            text = ocr_image(img)
            if text:
                all_texts.append(f"[图片{i + 1} OCR文本]\n{text}")
        finally:
            del img
            gc.collect()

    if all_texts:
        logger.info(f"OCR: extracted text from {len(all_texts)} images in PDF")
        return "\n\n".join(all_texts)
    return None


def ocr_docx_images(docx_path: str) -> Optional[str]:
    """流式逐图 OCR（不再全量加载图片列表）"""
    all_texts = []
    for i, img in enumerate(iter_images_from_docx(docx_path)):
        try:
            text = ocr_image(img)
            if text:
                all_texts.append(f"[图片{i + 1} OCR文本]\n{text}")
        finally:
            del img
            gc.collect()

    if all_texts:
        logger.info(f"OCR: extracted text from {len(all_texts)} images in DOCX")
        return "\n\n".join(all_texts)
    return None


async def ocr_pdf_images_v2(pdf_path: str, ai_client=None) -> Optional[str]:
    """流式逐图处理 PDF 图片（OCR + Vision），内存中最多 1 张图片"""
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    texts = await process_images_streaming(
        iter_images_from_pdf(pdf_path), ai_client, base_name=base_name,
    )

    if texts:
        logger.info(f"Vision-RAG: processed {len(texts)} images in PDF (OCR+Vision, streaming)")
        return "\n\n".join(texts)
    return None


async def ocr_docx_images_v2(docx_path: str, ai_client=None) -> Optional[str]:
    """流式逐图处理 DOCX 图片（OCR + Vision），内存中最多 1 张图片"""
    base_name = os.path.splitext(os.path.basename(docx_path))[0]
    texts = await process_images_streaming(
        iter_images_from_docx(docx_path), ai_client, base_name=base_name,
    )

    if texts:
        logger.info(f"Vision-RAG: processed {len(texts)} images in DOCX (OCR+Vision, streaming)")
        return "\n\n".join(texts)
    return None
