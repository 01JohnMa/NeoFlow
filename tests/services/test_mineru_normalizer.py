# tests/services/test_mineru_normalizer.py
"""MinerU fixture → ParseResult 归一化测试（不联网、不依赖 GPU）。

覆盖：块类型、坐标缩放、reading_order、source/confidence 规则、
VLM confidence 恒为 null、office-xml、缺 middle.json 的降级。
"""

from pathlib import Path

import pytest

from services.mineru_normalizer import (
    MinerUOutputError,
    normalize_mineru_content,
    normalize_mineru_output,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "mineru"

PIPELINE_PARAMS = {
    "model_version": "pipeline",
    "method": "auto",
    "effort": "medium",
}


def _normalize(backend: str, params=None):
    return normalize_mineru_output(str(FIXTURES / backend), params or PIPELINE_PARAMS)


class TestPipelineNormalization:
    def test_block_types_and_reading_order(self):
        result = _normalize("pipeline")

        assert [page.page_no for page in result.pages] == [1, 2]
        page_one = result.pages[0]
        assert [block.type for block in page_one.blocks] == [
            "header",
            "title",
            "text",
            "list",
            "table",
            "formula",
            "figure",
            "footer",
        ]
        assert [block.reading_order for block in page_one.blocks] == list(range(1, 9))
        assert page_one.blocks[0].id == "p1-b1"
        assert page_one.blocks[7].id == "p1-b8"
        assert result.pages[1].blocks[0].id == "p2-b1"

    def test_bbox_scaled_to_page_pixels(self):
        page_one = _normalize("pipeline").pages[0]

        assert page_one.width == 1190
        assert page_one.height == 1684
        assert page_one.coordinate_space == "pixel"
        assert page_one.blocks[0].bbox == [119.0, 84.2, 1071.0, 151.56]
        assert page_one.blocks[5].bbox == [357.0, 1263.0, 833.0, 1380.88]

    def test_source_and_confidence_rules(self):
        result = _normalize("pipeline")
        blocks = result.pages[0].blocks

        for block in blocks:
            if block.type in ("header", "title", "text", "list", "footer"):
                assert block.source == "native-text"
                assert block.confidence == 1.0

        for block in (blocks[4], blocks[5], blocks[6]):
            assert block.source == "ocr"
            assert block.confidence is None

        ocr_text = result.pages[1].blocks[0]
        assert ocr_text.source == "ocr"
        assert ocr_text.confidence == 0.93

    def test_content_payload_fields(self):
        blocks = _normalize("pipeline").pages[0].blocks

        assert blocks[3].text == "first item\nsecond item"
        assert blocks[4].table_html == "<table><tr><td>A</td><td>1</td></tr></table>"
        assert blocks[4].text == "Table 1 Metrics"
        assert blocks[5].latex == "E = mc^2"
        assert blocks[6].image_path == "images/fig1.jpg"
        assert blocks[6].text == "Figure 1 Architecture"

    def test_markdown_and_engine_metadata(self):
        result = _normalize("pipeline")

        assert "NeoFlow Annual Report" in result.markdown
        assert result.engine == {
            "name": "mineru",
            "backend": "pipeline",
            "effort": "medium",
            "version": "3.4.4",
            "model_version": "pipeline",
            "method": "auto",
        }
        assert result.warnings == []


class TestVlmNormalization:
    def test_vlm_confidence_is_always_null(self):
        result = _normalize("vlm", {
            "model_version": "vlm",
            "method": "auto",
            "effort": "medium",
        })

        assert len(result.pages) == 1
        for block in result.pages[0].blocks:
            assert block.source == "vlm"
            assert block.confidence is None

    def test_engine_keeps_mineru_raw_backend(self):
        result = _normalize("vlm", {"model_version": "vlm"})

        assert result.engine["backend"] == "hybrid"
        assert result.engine["model_version"] == "vlm"


class TestOfficeNormalization:
    def test_office_blocks_are_office_xml_with_full_confidence(self):
        result = _normalize("office", {"model_version": "pipeline"})

        assert len(result.pages) == 1
        assert result.engine["backend"] == "office"
        assert [block.type for block in result.pages[0].blocks] == [
            "title",
            "text",
            "table",
        ]
        for block in result.pages[0].blocks:
            assert block.source == "office-xml"
            assert block.confidence == 1.0

        table = result.pages[0].blocks[2]
        assert "alpha" in table.table_html

    def test_office_without_page_geometry_warns_and_keeps_empty_bbox(self):
        result = _normalize("office", {"model_version": "pipeline"})

        page = result.pages[0]
        assert (page.width, page.height) == (1000.0, 1000.0)
        assert page.coordinate_space == "normalized-1000"
        assert page.blocks[0].bbox == []
        assert any("page_size" in warning for warning in result.warnings)


class TestMissingMiddleJson:
    def test_warns_and_keeps_normalized_coordinates(self):
        result = _normalize("no-middle", {"model_version": "pipeline", "method": "auto"})

        assert any("middle.json" in warning for warning in result.warnings)
        page = result.pages[0]
        assert (page.width, page.height) == (1000.0, 1000.0)
        assert page.coordinate_space == "normalized-1000"
        assert page.blocks[0].bbox == [100.0, 200.0, 900.0, 260.0]
        assert page.blocks[0].source == "native-text"
        assert page.blocks[1].source == "ocr"

    def test_method_ocr_falls_back_to_ocr_source(self):
        result = _normalize("no-middle", {"model_version": "pipeline", "method": "ocr"})

        assert result.pages[0].blocks[0].source == "ocr"
        assert result.pages[0].blocks[0].confidence is None


class TestPureNormalization:
    def test_unknown_content_type_is_skipped_with_warning(self):
        result = normalize_mineru_content(
            [{"type": "weird", "bbox": [0, 0, 100, 100], "page_idx": 0}],
        )

        assert any("未知块类型" in warning for warning in result.warnings)
        assert result.pages[0].blocks == []

    def test_hybrid_without_vlm_param_warns(self):
        result = normalize_mineru_content(
            [{"type": "text", "text": "x", "bbox": [0, 0, 1000, 100], "page_idx": 0}],
            middle_json={"_backend": "hybrid", "pdf_info": []},
            params={"model_version": "pipeline", "method": "auto"},
        )

        assert any("hybrid" in warning for warning in result.warnings)

    def test_missing_content_list_raises(self, tmp_path):
        with pytest.raises(MinerUOutputError):
            normalize_mineru_output(str(tmp_path))
