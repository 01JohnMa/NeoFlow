import sys
import types

import pytest
from pydantic import BaseModel

from sdk import openai_agents_runtime as runtime


class FakeDistribution:
    def __init__(self, package_dir):
        self.package_dir = package_dir

    def locate_file(self, path):
        assert path == "agents"
        return self.package_dir


def test_load_agents_sdk_restores_local_agents_module(monkeypatch, tmp_path):
    package_dir = tmp_path / "agents"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text(
        "\n".join(
            [
                "from agents.model_settings import VALUE",
                "class Agent: pass",
                "class Runner: pass",
                "class AsyncOpenAI: pass",
                "class OpenAIChatCompletionsModel: pass",
                "class ModelSettings: pass",
            ]
        ),
        encoding="utf-8",
    )
    (package_dir / "model_settings.py").write_text("VALUE = 'sdk'\n", encoding="utf-8")

    local_agents = types.ModuleType("agents")
    local_agents.VALUE = "local"
    local_child = types.ModuleType("agents.workflow")

    monkeypatch.setitem(sys.modules, "agents", local_agents)
    monkeypatch.setitem(sys.modules, "agents.workflow", local_child)
    sys.modules.pop("_openai_agents_sdk", None)
    monkeypatch.delitem(sys.modules, "_openai_agents_sdk", raising=False)
    sys.modules.pop("agents.model_settings", None)
    monkeypatch.setattr(
        runtime.importlib.metadata,
        "distribution",
        lambda name: FakeDistribution(package_dir),
    )

    module = runtime.load_agents_sdk()

    assert module.VALUE == "sdk"
    assert module.Agent
    assert sys.modules["agents"] is local_agents
    assert sys.modules["agents.workflow"] is local_child
    assert "agents.model_settings" not in sys.modules
    assert sys.modules["_openai_agents_sdk"] is module


def test_load_agents_sdk_cleans_module_cache_after_import_failure(monkeypatch, tmp_path):
    package_dir = tmp_path / "agents"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text(
        "\n".join(
            [
                "from agents import transient",
                "raise RuntimeError('sdk import failed')",
            ]
        ),
        encoding="utf-8",
    )
    (package_dir / "transient.py").write_text("VALUE = 'sdk'\n", encoding="utf-8")

    local_agents = types.ModuleType("agents")
    local_child = types.ModuleType("agents.workflow")

    monkeypatch.setitem(sys.modules, "agents", local_agents)
    monkeypatch.setitem(sys.modules, "agents.workflow", local_child)
    sys.modules.pop("_openai_agents_sdk", None)
    sys.modules.pop("agents.transient", None)
    monkeypatch.setattr(
        runtime.importlib.metadata,
        "distribution",
        lambda name: FakeDistribution(package_dir),
    )

    with pytest.raises(RuntimeError, match="sdk import failed"):
        runtime.load_agents_sdk()

    assert sys.modules["agents"] is local_agents
    assert sys.modules["agents.workflow"] is local_child
    assert "agents.transient" not in sys.modules
    assert "_openai_agents_sdk" not in sys.modules


def test_load_agents_sdk_drops_cache_when_required_exports_missing(monkeypatch, tmp_path):
    package_dir = tmp_path / "agents"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text(
        "class Agent: pass\n",
        encoding="utf-8",
    )

    local_agents = types.ModuleType("agents")

    monkeypatch.setitem(sys.modules, "agents", local_agents)
    sys.modules.pop("_openai_agents_sdk", None)
    monkeypatch.setattr(
        runtime.importlib.metadata,
        "distribution",
        lambda name: FakeDistribution(package_dir),
    )

    with pytest.raises(runtime.OpenAIAgentsSDKUnavailable):
        runtime.load_agents_sdk()

    assert sys.modules["agents"] is local_agents
    assert "_openai_agents_sdk" not in sys.modules


