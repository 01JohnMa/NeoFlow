# services/platform_model_client.py
"""NeoFlow 唯一的平台模型入口：经 AI Center Model Gateway Relay。

平台部署注入三元组（见 ai-center 发布合同）：

- ``AI_CENTER_MODEL_GATEWAY_URL_TEMPLATE``：形如
  ``http://<platform>/api/v1/model-gateway/{invocation_id}/v1``；
- ``AI_CENTER_RUNTIME_CREDENTIAL``：per-Deployment Relay 凭据；
- ``AI_CENTER_MODEL_OPERATIONS``：允许的 operation 白名单（逗号分隔）。

行为约定：

- Relay 模式（模板+凭据齐备）是平台唯一模式：chat 与文本 embedding 都经
  Relay 发出，归因（schema v2、session id、traceparent）由平台注入；
- 未配置时 fail closed：任何模型调用返回 ``MODEL_CAPABILITY_UNAVAILABLE``，
  绝不回退直连 LiteLLM；
- 本地 direct 模式必须显式 ``NEOFLOW_LLM_MODE=direct``，仅供开发/测试，
  不得进入平台部署（平台从不注入该变量，ai-center.yaml 也不声明它）；
- invocation 通过 :func:`bind_platform_invocation` 在 Job 执行期间绑定；
  Relay 模式下没有绑定的模型调用直接失败（模型归因不可缺）；
- ``logical_call_id`` 承载稳定的逻辑调用标识（经 x-request-id 透传），
  同一逻辑调用的重试必须复用同一 id，避免重复记账。
"""

from __future__ import annotations

import hashlib
from contextvars import ContextVar, Token
from typing import Any, Dict, List, Optional, Sequence

import httpx
from config.settings import settings
from loguru import logger

_CURRENT_INVOCATION: ContextVar[Optional[str]] = ContextVar(
    "platform_model_invocation", default=None
)

REASON_UNAVAILABLE = "MODEL_CAPABILITY_UNAVAILABLE"
REASON_INVOCATION_MISSING = "MODEL_INVOCATION_MISSING"
REASON_ACCESS_EXPIRED = "MODEL_ACCESS_EXPIRED"
REASON_TIMEOUT = "MODEL_TIMEOUT"
REASON_UPSTREAM = "MODEL_UPSTREAM_ERROR"


class PlatformModelError(RuntimeError):
    """稳定的平台模型访问失败；reason 进入 Job 错误，不泄漏上游细节。"""

    def __init__(self, reason: str, message: str, status: Optional[int] = None) -> None:
        super().__init__(message)
        self.reason = reason
        self.status = status


def model_access_mode(config=None) -> str:
    """``relay`` / ``direct`` / ``unconfigured``；绝不猜测或回退。

    ``config`` 允许调用方（如 health 检查）传入显式 Settings 实例；
    默认使用进程级 settings 单例。
    """
    effective = config if config is not None else settings
    if (
        effective.AI_CENTER_MODEL_GATEWAY_URL_TEMPLATE.strip()
        and effective.AI_CENTER_RUNTIME_CREDENTIAL.strip()
    ):
        return "relay"
    if effective.NEOFLOW_LLM_MODE.strip().lower() == "direct":
        return "direct"
    return "unconfigured"


def bind_platform_invocation(invocation_id: Optional[str]) -> Token:
    """绑定当前异步任务的平台父 Invocation 引用。"""
    return _CURRENT_INVOCATION.set(invocation_id.strip() if invocation_id else None)


def restore_platform_invocation(token: Token) -> None:
    _CURRENT_INVOCATION.reset(token)


def current_invocation_id() -> Optional[str]:
    return _CURRENT_INVOCATION.get()


def _allowed_operations() -> frozenset[str]:
    raw = settings.AI_CENTER_MODEL_OPERATIONS.strip()
    if not raw:
        # 平台未注入白名单时视为不允许任何 operation（fail closed）。
        return frozenset()
    return frozenset(item.strip() for item in raw.split(",") if item.strip())


def _relay_endpoint(invocation_id: str, operation_path: str) -> str:
    template = settings.AI_CENTER_MODEL_GATEWAY_URL_TEMPLATE.strip()
    base = template.replace("{invocation_id}", invocation_id).rstrip("/")
    return f"{base}/{operation_path.lstrip('/')}"


def _require_relay(operation: str) -> str:
    """校验 Relay 模式与 operation 白名单，返回当前 invocation id。"""
    if model_access_mode() != "relay":
        raise PlatformModelError(
            REASON_UNAVAILABLE,
            "平台模型访问未配置 Relay（AI Center 模板/凭据缺失），且未启用本地 direct 模式",
        )
    if operation not in _allowed_operations():
        raise PlatformModelError(
            REASON_UNAVAILABLE,
            f"operation 不在平台允许的白名单内: {operation}",
        )
    invocation_id = current_invocation_id()
    if not invocation_id:
        raise PlatformModelError(
            REASON_INVOCATION_MISSING,
            "Relay 模式下模型调用缺少平台 Invocation 引用（Job 未保存或未绑定）",
        )
    return invocation_id


def _stable_logical_id(invocation_id: str, scope: str, payload: str) -> str:
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return f"{invocation_id}:{scope}:{digest}"


