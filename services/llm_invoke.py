# services/llm_invoke.py
"""LLM 窄接口：一次调用返回正文与元信息（finish_reason / usage / model / refusal）。

- 真实 HTTP 次数由调用方控制：max_retries=0，不做隐式重试；
- usage 缺失时保持 None（不把真实 0 与缺失混为一谈）；
- 拒绝信号与正文类型在此分类，调用方不必把非 JSON 内容送进修复流程；
- timeout 由调用方按 Job 剩余 deadline 传入；
- 可被测试替换（extract_service 以模块级函数调用）。
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx
from langchain_openai import ChatOpenAI
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)

from config.settings import settings
from services import platform_model_client


def is_retryable_transport_error(error: Exception) -> bool:
    """只把网络/超时/限流/服务端错误视为可在请求预算内重试的传输错误。"""
    if isinstance(error, platform_model_client.PlatformModelError):
        # 平台拒绝类（能力未接入/缺 Invocation/窗口过期）不可重试；
        # 超时与上游 5xx/429 属于传输类，可在预算内重试。
        if error.reason in {
            platform_model_client.REASON_TIMEOUT,
            platform_model_client.REASON_UPSTREAM,
        }:
            return error.status is None or error.status >= 500 or error.status == 429
        return False
    if isinstance(
        error,
        (
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.RemoteProtocolError,
            APIConnectionError,
            APITimeoutError,
            RateLimitError,
            InternalServerError,
        ),
    ):
        return True
    if isinstance(error, APIStatusError):
        status_code = error.status_code
        return status_code in {408, 429} or (
            isinstance(status_code, int) and status_code >= 500
        )
    status_code = getattr(error, "status_code", None)
    return status_code in {408, 429} or (
        isinstance(status_code, int) and status_code >= 500
    )


@dataclass
class LLMResult:
    content: str
    finish_reason: Optional[str]
    model: Optional[str]
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    request_id: Optional[str]
    refusal: Optional[str] = None
    content_invalid: bool = False


def _as_int(value: Any) -> Optional[int]:
    return value if isinstance(value, int) else None


def _pick_int(usage: Dict[str, Any], *keys: str) -> Optional[int]:
    for key in keys:
        value = usage.get(key)
        if isinstance(value, int):
            return value
    return None


def _extract_text(content: Any) -> tuple[str, bool]:
    """返回 (正文, 是否类型异常)。

    仅接受字符串；content blocks 形式拼接 text 块；其余类型视为异常。
    """
    if isinstance(content, str):
        return content, False
    if isinstance(content, list):
        parts: List[str] = []
        content_invalid = False
        for block in content:
            if isinstance(block, dict) and block.get("type") in {"text", "output_text"}:
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
                else:
                    content_invalid = True
            elif isinstance(block, str):
                parts.append(block)
            else:
                content_invalid = True
        joined = "".join(parts)
        return joined, content_invalid or not joined.strip()
    return "", True


async def invoke_llm(
    messages: List[Dict[str, str]],
    *,
    json_mode: bool = True,
    max_output_tokens: Optional[int] = None,
    timeout: Optional[float] = None,
    logical_call_id: Optional[str] = None,
) -> LLMResult:
    """调用一次模型；不隐藏失败、不重试。

    Relay 模式（平台部署）经 platform_model_client 走 AI Center Relay，归因
    由平台注入；本地 direct 模式维持 ChatOpenAI 直连。``logical_call_id``
    是同一逻辑调用重试时的幂等标识（仅 Relay 路径使用）。
    """
    if platform_model_client.model_access_mode() == "relay":
        return await _invoke_via_relay(
            messages,
            json_mode=json_mode,
            max_output_tokens=max_output_tokens,
            timeout=timeout,
            logical_call_id=logical_call_id,
        )
    kwargs: Dict[str, Any] = {
        "model": settings.LLM_MODEL_ID,
        **settings.llm_connection(),
        "temperature": settings.LLM_TEMPERATURE,
        "max_retries": 0,
    }
    if timeout is not None:
        kwargs["request_timeout"] = timeout
    llm = ChatOpenAI(**kwargs)

    call_kwargs: Dict[str, Any] = {}
    if max_output_tokens:
        call_kwargs["max_tokens"] = max_output_tokens
    if json_mode:
        call_kwargs["response_format"] = {"type": "json_object"}

    response = await llm.ainvoke(messages, **call_kwargs)
    metadata = getattr(response, "response_metadata", None) or {}
    extra = getattr(response, "additional_kwargs", None) or {}
    usage = metadata.get("token_usage") or getattr(response, "usage_metadata", None) or {}
    raw_content = getattr(response, "content", None)
    content, content_invalid = _extract_text(raw_content)
    finish_reason = metadata.get("finish_reason")
    model = metadata.get("model_name") or metadata.get("model")
    refusal = extra.get("refusal") or metadata.get("refusal")
    if isinstance(raw_content, list) and not refusal:
        for block in raw_content:
            if isinstance(block, dict) and block.get("type") == "refusal":
                refusal = block.get("refusal") or "模型拒绝返回内容"
                break

    return LLMResult(
        content=content,
        finish_reason=str(finish_reason) if finish_reason is not None else None,
        model=str(model) if model else None,
        input_tokens=_pick_int(usage, "prompt_tokens", "input_tokens"),
        output_tokens=_pick_int(usage, "completion_tokens", "output_tokens"),
        request_id=metadata.get("id"),
        refusal=str(refusal) if refusal else None,
        content_invalid=content_invalid,
    )


async def _invoke_via_relay(
    messages: List[Dict[str, str]],
    *,
    json_mode: bool,
    max_output_tokens: Optional[int],
    timeout: Optional[float],
    logical_call_id: Optional[str],
) -> LLMResult:
    """Relay 路径：OpenAI 兼容响应映射为 LLMResult，语义与直连一致。"""
    extra_body: Dict[str, Any] = {}
    if max_output_tokens:
        extra_body["max_tokens"] = max_output_tokens
    document = await platform_model_client.chat_completion(
        messages,
        json_mode=json_mode,
        timeout=timeout,
        logical_call_id=logical_call_id,
        extra_body=extra_body or None,
    )
    choices = document.get("choices") if isinstance(document, dict) else None
    choice = choices[0] if isinstance(choices, list) and choices else {}
    message = choice.get("message") if isinstance(choice, dict) else None
    raw_content = message.get("content") if isinstance(message, dict) else None
    content, content_invalid = _extract_text(raw_content)
    usage = document.get("usage") if isinstance(document.get("usage"), dict) else {}
    refusal = message.get("refusal") if isinstance(message, dict) else None
    return LLMResult(
        content=content,
        finish_reason=str(choice.get("finish_reason")) if choice.get("finish_reason") else None,
        model=str(document.get("model")) if document.get("model") else None,
        input_tokens=_pick_int(usage, "prompt_tokens", "input_tokens"),
        output_tokens=_pick_int(usage, "completion_tokens", "output_tokens"),
        request_id=document.get("id"),
        refusal=str(refusal) if refusal else None,
        content_invalid=content_invalid,
    )
