"""Lazy OpenAI Agents SDK loader.

The project already owns a top-level ``agents`` package for the document
workflow, while the OpenAI Agents SDK also imports as ``agents``. This loader
keeps production imports lazy and gives a clear error instead of breaking the
existing package at application startup.
"""

import importlib.metadata
import importlib.util
import json
import sys
from pathlib import Path


_OPENAI_AGENTS_MODULE = "_openai_agents_sdk"
_REQUIRED_EXPORTS = (
    "Agent",
    "Runner",
    "AsyncOpenAI",
    "OpenAIChatCompletionsModel",
    "ModelSettings",
)
_JSON_OBJECT_MAX_ATTEMPTS = 3
_JSON_OBJECT_MAX_TOKENS = 4096


class OpenAIAgentsSDKUnavailable(RuntimeError):
    pass


def load_agents_sdk():
    existing = sys.modules.get(_OPENAI_AGENTS_MODULE)
    if existing:
        _validate_agents_sdk(existing)
        return existing

    module = _load_agents_sdk_from_distribution()
    _validate_agents_sdk(module)
    return module


def _validate_agents_sdk(module):
    missing = [name for name in _REQUIRED_EXPORTS if not hasattr(module, name)]
    if missing:
        sys.modules.pop(_OPENAI_AGENTS_MODULE, None)
        raise OpenAIAgentsSDKUnavailable(
            "当前仓库的本地 agents 包遮蔽了 OpenAI Agents SDK；"
            "需要先解决 import name 冲突或在隔离环境中加载 SDK"
        )


def _load_agents_sdk_from_distribution():
    try:
        dist = importlib.metadata.distribution("openai-agents")
    except importlib.metadata.PackageNotFoundError as exc:
        raise OpenAIAgentsSDKUnavailable("OpenAI Agents SDK 未安装") from exc

    package_dir = Path(dist.locate_file("agents"))
    init_file = package_dir / "__init__.py"
    if not init_file.exists():
        raise OpenAIAgentsSDKUnavailable("OpenAI Agents SDK 包结构异常，找不到 agents/__init__.py")

    spec = importlib.util.spec_from_file_location(
        "_openai_agents_sdk",
        init_file,
        submodule_search_locations=[str(package_dir)],
    )
    if not spec or not spec.loader:
        raise OpenAIAgentsSDKUnavailable("OpenAI Agents SDK 加载失败")

    module = importlib.util.module_from_spec(spec)
    previous_agents_modules = _snapshot_agents_modules()
    sys.modules[_OPENAI_AGENTS_MODULE] = module
    sys.modules["agents"] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(_OPENAI_AGENTS_MODULE, None)
        raise
    finally:
        _restore_agents_modules(previous_agents_modules)
    return module


def _snapshot_agents_modules():
    return {
        name: module
        for name, module in sys.modules.items()
        if name == "agents" or name.startswith("agents.")
    }


def _restore_agents_modules(snapshot):
    current_agents_modules = [
        name for name in sys.modules if name == "agents" or name.startswith("agents.")
    ]
    for name in current_agents_modules:
        if name not in snapshot:
            sys.modules.pop(name, None)
    for name, module in snapshot.items():
        sys.modules[name] = module


async def run_structured_agent(
    *,
    name: str,
    instructions: str,
    prompt: str,
    output_type,
    model_profile=None,
):
    config = _merge_model_profile(get_model_config(), model_profile)
    if _uses_deepseek_json_object_mode(config):
        return await _run_json_object_agent(
            instructions=instructions,
            prompt=prompt,
            output_type=output_type,
            config=config,
        )

    try:
        return await _run_agent_once(
            name=name,
            instructions=instructions,
            prompt=prompt,
            output_type=output_type,
            structured=True,
            config=config,
        )
    except Exception as exc:
        if not _is_unsupported_response_format_error(exc):
            raise

    schema = output_type.model_json_schema() if hasattr(output_type, "model_json_schema") else {}
    fallback_prompt = (
        f"{prompt}\n\n"
        "请严格输出一个 JSON 对象，不要输出 Markdown 或解释文字。\n"
        f"JSON Schema:\n{json.dumps(schema, ensure_ascii=False)}"
    )
    raw_output = await _run_agent_once(
        name=name,
        instructions=(
            f"{instructions}\n\n"
            "当前模型不支持 response_format 结构化输出；请改为只返回可被 json.loads 解析的 JSON 对象。"
        ),
        prompt=fallback_prompt,
        output_type=None,
        structured=False,
        config=config,
    )
    return _validate_json_output(raw_output, output_type)


