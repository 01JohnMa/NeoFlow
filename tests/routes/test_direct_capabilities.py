"""Direct AI Center Parse/Extract capability contracts."""

import io
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from api.dependencies.auth import CurrentUser, require_platform_scope
from api.routes import extract as extract_route
from api.routes import parse as parse_route
from tests.conftest import TENANT_ID, USER_ID


def _user() -> CurrentUser:
    return CurrentUser(user_id=USER_ID, token="platform", tenant_id=TENANT_ID)


def _upload(name: str = "sample.pdf") -> UploadFile:
    return UploadFile(file=io.BytesIO(b"pdf-bytes"), filename=name, headers={})


class _Request:
    def __init__(self, values=None):
        self.values = values or {}

    async def form(self):
        return self.values


@pytest.mark.asyncio
async def test_direct_parse_uploads_and_admits_one_job(monkeypatch, tmp_path):
    monkeypatch.setattr(parse_route.settings, "UPLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(parse_route.supabase_service, "create_document", AsyncMock())
    monkeypatch.setattr(parse_route.supabase_service, "delete_document", AsyncMock())
    monkeypatch.setattr(
        parse_route.parse_request_service,
        "admit",
        AsyncMock(return_value={"status": "ok", "job_ids": ["job-1"]}),
    )

    response = await parse_route.create_direct_parse(
        request=_Request(),
        file=_upload(),
        parse_mode=None,
        language=None,
        enable_formula=None,
        enable_table=None,
        remove_watermark=None,
        watermark_keywords=None,
        target_pages=None,
        user=_user(),
    )

    assert response["data"]["job_ids"] == ["job-1"]
    assert response["data"]["job_id"] == "job-1"
    assert response["data"]["status"] == "ok"
    parse_route.supabase_service.create_document.assert_awaited_once()
    assert response["data"]["document_id"]
    assert list(tmp_path.glob("*.pdf"))


@pytest.mark.asyncio
async def test_direct_extract_selects_published_template_code_and_pins_revision(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(parse_route.settings, "UPLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(extract_route.supabase_service, "create_document", AsyncMock())
    monkeypatch.setattr(extract_route.supabase_service, "delete_document", AsyncMock())
    monkeypatch.setattr(
        extract_route.configuration_service,
        "get_published_extract_configuration_by_code",
        AsyncMock(
            return_value={
                "id": "cfg-1",
                "tenant_id": TENANT_ID,
                "code": "inspection_report",
                "type": "extract",
                "status": "published",
                "current_revision_id": "rev-1",
            }
        ),
    )
    monkeypatch.setattr(
        extract_route.configuration_service,
        "get_revision",
        AsyncMock(
            return_value={
                "id": "rev-1",
                "definition": {
                    "target": "per_doc",
                    "data_schema": {"type": "object", "properties": {}},
                },
            }
        ),
    )
    monkeypatch.setattr(extract_route, "create_job", AsyncMock(return_value="job-2"))

    response = await extract_route.create_direct_extract(
        request=_Request(), file=_upload(), template_code=" inspection_report ", user=_user()
    )

    assert response["data"]["template_code"] == "inspection_report"
    assert response["data"]["revision_id"] == "rev-1"
    assert response["data"]["job_id"] == "job-2"
    extract_route.configuration_service.get_published_extract_configuration_by_code.assert_awaited_once_with(
        TENANT_ID, "inspection_report"
    )
    extract_route.create_job.assert_awaited_once()
    assert extract_route.create_job.await_args.kwargs["configuration_revision_id"] == "rev-1"


@pytest.mark.asyncio
async def test_private_gateway_context_requires_tenant_and_scope(monkeypatch):
    async def fake_canonical_tenant(raw_tenant_id):
        return TENANT_ID

    monkeypatch.setattr(
        "api.dependencies.auth._canonical_platform_tenant_id", fake_canonical_tenant
    )
    dependency = require_platform_scope("extract")
    user = await dependency(
        tenant_id=TENANT_ID,
        application_id="app-neoflow",
        version_id="version-1",
        invocation_id="invocation-1",
        caller_id=USER_ID,
        raw_scope="extract jobs.read results.read",
    )
    assert user.user_id == USER_ID
    assert user.tenant_id == TENANT_ID

    with pytest.raises(Exception):
        await dependency(
            tenant_id=TENANT_ID,
            application_id="app-neoflow",
            version_id="version-1",
            invocation_id="invocation-1",
            caller_id=USER_ID,
            raw_scope="parse",
        )


@pytest.mark.asyncio
async def test_direct_capabilities_reject_internal_selectors():
    with pytest.raises(HTTPException) as exc:
        await parse_route.reject_forbidden_direct_fields(
            _Request({"configuration_id": "internal", "file": _upload()})
        )
    assert exc.value.status_code == 422


def _platform_user() -> CurrentUser:
    from api.dependencies.auth import PlatformContext

    return CurrentUser(
        user_id=USER_ID,
        token="platform",
        tenant_id=TENANT_ID,
        platform_context=PlatformContext(
            tenant_id=TENANT_ID,
            application_id="app-neoflow",
            application_version_id="version-1",
            invocation_id="invocation-platform-9",
            caller_id="caller-1",
            scopes=("parse", "extract"),
        ),
    )


@pytest.mark.asyncio
async def test_direct_parse_persists_platform_invocation(monkeypatch, tmp_path):
    monkeypatch.setattr(parse_route.settings, "UPLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(parse_route.supabase_service, "create_document", AsyncMock())
    monkeypatch.setattr(parse_route.supabase_service, "delete_document", AsyncMock())
    admit = AsyncMock(return_value={"status": "ok", "job_ids": ["job-1"]})
    monkeypatch.setattr(parse_route.parse_request_service, "admit", admit)

    await parse_route.create_direct_parse(
        request=_Request(),
        file=_upload(),
        parse_mode=None,
        language=None,
        enable_formula=None,
        enable_table=None,
        remove_watermark=None,
        watermark_keywords=None,
        target_pages=None,
        user=_platform_user(),
    )

    admit.assert_awaited_once()
    assert admit.call_args.kwargs["platform_invocation_id"] == "invocation-platform-9"


@pytest.mark.asyncio
async def test_direct_parse_without_platform_context_passes_none(monkeypatch, tmp_path):
    monkeypatch.setattr(parse_route.settings, "UPLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(parse_route.supabase_service, "create_document", AsyncMock())
    admit = AsyncMock(return_value={"status": "ok", "job_ids": ["job-1"]})
    monkeypatch.setattr(parse_route.parse_request_service, "admit", admit)

    await parse_route.create_direct_parse(
        request=_Request(),
        file=_upload(),
        parse_mode=None,
        language=None,
        enable_formula=None,
        enable_table=None,
        remove_watermark=None,
        watermark_keywords=None,
        target_pages=None,
        user=_user(),
    )

    assert admit.call_args.kwargs["platform_invocation_id"] is None


@pytest.mark.asyncio
async def test_direct_extract_persists_platform_invocation(monkeypatch, tmp_path):
    monkeypatch.setattr(
        extract_route, "save_uploaded_document", AsyncMock(
            return_value={"document_id": "doc-1", "file_path": str(tmp_path / "f.pdf")}
        )
    )
    monkeypatch.setattr(
        extract_route.configuration_service,
        "get_published_extract_configuration_by_code",
        AsyncMock(
            return_value={"id": "cfg-1", "code": "T1", "status": "published"}
        ),
    )
    monkeypatch.setattr(extract_route.supabase_service, "create_document", AsyncMock())
    monkeypatch.setattr(
        extract_route, "_load_definition_and_spec", AsyncMock(return_value=("rev-1", {}))
    )
    create_job = AsyncMock(return_value="job-9")
    monkeypatch.setattr(extract_route, "create_job", create_job)

    await extract_route.create_direct_extract(
        request=_Request(),
        file=_upload(),
        template_code="T1",
        user=_platform_user(),
    )

    create_job.assert_awaited_once()
    assert create_job.call_args.kwargs["platform_invocation_id"] == "invocation-platform-9"
