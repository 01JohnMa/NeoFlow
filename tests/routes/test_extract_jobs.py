# tests/routes/test_extract_jobs.py
"""Extract 能力路由测试：草稿快照 / 已发布 pin / 校验拒绝 / 结果读取不回退。"""

from unittest.mock import AsyncMock

import pytest

from tests.conftest import DOCUMENT_ID, TENANT_ID, USER_ID

SCHEMA = {
    "type": "object",
    "properties": {"report_no": {"type": "string"}},
    "required": ["report_no"],
    "additionalProperties": False,
}


def _draft_config(definition=None):
    return {
        "id": "cfg-1",
        "tenant_id": TENANT_ID,
        "type": "extract",
        "status": "draft",
        "current_revision_id": None,
        "draft_definition": definition
        or {"target": "per_doc", "data_schema": SCHEMA, "fields": []},
    }


def _published_config():
    return {
        "id": "cfg-1",
        "tenant_id": TENANT_ID,
        "type": "extract",
        "status": "published",
        "current_revision_id": "rev-1",
        "draft_definition": {"target": "per_doc", "data_schema": SCHEMA, "fields": []},
    }


def _document():
    return {"id": DOCUMENT_ID, "tenant_id": TENANT_ID, "user_id": USER_ID}


def _patch(monkeypatch, configuration, *, revision=None):
    from api.routes import extract as extract_mod

    monkeypatch.setattr(
        extract_mod.configuration_service,
        "get_configuration",
        AsyncMock(return_value=configuration),
    )
    monkeypatch.setattr(
        extract_mod.configuration_service,
        "get_revision",
        AsyncMock(
            return_value=revision
            if revision is not None
            else {"id": "rev-1", "definition": {"target": "per_doc", "data_schema": SCHEMA}}
        ),
    )
    monkeypatch.setattr(
        extract_mod.supabase_service, "get_document", AsyncMock(return_value=_document())
    )
    monkeypatch.setattr(extract_mod, "create_job", AsyncMock(return_value="job-1"))
    return extract_mod


class TestCreateExtractJobs:
    def test_draft_freezes_snapshot(self, client, monkeypatch):
        mod = _patch(monkeypatch, _draft_config())

        resp = client.post(
            "/api/extract/jobs",
            json={"configuration_id": "cfg-1", "document_ids": [DOCUMENT_ID]},
        )

        assert resp.status_code == 201
        body = resp.json()["data"]
        assert body["mode"] == "draft"
        kwargs = mod.create_job.await_args.kwargs
        assert kwargs["configuration_revision_id"] is None
        assert kwargs["execution_spec"]["capability"] == "extract"
        assert kwargs["execution_spec"]["effective_params"]["data_schema"] == SCHEMA

    def test_published_pins_revision(self, client, monkeypatch):
        mod = _patch(monkeypatch, _published_config())

        resp = client.post(
            "/api/extract/jobs",
            json={"configuration_id": "cfg-1", "document_ids": [DOCUMENT_ID]},
        )

        assert resp.status_code == 201
        body = resp.json()["data"]
        assert body["mode"] == "published"
        assert body["revision_id"] == "rev-1"
        kwargs = mod.create_job.await_args.kwargs
        assert kwargs["configuration_revision_id"] == "rev-1"
        assert kwargs["execution_spec"] is None

    def test_invalid_schema_rejected_with_422(self, client, monkeypatch):
        bad = _draft_config(
            definition={"target": "per_doc", "data_schema": {"anyOf": []}, "fields": []}
        )
        mod = _patch(monkeypatch, bad)

        resp = client.post(
            "/api/extract/jobs",
            json={"configuration_id": "cfg-1", "document_ids": [DOCUMENT_ID]},
        )

        assert resp.status_code == 422
        mod.create_job.assert_not_awaited()

    def test_per_table_row_rejected_with_422(self, client, monkeypatch):
        mod = _patch(
            monkeypatch,
            _draft_config(
                definition={"target": "per_table_row", "data_schema": SCHEMA, "fields": []}
            ),
        )

        resp = client.post(
            "/api/extract/jobs",
            json={"configuration_id": "cfg-1", "document_ids": [DOCUMENT_ID]},
        )

        assert resp.status_code == 422
        mod.create_job.assert_not_awaited()

    def test_unauthenticated_rejected(self, unauth_client):
        resp = unauth_client.post(
            "/api/extract/jobs",
            json={"configuration_id": "cfg-1", "document_ids": [DOCUMENT_ID]},
        )
        assert resp.status_code == 401


class TestExtractResultReads:
    def test_document_result_404_when_missing(self, client, monkeypatch):
        from api.routes import extract as extract_mod

        monkeypatch.setattr(
            extract_mod.supabase_service, "get_document", AsyncMock(return_value=_document())
        )
        monkeypatch.setattr(
            extract_mod.result_service, "list_results", AsyncMock(return_value=[])
        )

        resp = client.get(f"/api/documents/{DOCUMENT_ID}/extract-result")
        assert resp.status_code == 404

    def test_document_result_returns_data_and_engine(self, client, monkeypatch):
        from api.routes import extract as extract_mod

        monkeypatch.setattr(
            extract_mod.supabase_service, "get_document", AsyncMock(return_value=_document())
        )
        monkeypatch.setattr(
            extract_mod.result_service,
            "list_results",
            AsyncMock(
                return_value=[
                    {
                        "id": "res-1",
                        "job_id": "job-1",
                        "data": {"report_no": "WT-1"},
                        "engine": {"target": "per_doc"},
                    }
                ]
            ),
        )

        resp = client.get(f"/api/documents/{DOCUMENT_ID}/extract-result")

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == {"report_no": "WT-1"}
        assert body["engine"]["target"] == "per_doc"

    def test_job_result_does_not_fall_back_to_document(self, client, monkeypatch):
        from api.routes import extract as extract_mod

        monkeypatch.setattr(
            extract_mod.supabase_service, "get_document", AsyncMock(return_value=_document())
        )
        monkeypatch.setattr(
            extract_mod,
            "get_job",
            AsyncMock(
                return_value={
                    "job_id": "job-1",
                    "tenant_id": TENANT_ID,
                    "created_by": USER_ID,
                    "document_ids": [DOCUMENT_ID],
                    "status": "failed",
                }
            ),
        )
        monkeypatch.setattr(
            extract_mod.result_service, "list_results", AsyncMock(return_value=[])
        )

        resp = client.get("/api/jobs/job-1/extract-result")
        assert resp.status_code == 404
