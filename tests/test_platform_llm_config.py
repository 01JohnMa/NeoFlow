import pytest

from config.settings import Settings


def test_litellm_pair_overrides_llm_and_sdk_defaults():
    settings = Settings(
        LLM_API_KEY="local-key", LLM_BASE_URL="http://local",
        SDK_API_KEY="sdk-key", SDK_BASE_URL="http://sdk",
        LITELLM_API_KEY="platform-key", LITELLM_BASE_URL="http://platform",
    )
    assert settings.llm_connection() == {"api_key": "platform-key", "base_url": "http://platform"}
    assert settings.llm_connection(sdk=True) == {"api_key": "platform-key", "base_url": "http://platform"}


def test_litellm_requires_both_values():
    settings = Settings(LITELLM_BASE_URL="http://platform")
    with pytest.raises(ValueError, match="configured together"):
        settings.llm_connection()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url,key,provider",
    [
        ("http://relay/v1", "relay-secret", "relay"),
        ("", "", "unconfigured"),
    ],
)
async def test_config_health_reports_mode_without_endpoints_or_credentials(monkeypatch, url, key, provider):
    import json
    from api.routes import health

    settings = Settings(
        _env_file=None,
        AI_CENTER_MODEL_GATEWAY_URL_TEMPLATE=url,
        AI_CENTER_RUNTIME_CREDENTIAL=key,
        AI_CENTER_MODEL_OPERATIONS="chat.completions" if url else "",
        LLM_BASE_URL="http://local/v1",
        LLM_API_KEY="local-secret",
    )
    monkeypatch.setattr(health, "settings", settings)
    result = await health.config_check()
    assert result["llm_provider"] == provider
    # readiness 只回显模式；不回显端点地址与任何凭据
    assert "llm_base_url" not in result
    dumped = json.dumps(result)
    assert "relay-secret" not in dumped
    assert "local-secret" not in dumped
    assert "http://relay/v1" not in dumped
    assert "http://local/v1" not in dumped