def test_load_agents_sdk_drops_invalid_existing_cache(monkeypatch):
    local_agents = types.ModuleType("agents")
    local_child = types.ModuleType("agents.workflow")
    invalid_sdk = types.ModuleType("_openai_agents_sdk")
    invalid_sdk.Agent = object

    monkeypatch.setitem(sys.modules, "agents", local_agents)
    monkeypatch.setitem(sys.modules, "agents.workflow", local_child)
    monkeypatch.setitem(sys.modules, "_openai_agents_sdk", invalid_sdk)

    with pytest.raises(runtime.OpenAIAgentsSDKUnavailable):
        runtime.load_agents_sdk()

    assert sys.modules["agents"] is local_agents
    assert sys.modules["agents.workflow"] is local_child
    assert "_openai_agents_sdk" not in sys.modules


def test_run_structured_agent_uses_sdk_model_settings(monkeypatch):
    class FakeModelSettings:
        pass

    class FakeAsyncOpenAI:
        def __init__(self, *, api_key, base_url):
            self.api_key = api_key
            self.base_url = base_url

    class FakeOpenAIChatCompletionsModel:
        def __init__(self, *, model, openai_client):
            self.model = model
            self.openai_client = openai_client

    class FakeAgent:
        def __init__(self, *, name, instructions, model, model_settings, output_type):
            assert name == "Analyzer"
            assert instructions == "instructions"
            assert model.model == "test-model"
            assert isinstance(model_settings, FakeModelSettings)
            assert output_type is dict

    class FakeRunner:
        @staticmethod
        async def run(agent, prompt):
            assert prompt == "prompt"
            return types.SimpleNamespace(final_output={"ok": True})

    fake_sdk = types.ModuleType("_openai_agents_sdk")
    fake_sdk.Agent = FakeAgent
    fake_sdk.Runner = FakeRunner
    fake_sdk.AsyncOpenAI = FakeAsyncOpenAI
    fake_sdk.OpenAIChatCompletionsModel = FakeOpenAIChatCompletionsModel
    fake_sdk.ModelSettings = FakeModelSettings

    monkeypatch.setitem(sys.modules, "_openai_agents_sdk", fake_sdk)
    monkeypatch.setattr(
        runtime,
        "get_model_config",
        lambda: {"api_key": "test-key", "base_url": "https://example.test/v1", "model": "test-model"},
    )

    import asyncio

    result = asyncio.run(
        runtime.run_structured_agent(
            name="Analyzer",
            instructions="instructions",
            prompt="prompt",
            output_type=dict,
        )
    )

    assert result == {"ok": True}


def test_run_structured_agent_allows_per_request_model_profile(monkeypatch):
    captured = {}

    class FakeModelSettings:
        def __init__(self, **kwargs):
            captured["model_settings"] = kwargs

    class FakeAsyncOpenAI:
        def __init__(self, *, api_key, base_url):
            captured["api_key"] = api_key
            captured["base_url"] = base_url

    class FakeOpenAIChatCompletionsModel:
        def __init__(self, *, model, openai_client):
            captured["model"] = model

    class FakeAgent:
        def __init__(self, *, name, instructions, model, model_settings, output_type):
            assert output_type is dict

    class FakeRunner:
        @staticmethod
        async def run(agent, prompt):
            return types.SimpleNamespace(final_output={"ok": True})

    fake_sdk = types.ModuleType("_openai_agents_sdk")
    fake_sdk.Agent = FakeAgent
    fake_sdk.Runner = FakeRunner
    fake_sdk.AsyncOpenAI = FakeAsyncOpenAI
    fake_sdk.OpenAIChatCompletionsModel = FakeOpenAIChatCompletionsModel
    fake_sdk.ModelSettings = FakeModelSettings

    monkeypatch.setitem(sys.modules, "_openai_agents_sdk", fake_sdk)
    monkeypatch.setattr(
        runtime,
        "get_model_config",
        lambda: {
            "api_key": "default-key",
            "base_url": "https://default.test/v1",
            "model": "default-model",
            "temperature": 0.1,
        },
    )

    import asyncio

    result = asyncio.run(
        runtime.run_structured_agent(
            name="Analyzer",
            instructions="instructions",
            prompt="prompt",
            output_type=dict,
            model_profile={
                "api_key": "override-key",
                "base_url": "https://override.test/v1",
                "model": "override-model",
                "temperature": 0.7,
            },
        )
    )

    assert result == {"ok": True}
    assert captured == {
        "api_key": "override-key",
        "base_url": "https://override.test/v1",
        "model": "override-model",
        "model_settings": {"temperature": 0.7},
    }


