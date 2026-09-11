# tests/services/test_parse_extraction.py
"""从 ParseResult 执行抽取的单元测试（不依赖 OCR/VLM/LangChain）。"""

import pytest

from services.parse_extraction import run_parse_extraction

PARSE_DATA = {
    "pages": [
        {"page_no": 1, "width": 100, "height": 200, "markdown": "第一页 markdown"},
        {"page_no": 2, "width": 100, "height": 200, "markdown": "第二页 markdown"},
    ],
    "markdown": "整文档 markdown",
    "engine": {"name": "mineru", "backend": "pipeline"},
    "warnings": [],
}


def _configuration(**overrides):
    config = {
        "id": "config-1",
        "name": "检测报告",
        "code": "inspection_report",
        "extraction_mode": "ocr_llm",
        "per_page_extraction": False,
    }
    config.update(overrides)
    return config


@pytest.mark.asyncio
async def test_single_pass_uses_document_markdown():
    prompts = []

    async def fake_llm(prompt):
        prompts.append(prompt)
        return '{"sample_name": "LED灯"}'

    payload = await run_parse_extraction(
        configuration=_configuration(),
        parse_data=PARSE_DATA,
        llm_invoke=fake_llm,
    )

    assert payload["extraction_data"] == {"sample_name": "LED灯"}
    assert payload["markdown"] == "整文档 markdown"
    assert "整文档 markdown" in prompts[0]
    assert len(prompts) == 1


@pytest.mark.asyncio
async def test_per_page_uses_each_page_markdown():
    prompts = []

    async def fake_llm(prompt):
        prompts.append(prompt)
        return f'{{"page": "{len(prompts)}"}}'

    payload = await run_parse_extraction(
        configuration=_configuration(per_page_extraction=True),
        parse_data=PARSE_DATA,
        llm_invoke=fake_llm,
    )

    assert "第一页 markdown" in prompts[0]
    assert "第二页 markdown" in prompts[1]
    assert payload["extraction_data"] == {"page": "1"}
    assert payload["extraction_results"] == [
        {"sample_index": 1, "data": {"page": "1"}},
        {"sample_index": 2, "data": {"page": "2"}},
    ]


@pytest.mark.asyncio
async def test_per_page_skips_empty_pages():
    prompts = []

    async def fake_llm(prompt):
        prompts.append(prompt)
        return '{"ok": true}'

    parse_data = {
        "pages": [
            {"page_no": 1, "markdown": ""},
            {"page_no": 2, "markdown": "有内容"},
        ],
        "markdown": "整文档",
    }

    payload = await run_parse_extraction(
        configuration=_configuration(per_page_extraction=True),
        parse_data=parse_data,
        llm_invoke=fake_llm,
    )

    assert len(prompts) == 1
    assert payload["extraction_data"] == {"ok": True}
    assert "extraction_results" not in payload
