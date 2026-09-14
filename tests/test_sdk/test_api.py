from pathlib import Path
from io import BytesIO
import importlib.util

import pytest
from openpyxl import Workbook
from fastapi import FastAPI
from unittest.mock import AsyncMock

from api.dependencies.auth import CurrentUser, get_current_user

USER_ID = "11111111-1111-4111-8111-111111111111"
TENANT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"

PARSE_MARKDOWN = "# 解析结果\n样品名称：小型断路器\n检验结论：合格"


def _load_sdk_route_module():
    module_path = Path(__file__).resolve().parents[2] / "api" / "routes" / "sdk.py"
    spec = importlib.util.spec_from_file_location("sdk_route_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


sdk_route = _load_sdk_route_module()
sdk_router = sdk_route.router


async def _tenant_admin_user():
    return CurrentUser(
        user_id=USER_ID,
        token="test-token",
        tenant_id=TENANT_ID,
        role="tenant_admin",
    )


async def _other_tenant_admin_user():
    return CurrentUser(
        user_id="22222222-2222-4222-8222-222222222222",
        token="test-token",
        tenant_id=TENANT_ID,
        role="tenant_admin",
    )


async def _regular_user():
    return CurrentUser(
        user_id=USER_ID,
        token="test-token",
        tenant_id=TENANT_ID,
        role="user",
    )


@pytest.fixture
def admin_client():
    test_app = FastAPI()
    test_app.include_router(sdk_router, prefix="/api")
    test_app.dependency_overrides[get_current_user] = _tenant_admin_user
    try:
        from fastapi.testclient import TestClient

        with TestClient(test_app) as test_client:
            yield test_client
    finally:
        test_app.dependency_overrides.clear()


@pytest.fixture
def client():
    test_app = FastAPI()
    test_app.include_router(sdk_router, prefix="/api")
    test_app.dependency_overrides[get_current_user] = _regular_user
    try:
        from fastapi.testclient import TestClient

        with TestClient(test_app) as test_client:
            yield test_client
    finally:
        test_app.dependency_overrides.clear()


def _excel_template_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Report"
    sheet["A1"] = "订单号"
    sheet["B1"] = "{{order_no}}"
    sheet["A2"] = "数量"
    sheet["B2"] = "{{quantity}} 件"
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _parse_result_row(markdown: str = PARSE_MARKDOWN, model_version: str = "pipeline"):
    return {
        "id": "result-1",
        "data": {
            "markdown": markdown,
            "engine": {"name": "mineru", "model_version": model_version},
        },
    }


def _patch_parse_env(monkeypatch, tmp_path) -> dict:
    """把创建会话所需的解析依赖全部替换掉，返回可断言的 mock 集合。"""
    mocks = {
        "create_document": AsyncMock(return_value={"id": "doc"}),
        "create_job": AsyncMock(return_value="job-1"),
        "ensure_parse_revision": AsyncMock(return_value={"id": "revision-1"}),
        "get_document_parse_result": AsyncMock(return_value=None),
        "get_job": AsyncMock(return_value={"status": "processing", "progress": 30}),
        "get_document": AsyncMock(return_value=None),
    }
    monkeypatch.setattr(sdk_route.settings, "UPLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(sdk_route.supabase_service, "create_document", mocks["create_document"])
    monkeypatch.setattr(sdk_route, "create_job", mocks["create_job"])
    monkeypatch.setattr(sdk_route, "ensure_parse_revision", mocks["ensure_parse_revision"])
    monkeypatch.setattr(
        sdk_route.result_service,
        "get_document_parse_result",
        mocks["get_document_parse_result"],
    )
    monkeypatch.setattr(sdk_route, "get_job", mocks["get_job"])
    monkeypatch.setattr(sdk_route.supabase_service, "get_document", mocks["get_document"])
    return mocks


def _create_session(admin_client, files=None, data=None):
    form = {
        "template_name": "检测报告",
        "template_code": "inspection_report",
        "tenant_id": TENANT_ID,
    }
    form.update(data or {})
    return admin_client.post(
        "/api/sdk/sessions",
        files=files or {"file": ("report.pdf", b"%PDF-1.4 sample", "application/pdf")},
        data=form,
    )


def test_create_session_starts_parse_job(admin_client, monkeypatch, tmp_path):
    mocks = _patch_parse_env(monkeypatch, tmp_path)

    response = _create_session(admin_client)

    assert response.status_code == 201
    payload = response.json()
    assert payload["file_name"] == "report.pdf"
    assert payload["id"] == "job-1"
    assert payload["state"] == "parsing"
    assert payload["parse_mode"] == "pipeline"
    assert payload["parse_job_id"] == "job-1"
    assert payload["document_id"]
    assert payload["parse_progress"] == 0

    document_payload = mocks["create_document"].await_args.args[0]
    assert document_payload["tenant_id"] == TENANT_ID
    assert document_payload["user_id"] == USER_ID
    assert Path(document_payload["file_path"]).exists()

    job_kwargs = mocks["create_job"].await_args.kwargs
    assert job_kwargs["configuration_revision_id"] == "revision-1"
    assert job_kwargs["related_document_ids"] == [payload["document_id"]]
    mocks["ensure_parse_revision"].assert_awaited_once()


def test_create_session_accepts_parse_mode(admin_client, monkeypatch, tmp_path):
    mocks = _patch_parse_env(monkeypatch, tmp_path)

    response = _create_session(admin_client, data={"parse_mode": "vlm"})

    assert response.status_code == 201
    assert response.json()["parse_mode"] == "vlm"
    assert mocks["ensure_parse_revision"].await_args.args[1] == "vlm"


def test_get_session_syncs_completed_parse(admin_client, monkeypatch, tmp_path):
    mocks = _patch_parse_env(monkeypatch, tmp_path)
    session_id = _create_session(admin_client).json()["id"]

    mocks["get_job"].return_value = {"status": "completed", "progress": 100}
    mocks["get_document_parse_result"].return_value = _parse_result_row()

    response = admin_client.get(f"/api/sdk/sessions/{session_id}")

    assert response.status_code == 200
    assert response.json()["state"] == "parsed"


def test_get_session_marks_parse_failed(admin_client, monkeypatch, tmp_path):
    mocks = _patch_parse_env(monkeypatch, tmp_path)
    session_id = _create_session(admin_client).json()["id"]

    mocks["get_job"].return_value = {"status": "failed", "error": "MinerU 超时"}

    response = admin_client.get(f"/api/sdk/sessions/{session_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "parse_failed"
    assert payload["parse_error"] == "MinerU 超时"


def test_retry_parse_creates_new_job(admin_client, monkeypatch, tmp_path):
    mocks = _patch_parse_env(monkeypatch, tmp_path)
    session_id = _create_session(admin_client).json()["id"]
    mocks["get_job"].return_value = {"status": "failed", "error": "解析失败"}
    admin_client.get(f"/api/sdk/sessions/{session_id}")

    mocks["create_job"].return_value = "job-2"
    mocks["get_job"].return_value = {"status": "queued", "progress": 0}

    response = admin_client.post(
        f"/api/sdk/sessions/{session_id}/parse",
        json={"parse_mode": "vlm"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "job-2"
    assert payload["state"] == "parsing"
    assert payload["parse_job_id"] == "job-2"
    assert payload["parse_mode"] == "vlm"
    assert mocks["create_job"].await_count == 2
    assert mocks["ensure_parse_revision"].await_args.args[1] == "vlm"


def test_retry_parse_reuses_matching_result(admin_client, monkeypatch, tmp_path):
    mocks = _patch_parse_env(monkeypatch, tmp_path)
    session_id = _create_session(admin_client).json()["id"]

    mocks["get_job"].return_value = {"status": "completed", "progress": 100}
    mocks["get_document_parse_result"].return_value = _parse_result_row()

    response = admin_client.post(f"/api/sdk/sessions/{session_id}/parse", json={})

    assert response.status_code == 200
    assert response.json()["state"] == "parsed"
    assert mocks["create_job"].await_count == 1


def test_analyze_uses_parse_markdown(admin_client, monkeypatch, tmp_path):
    mocks = _patch_parse_env(monkeypatch, tmp_path)
    session_id = _create_session(admin_client).json()["id"]
    mocks["get_job"].return_value = {"status": "completed", "progress": 100}
    mocks["get_document_parse_result"].return_value = _parse_result_row()

    captured = {}

    async def fake_analyze(session, parse_text, **kwargs):
        captured["parse_text"] = parse_text
        return {
            "detected_fields": [
                {
                    "field_key": "sample_name",
                    "field_label": "样品名称",
                    "field_type": "text",
                    "extraction_hint": "位于样品名称标签后",
                    "review_enforced": False,
                    "review_allowed_values": None,
                    "sample_value": "小型断路器",
                }
            ],
        }

    monkeypatch.setattr(sdk_route.orchestrator, "analyze_document", fake_analyze)

    response = admin_client.post(f"/api/sdk/sessions/{session_id}/analyze")

    assert response.status_code == 200
    assert response.json()["analysis"]["detected_fields"]
    assert captured["parse_text"] == PARSE_MARKDOWN


def test_analyze_rejects_while_parsing(admin_client, monkeypatch, tmp_path):
    _patch_parse_env(monkeypatch, tmp_path)
    session_id = _create_session(admin_client).json()["id"]

    response = admin_client.post(f"/api/sdk/sessions/{session_id}/analyze")

    assert response.status_code == 409


def test_create_session_accepts_excel_template_and_returns_slots(
    admin_client,
    monkeypatch,
    tmp_path,
):
    _patch_parse_env(monkeypatch, tmp_path)

    response = _create_session(
        admin_client,
        files={
            "file": ("scan.jpg", b"image bytes", "image/jpeg"),
            "excel_template": (
                "template.xlsx",
                _excel_template_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["file_name"] == "scan.jpg"
    assert data["excel_template_file_name"] == "template.xlsx"
    assert [
        (item["sheet_name"], item["coordinate"], item["field_key"])
        for item in data["excel_placeholders"]
    ] == [
        ("Report", "B1", "order_no"),
        ("Report", "B2", "quantity"),
    ]


def test_analyze_adds_excel_slots_to_field_draft(admin_client, monkeypatch, tmp_path):
    mocks = _patch_parse_env(monkeypatch, tmp_path)
    mocks["get_job"].return_value = {"status": "completed", "progress": 100}
    mocks["get_document_parse_result"].return_value = _parse_result_row()

    analysis_payload = {
        "detected_fields": [
            {
                "field_key": "order_no",
                "field_label": "订单号",
                "field_type": "text",
                "extraction_hint": "从订单号标签后提取",
                "review_enforced": False,
                "review_allowed_values": None,
                "sample_value": "NOZS0311046",
            }
        ],
    }

    async def fake_analyze(session, parse_text, **kwargs):
        return analysis_payload

    monkeypatch.setattr(sdk_route.orchestrator, "analyze_document", fake_analyze)

    create_response = _create_session(
        admin_client,
        files={
            "file": ("scan.jpg", b"image bytes", "image/jpeg"),
            "excel_template": (
                "template.xlsx",
                _excel_template_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        },
    )

    session_id = create_response.json()["id"]
    analyze_response = admin_client.post(f"/api/sdk/sessions/{session_id}/analyze")

    assert analyze_response.status_code == 200
    fields = analyze_response.json()["analysis"]["detected_fields"]
    assert [field["field_key"] for field in fields] == ["order_no", "quantity"]
    assert fields[1]["field_label"] == "quantity"
    assert "Excel" in fields[1]["extraction_hint"]


def test_sdk_session_flow_analyze_prompt_and_commit(admin_client, monkeypatch, tmp_path):
    mocks = _patch_parse_env(monkeypatch, tmp_path)
    mocks["get_job"].return_value = {"status": "completed", "progress": 100}
    mocks["get_document_parse_result"].return_value = _parse_result_row()

    analysis_payload = {
        "detected_fields": [
            {
                "field_key": "sample_name",
                "field_label": "样品名称",
                "field_type": "text",
                "extraction_hint": "位于样品名称标签后",
                "review_enforced": False,
                "review_allowed_values": None,
                "sample_value": "小型断路器",
            }
        ],
    }

    async def fake_analyze(session, parse_text, **kwargs):
        return analysis_payload

    async def fake_generate_prompt(session, **kwargs):
        return "请提取字段：sample_name\n{ocr_text}"

    commit_session_payload = {}

    async def fake_commit(session):
        commit_session_payload["prompt"] = session.prompt
        commit_session_payload["cleaner_code"] = session.cleaner_code
        return {
            "tenant_id": TENANT_ID,
            "configuration_id": "config-1",
            "revision_id": "revision-1",
            "revision_number": 1,
            "field_count": 1,
            "example_count": 1,
        }

    monkeypatch.setattr(sdk_route.orchestrator, "analyze_document", fake_analyze)
    monkeypatch.setattr(sdk_route.orchestrator, "generate_prompt", fake_generate_prompt)
    monkeypatch.setattr(sdk_route.orchestrator, "commit", fake_commit)

    create_response = _create_session(admin_client)
    session_id = create_response.json()["id"]

    analyze_response = admin_client.post(f"/api/sdk/sessions/{session_id}/analyze")
    assert analyze_response.status_code == 200
    assert analyze_response.json()["analysis"]["detected_fields"]

    confirm_response = admin_client.post(
        f"/api/sdk/sessions/{session_id}/confirm-template",
        json={
            "template_name": "检测报告",
            "template_code": "inspection_report",
            "description": "AI 生成模板",
            "per_page_extraction": False,
            "fields": analysis_payload["detected_fields"],
            "examples": [],
        },
    )
    assert confirm_response.status_code == 200

    prompt_response = admin_client.post(f"/api/sdk/sessions/{session_id}/prompt")
    assert prompt_response.status_code == 200
    assert "{ocr_text}" in prompt_response.json()["prompt"]

    commit_response = admin_client.post(
        f"/api/sdk/sessions/{session_id}/commit",
        json={
            "prompt": "管理员最终确认的 prompt\n{ocr_text}",
            "cleaner_code": "def clean_sample_name(value: str) -> str:\n    return value.strip()",
        },
    )
    assert commit_response.status_code == 200
    assert commit_response.json()["commit_result"]["configuration_id"] == "config-1"
    assert commit_response.json()["commit_result"]["revision_id"] == "revision-1"
    assert commit_session_payload == {
        "prompt": "管理员最终确认的 prompt\n{ocr_text}",
        "cleaner_code": "def clean_sample_name(value: str) -> str:\n    return value.strip()",
    }


def test_llm_routes_pass_request_model_profile_without_returning_key(
    admin_client,
    monkeypatch,
    tmp_path,
):
    analysis_payload = {
        "detected_fields": [
            {
                "field_key": "sample_name",
                "field_label": "样品名称",
                "field_type": "text",
                "extraction_hint": "位于样品名称标签后",
                "review_enforced": False,
                "review_allowed_values": None,
                "sample_value": "小型断路器",
            }
        ],
    }
    profile_payload = {
        "name": "step-test",
        "model": "step-3.7-flash",
        "base_url": "https://api.stepfun.ai/v1",
        "api_key": "profile-secret-key",
        "temperature": 0.4,
    }
    captured_profiles = {}

    async def fake_analyze(session, parse_text, *, model_profile):
        captured_profiles["analyze"] = model_profile
        return analysis_payload

    async def fake_generate_prompt(session, *, model_profile):
        captured_profiles["prompt"] = model_profile
        return "请提取字段：sample_name\n{ocr_text}"

    async def fake_generate_code(session, *, model_profile):
        captured_profiles["code"] = model_profile
        return "def clean_sample_name(value: str) -> str:\n    return value.strip()"

    mocks = _patch_parse_env(monkeypatch, tmp_path)
    mocks["get_job"].return_value = {"status": "completed", "progress": 100}
    mocks["get_document_parse_result"].return_value = _parse_result_row()
    monkeypatch.setattr(sdk_route.orchestrator, "analyze_document", fake_analyze)
    monkeypatch.setattr(sdk_route.orchestrator, "generate_prompt", fake_generate_prompt)
    monkeypatch.setattr(sdk_route.orchestrator, "generate_code", fake_generate_code)

    create_response = admin_client.post(
        "/api/sdk/sessions",
        files={"file": ("report.pdf", b"%PDF-1.4 sample", "application/pdf")},
        data={
            "template_name": "检测报告",
            "template_code": "inspection_report",
            "tenant_id": TENANT_ID,
        },
    )
    session_id = create_response.json()["id"]

    analyze_response = admin_client.post(
        f"/api/sdk/sessions/{session_id}/analyze",
        json={"model_profile": profile_payload},
    )
    assert analyze_response.status_code == 200
    assert "profile-secret-key" not in analyze_response.text

    confirm_response = admin_client.post(
        f"/api/sdk/sessions/{session_id}/confirm-template",
        json={
            "template_name": "检测报告",
            "template_code": "inspection_report",
            "description": "AI 生成模板",
            "per_page_extraction": False,
            "fields": analysis_payload["detected_fields"],
            "examples": [],
        },
    )
    assert confirm_response.status_code == 200

    prompt_response = admin_client.post(
        f"/api/sdk/sessions/{session_id}/prompt",
        json={"model_profile": profile_payload},
    )
    code_response = admin_client.post(
        f"/api/sdk/sessions/{session_id}/code",
        json={"model_profile": profile_payload},
    )

    assert prompt_response.status_code == 200
    assert code_response.status_code == 200
    assert "profile-secret-key" not in prompt_response.text
    assert "profile-secret-key" not in code_response.text
    assert [
        captured_profiles[name].model_dump()
        for name in ("analyze", "prompt", "code")
    ] == [profile_payload, profile_payload, profile_payload]


def test_sdk_routes_require_admin(client):
    response = client.post(
        "/api/sdk/sessions",
        files={"file": ("report.pdf", b"%PDF-1.4 sample", "application/pdf")},
    )

    assert response.status_code == 403


def test_sdk_session_owner_is_enforced(admin_client, monkeypatch, tmp_path):
    _patch_parse_env(monkeypatch, tmp_path)

    create_response = _create_session(admin_client)
    session_id = create_response.json()["id"]

    test_app = FastAPI()
    test_app.include_router(sdk_router, prefix="/api")
    test_app.dependency_overrides[get_current_user] = _other_tenant_admin_user
    try:
        from fastapi.testclient import TestClient

        with TestClient(test_app) as other_client:
            response = other_client.get(f"/api/sdk/sessions/{session_id}")
    finally:
        test_app.dependency_overrides.clear()

    assert response.status_code == 403


def _document_row(document_id: str, *, tenant_id: str = TENANT_ID, user_id: str = USER_ID):
    return {
        "id": document_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "file_name": "stored.png",
        "original_file_name": "report.pdf",
        "file_path": "/tmp/report.pdf",
    }


def _completed_job(document_id: str):
    return {
        "status": "completed",
        "progress": 100,
        "document_ids": [document_id],
        "created_at": "2026-09-14T08:00:00+00:00",
        "configuration_revision_id": "revision-1",
    }


def _stub_revision(monkeypatch, model_version: str = "vlm"):
    monkeypatch.setattr(
        "services.configuration_service.configuration_service.get_revision",
        AsyncMock(
            return_value={
                "id": "revision-1",
                "definition": {"parse": {"model_version": model_version}},
            }
        ),
    )


def test_get_session_rebuilds_from_job_after_restart(admin_client, monkeypatch, tmp_path):
    mocks = _patch_parse_env(monkeypatch, tmp_path)
    created = _create_session(admin_client).json()
    session_id = created["id"]
    document_id = created["document_id"]

    sdk_route.session_store.delete(session_id)  # 模拟 API 重启后内存丢失
    mocks["get_job"].return_value = _completed_job(document_id)
    mocks["get_document"].return_value = _document_row(document_id)
    mocks["get_document_parse_result"].return_value = _parse_result_row()
    _stub_revision(monkeypatch, "vlm")

    response = admin_client.get(f"/api/sdk/sessions/{session_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "parsed"
    assert payload["parse_mode"] == "vlm"
    assert payload["document_id"] == document_id
    assert payload["file_name"] == "report.pdf"


def test_get_session_rebuild_returns_404_when_document_missing(
    admin_client,
    monkeypatch,
    tmp_path,
):
    mocks = _patch_parse_env(monkeypatch, tmp_path)
    created = _create_session(admin_client).json()
    sdk_route.session_store.delete(created["id"])

    mocks["get_job"].return_value = _completed_job(created["document_id"])
    mocks["get_document"].return_value = None

    response = admin_client.get(f"/api/sdk/sessions/{created['id']}")

    assert response.status_code == 404


def test_get_session_rebuild_rejects_other_tenant(admin_client, monkeypatch, tmp_path):
    mocks = _patch_parse_env(monkeypatch, tmp_path)
    created = _create_session(admin_client).json()
    sdk_route.session_store.delete(created["id"])

    mocks["get_job"].return_value = _completed_job(created["document_id"])
    mocks["get_document"].return_value = _document_row(
        created["document_id"],
        tenant_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        user_id="22222222-2222-4222-8222-222222222222",
    )

    response = admin_client.get(f"/api/sdk/sessions/{created['id']}")

    assert response.status_code == 404


def test_get_session_recovers_excel_template_after_restart(
    admin_client,
    monkeypatch,
    tmp_path,
):
    mocks = _patch_parse_env(monkeypatch, tmp_path)
    created = _create_session(
        admin_client,
        files={
            "file": ("scan.jpg", b"image bytes", "image/jpeg"),
            "excel_template": (
                "template.xlsx",
                _excel_template_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        },
    ).json()
    session_id = created["id"]
    document_id = created["document_id"]

    sdk_route.session_store.delete(session_id)
    mocks["get_job"].return_value = _completed_job(document_id)
    mocks["get_document"].return_value = _document_row(document_id)
    mocks["get_document_parse_result"].return_value = _parse_result_row()
    _stub_revision(monkeypatch, "pipeline")

    response = admin_client.get(f"/api/sdk/sessions/{session_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["excel_template_file_name"] == "template.xlsx"
    assert [
        (item["sheet_name"], item["coordinate"], item["field_key"])
        for item in payload["excel_placeholders"]
    ] == [
        ("Report", "B1", "order_no"),
        ("Report", "B2", "quantity"),
    ]


def test_delete_session_keeps_sample_document_file(admin_client, monkeypatch, tmp_path):
    _patch_parse_env(monkeypatch, tmp_path)
    created = _create_session(
        admin_client,
        files={
            "file": ("scan.jpg", b"image bytes", "image/jpeg"),
            "excel_template": (
                "template.xlsx",
                _excel_template_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        },
    ).json()

    response = admin_client.delete(f"/api/sdk/sessions/{created['id']}")

    assert response.status_code == 200
    assert list(tmp_path.glob("*.jpg")), "样例文档文件应保留"
    assert not list((tmp_path / "sdk_sessions").glob("*")), "Excel 模板文件应被清理"


def test_create_session_requires_document_kind(admin_client, monkeypatch, tmp_path):
    _patch_parse_env(monkeypatch, tmp_path)

    response = admin_client.post(
        "/api/sdk/sessions",
        files={"file": ("report.pdf", b"%PDF-1.4 sample", "application/pdf")},
        data={"tenant_id": TENANT_ID},
    )

    assert response.status_code == 400
    assert "文档类型" in response.json()["detail"]


def test_create_session_rejects_other_tenant(admin_client, monkeypatch, tmp_path):
    mocks = _patch_parse_env(monkeypatch, tmp_path)

    response = _create_session(
        admin_client,
        data={"tenant_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"},
    )

    assert response.status_code == 403
    mocks["create_document"].assert_not_awaited()


def test_create_session_requires_tenant(admin_client, monkeypatch, tmp_path):
    _patch_parse_env(monkeypatch, tmp_path)
    test_app = FastAPI()
    test_app.include_router(sdk_router, prefix="/api")
    test_app.dependency_overrides[get_current_user] = _regular_tenant_missing_admin
    try:
        from fastapi.testclient import TestClient

        with TestClient(test_app) as no_tenant_client:
            response = no_tenant_client.post(
                "/api/sdk/sessions",
                files={"file": ("report.pdf", b"%PDF-1.4 sample", "application/pdf")},
                data={"template_name": "检测报告", "template_code": "inspection_report"},
            )
    finally:
        test_app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "租户" in response.json()["detail"]


async def _regular_tenant_missing_admin():
    return CurrentUser(
        user_id=USER_ID,
        token="test-token",
        tenant_id=None,
        role="tenant_admin",
    )


def test_analyze_returns_only_field_candidates(admin_client, monkeypatch, tmp_path):
    mocks = _patch_parse_env(monkeypatch, tmp_path)
    session_id = _create_session(admin_client).json()["id"]
    mocks["get_job"].return_value = {"status": "completed", "progress": 100}
    mocks["get_document_parse_result"].return_value = _parse_result_row()

    async def fake_analyze(session, parse_text, **kwargs):
        return {"detected_fields": []}

    monkeypatch.setattr(sdk_route.orchestrator, "analyze_document", fake_analyze)

    response = admin_client.post(f"/api/sdk/sessions/{session_id}/analyze")

    assert response.status_code == 200
    analysis = response.json()["analysis"]
    assert analysis == {"detected_fields": []}
