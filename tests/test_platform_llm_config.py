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