async def _run_json_object_agent(*, instructions: str, prompt: str, output_type, config: dict):
    agents_sdk = load_agents_sdk()
    client = agents_sdk.AsyncOpenAI(
        api_key=config["api_key"],
        base_url=config["base_url"],
    )
    messages = _build_json_object_messages(instructions, prompt, output_type)
    use_response_format = True

    for attempt in range(_JSON_OBJECT_MAX_ATTEMPTS):
        try:
            response = await _create_json_completion(
                client,
                config,
                messages,
                use_response_format=use_response_format,
            )
        except Exception as exc:
            if not use_response_format or not _is_unsupported_response_format_error(exc):
                raise
            use_response_format = False
            messages = _build_json_object_messages(
                instructions,
                prompt,
                output_type,
                retry_reason="当前模型接口不支持 response_format=json_object，已改用提示词 JSON 模式",
            )
            response = await _create_json_completion(
                client,
                config,
                messages,
                use_response_format=use_response_format,
            )

        raw_output, finish_reason = _extract_chat_completion_output(response)
        if finish_reason == "length":
            raise ValueError("模型 JSON 输出被 max_tokens 截断，请提高 max_tokens 或收窄输出 schema")
        try:
            if not raw_output.strip():
                raise ValueError("上一次输出为空")
            return _validate_json_output(raw_output, output_type)
        except Exception as exc:
            if attempt + 1 >= _JSON_OBJECT_MAX_ATTEMPTS:
                raise
            messages = _build_json_object_messages(
                instructions,
                prompt,
                output_type,
                retry_reason=str(exc),
            )


async def _create_json_completion(client, config: dict, messages: list[dict], *, use_response_format: bool):
    request = {
        "model": config["model"],
        "messages": messages,
        "max_tokens": _JSON_OBJECT_MAX_TOKENS,
    }
    if config.get("temperature") is not None:
        request["temperature"] = config["temperature"]
    if use_response_format:
        request["response_format"] = {"type": "json_object"}
    return await client.chat.completions.create(**request)


async def _run_agent_once(
    *, name: str, instructions: str, prompt: str, output_type, structured: bool, config: dict
):
    agents_sdk = load_agents_sdk()
    client = agents_sdk.AsyncOpenAI(
        api_key=config["api_key"],
        base_url=config["base_url"],
    )
    model = agents_sdk.OpenAIChatCompletionsModel(
        model=config["model"],
        openai_client=client,
    )
    model_settings_kwargs = {}
    if config.get("temperature") is not None:
        model_settings_kwargs["temperature"] = config["temperature"]
    agent_kwargs = {
        "name": name,
        "instructions": instructions,
        "model": model,
        "model_settings": agents_sdk.ModelSettings(**model_settings_kwargs),
    }
    if structured:
        agent_kwargs["output_type"] = output_type
    agent = agents_sdk.Agent(**agent_kwargs)
    result = await agents_sdk.Runner.run(agent, prompt)
    return result.final_output


