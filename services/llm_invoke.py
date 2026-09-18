# services/llm_invoke.py
"""LLM 窄接口：一次调用返回正文与元信息（finish_reason / usage / model）。

- 真实 HTTP 次数由调用方控制：max_retries=0，不做隐式重试；
- usage 缺失时保持 None（不伪装成 0）；
- 可被测试替换（extract_service 以模块级函数调用）。
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from langchain_openai import ChatOpenAI

from config.settings import settings


@dataclass
class LLMResult:
    content: str
    finish_reason: Optional[str]
    model: Optional[str]
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    request_id: Optional[str]


def _as_int(value: Any) -> Optional[int]:
    return value if isinstance(value, int) else None


async def invoke_llm(
    messages: List[Dict[str, str]],
    *,
    json_mode: bool = True,
    max_output_tokens: Optional[int] = None,
) -> LLMResult:
    """调用一次模型；不隐藏失败、不重试。"""
    llm = ChatOpenAI(
        model=settings.LLM_MODEL_ID,
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        temperature=settings.LLM_TEMPERATURE,
        max_retries=0,
    )
    kwargs: Dict[str, Any] = {}
    if max_output_tokens:
        kwargs["max_tokens"] = max_output_tokens
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = await llm.ainvoke(messages, **kwargs)
    metadata = getattr(response, "response_metadata", None) or {}
    usage = metadata.get("token_usage") or getattr(response, "usage_metadata", None) or {}
    content = response.content if isinstance(response.content, str) else str(response.content)
    finish_reason = metadata.get("finish_reason")
    model = metadata.get("model_name") or metadata.get("model")

    return LLMResult(
        content=content,
        finish_reason=str(finish_reason) if finish_reason is not None else None,
        model=str(model) if model else None,
        input_tokens=_as_int(usage.get("prompt_tokens") or usage.get("input_tokens")),
        output_tokens=_as_int(usage.get("completion_tokens") or usage.get("output_tokens")),
        request_id=metadata.get("id"),
    )