def test_run_structured_agent_falls_back_when_response_format_is_unsupported(monkeypatch):
    class Output(BaseModel):
        ok: bool

    class BadRequestError(Exception):
        status_code = 400

    class FakeModelSettings:
        pass

    class FakeAsyncOpenAI:
        def __init__(self, *, api_key, base_url):
            self.api_key = api_key
            self.base_url = base_url

    class FakeOpenAIChatCompletionsModel:
        def __init__(self, *, model, openai_client):
            self.model = model
            self.openai_client = openai_client

    class FakeAgent:
        def __init__(self, *, name, instructions, model, model_settings, output_type=None):
            self.output_type = output_type
            assert isinstance(model_settings, FakeModelSettings)

    calls = []

    class FakeRunner:
        @staticmethod
        async def run(agent, prompt):
            calls.append((agent.output_type, prompt))
            if agent.output_type is Output:
                raise BadRequestError("response_format is not supported by this model")
            assert "JSON Schema:" in prompt
            return types.SimpleNamespace(final_output='{"ok": true}')

    fake_sdk = types.ModuleType("_openai_agents_sdk")
    fake_sdk.Agent = FakeAgent
    fake_sdk.Runner = FakeRunner
    fake_sdk.AsyncOpenAI = FakeAsyncOpenAI
    fake_sdk.OpenAIChatCompletionsModel = FakeOpenAIChatCompletionsModel
    fake_sdk.ModelSettings = FakeModelSettings

    monkeypatch.setitem(sys.modules, "_openai_agents_sdk", fake_sdk)
    monkeypatch.setattr(
        runtime,
        "get_model_config",
        lambda: {"api_key": "test-key", "base_url": "https://example.test/v1", "model": "test-model"},
    )

    import asyncio

    result = asyncio.run(
        runtime.run_structured_agent(
            name="Analyzer",
            instructions="instructions",
            prompt="prompt",
            output_type=Output,
        )
    )

    assert result == Output(ok=True)
    assert calls[0][0] is Output
    assert calls[1][0] is None


def test_run_structured_agent_uses_deepseek_json_object_mode(monkeypatch):
    class Output(BaseModel):
        ok: bool

    class FakeMessage:
        content = '{"ok": true}'

    class FakeChoice:
        message = FakeMessage()
        finish_reason = "stop"

    class FakeChatCompletions:
        def __init__(self):
            self.calls = []

        async def create(self, **kwargs):
            self.calls.append(kwargs)
            return types.SimpleNamespace(choices=[FakeChoice()])

    class FakeAsyncOpenAI:
        completions = FakeChatCompletions()

        def __init__(self, *, api_key, base_url):
            self.api_key = api_key
            self.base_url = base_url
            self.chat = types.SimpleNamespace(completions=self.completions)

    class FakeAgent:
        def __init__(self, **kwargs):
            raise AssertionError("DeepSeek JSON mode should not construct an Agent")

    fake_sdk = types.ModuleType("_openai_agents_sdk")
    fake_sdk.Agent = FakeAgent
    fake_sdk.Runner = object
    fake_sdk.AsyncOpenAI = FakeAsyncOpenAI
    fake_sdk.OpenAIChatCompletionsModel = object
    fake_sdk.ModelSettings = object

    monkeypatch.setitem(sys.modules, "_openai_agents_sdk", fake_sdk)
    monkeypatch.setattr(
        runtime,
        "get_model_config",
        lambda: {
            "api_key": "test-key",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-v4-flash",
            "temperature": 0.2,
        },
    )

    import asyncio

    result = asyncio.run(
        runtime.run_structured_agent(
            name="Analyzer",
            instructions="instructions",
            prompt="prompt",
            output_type=Output,
        )
    )

    call = FakeAsyncOpenAI.completions.calls[0]
    assert result == Output(ok=True)
    assert call["response_format"] == {"type": "json_object"}
    assert call["model"] == "deepseek-v4-flash"
    assert call["temperature"] == 0.2
    assert "JSON Schema:" in call["messages"][0]["content"]
    assert "EXAMPLE JSON OUTPUT:" in call["messages"][0]["content"]