def _build_json_object_messages(instructions: str, prompt: str, output_type, retry_reason: str | None = None):
    schema = output_type.model_json_schema() if hasattr(output_type, "model_json_schema") else {}
    example = _json_schema_example(schema)
    system_content = (
        f"{instructions}\n\n"
        "请只输出一个合法 JSON 对象，不要输出 Markdown、代码块或解释文字。\n"
        "输出必须能被 json.loads 解析，并且符合下面的 JSON Schema。\n"
        f"JSON Schema:\n{json.dumps(schema, ensure_ascii=False)}\n\n"
        f"EXAMPLE JSON OUTPUT:\n{json.dumps(example, ensure_ascii=False)}"
    )
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": prompt},
    ]
    if retry_reason:
        messages.append(
            {
                "role": "user",
                "content": (
                    f"上一次输出无法作为目标 JSON 使用，原因：{retry_reason}。\n"
                    "请重新只输出一个合法 JSON 对象。"
                ),
            }
        )
    return messages


def _json_schema_example(schema: dict, root_schema: dict | None = None):
    root_schema = root_schema or schema
    if "$ref" in schema:
        ref = schema["$ref"]
        if ref.startswith("#/$defs/"):
            definition_name = ref.rsplit("/", 1)[-1]
            definition = root_schema.get("$defs", {}).get(definition_name, {})
            return _json_schema_example(definition, root_schema)
    if "anyOf" in schema:
        options = [option for option in schema["anyOf"] if option.get("type") != "null"]
        return _json_schema_example(options[0], root_schema) if options else None

    schema_type = schema.get("type")
    if schema_type == "object" or "properties" in schema:
        return {
            key: _json_schema_example(value, root_schema)
            for key, value in schema.get("properties", {}).items()
        }
    if schema_type == "array":
        return [_json_schema_example(schema.get("items", {}), root_schema)]
    if schema_type == "string":
        return ""
    if schema_type in ("number", "integer"):
        return 0
    if schema_type == "boolean":
        return False
    return None


def _extract_chat_completion_output(response):
    choices = getattr(response, "choices", None) or []
    if not choices:
        return "", None
    choice = choices[0]
    message = getattr(choice, "message", None)
    content = getattr(message, "content", "") if message else ""
    if content is None:
        content = ""
    return str(content), getattr(choice, "finish_reason", None)


def _validate_json_output(raw_output: str, output_type):
    from agents.json_cleaner import parse_llm_json

    if not str(raw_output).strip():
        raise ValueError("模型未返回合法 JSON 对象")
    parsed = parse_llm_json(raw_output)
    if (
        isinstance(parsed, dict)
        and set(parsed) == {"raw_response"}
        and parsed["raw_response"] == str(raw_output).strip()
    ):
        raise ValueError("模型未返回合法 JSON 对象")
    if not isinstance(parsed, dict):
        raise ValueError("模型未返回合法 JSON 对象")
    if hasattr(output_type, "model_validate"):
        return output_type.model_validate(parsed)
    return parsed


def _uses_deepseek_json_object_mode(config: dict) -> bool:
    model = str(config.get("model") or "").lower()
    base_url = str(config.get("base_url") or "").lower()
    return model.startswith("deepseek") or "api.deepseek.com" in base_url


def _merge_model_profile(config: dict, model_profile) -> dict:
    if not model_profile:
        return dict(config)
    if hasattr(model_profile, "model_dump"):
        profile = model_profile.model_dump()
    else:
        profile = dict(model_profile)
    merged = dict(config)
    for key in ("model", "api_key", "base_url", "temperature"):
        value = profile.get(key)
        if value is not None and value != "":
            merged[key] = value
    return merged


def _is_unsupported_response_format_error(exc: Exception) -> bool:
    text_parts = [str(exc)]
    for attr in ("body", "response", "code", "param"):
        value = getattr(exc, attr, None)
        if value:
            text_parts.append(str(value))
    text = " ".join(text_parts).lower()
    status_code = getattr(exc, "status_code", None)
    unsupported_markers = (
        "unavailable",
        "unsupported",
        "not supported",
        "invalid_request_error",
        "invalid parameter",
        "invalid param",
        "not available",
    )
    return (
        ("response_format" in text or "response format" in text)
        and (status_code in (None, 400, 422))
        and any(marker in text for marker in unsupported_markers)
    )


def get_model_config():
    from sdk.config import get_sdk_model_config

    return get_sdk_model_config()
