import pytest

from services.configuration_service import normalize_definition
from sdk.agents.orchestrator import SDKOrchestrator
from sdk.models import (
    ConfirmTemplateRequest,
    DocumentAnalysis,
    ExcelTemplatePlaceholder,
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
async def test_commit_creates_and_publishes_configuration(monkeypatch):
    captured_payload = {}
    captured_publish = {}

    async def fake_create_configuration(payload, created_by=None):
        captured_payload["payload"] = payload
        captured_payload["created_by"] = created_by
        return {"id": "config-1", "status": "draft", "tenant_id": payload["tenant_id"]}

    async def fake_publish_configuration(configuration_id, created_by=None):
        captured_publish["configuration_id"] = configuration_id
        captured_publish["created_by"] = created_by
        return {
            "configuration": {"id": configuration_id, "status": "published"},
            "revision": {"id": "revision-1", "revision_number": 1},
        }

    monkeypatch.setattr(
        "sdk.agents.orchestrator.configuration_service.create_configuration",
        fake_create_configuration,
    )
    monkeypatch.setattr(
        "sdk.agents.orchestrator.configuration_service.publish_configuration",
        fake_publish_configuration,
    )

    session = _build_session(
        parse_mode="vlm",
        excel_template_file_name="template.xlsx",
        excel_template_path="/tmp/template.xlsx",
        excel_placeholders=[
            ExcelTemplatePlaceholder(
                sheet_name="Report",
                coordinate="B1",
                field_key="order_no",
                raw_value="{{order_no}}",
            )
        ],
        state=SDKSessionState.TEMPLATE_CONFIRMED,
        confirmed_template=ConfirmTemplateRequest(
            template_name="出货单",
            template_code="shipment_report",
            tenant_id="tenant-1",
            extraction_mode="vlm",
            per_page_extraction=True,
            fields=[
                {
                    "field_key": "order_no",
                    "field_label": "订单号",
                    "field_type": "text",
                    "extraction_hint": "从订单号标签后提取",
                    "sample_value": "NOZS0311046",
                }
            ],
            examples=[
                {
                    "example_input": "订单号：NOZS0311046",
                    "example_output": {"order_no": "NOZS0311046"},
                }
            ],
        ),
        prompt="抽取订单号 {ocr_text}",
    )

    result = await SDKOrchestrator().commit(session)

    payload = captured_payload["payload"]
    assert payload["tenant_id"] == "tenant-1"
    assert payload["name"] == "出货单"
    assert payload["code"] == "shipment_report"
    assert payload["type"] == "extract"
    assert captured_payload["created_by"] == session.user_id
    assert captured_publish["configuration_id"] == "config-1"
    assert captured_publish["created_by"] == session.user_id

    definition = normalize_definition(payload["definition"])
    assert definition["extraction_prompt"] == "抽取订单号 {ocr_text}"
    assert definition["parse"]["model_version"] == "vlm"
    assert definition["per_page_extraction"] is True
    assert definition["output_mode"] == "both"
    assert definition["excel"] == {
        "file_name": "template.xlsx",
        "path": "/tmp/template.xlsx",
        "placeholders": [
            {
                "sheet_name": "Report",
                "coordinate": "B1",
                "field_key": "order_no",
                "raw_value": "{{order_no}}",
            }
        ],
    }
    assert definition["fields"] == [
        {
            "field_key": "order_no",
            "field_label": "订单号",
            "field_type": "text",
            "extraction_hint": "从订单号标签后提取",
            "feishu_column": "",
            "sort_order": 0,
            "review_enforced": False,
            "review_allowed_values": None,
            "is_required": False,
            "default_value": None,
            "source_doc_type": None,
        }
    ]
    assert definition["examples"] == [
        {
            "example_input": "订单号：NOZS0311046",
            "example_output": {"order_no": "NOZS0311046"},
            "description": None,
            "sort_order": 0,
            "is_active": True,
        }
    ]

    assert result.configuration_id == "config-1"
    assert result.revision_id == "revision-1"
    assert result.revision_number == 1
    assert result.field_count == 1
    assert result.example_count == 1
    assert session.state == SDKSessionState.COMMITTED


@pytest.mark.asyncio
async def test_commit_uses_fallback_prompt_when_missing(monkeypatch):
    captured_payload = {}

    async def fake_create_configuration(payload, created_by=None):
        captured_payload.update(payload)
        return {"id": "config-2"}

    async def fake_publish_configuration(configuration_id, created_by=None):
        return {"configuration": {"id": configuration_id}, "revision": {"id": "rev-2"}}

    monkeypatch.setattr(
        "sdk.agents.orchestrator.configuration_service.create_configuration",
        fake_create_configuration,
    )
    monkeypatch.setattr(
        "sdk.agents.orchestrator.configuration_service.publish_configuration",
        fake_publish_configuration,
    )

    session = _build_session(
        id="session-2",
        user_id="user-1",
        state=SDKSessionState.TEMPLATE_CONFIRMED,
        confirmed_template=ConfirmTemplateRequest(
            template_name="检测报告",
            template_code="inspection_report",
            tenant_id="tenant-1",
            fields=[
                {"field_key": "sample_name", "field_label": "样品名称"},
            ],
        ),
    )

    result = await SDKOrchestrator().commit(session)

    assert captured_payload["definition"]["output_mode"] == "bitable"
    assert "sample_name" in captured_payload["definition"]["extraction_prompt"]
    assert captured_payload["definition"]["excel"] == {
        "file_name": None,
        "path": None,
        "placeholders": [],
    }
    assert result.revision_id == "rev-2"


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
        return "请提取字段：sample_name\n{ocr_text}"

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
            tenant_id="tenant-1",
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

    assert result == "请提取字段：sample_name\n{ocr_text}"
    assert captured["confirmed"] is session.confirmed_template
    assert captured["model_profile"] is model_profile


@pytest.mark.asyncio
async def test_generate_code_passes_model_profile_to_agent(monkeypatch):
    captured = {}

    async def fake_generate_cleaner_code(confirmed, *, model_profile):
        captured["confirmed"] = confirmed
        captured["model_profile"] = model_profile
        return "def clean_sample_name(value: str) -> str:\n    return value.strip()"

    monkeypatch.setattr(
        "sdk.agents.orchestrator.generate_cleaner_code",
        fake_generate_cleaner_code,
    )

    session = _build_session(
        user_id="user-1",
        state=SDKSessionState.TEMPLATE_CONFIRMED,
        confirmed_template=ConfirmTemplateRequest(
            template_name="检测报告",
            template_code="inspection_report",
            tenant_id="tenant-1",
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

    result = await SDKOrchestrator().generate_code(
        session,
        model_profile=model_profile,
    )

    assert result == "def clean_sample_name(value: str) -> str:\n    return value.strip()"
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
            tenant_id="tenant-1",
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
            tenant_id="tenant-1",
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

    assert "OCR文本" in result
    assert "{ocr_text}" in result