def test_deepseek_json_object_mode_omits_null_temperature(monkeypatch):
    class Output(BaseModel):
        ok: bool

    class FakeChatCompletions:
        def __init__(self):
            self.calls = []

        async def create(self, **kwargs):
            self.calls.append(kwargs)
            message = types.SimpleNamespace(content='{"ok": true}')
            choice = types.SimpleNamespace(message=message, finish_reason="stop")
            return types.SimpleNamespace(choices=[choice])

    class FakeAsyncOpenAI:
        completions = FakeChatCompletions()

        def __init__(self, *, api_key, base_url):
            self.api_key = api_key
            self.base_url = base_url
            self.chat = types.SimpleNamespace(completions=self.completions)

    fake_sdk = types.ModuleType("_openai_agents_sdk")
    fake_sdk.Agent = object
    fake_sdk.Runner = object
    fake_sdk.AsyncOpenAI = FakeAsyncOpenAI
    fake_sdk.OpenAIChatCompletionsModel = object
    fake_sdk.ModelSettings = object

    monkeypatch.setitem(sys.modules, "_openai_agents_sdk", fake_sdk)
    monkeypatch.setattr(
        runtime,
        "get_model_config",
        lambda: {
            "api_key": "test-key",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-chat",
            "temperature": None,
        },
    )

    import asyncio

    result = asyncio.run(
        runtime.run_structured_agent(
            name="Analyzer",
            instructions="instructions",
            prompt="prompt",
            output_type=Output,
        )
    )

    assert result == Output(ok=True)
    assert "temperature" not in FakeAsyncOpenAI.completions.calls[0]


