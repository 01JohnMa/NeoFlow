"""Classify/Split 的 ParseResult seam 测试。"""

from unittest.mock import AsyncMock

import pytest

from services.classify_split_service import run_classify, run_split


PARSE_DATA = {
    "markdown": "第一页内容\n第二页内容",
    "pages": [
        {
            "page_no": 1,
            "coordinate_space": "pixel",
            "blocks": [
                {
                    "id": "p1-b1",
                    "bbox": [1, 2, 30, 40],
                    "source": "native-text",
                }
            ],
        },
        {
            "page_no": 2,
            "coordinate_space": "pixel",
            "blocks": [
                {
                    "id": "p2-b1",
                    "bbox": [5, 6, 50, 60],
                    "source": "ocr",
                }
            ],
        },
    ],
}


@pytest.mark.asyncio
async def test_classify_returns_rule_result_with_block_provenance():
    invoke = AsyncMock(return_value='{"label":"invoice","confidence":0.91,"reasoning":"has invoice number","source_pages":[1]}')

    result = await run_classify(
        parse_data=PARSE_DATA,
        definition={"rules": ["invoice: contains invoice number"]},
        llm_invoke=invoke,
    )

    assert result["label"] == "invoice"
    assert result["confidence"] == 0.91
    assert result["source_refs"] == [
        {
            "page_no": 1,
            "block_id": "p1-b1",
            "bbox": [1, 2, 30, 40],
            "coordinate_space": "pixel",
            "source": "native-text",
        }
    ]
    invoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_split_normalizes_segments_and_uncategorized_pages():
    invoke = AsyncMock(return_value='{"segments":[{"category":"invoice","pages":[1]}],"uncategorized_pages":[2]}')

    result = await run_split(
        parse_data=PARSE_DATA,
        definition={"categories": [{"name": "invoice", "description": "invoice pages"}]},
        llm_invoke=invoke,
    )

    assert result["segments"][0]["segment_id"] == "segment-1"
    assert result["segments"][0]["pages"] == [1]
    assert result["segments"][0]["source_refs"][0]["block_id"] == "p1-b1"
    assert result["uncategorized_pages"] == [2]


@pytest.mark.asyncio
async def test_invalid_classify_payload_fails_closed_to_fallback():
    result = await run_classify(
        parse_data=PARSE_DATA,
        definition={"fallback_label": "other"},
        llm_invoke=AsyncMock(return_value='{"raw_response":"bad"}'),
    )

    assert result["label"] == "other"
    assert result["confidence"] is None
    assert result["source_refs"] == []
