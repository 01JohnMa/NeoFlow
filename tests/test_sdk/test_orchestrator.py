import pytest

from unittest.mock import AsyncMock

from services.extract_configuration import validate_extract_definition
from sdk.agents.orchestrator import SDKOrchestrator
from sdk.models import (
    ConfirmTemplateRequest,
    DocumentAnalysis,
    SDKModelProfile,
    SDKSession,
    SDKSessionState,
)


def _build_session(**overrides) -> SDKSession:
    payload = {
        "id": "session-1",
        "file_name": "scan.jpg",
        "file_path": "/tmp/scan.jpg",
        "tenant_id": "tenant-1",
        "template_name": "检测报告",
        "template_code": "inspection_report",
        "document_id": "doc-1",
        "parse_job_id": "job-1",
        "user_id": "11111111-1111-4111-8111-111111111111",
        "state": SDKSessionState.PARSED,
        "created_at": 1000,
        "updated_at": 1000,
    }
    payload.update(overrides)
    return SDKSession(**payload)


@pytest.mark.asyncio
async def test_analyze_uses_parse_markdown(monkeypatch):
    captured = {}

    async def fake_run_doc_analyzer(*, parse_text, file_name, instruction, model_profile=None):
        captured["parse_text"] = parse_text
        captured["file_name"] = file_name
        captured["instruction"] = instruction
        captured["model_profile"] = model_profile
        return DocumentAnalysis(
            detected_fields=[
                {"field_key": "sample_name", "field_label": "样品名称", "field_type": "text"}
            ],
        )

    monkeypatch.setattr("sdk.agents.orchestrator.run_doc_analyzer", fake_run_doc_analyzer)

    analysis = await SDKOrchestrator().analyze_document(
        _build_session(file_name="report.pdf", instruction="关注样品名称与结论"),
        "# 解析结果\n样品名称：小型断路器",
    )

    assert captured["parse_text"].startswith("# 解析结果")
    assert captured["file_name"] == "report.pdf"
    assert captured["instruction"] == "关注样品名称与结论"
    assert [field.field_key for field in analysis.detected_fields] == ["sample_name"]


@pytest.mark.asyncio
async def test_commit_creates_schema_draft_without_publishing(monkeypatch):
    create = AsyncMock(return_value={"id": "config-1", "status": "draft", "tenant_id": "tenant-1"})
    publish = AsyncMock()
    monkeypatch.setattr("sdk.agents.orchestrator.configuration_service.create_configuration", create)
    monkeypatch.setattr("sdk.agents.orchestrator.configuration_service.publish_configuration", publish)
    session = _build_session(
        parse_mode="vlm",
        state=SDKSessionState.TEMPLATE_CONFIRMED,
        confirmed_template=ConfirmTemplateRequest(
            template_name="出货单", template_code="shipment_report",
            fields=[{
                "field_key": "order_no", "field_label": "订单号", "field_type": "text",
                "extraction_hint": "从订单号标签后提取", "sample_value": "NOZS0311046",
            }],
        ),
        prompt="仅从订单号标签后的原文提取，有歧义时省略。",
    )
    result = await SDKOrchestrator().commit(session)
    create.assert_awaited_once()
    publish.assert_not_awaited()
    payload = create.await_args.args[0]
    assert create.await_args.kwargs["created_by"] == session.user_id
    assert payload["tenant_id"] == "tenant-1"
    assert payload["name"] == "出货单"
    assert payload["code"] == "shipment_report"
    assert payload["type"] == "extract"
    definition = validate_extract_definition(payload["definition"])
    assert set(definition) == {"data_schema", "target", "ui", "extraction_strategy"}
    assert definition["extraction_strategy"] == "full_document"
    assert definition["target"] == "per_doc"
    assert definition["data_schema"] == {
        "type": "object", "additionalProperties": False,
        "description": session.prompt,
        "properties": {"order_no": {"type": "string", "description": "从订单号标签后提取"}},
    }
    assert definition["ui"] == {"/properties/order_no": {"label": "订单号", "order": 0}}
    assert "NOZS0311046" not in str(definition)
    assert result.configuration_id == "config-1"
    assert result.tenant_id == "tenant-1"
    assert result.status == "draft"
    assert result.revision_id is None and result.revision_number is None
    assert result.field_count == 1
    assert session.state == SDKSessionState.COMMITTED


@pytest.mark.asyncio
async def test_commit_uses_fallback_schema_description_when_missing(monkeypatch):
    create = AsyncMock(return_value={"id": "config-2"})
    publish = AsyncMock()
    monkeypatch.setattr("sdk.agents.orchestrator.configuration_service.create_configuration", create)
    monkeypatch.setattr("sdk.agents.orchestrator.configuration_service.publish_configuration", publish)
    session = _build_session(
        id="session-2", user_id="user-1", state=SDKSessionState.TEMPLATE_CONFIRMED,
        confirmed_template=ConfirmTemplateRequest(
            template_name="检测报告", template_code="inspection_report",
            fields=[{"field_key": "sample_name", "field_label": "样品名称"}],
        ),
    )
    result = await SDKOrchestrator().commit(session)
    create.assert_awaited_once()
    publish.assert_not_awaited()
    definition = validate_extract_definition(create.await_args.args[0]["definition"])
    assert set(definition) == {"data_schema", "target", "ui", "extraction_strategy"}
    assert definition["extraction_strategy"] == "full_document"
    assert definition["data_schema"]["properties"]["sample_name"]["type"] == "string"
    description = definition["data_schema"]["description"]
    assert "可选字段省略" in description
    assert "{markdown}" not in description
    assert result.status == "draft"
    assert result.revision_id is None and result.revision_number is None


