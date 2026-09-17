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

    始终以整份 ParseResult markdown 执行一次抽取。

    Returns:
        {
          "extraction_data": {...},
          "markdown": str,
        }
    """
    markdown = parse_data.get("markdown") or ""
    extraction_data = parse_llm_json(
        await llm_invoke(build_extraction_prompt(configuration, markdown))
    )
    return {"extraction_data": extraction_data, "markdown": markdown}
