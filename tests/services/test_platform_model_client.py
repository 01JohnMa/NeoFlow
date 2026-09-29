# tests/services/test_platform_model_client.py
"""平台模型客户端行为：模式判定、fail closed、Relay 请求形状与 logical call id。"""

from __future__ import annotations

import json

import httpx
import pytest

from config.settings import Settings
from services import platform_model_client
_REAL_ASYNC_CLIENT = httpx.AsyncClient
from services.platform_model_client import (
    PlatformModelError,
    bind_platform_invocation,
    chat_completion,
    current_invocation_id,
    model_access_mode,
    relay_openai_connection,
    text_embeddings,
)


def _relay_settings(**overrides) -> Settings:
    values = dict(
        _env_file=None,
        AI_CENTER_MODEL_GATEWAY_URL_TEMPLATE=(
            "http://platform:8001/api/v1/model-gateway/{invocation_id}/v1"
        ),
        AI_CENTER_RUNTIME_CREDENTIAL="arc-test-secret",
        AI_CENTER_MODEL_OPERATIONS="chat.completions,embeddings",
    )
    values.update(overrides)
    return Settings(**values)


def test_mode_is_unconfigured_without_platform_injection(monkeypatch):
    monkeypatch.setattr(platform_model_client, "settings", Settings(_env_file=None))
    assert model_access_mode() == "unconfigured"


def test_mode_is_relay_when_template_and_credential_present(monkeypatch):
    monkeypatch.setattr(platform_model_client, "settings", _relay_settings())
    assert model_access_mode() == "relay"


def test_mode_is_direct_only_when_explicitly_enabled(monkeypatch):
    monkeypatch.setattr(
        platform_model_client,
        "settings",
        Settings(_env_file=None, NEOFLOW_LLM_MODE="direct", LLM_API_KEY="local"),
    )
    assert model_access_mode() == "direct"


@pytest.mark.asyncio
async def test_relay_chat_requires_bound_invocation(monkeypatch):
    monkeypatch.setattr(platform_model_client, "settings", _relay_settings())
    with pytest.raises(PlatformModelError) as raised:
        await chat_completion([{"role": "user", "content": "hi"}])
    assert raised.value.reason == platform_model_client.REASON_INVOCATION_MISSING


@pytest.mark.asyncio
async def test_relay_chat_requires_operation_allowlist(monkeypatch):
    monkeypatch.setattr(
        platform_model_client,
        "settings",
        _relay_settings(AI_CENTER_MODEL_OPERATIONS="embeddings"),
    )
    token = bind_platform_invocation("invocation-1")
    try:
        with pytest.raises(PlatformModelError) as raised:
            await chat_completion([{"role": "user", "content": "hi"}])
        assert raised.value.reason == platform_model_client.REASON_UNAVAILABLE
    finally:
        platform_model_client.restore_platform_invocation(token)


class _RelayTransport(httpx.MockTransport):
    """记录请求并返回固定响应的 Relay 假上游。"""

    def __init__(self, response: httpx.Response) -> None:
        self.requests: list[httpx.Request] = []
        super().__init__(lambda request: self._handle(request, response))

    def _handle(self, request: httpx.Request, response: httpx.Response) -> httpx.Response:
        self.requests.append(request)
        return response