@pytest.mark.asyncio
async def test_analyze_document_passes_model_profile_to_agent(monkeypatch):
    captured = {}

    async def fake_run_doc_analyzer(*, parse_text, file_name, instruction, model_profile):
        captured["parse_text"] = parse_text
        captured["file_name"] = file_name
        captured["instruction"] = instruction
        captured["model_profile"] = model_profile
        return DocumentAnalysis(
            detected_fields=[
                {"field_key": "sample_name", "field_label": "样品名称", "field_type": "text"}
            ],
        )

    monkeypatch.setattr(
        "sdk.agents.orchestrator.run_doc_analyzer",
        fake_run_doc_analyzer,
    )

    session = _build_session(user_id="user-1")
    model_profile = SDKModelProfile(
        name="step",
        model="step-3.7-flash",
        base_url="https://api.stepfun.ai/v1",
        api_key="secret",
        temperature=0.4,
    )

    result = await SDKOrchestrator().analyze_document(
        session,
        "样品名称：小型断路器",
        model_profile=model_profile,
    )

    assert [field.field_key for field in result.detected_fields] == ["sample_name"]
    assert captured["parse_text"] == "样品名称：小型断路器"
    assert captured["file_name"] == "scan.jpg"
    assert captured["model_profile"] is model_profile


@pytest.mark.asyncio
async def test_generate_prompt_passes_model_profile_to_agent(monkeypatch):
    captured = {}

    async def fake_run_prompt_agent(confirmed, *, model_profile):
        captured["confirmed"] = confirmed
        captured["model_profile"] = model_profile
        return "仅依据样品名称标签后的原文提取 sample_name"

    monkeypatch.setattr(
        "sdk.agents.orchestrator.run_prompt_agent",
        fake_run_prompt_agent,
    )

    session = _build_session(
        user_id="user-1",
        state=SDKSessionState.TEMPLATE_CONFIRMED,
        confirmed_template=ConfirmTemplateRequest(
            template_name="检测报告",
            template_code="inspection_report",
            fields=[],
        ),
    )
    model_profile = SDKModelProfile(
        name="step",
        model="step-3.7-flash",
        base_url="https://api.stepfun.ai/v1",
        api_key="secret",
        temperature=0.4,
    )

    result = await SDKOrchestrator().generate_prompt(
        session,
        model_profile=model_profile,
    )

    assert result == "仅依据样品名称标签后的原文提取 sample_name"
    assert captured["confirmed"] is session.confirmed_template
    assert captured["model_profile"] is model_profile


@pytest.mark.asyncio
async def test_generate_prompt_does_not_fallback_when_model_profile_is_used(monkeypatch):
    async def fake_run_prompt_agent(confirmed, *, model_profile):
        raise RuntimeError("provider rejected api key")

    monkeypatch.setattr(
        "sdk.agents.orchestrator.run_prompt_agent",
        fake_run_prompt_agent,
    )

    session = _build_session(
        user_id="user-1",
        state=SDKSessionState.TEMPLATE_CONFIRMED,
        confirmed_template=ConfirmTemplateRequest(
            template_name="检测报告",
            template_code="inspection_report",
            fields=[
                {
                    "field_key": "sample_name",
                    "field_label": "样品名称",
                    "field_type": "text",
                    "extraction_hint": "从样品名称标签后提取",
                }
            ],
        ),
    )
    model_profile = SDKModelProfile(
        name="step",
        model="step-3.7-flash",
        base_url="https://api.stepfun.ai/v1",
        api_key="secret",
        temperature=0.4,
    )

    with pytest.raises(RuntimeError, match="provider rejected api key"):
        await SDKOrchestrator().generate_prompt(session, model_profile=model_profile)


@pytest.mark.asyncio
async def test_generate_prompt_keeps_fallback_without_model_profile(monkeypatch):
    async def fake_run_prompt_agent(confirmed, *, model_profile):
        assert model_profile is None
        raise RuntimeError("default provider unavailable")

    monkeypatch.setattr(
        "sdk.agents.orchestrator.run_prompt_agent",
        fake_run_prompt_agent,
    )

    session = _build_session(
        user_id="user-1",
        state=SDKSessionState.TEMPLATE_CONFIRMED,
        confirmed_template=ConfirmTemplateRequest(
            template_name="检测报告",
            template_code="inspection_report",
            fields=[
                {
                    "field_key": "sample_name",
                    "field_label": "样品名称",
                    "field_type": "text",
                    "extraction_hint": "从样品名称标签后提取",
                }
            ],
        ),
    )

    result = await SDKOrchestrator().generate_prompt(session)

    assert "可选字段省略" in result
    assert "{markdown}" not in result