def test_run_structured_agent_retries_empty_deepseek_json_content(monkeypatch):
    class Output(BaseModel):
        ok: bool

    class FakeChatCompletions:
        def __init__(self):
            self.calls = []

        async def create(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                message = types.SimpleNamespace(content="")
            else:
                message = types.SimpleNamespace(content='{"ok": true}')
            choice = types.SimpleNamespace(message=message, finish_reason="stop")
            return types.SimpleNamespace(choices=[choice])

    class FakeAsyncOpenAI:
        completions = FakeChatCompletions()

        def __init__(self, *, api_key, base_url):
            self.api_key = api_key
            self.base_url = base_url
            self.chat = types.SimpleNamespace(completions=self.completions)

    fake_sdk = types.ModuleType("_openai_agents_sdk")
    fake_sdk.Agent = object
    fake_sdk.Runner = object
    fake_sdk.AsyncOpenAI = FakeAsyncOpenAI
    fake_sdk.OpenAIChatCompletionsModel = object
    fake_sdk.ModelSettings = object

    monkeypatch.setitem(sys.modules, "_openai_agents_sdk", fake_sdk)
    monkeypatch.setattr(
        runtime,
        "get_model_config",
        lambda: {
            "api_key": "test-key",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-chat",
            "temperature": 0.2,
        },
    )

    import asyncio

    result = asyncio.run(
        runtime.run_structured_agent(
            name="Analyzer",
            instructions="instructions",
            prompt="prompt",
            output_type=Output,
        )
    )

    assert result == Output(ok=True)
    assert len(FakeAsyncOpenAI.completions.calls) == 2
    assert "上一次输出为空" in FakeAsyncOpenAI.completions.calls[1]["messages"][-1]["content"]


def test_run_structured_agent_falls_back_when_deepseek_json_object_is_unsupported(monkeypatch):
    class Output(BaseModel):
        ok: bool

    class APIStatusError(Exception):
        status_code = 422

    class FakeChatCompletions:
        def __init__(self):
            self.calls = []

        async def create(self, **kwargs):
            self.calls.append(kwargs)
            if "response_format" in kwargs:
                raise APIStatusError("invalid parameter: response_format json_object unsupported")
            message = types.SimpleNamespace(content='{"ok": true}')
            choice = types.SimpleNamespace(message=message, finish_reason="stop")
            return types.SimpleNamespace(choices=[choice])

    class FakeAsyncOpenAI:
        completions = FakeChatCompletions()

        def __init__(self, *, api_key, base_url):
            self.api_key = api_key
            self.base_url = base_url
            self.chat = types.SimpleNamespace(completions=self.completions)

    fake_sdk = types.ModuleType("_openai_agents_sdk")
    fake_sdk.Agent = object
    fake_sdk.Runner = object
    fake_sdk.AsyncOpenAI = FakeAsyncOpenAI
    fake_sdk.OpenAIChatCompletionsModel = object
    fake_sdk.ModelSettings = object

    monkeypatch.setitem(sys.modules, "_openai_agents_sdk", fake_sdk)
    monkeypatch.setattr(
        runtime,
        "get_model_config",
        lambda: {
            "api_key": "test-key",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-chat",
            "temperature": 0.2,
        },
    )

    import asyncio

    result = asyncio.run(
        runtime.run_structured_agent(
            name="Analyzer",
            instructions="instructions",
            prompt="prompt",
            output_type=Output,
        )
    )

    assert result == Output(ok=True)
    assert FakeAsyncOpenAI.completions.calls[0]["response_format"] == {"type": "json_object"}
    assert "response_format" not in FakeAsyncOpenAI.completions.calls[1]


def test_validate_json_output_rejects_unparseable_dict_output():
    with pytest.raises(ValueError, match="模型未返回合法 JSON 对象"):
        runtime._validate_json_output("not json", dict)


def test_deepseek_json_object_unsupported_then_empty_content_retries_without_response_format(monkeypatch):
    class Output(BaseModel):
        ok: bool

    class APIStatusError(Exception):
        status_code = 400

    class FakeChatCompletions:
        def __init__(self):
            self.calls = []

        async def create(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                raise APIStatusError("This response_format type is unavailable now")
            content = "" if len(self.calls) == 2 else '{"ok": true}'
            message = types.SimpleNamespace(content=content)
            choice = types.SimpleNamespace(message=message, finish_reason="stop")
            return types.SimpleNamespace(choices=[choice])

    class FakeAsyncOpenAI:
        completions = FakeChatCompletions()

        def __init__(self, *, api_key, base_url):
            self.api_key = api_key
            self.base_url = base_url
            self.chat = types.SimpleNamespace(completions=self.completions)

    fake_sdk = types.ModuleType("_openai_agents_sdk")
    fake_sdk.Agent = object
    fake_sdk.Runner = object
    fake_sdk.AsyncOpenAI = FakeAsyncOpenAI
    fake_sdk.OpenAIChatCompletionsModel = object
    fake_sdk.ModelSettings = object

    monkeypatch.setitem(sys.modules, "_openai_agents_sdk", fake_sdk)
    monkeypatch.setattr(
        runtime,
        "get_model_config",
        lambda: {
            "api_key": "test-key",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-chat",
            "temperature": 0.2,
        },
    )

    import asyncio

    result = asyncio.run(
        runtime.run_structured_agent(
            name="Analyzer",
            instructions="instructions",
            prompt="prompt",
            output_type=Output,
        )
    )

    assert result == Output(ok=True)
    assert FakeAsyncOpenAI.completions.calls[0]["response_format"] == {"type": "json_object"}
    assert "response_format" not in FakeAsyncOpenAI.completions.calls[1]
    assert "response_format" not in FakeAsyncOpenAI.completions.calls[2]
    assert "上一次输出为空" in FakeAsyncOpenAI.completions.calls[2]["messages"][-1]["content"]
