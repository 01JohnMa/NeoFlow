from types import SimpleNamespace

import pytest

from services import llm_invoke


class FakeChatOpenAI:
    response = None
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.__class__.instances.append(self)

    async def ainvoke(self, messages, **kwargs):
        self.call = (messages, kwargs)
        return self.__class__.response


@pytest.mark.asyncio
async def test_unknown_content_block_is_not_silently_dropped(monkeypatch):
    FakeChatOpenAI.response = SimpleNamespace(
        content=[
            {"type": "text", "text": '{"ok": true}'},
            {"type": "image", "image_url": "https://example.test/image"},
        ],
        response_metadata={"finish_reason": "stop", "model_name": "fake"},
        additional_kwargs={},
    )
    FakeChatOpenAI.instances = []
    monkeypatch.setattr(llm_invoke, "ChatOpenAI", FakeChatOpenAI)

    result = await llm_invoke.invoke_llm([{"role": "user", "content": "x"}], timeout=2)

    assert result.content == '{"ok": true}'
    assert result.content_invalid is True
    assert FakeChatOpenAI.instances[0].kwargs["max_retries"] == 0
    assert FakeChatOpenAI.instances[0].kwargs["request_timeout"] == 2


@pytest.mark.asyncio
async def test_refusal_content_block_is_classified_before_json_repair(monkeypatch):
    FakeChatOpenAI.response = SimpleNamespace(
        content=[{"type": "refusal", "refusal": "policy refusal"}],
        response_metadata={"finish_reason": "stop"},
        additional_kwargs={},
    )
    FakeChatOpenAI.instances = []
    monkeypatch.setattr(llm_invoke, "ChatOpenAI", FakeChatOpenAI)

    result = await llm_invoke.invoke_llm([{"role": "user", "content": "x"}])

    assert result.refusal == "policy refusal"
    assert result.content_invalid is True
