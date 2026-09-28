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
@pytest.mark.parametrize("url,key,provider", [("http://platform/v1", "platform-secret", "litellm"), ("", "", "direct")])
async def test_config_health_reports_effective_connection_without_credentials(monkeypatch, url, key, provider):
    import json
    from api.routes import health

    settings = Settings(_env_file=None, LITELLM_BASE_URL=url, LITELLM_API_KEY=key,
                        LLM_BASE_URL="http://local/v1", LLM_API_KEY="local-secret")
    monkeypatch.setattr(health, "settings", settings)
    result = await health.config_check()
    assert result["llm_provider"] == provider
    assert result["llm_base_url"] == (url or "http://local/v1")
    assert "platform-secret" not in json.dumps(result)
    assert "local-secret" not in json.dumps(result)