@pytest.mark.asyncio
async def test_relay_chat_builds_url_headers_and_stable_logical_id(monkeypatch):
    monkeypatch.setattr(platform_model_client, "settings", _relay_settings())
    transport = _RelayTransport(
        httpx.Response(
            200,
            json={
                "id": "resp-1",
                "model": "deepseek-v4-flash",
                "choices": [
                    {"finish_reason": "stop", "message": {"content": "{\"ok\":true}"}}
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 5},
            },
        )
    )

    def _fake_client(**kwargs):
        return _REAL_ASYNC_CLIENT(transport=transport, **kwargs)

    monkeypatch.setattr(platform_model_client.httpx, "AsyncClient", _fake_client)
    token = bind_platform_invocation("invocation-abc")
    try:
        first = await chat_completion(
            [{"role": "user", "content": "extract"}],
            json_mode=True,
            logical_call_id="job-1:unit:f1",
        )
        second = await chat_completion(
            [{"role": "user", "content": "extract"}],
            json_mode=True,
            logical_call_id="job-1:unit:f1",
        )
    finally:
        platform_model_client.restore_platform_invocation(token)

    assert first["choices"][0]["message"]["content"] == "{\"ok\":true}"
    assert second == first
    assert len(transport.requests) == 2
    request = transport.requests[0]
    # URL 按 invocation 寻址；凭据进 Authorization；logical call id 进 x-request-id
    assert (
        request.url == "http://platform:8001/api/v1/model-gateway/invocation-abc/v1/chat/completions"
    )
    assert request.headers["Authorization"] == "Bearer arc-test-secret"
    assert request.headers["x-request-id"] == "job-1:unit:f1"
    body = json.loads(request.content.decode("utf-8"))
    assert body["model"] == "deepseek-v4-flash"
    assert body["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_relay_embeddings_validates_vector_count(monkeypatch):
    monkeypatch.setattr(platform_model_client, "settings", _relay_settings())
    transport = _RelayTransport(
        httpx.Response(
            200,
            json={"data": [{"embedding": [0.1, 0.2]}, {"embedding": [0.3, 0.4]}]},
        )
    )

    def _fake_client(**kwargs):
        return _REAL_ASYNC_CLIENT(transport=transport, **kwargs)

    monkeypatch.setattr(platform_model_client.httpx, "AsyncClient", _fake_client)
    token = bind_platform_invocation("invocation-emb")
    try:
        vectors = await text_embeddings(["a", "b"])
    finally:
        platform_model_client.restore_platform_invocation(token)
    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert transport.requests[0].url.path.endswith("/v1/embeddings")

    # 数量不一致时明确失败
    transport2 = _RelayTransport(httpx.Response(200, json={"data": []}))

    def _fake_client2(**kwargs):
        return _REAL_ASYNC_CLIENT(transport=transport2, **kwargs)

    monkeypatch.setattr(platform_model_client.httpx, "AsyncClient", _fake_client2)
    token = bind_platform_invocation("invocation-emb2")
    try:
        with pytest.raises(PlatformModelError):
            await text_embeddings(["a"])
    finally:
        platform_model_client.restore_platform_invocation(token)


@pytest.mark.asyncio
async def test_relay_access_expired_maps_to_stable_reason(monkeypatch):
    monkeypatch.setattr(platform_model_client, "settings", _relay_settings())
    transport = _RelayTransport(
        httpx.Response(
            403,
            json={"error": {"code": "MODEL_ACCESS_EXPIRED", "message": "window closed"}},
        )
    )

    def _fake_client(**kwargs):
        return _REAL_ASYNC_CLIENT(transport=transport, **kwargs)

    monkeypatch.setattr(platform_model_client.httpx, "AsyncClient", _fake_client)
    token = bind_platform_invocation("invocation-old")
    try:
        with pytest.raises(PlatformModelError) as raised:
            await chat_completion([{"role": "user", "content": "x"}])
        assert raised.value.reason == platform_model_client.REASON_ACCESS_EXPIRED
    finally:
        platform_model_client.restore_platform_invocation(token)


def test_relay_openai_connection_resolves_bound_invocation(monkeypatch):
    monkeypatch.setattr(platform_model_client, "settings", _relay_settings())
    token = bind_platform_invocation("invocation-llama")
    try:
        connection = relay_openai_connection()
    finally:
        platform_model_client.restore_platform_invocation(token)
    assert connection == {
        "base_url": "http://platform:8001/api/v1/model-gateway/invocation-llama/v1",
        "api_key": "arc-test-secret",
    }


def test_unconfigured_mode_never_falls_back_to_litellm(monkeypatch):
    monkeypatch.setattr(
        platform_model_client,
        "settings",
        Settings(
            _env_file=None,
            LITELLM_BASE_URL="http://litellm-direct:4000",
            LITELLM_API_KEY="master-key",
        ),
    )
    assert model_access_mode() == "unconfigured"
    # llm_invoke 的 Relay 分支不会被选中；连接解析在 unconfigured 下返回 None
    assert relay_openai_connection() is None


def test_contextvar_binding_scopes_invocation():
    token = bind_platform_invocation("invocation-x")
    try:
        assert current_invocation_id() == "invocation-x"
        inner = bind_platform_invocation("invocation-y")
        try:
            assert current_invocation_id() == "invocation-y"
        finally:
            platform_model_client.restore_platform_invocation(inner)
        assert current_invocation_id() == "invocation-x"
    finally:
        platform_model_client.restore_platform_invocation(token)
    assert current_invocation_id() is None