def _error_from_response(status: int, body: str) -> PlatformModelError:
    code = ""
    try:
        import json

        document = json.loads(body) if body else {}
        code = str(((document or {}).get("error") or {}).get("code") or "")
    except Exception:  # noqa: BLE001 - 错误体不是 JSON 时按非 2xx 处理
        code = ""
    if code == "MODEL_ACCESS_EXPIRED" or status == 403 and "expired" in body.lower():
        return PlatformModelError(REASON_ACCESS_EXPIRED, "平台模型访问窗口已过期", status)
    if code == "MODEL_GATEWAY_UNAUTHORIZED" or status == 401:
        return PlatformModelError(REASON_UPSTREAM, "Relay 凭据无效或已吊销", status)
    return PlatformModelError(REASON_UPSTREAM, f"Relay 返回非成功状态: {status}", status)


async def chat_completion(
    messages: Sequence[Dict[str, Any]],
    *,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    json_mode: bool = False,
    timeout: Optional[float] = None,
    logical_call_id: Optional[str] = None,
    extra_body: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """一次 Chat 调用，返回 OpenAI chat/completions 响应 JSON（dict）。"""
    invocation_id = _require_relay("chat.completions")
    prompt_text = "\n".join(str(m.get("content") or "") for m in messages)
    call_id = logical_call_id or _stable_logical_id(invocation_id, "chat", prompt_text)
    payload: Dict[str, Any] = {
        "model": model or settings.LLM_MODEL_ID,
        "messages": list(messages),
        "temperature": settings.LLM_TEMPERATURE if temperature is None else temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    if extra_body:
        payload.update(extra_body)
    return await _post_relay(
        invocation_id, "chat/completions", call_id, payload, timeout=timeout
    )


async def text_embeddings(
    inputs: Sequence[str],
    *,
    model: Optional[str] = None,
    dimensions: Optional[int] = None,
    timeout: Optional[float] = None,
    logical_call_id: Optional[str] = None,
) -> List[List[float]]:
    """文本 Embedding；返回与输入顺序一致的向量列表。"""
    invocation_id = _require_relay("embeddings")
    call_id = logical_call_id or _stable_logical_id(
        invocation_id, "emb", "\n".join(inputs)
    )
    payload: Dict[str, Any] = {
        "model": model or settings.EMBEDDING_MODEL,
        "input": list(inputs),
    }
    if dimensions:
        payload["dimensions"] = int(dimensions)
    document = await _post_relay(
        invocation_id, "embeddings", call_id, payload, timeout=timeout
    )
    data = document.get("data") if isinstance(document, dict) else None
    if not isinstance(data, list) or len(data) != len(inputs):
        raise PlatformModelError(REASON_UPSTREAM, "Embedding 响应与输入数量不一致")
    vectors: List[List[float]] = []
    for item in data:
        vector = item.get("embedding") if isinstance(item, dict) else None
        if not isinstance(vector, list) or not vector:
            raise PlatformModelError(REASON_UPSTREAM, "Embedding 响应缺少向量")
        vectors.append([float(x) for x in vector])
    return vectors


async def _post_relay(
    invocation_id: str,
    operation_path: str,
    logical_call_id: str,
    payload: Dict[str, Any],
    *,
    timeout: Optional[float],
) -> Dict[str, Any]:
    endpoint = _relay_endpoint(invocation_id, operation_path)
    headers = {
        "Authorization": f"Bearer {settings.AI_CENTER_RUNTIME_CREDENTIAL.strip()}",
        "Content-Type": "application/json",
        "x-request-id": logical_call_id,
    }
    request_timeout = timeout if timeout and timeout > 0 else min(
        120.0, float(settings.EXTRACT_TIMEOUT_SECONDS)
    )
    try:
        async with httpx.AsyncClient(timeout=request_timeout) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
    except httpx.TimeoutException as exc:
        raise PlatformModelError(REASON_TIMEOUT, "平台模型请求超时") from exc
    except httpx.HTTPError as exc:
        raise PlatformModelError(REASON_UPSTREAM, f"平台模型请求失败: {exc}") from exc
    if response.status_code < 200 or response.status_code >= 300:
        raise _error_from_response(response.status_code, response.text)
    try:
        return response.json()
    except ValueError as exc:
        raise PlatformModelError(REASON_UPSTREAM, "平台模型响应不是 JSON") from exc


def relay_openai_connection() -> Optional[Dict[str, str]]:
    """OpenAI 兼容客户端（llama_index/ChatOpenAI）的 Relay 连接参数。

    Relay 模式且已绑定 Invocation 时返回 ``{"base_url", "api_key"}``；
    否则返回 None，由调用方走本地 direct 连接。
    """
    if model_access_mode() != "relay":
        return None
    invocation_id = current_invocation_id()
    if not invocation_id:
        raise PlatformModelError(
            REASON_INVOCATION_MISSING,
            "Relay 模式下模型客户端构造缺少平台 Invocation 引用",
        )
    base_url = (
        settings.AI_CENTER_MODEL_GATEWAY_URL_TEMPLATE.strip()
        .replace("{invocation_id}", invocation_id)
        .rstrip("/")
    )
    logger.debug(f"平台模型客户端经 Relay: invocation={invocation_id}")
    return {"base_url": base_url, "api_key": settings.AI_CENTER_RUNTIME_CREDENTIAL.strip()}
