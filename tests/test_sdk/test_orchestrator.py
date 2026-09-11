import pytest

from services.configuration_service import normalize_definition
from sdk.agents.orchestrator import SDKOrchestrator
from sdk.models import (
    ConfirmTemplateRequest,
    ExcelTemplatePlaceholder,
    SDKSession,
    SDKSessionState,
)


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

    session = SDKSession(
        id="session-1",
        file_name="scan.jpg",
        file_path="/tmp/scan.jpg",
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
        ocr_text="订单号：NOZS0311046",
        ocr_confidence=0.93,
        page_count=1,
        user_id="11111111-1111-4111-8111-111111111111",
        state=SDKSessionState.TEMPLATE_CONFIRMED,
        created_at=1000,
        updated_at=1000,
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
    assert definition["extraction_mode"] == "vlm"
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

    session = SDKSession(
        id="session-2",
        file_name="scan.jpg",
        file_path="/tmp/scan.jpg",
        ocr_text="文本",
        ocr_confidence=0.9,
        page_count=1,
        user_id="user-1",
        state=SDKSessionState.TEMPLATE_CONFIRMED,
        created_at=1000,
        updated_at=1000,
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
