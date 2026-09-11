# services/parse_extraction.py
"""从 ParseResult 的 markdown 执行抽取（不依赖 OCR/VLM）。

Extract 的 parse 输入路径：prompt 直接用解析产物的 markdown（或逐页 markdown），
LLM 调用由调用方注入，便于测试与复用。
"""

from typing import Any, Awaitable, Callable, Dict

from loguru import logger

from agents.json_cleaner import parse_llm_json
from services.base import build_extraction_prompt

LlmInvoke = Callable[[str], Awaitable[str]]


async def run_parse_extraction(
    *,
    configuration: Dict[str, Any],
    parse_data: Dict[str, Any],
    llm_invoke: LlmInvoke,
) -> Dict[str, Any]:
    """用 ParseResult 的 markdown 构建 prompt 并执行 LLM 抽取。

    - per_page_extraction=True：逐页 markdown，每页独立抽取
    - 否则：整文档 markdown

    Returns:
        {
          "extraction_data": {...},   # 主样品（第一页）字段
          "extraction_results": [{"sample_index": n, "data": {...}}, ...],  # 逐页多样品时
          "markdown": str,
        }
    """
    markdown = parse_data.get("markdown") or ""
    per_page = configuration.get("per_page_extraction", False)

    if per_page:
        page_results = []
        for page in parse_data.get("pages") or []:
            page_markdown = (page.get("markdown") or "").strip()
            if not page_markdown:
                continue
            extracted = parse_llm_json(
                await llm_invoke(build_extraction_prompt(configuration, page_markdown))
            )
            page_results.append(extracted)
            logger.info(f"解析第{page.get('page_no')}页提取完成: {len(extracted)}个字段")

        payload: Dict[str, Any] = {
            "extraction_data": page_results[0] if page_results else {},
            "markdown": markdown,
        }
        if len(page_results) > 1:
            payload["extraction_results"] = [
                {"sample_index": index + 1, "data": data}
                for index, data in enumerate(page_results)
            ]
        return payload

    extraction_data = parse_llm_json(
        await llm_invoke(build_extraction_prompt(configuration, markdown))
    )
    return {"extraction_data": extraction_data, "markdown": markdown}
