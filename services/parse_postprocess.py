# services/parse_postprocess.py
"""解析产物后处理：在适配器输出与落库之间执行的内容过滤。

水印过滤（remove_watermark 开启时）两种模式：
- 指定关键词：按调用方给出的词表匹配（ASCII 整词、含中文子串，大小写不敏感）；
- 未指定关键词：自动识别全文中重复出现的块文本（≥ PARSE_WATERMARK_REPEAT_THRESHOLD 次，
  忽略大小写与首尾空白），按整块 / 整行精确移除。

命中统计与自动识别出的文本写入 engine 元信息，便于核对。
"""

import re
from collections import Counter
from typing import Iterable, List, Sequence, Tuple

from services.parse_result import Block, ParseResult

KEYWORD_FIELDS = ("text", "table_html", "latex")
AUTO_TEXT_FIELDS = ("text",)
MAX_RECORDED_AUTO_TEXTS = 10


def _normalize(value: str) -> str:
    return " ".join(value.split()).casefold()


class KeywordMatcher:
    """按词表匹配文本（ASCII 整词、含中文子串，大小写不敏感）。"""

    def __init__(self, keywords: Sequence[str]):
        self._matchers: List[re.Pattern] = []
        for keyword in keywords:
            if not keyword or not keyword.strip():
                continue
            value = keyword.strip()
            escaped = re.escape(value)
            if value.isascii():
                self._matchers.append(
                    re.compile(
                        rf"(?<![0-9A-Za-z]){escaped}(?![0-9A-Za-z])",
                        re.IGNORECASE,
                    )
                )
            else:
                self._matchers.append(re.compile(escaped, re.IGNORECASE))

    def __bool__(self) -> bool:
        return bool(self._matchers)

    def matches_text(self, value: object) -> bool:
        if not value:
            return False
        text = str(value)
        return any(matcher.search(text) for matcher in self._matchers)

    def matches_block(self, block: Block) -> bool:
        return any(self.matches_text(getattr(block, field)) for field in KEYWORD_FIELDS)


def detect_repeated_texts(result: ParseResult, threshold: int) -> List[str]:
    """统计全文重复出现的块文本，返回达到阈值的规范化文本（保持首次出现顺序）。"""
    if threshold <= 1:
        return []
    counts: Counter = Counter()
    for page in result.pages:
        for block in page.blocks:
            for field in AUTO_TEXT_FIELDS:
                text = getattr(block, field)
                if text and text.strip():
                    counts[_normalize(text)] += 1
    return [text for text, count in counts.items() if count >= threshold]


class WatermarkFilter:
    """组合关键词规则与自动识别的重复文本，统一判定块 / markdown 行是否属于水印。"""

    def __init__(
        self,
        keywords: Sequence[str] = (),
        auto_texts: Iterable[str] = (),
    ):
        self._keywords = KeywordMatcher(keywords)
        self._auto_texts = {_normalize(text) for text in auto_texts if text and text.strip()}

    def __bool__(self) -> bool:
        return bool(self._keywords) or bool(self._auto_texts)

    def matches_text(self, value: object) -> bool:
        if self._keywords.matches_text(value):
            return True
        if not value:
            return False
        return _normalize(str(value)) in self._auto_texts

    def matches_block(self, block: Block) -> bool:
        if self._keywords.matches_block(block):
            return True
        return bool(block.text) and _normalize(block.text) in self._auto_texts

    def strip_markdown(self, markdown: str) -> Tuple[str, int]:
        """移除命中行；返回 (新 markdown, 移除行数)。"""
        lines = markdown.splitlines()
        kept = [line for line in lines if not self.matches_text(line)]
        removed = len(lines) - len(kept)
        if removed == 0:
            return markdown, 0
        rebuilt = "\n".join(kept)
        if markdown.endswith("\n") and rebuilt:
            rebuilt += "\n"
        return rebuilt, removed


def strip_watermark_content(
    result: ParseResult,
    keywords: Sequence[str] = (),
    auto_texts: Sequence[str] = (),
) -> int:
    """按关键词或自动识别文本移除水印块与 markdown 行；返回移除的块数。"""
    watermarks = WatermarkFilter(keywords=keywords, auto_texts=auto_texts)
    if not watermarks:
        return 0

    removed_blocks = 0
    removed_lines = 0
    for page in result.pages:
        kept: List[Block] = []
        for block in page.blocks:
            if watermarks.matches_block(block):
                removed_blocks += 1
                continue
            kept.append(block)
        for index, block in enumerate(kept, start=1):
            block.reading_order = index
        page.blocks = kept
        if page.markdown:
            page.markdown, dropped = watermarks.strip_markdown(page.markdown)
            removed_lines += dropped

    if result.markdown:
        result.markdown, dropped = watermarks.strip_markdown(result.markdown)
        removed_lines += dropped

    if removed_blocks or removed_lines:
        info = {
            "mode": "auto" if auto_texts else "keywords",
            "removed_blocks": removed_blocks,
            "removed_lines": removed_lines,
        }
        if auto_texts:
            info["auto_texts"] = list(auto_texts)[:MAX_RECORDED_AUTO_TEXTS]
        result.engine["watermark_filter"] = info
    return removed_blocks
