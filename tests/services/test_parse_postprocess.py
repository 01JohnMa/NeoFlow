# tests/services/test_parse_postprocess.py
"""解析产物后处理测试 — 水印过滤：关键词模式、重复文本自动识别与统计。"""

from services.parse_postprocess import (
    KeywordMatcher,
    detect_repeated_texts,
    strip_watermark_content,
)
from services.parse_result import Block, Page, ParseResult

KEYWORDS = ["COPY", "样本"]


def _block(block_id: str, text: str, order: int, block_type: str = "text") -> Block:
    return Block(
        id=block_id,
        type=block_type,
        bbox=[0, order * 10, 10, order * 10 + 10],
        reading_order=order,
        text=text,
        source="native-text",
    )


def _keyword_result() -> ParseResult:
    return ParseResult(
        pages=[Page(page_no=1, width=100, height=200, blocks=[
            _block("b1", "Knowledge is power", 1),
            _block("b2", "COPY", 2),
            _block("b3", "第 3 页 样本", 3),
            Block(id="b4", type="figure", bbox=[0, 30, 10, 40], reading_order=4,
                  image_path="img.png", source="native-text"),
            _block("b5", "copyright notice", 5),
        ])],
        markdown="Knowledge is power\nCOPY\n图 1\n",
        engine={"name": "mineru"},
    )


class TestKeywordMatcher:
    def test_ascii_keyword_requires_word_boundary(self):
        watermarks = KeywordMatcher(KEYWORDS)
        assert watermarks.matches_text("cOpY") is True
        assert watermarks.matches_text("Knowledge is power") is False
        assert watermarks.matches_text("copyright notice") is False

    def test_chinese_keyword_matches_substring(self):
        watermarks = KeywordMatcher(KEYWORDS)
        assert watermarks.matches_text("第 3 页 样本") is True

    def test_empty_keywords_disable_matcher(self):
        assert not KeywordMatcher([])
        assert not KeywordMatcher(["  "])


class TestDetectRepeatedTexts:
    def test_detects_text_at_or_above_threshold(self):
        result = ParseResult(pages=[
            Page(page_no=1, width=100, height=200, blocks=[_block("a", "COPY", 1)]),
            Page(page_no=2, width=100, height=200, blocks=[_block("b", "copy", 1)]),
            Page(page_no=3, width=100, height=200, blocks=[_block("c", " CoPy ", 1)]),
        ])

        assert detect_repeated_texts(result, threshold=3) == ["copy"]

    def test_below_threshold_not_detected(self):
        result = ParseResult(pages=[
            Page(page_no=1, width=100, height=200, blocks=[_block("a", "COPY", 1)]),
            Page(page_no=2, width=100, height=200, blocks=[_block("b", "COPY", 1)]),
        ])

        assert detect_repeated_texts(result, threshold=3) == []

    def test_threshold_below_two_disabled(self):
        result = ParseResult(pages=[
            Page(page_no=1, width=100, height=200, blocks=[_block("a", "COPY", 1)]),
        ])

        assert detect_repeated_texts(result, threshold=1) == []


class TestStripWatermarkContent:
    def test_keyword_mode_removes_matching_blocks_and_keeps_others(self):
        result = _keyword_result()

        removed = strip_watermark_content(result, keywords=KEYWORDS)

        assert removed == 2
        blocks = result.pages[0].blocks
        assert [block.text for block in blocks if block.type == "text"] == [
            "Knowledge is power",
            "copyright notice",
        ]
        assert [block.type for block in blocks] == ["text", "figure", "text"]

    def test_keyword_mode_reassigns_reading_order_and_syncs_markdown(self):
        result = _keyword_result()
        result.pages[0].markdown = "第一段\nCOPY\n第二段"

        strip_watermark_content(result, keywords=KEYWORDS)

        assert [block.reading_order for block in result.pages[0].blocks] == [1, 2, 3]
        assert result.pages[0].markdown == "第一段\n第二段"
        assert result.markdown == "Knowledge is power\n图 1\n"
        assert result.engine["watermark_filter"] == {
            "mode": "keywords",
            "removed_blocks": 2,
            "removed_lines": 2,
        }

    def test_auto_mode_removes_only_exact_repeated_text(self):
        result = ParseResult(pages=[
            Page(page_no=1, width=100, height=200, blocks=[
                _block("a", "COPY", 1),
                _block("b", "copyright notice", 2),
            ]),
            Page(page_no=2, width=100, height=200, blocks=[_block("c", "COPY", 1)]),
            Page(page_no=3, width=100, height=200, blocks=[_block("d", "COPY", 1)]),
        ])
        auto_texts = detect_repeated_texts(result, threshold=3)

        removed = strip_watermark_content(result, auto_texts=auto_texts)

        assert removed == 3
        assert [block.text for page in result.pages for block in page.blocks] == [
            "copyright notice",
        ]
        assert result.engine["watermark_filter"] == {
            "mode": "auto",
            "removed_blocks": 3,
            "removed_lines": 0,
            "auto_texts": ["copy"],
        }

    def test_auto_mode_markdown_lines_require_exact_match(self):
        result = ParseResult(
            pages=[Page(page_no=1, width=100, height=200, blocks=[_block("a", "COPY", 1)])],
            markdown="COPY\ncopyright notice\n",
            engine={"name": "mineru"},
        )

        strip_watermark_content(result, auto_texts=["COPY"])

        assert result.markdown == "copyright notice\n"

    def test_no_match_keeps_result_untouched(self):
        result = ParseResult(
            pages=[Page(page_no=1, width=100, height=200, blocks=[_block("a", "hello", 1)])],
            markdown="hello",
            engine={"name": "mineru"},
        )

        removed = strip_watermark_content(result, keywords=KEYWORDS)

        assert removed == 0
        assert "watermark_filter" not in result.engine
        assert result.markdown == "hello"
