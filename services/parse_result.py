# services/parse_result.py
"""ParseResult 契约 - 解析后端与下游能力之间的统一块模型。

契约要点（#2 / #8）：
- 文档 → 页 → 块；块 type 限定为 8 类，坐标统一到页面像素空间；
- source 标记内容来源：native-text | ocr | vlm | office-xml；
- confidence 可为 null：
  * VLM 一律 null（VLM 没有校准过的块级置信度，禁止伪造）；
  * native-text / office-xml 固定 1.0；
  * ocr 透传模型 score，拿不到时保持 null。

MinerU 的 middle.json / content_list.json 只是 adapter 内部输入，
下游只依赖本契约。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

BLOCK_TYPES = (
    "title",
    "text",
    "list",
    "table",
    "figure",
    "formula",
    "header",
    "footer",
)

SOURCE_TYPES = (
    "native-text",
    "ocr",
    "vlm",
    "office-xml",
)

COORDINATE_SPACE_PIXEL = "pixel"
COORDINATE_SPACE_NORMALIZED = "normalized-1000"


def resolve_confidence(source: str, confidence: Optional[float]) -> Optional[float]:
    """按契约归一化 confidence，保证 source 与置信度语义一致。"""
    if source == "vlm":
        return None
    if source in ("native-text", "office-xml"):
        return 1.0
    return confidence


@dataclass
class Block:
    """ParseResult 块：统一类型 + 坐标 + 文本载荷 + 来源/置信度。"""

    id: str
    type: str
    bbox: List[float]
    reading_order: int
    text: Optional[str] = None
    table_html: Optional[str] = None
    image_path: Optional[str] = None
    latex: Optional[str] = None
    source: str = "ocr"
    confidence: Optional[float] = None

    def __post_init__(self):
        if self.type not in BLOCK_TYPES:
            raise ValueError(f"非法块类型: {self.type}")
        if self.source not in SOURCE_TYPES:
            raise ValueError(f"非法来源: {self.source}")
        self.confidence = resolve_confidence(self.source, self.confidence)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "bbox": self.bbox,
            "text": self.text,
            "table_html": self.table_html,
            "image_path": self.image_path,
            "latex": self.latex,
            "source": self.source,
            "confidence": self.confidence,
            "reading_order": self.reading_order,
        }


@dataclass
class Page:
    """ParseResult 页：页尺寸 + 页内块（reading_order 为页内顺序）。"""

    page_no: int
    width: float
    height: float
    blocks: List[Block] = field(default_factory=list)
    markdown: Optional[str] = None
    coordinate_space: str = COORDINATE_SPACE_PIXEL

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_no": self.page_no,
            "width": self.width,
            "height": self.height,
            "coordinate_space": self.coordinate_space,
            "markdown": self.markdown,
            "blocks": [block.to_dict() for block in self.blocks],
        }


@dataclass
class ParseResult:
    """一次解析的完整输出（与具体解析后端解耦）。"""

    pages: List[Page] = field(default_factory=list)
    markdown: str = ""
    engine: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pages": [page.to_dict() for page in self.pages],
            "markdown": self.markdown,
            "engine": self.engine,
            "warnings": self.warnings,
        }
