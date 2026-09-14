import pytest
from pydantic import ValidationError

from sdk.models import SDKModelProfile


def test_model_profile_rejects_partial_provider_override():
    with pytest.raises(ValidationError):
        SDKModelProfile(base_url="https://attacker.example/v1")

    with pytest.raises(ValidationError):
        SDKModelProfile(model="custom-model")

    with pytest.raises(ValidationError):
        SDKModelProfile(model="custom-model", api_key="secret")


def test_model_profile_allows_complete_provider_override():
    profile = SDKModelProfile(
        model="custom-model",
        base_url="https://provider.example/v1",
        api_key="secret",
        temperature=0.4,
    )

    assert profile.model == "custom-model"
    assert profile.base_url == "https://provider.example/v1"
    assert profile.api_key == "secret"


def test_model_profile_allows_temperature_only_override():
    profile = SDKModelProfile(temperature=0.1)

    assert profile.temperature == 0.1
    assert profile.model is None
