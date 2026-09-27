"""OpenAI Agents SDK configuration helpers."""

from config.settings import settings


def get_sdk_model_config() -> dict:
    return {
        "model": settings.SDK_MODEL_ID or settings.LLM_MODEL_ID,
        **settings.llm_connection(sdk=True),
        "temperature": settings.SDK_TEMPERATURE,
    }
