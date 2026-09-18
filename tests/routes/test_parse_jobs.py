# tests/routes/test_parse_jobs.py
"""Parse 能力入口路由测试 — D4 状态映射、参数校验与幂等头传递。"""

from unittest.mock import AsyncMock, patch

from tests.conftest import DOCUMENT_ID, TENANT_ID, USER_ID

OTHER_DOCUMENT_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"


def _ok_response(**overrides):
    payload = {
        "status": "ok",
        "request_id": "req-1",
        "job_ids": ["job-1"],
        "reason": None,
    }
    payload.update(overrides)
    return payload


def _patch_service():
    return patch("api.routes.parse.parse_request_service")


class TestCreateParseJobs:
    def test_unauthenticated_rejected(self, unauth_client):
        resp = unauth_client.post("/api/parse/jobs", json={"document_ids": [DOCUMENT_ID]})
        assert resp.status_code == 401

    def test_missing_tenant_forbidden(self):
        from api.dependencies.auth import CurrentUser, get_current_user
        from api.main import app
        from fastapi.testclient import TestClient

        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            user_id=USER_ID, token="t", tenant_id=None, role="user"
        )
        try:
            with TestClient(app) as client:
                resp = client.post("/api/parse/jobs", json={"document_ids": [DOCUMENT_ID]})
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 403

    def test_creates_jobs_and_passes_normalized_request(self, client):
        with _patch_service() as mock_svc:
            mock_svc.admit = AsyncMock(return_value=_ok_response())
            resp = client.post(
                "/api/parse/jobs",
                headers={"Idempotency-Key": "K1"},
                json={
                    "document_ids": [OTHER_DOCUMENT_ID, DOCUMENT_ID],
                    "parse_mode": "vlm",
                    "page_ranges": {"target_pages": "3,1-2"},
                    "language": "en",
                    "enable_formula": False,
                    "enable_table": True,
                    "remove_watermark": True,
                    "watermark_keywords": ["COPY", "COPY"],
                },
            )

        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["job_ids"] == ["job-1"]
        assert data["reused"] is False

        kwargs = mock_svc.admit.await_args.kwargs
        assert kwargs["tenant_id"] == TENANT_ID
        assert kwargs["requester_id"] == USER_ID
        assert kwargs["is_admin"] is False
        assert kwargs["document_ids"] == sorted([DOCUMENT_ID, OTHER_DOCUMENT_ID])
        assert kwargs["parse_mode"] == "vlm"
        assert kwargs["target_pages"] == [1, 2, 3]
        assert kwargs["idempotency_key"] == "K1"
        assert kwargs["options"] == {
            "language": "en",
            "enable_formula": False,
            "enable_table": True,
            "remove_watermark": True,
            "watermark_keywords": ["COPY"],
        }

    def test_omitted_options_are_not_injected(self, client):
        with _patch_service() as mock_svc:
            mock_svc.admit = AsyncMock(return_value=_ok_response())
            resp = client.post(
                "/api/parse/jobs", json={"document_ids": [DOCUMENT_ID]}
            )

        assert resp.status_code == 201
        assert mock_svc.admit.await_args.kwargs["options"] == {}

    def test_unsupported_language_rejected_before_admission(self, client):
        with _patch_service() as mock_svc:
            mock_svc.admit = AsyncMock(return_value=_ok_response())
            resp = client.post(
                "/api/parse/jobs",
                json={"document_ids": [DOCUMENT_ID], "language": "klingon"},
            )

        assert resp.status_code == 422
        mock_svc.admit.assert_not_awaited()

    def test_idempotent_replay_maps_to_200(self, client):
        with _patch_service() as mock_svc:
            mock_svc.admit = AsyncMock(
                return_value=_ok_response(status="reused", reason="idempotent_replay")
            )
            resp = client.post(
                "/api/parse/jobs",
                headers={"Idempotency-Key": "K1"},
                json={"document_ids": [DOCUMENT_ID]},
            )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["reused"] is True
        assert data["reuse_reason"] == "idempotent_replay"

    def test_active_reuse_maps_to_200(self, client):
        with _patch_service() as mock_svc:
            mock_svc.admit = AsyncMock(
                return_value=_ok_response(status="reused", reason="active_request_reused")
            )
            resp = client.post(
                "/api/parse/jobs",
                json={"document_ids": [DOCUMENT_ID], "parse_mode": "pipeline"},
            )

        assert resp.status_code == 200
        assert resp.json()["data"]["reuse_reason"] == "active_request_reused"

    def test_conflict_maps_to_409(self, client):
        with _patch_service() as mock_svc:
            mock_svc.admit = AsyncMock(
                return_value=_ok_response(status="conflict", reason="input_overlaps_active_request")
            )
            resp = client.post("/api/parse/jobs", json={"document_ids": [DOCUMENT_ID]})

        assert resp.status_code == 409
        assert "input_overlaps_active_request" in resp.json()["error"]

    def test_document_unavailable_maps_to_404(self, client):
        with _patch_service() as mock_svc:
            mock_svc.admit = AsyncMock(
                return_value=_ok_response(status="not_found", reason="document_unavailable")
            )
            resp = client.post("/api/parse/jobs", json={"document_ids": [DOCUMENT_ID]})

        assert resp.status_code == 404

    def test_limit_exceeded_maps_to_422(self, client):
        with _patch_service() as mock_svc:
            mock_svc.admit = AsyncMock(
                return_value=_ok_response(status="limit_exceeded", reason="max_active_jobs_per_tenant")
            )
            resp = client.post("/api/parse/jobs", json={"document_ids": [DOCUMENT_ID]})

        assert resp.status_code == 422

    def test_invalid_target_pages_rejected_before_admission(self, client):
        with _patch_service() as mock_svc:
            mock_svc.admit = AsyncMock(return_value=_ok_response())
            resp = client.post(
                "/api/parse/jobs",
                json={"document_ids": [DOCUMENT_ID], "page_ranges": {"target_pages": "9-1"}},
            )

        assert resp.status_code == 422
        mock_svc.admit.assert_not_awaited()

    def test_unknown_fields_rejected(self, client):
        with _patch_service() as mock_svc:
            mock_svc.admit = AsyncMock(return_value=_ok_response())
            resp = client.post(
                "/api/parse/jobs",
                json={"document_ids": [DOCUMENT_ID], "max_pages": 5},
            )

        assert resp.status_code == 422
        mock_svc.admit.assert_not_awaited()

    def test_empty_document_ids_rejected(self, client):
        with _patch_service() as mock_svc:
            mock_svc.admit = AsyncMock(return_value=_ok_response())
            resp = client.post("/api/parse/jobs", json={"document_ids": []})

        assert resp.status_code == 422
        mock_svc.admit.assert_not_awaited()

    def test_bad_parse_mode_rejected(self, client):
        with _patch_service() as mock_svc:
            mock_svc.admit = AsyncMock(return_value=_ok_response())
            resp = client.post(
                "/api/parse/jobs",
                json={"document_ids": [DOCUMENT_ID], "parse_mode": "agentic"},
            )

        assert resp.status_code == 422
        mock_svc.admit.assert_not_awaited()
