# services/mineru_normalizer.py
"""MinerU 输出 → ParseResult 归一化。

MinerU 的 content_list.json（读取顺序的扁平块）与 middle.json/layout.json
（页尺寸、span score、后端标记）只是本模块的输入，不暴露给下游：
- 块列表与 reading_order 取 content_list；
- 页尺寸与像素坐标换算取 middle.json 的 page_size；
- source/confidence 按 middle.json 的 `_backend` 与 span score 推断：
  * pipeline：有 span score 的文本 → ocr（透传最小 score）；
    无 score 的文本 → native-text（1.0）；
    表格/图片/公式由页面图像模型产出 → ocr（无校准 score 时为 null）；
  * vlm / 托管 API 的 vlm：一律 vlm + confidence=null（不伪造）；
  * office：office-xml + 1.0。
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from services.parse_result import (
    Block,
    COORDINATE_SPACE_NORMALIZED,
    COORDINATE_SPACE_PIXEL,
    Page,
    ParseResult,
)

CONTENT_LIST_SUFFIX = "_content_list.json"
CONTENT_LIST_V2_SUFFIX = "_content_list_v2.json"
MIDDLE_SUFFIX = "_middle.json"
MIDDLE_FILENAME = "layout.json"
MARKDOWN_FILENAME = "full.md"

TEXT_LIKE_BLOCK_TYPES = ("title", "text", "list", "header", "footer")

CONTENT_TYPE_TO_BLOCK_TYPE = {
    "title": "title",
    "paragraph": "text",
    "image": "figure",
    "chart": "figure",
    "table": "table",
    "equation": "formula",
    "equation_interline": "formula",
    "list": "list",
    "code": "text",
    "algorithm": "text",
    "header": "header",
    "page_header": "header",
    "footer": "footer",
    "page_footer": "footer",
    "page_number": "footer",
    "page_footnote": "footer",
    "aside_text": "text",
    "page_aside_text": "text",
}

CAPTION_KEYS = (
    "table_caption",
    "table_footnote",
    "image_caption",
    "image_footnote",
    "chart_caption",
    "chart_footnote",
)


class MinerUOutputError(Exception):
    """MinerU 输出无法归一化（缺关键文件或结构不合法）。"""


@dataclass
class _PageContext:
    page_size: Optional[List[float]] = None
    blocks: List[Dict[str, Any]] = field(default_factory=list)
    has_text_spans: bool = False
    has_scored_spans: bool = False


def _find_first_file(root: str, predicate) -> Optional[str]:
    matches: List[str] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            if predicate(filename):
                matches.append(os.path.join(dirpath, filename))
    return sorted(matches)[0] if matches else None


def _load_json(path: str) -> Any:
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise MinerUOutputError(f"读取 MinerU 输出失败: {os.path.basename(path)}: {exc}")


def load_mineru_output(directory: str) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]], str, List[str]]:
    """定位并加载 content_list / middle / markdown，返回 (items, middle, md, warnings)。"""
    warnings: List[str] = []

    content_path = _find_first_file(
        directory,
        lambda name: name.endswith(CONTENT_LIST_SUFFIX)
        and not name.endswith(CONTENT_LIST_V2_SUFFIX),
    )
    if not content_path:
        raise MinerUOutputError(
            f"MinerU 输出缺少 content_list.json: {directory}"
        )

    content_list = _load_json(content_path)
    if not isinstance(content_list, list):
        raise MinerUOutputError("MinerU content_list.json 顶层应为数组")

    middle_path = _find_first_file(
        directory,
        lambda name: name.endswith(MIDDLE_SUFFIX) or name == MIDDLE_FILENAME,
    )
    middle_json: Optional[Dict[str, Any]] = None
    if middle_path:
        loaded = _load_json(middle_path)
        if isinstance(loaded, dict):
            middle_json = loaded
        else:
            warnings.append("MinerU middle.json 顶层不是对象，已忽略")
    else:
        warnings.append(
            "MinerU 输出缺少 middle.json/layout.json，source 按解析参数推断且坐标为 0-1000 归一化"
        )

    markdown_path = _find_first_file(
        directory,
        lambda name: name == MARKDOWN_FILENAME,
    ) or _find_first_file(directory, lambda name: name.endswith(".md"))
    markdown = ""
    if markdown_path:
        try:
            with open(markdown_path, encoding="utf-8") as handle:
                markdown = handle.read()
        except OSError as exc:
            warnings.append(f"读取 MinerU markdown 失败: {exc}")
    else:
        warnings.append("MinerU 输出缺少 markdown（full.md）")

    return content_list, middle_json, markdown, warnings


def normalize_mineru_output(
    directory: str,
    params: Optional[Dict[str, Any]] = None,
) -> ParseResult:
    """从 MinerU 输出目录构建 ParseResult。"""
    content_list, middle_json, markdown, warnings = load_mineru_output(directory)
    result = normalize_mineru_content(
        content_list,
        middle_json=middle_json,
        markdown=markdown,
        params=params,
    )
    result.warnings = warnings + result.warnings
    return result


def normalize_mineru_content(
    content_items: List[Dict[str, Any]],
    *,
    middle_json: Optional[Dict[str, Any]] = None,
    markdown: str = "",
    params: Optional[Dict[str, Any]] = None,
) -> ParseResult:
    """把 MinerU content_list + middle 归一化为 ParseResult（纯函数，便于 fixture 测试）。"""
    params = dict(params or {})
    warnings: List[str] = []
    raw_backend = (middle_json or {}).get("_backend")
    backend = _infer_backend(middle_json, params)
    if raw_backend == "hybrid" and backend != "vlm":
        warnings.append("MinerU hybrid 后端按 span score 推断 source（本地后端接入后细化）")

    contexts = _build_page_contexts(middle_json)

    pages: Dict[int, Page] = {}
    # pdf_info is the provider's authoritative physical-page inventory. Create
    # entries before content items so blank pages are preserved explicitly.
    for page_idx, context in contexts.items():
        width, height, coordinate_space = _page_size(context.page_size, warnings, page_idx)
        pages[page_idx] = Page(page_no=page_idx + 1, width=width, height=height,
                                coordinate_space=coordinate_space)
    for item in content_items:
        if not isinstance(item, dict):
            warnings.append("忽略非对象 content_list 条目")
            continue

        page_idx = int(item.get("page_idx") or 0)
        page = pages.get(page_idx)
        if page is None:
            context = contexts.get(page_idx)
            page_size = context.page_size if context else None
            width, height, coordinate_space = _page_size(page_size, warnings, page_idx)
            page = Page(
                page_no=page_idx + 1,
                width=width,
                height=height,
                coordinate_space=coordinate_space,
            )
            pages[page_idx] = page

        block_type = _content_type_to_block_type(item.get("type"), item)
        if block_type is None:
            warnings.append(f"忽略未知块类型: {item.get('type')}")
            continue

        context = contexts.get(page_idx)
        pixel_bbox = _scale_bbox(item.get("bbox"), context.page_size if context else None)
        source, confidence = _resolve_source(
            block_type, item, pixel_bbox, context, backend, params
        )
        reading_order = len(page.blocks) + 1
        page.blocks.append(Block(
            id=f"p{page.page_no}-b{reading_order}",
            type=block_type,
            bbox=pixel_bbox,
            reading_order=reading_order,
            text=_item_text(item, block_type),
            table_html=item.get("table_body") if block_type == "table" else None,
            image_path=item.get("img_path"),
            latex=_item_latex(item) if block_type == "formula" else None,
            source=source,
            confidence=confidence,
        ))

    observed = sorted(page_no + 1 for page_no in pages)
    expected = sorted(index + 1 for index in contexts)
    coverage_status = "unknown" if not contexts else ("complete" if observed == expected else "incomplete")
    engine = {
        "name": "mineru",
        "backend": raw_backend or backend,
        "effort": params.get("effort"),
        "version": (middle_json or {}).get("_version_name"),
        "model_version": params.get("model_version"),
        "method": params.get("method"),
        "coverage": {
            "status": coverage_status,
            "expected_page_count": len(expected) if contexts else None,
            "observed_page_numbers": observed,
            "page_states": {str(number): ("blank_confirmed" if not pages[number - 1].blocks else "observed")
                            for number in observed if number - 1 in pages},
            "provider": "pdf_info" if contexts else None,
        },
    }
    engine = {key: value for key, value in engine.items() if value not in (None, "")}

    return ParseResult(
        pages=[pages[key] for key in sorted(pages)],
        markdown=markdown or "",
        engine=engine,
        warnings=warnings,
    )


def _infer_backend(
    middle_json: Optional[Dict[str, Any]],
    params: Dict[str, Any],
) -> str:
    raw = (middle_json or {}).get("_backend")
    model_version = params.get("model_version")
    if raw == "office":
        return "office"
    if raw == "vlm":
        return "vlm"
    if raw == "pipeline":
        return "pipeline"
    if raw == "hybrid":
        return "vlm" if model_version == "vlm" else "hybrid"
    return "vlm" if model_version == "vlm" else "pipeline"


def _content_type_to_block_type(
    content_type: Any,
    item: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    if content_type is None:
        return None
    content_type = str(content_type).lower()
    if content_type == "text":
        return "title" if (item or {}).get("text_level") else "text"
    return CONTENT_TYPE_TO_BLOCK_TYPE.get(content_type)


def _page_size(
    page_size: Optional[List[float]],
    warnings: List[str],
    page_idx: int,
) -> Tuple[float, float, str]:
    if page_size and len(page_size) >= 2:
        return float(page_size[0]), float(page_size[1]), COORDINATE_SPACE_PIXEL

    warning = f"第 {page_idx + 1} 页缺少 page_size，坐标保持 0-1000 归一化"
    if warning not in warnings:
        warnings.append(warning)
    return 1000.0, 1000.0, COORDINATE_SPACE_NORMALIZED


def _scale_bbox(
    bbox: Any,
    page_size: Optional[List[float]],
) -> List[float]:
    if not bbox or len(bbox) != 4:
        return []
    x0, y0, x1, y1 = (float(value) for value in bbox)
    if not page_size or len(page_size) < 2:
        return [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)]
    width, height = float(page_size[0]), float(page_size[1])
    return [
        round(x0 / 1000 * width, 2),
        round(y0 / 1000 * height, 2),
        round(x1 / 1000 * width, 2),
        round(y1 / 1000 * height, 2),
    ]


def _build_page_contexts(
    middle_json: Optional[Dict[str, Any]],
) -> Dict[int, _PageContext]:
    contexts: Dict[int, _PageContext] = {}
    for page in (middle_json or {}).get("pdf_info") or []:
        if not isinstance(page, dict):
            continue
        page_idx = page.get("page_idx")
        if page_idx is None:
            continue

        root_blocks = page.get("para_blocks") or page.get("preproc_blocks")
        blocks = list(_iter_leaf_blocks(root_blocks))
        for key in (
            "discarded_blocks",
            "images",
            "tables",
            "charts",
            "interline_equations",
        ):
            blocks.extend(_iter_leaf_blocks(page.get(key)))

        context = _PageContext(
            page_size=page.get("page_size"),
            blocks=blocks,
        )
        for block in blocks:
            for span in _iter_spans(block):
                if str(span.get("content") or "").strip() or span.get("html"):
                    context.has_text_spans = True
                if isinstance(span.get("score"), (int, float)):
                    context.has_scored_spans = True
        contexts[int(page_idx)] = context
    return contexts


def _iter_leaf_blocks(blocks: Any):
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        children = block.get("blocks")
        if children:
            yield from _iter_leaf_blocks(children)
        else:
            yield block


def _iter_spans(block: Dict[str, Any]):
    for line in block.get("lines") or []:
        if not isinstance(line, dict):
            continue
        for span in line.get("spans") or []:
            if isinstance(span, dict):
                yield span


def _find_matching_block(
    context: Optional[_PageContext],
    bbox: List[float],
) -> Optional[Dict[str, Any]]:
    if not context or not bbox:
        return None
    best: Optional[Dict[str, Any]] = None
    best_ratio = 0.0
    for block in context.blocks:
        ratio = _overlap_ratio(bbox, block.get("bbox"))
        if ratio > best_ratio:
            best, best_ratio = block, ratio
    return best if best_ratio >= 0.5 else None


def _overlap_ratio(bbox: List[float], other: Any) -> float:
    if not bbox or not other or len(other) < 4:
        return 0.0
    x0 = max(bbox[0], float(other[0]))
    y0 = max(bbox[1], float(other[1]))
    x1 = min(bbox[2], float(other[2]))
    y1 = min(bbox[3], float(other[3]))
    if x1 <= x0 or y1 <= y0:
        return 0.0
    intersection = (x1 - x0) * (y1 - y0)
    area = max((bbox[2] - bbox[0]) * (bbox[3] - bbox[1]), 1e-6)
    return intersection / area


def _resolve_source(
    block_type: str,
    item: Dict[str, Any],
    pixel_bbox: List[float],
    context: Optional[_PageContext],
    backend: str,
    params: Dict[str, Any],
) -> Tuple[str, Optional[float]]:
    """返回 (source, confidence)；Block 构造时会再次执行契约归一化。"""
    if backend == "vlm":
        return "vlm", None
    if backend == "office":
        return "office-xml", None

    matched = _find_matching_block(context, pixel_bbox)
    spans = list(_iter_spans(matched)) if matched else []
    scores = [
        float(span["score"])
        for span in spans
        if isinstance(span.get("score"), (int, float))
    ]

    if block_type in TEXT_LIKE_BLOCK_TYPES:
        if scores:
            return "ocr", min(scores)
        if any(str(span.get("content") or "").strip() for span in spans):
            return "native-text", None
        if context and context.has_scored_spans:
            return "ocr", None
        if context and context.has_text_spans:
            return "native-text", None
        return _fallback_source(params), None

    if scores:
        return "ocr", min(scores)
    return "ocr", None


def _fallback_source(params: Dict[str, Any]) -> str:
    method = str(params.get("method") or "auto").lower()
    return "ocr" if method == "ocr" else "native-text"


def _item_text(item: Dict[str, Any], block_type: str) -> Optional[str]:
    if block_type == "list":
        items = item.get("list_items") or []
        joined = "\n".join(str(value) for value in items)
        return joined or None

    if block_type in ("table", "figure"):
        parts: List[str] = []
        for key in CAPTION_KEYS:
            for value in item.get(key) or []:
                parts.append(str(value))
        joined = "\n".join(part for part in parts if part)
        return joined or None

    text = item.get("text")
    return str(text) if text else None


def _item_latex(item: Dict[str, Any]) -> Optional[str]:
    text = item.get("text")
    if not text:
        return None
    stripped = str(text).strip()
    for prefix, suffix in (("$$", "$$"), ("\\[", "\\]"), ("\\(", "\\)")):
        if stripped.startswith(prefix) and stripped.endswith(suffix) and len(stripped) > len(prefix) + len(suffix):
            return stripped[len(prefix):-len(suffix)].strip()
    return stripped
