# tests/routes/test_jobs.py
"""Job/Result 路由测试 — 创建、状态查询、结果读取、租户隔离。"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.conftest import DOCUMENT_ID, TENANT_ID, USER_ID

OTHER_TENANT_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
CONFIG_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
REVISION_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
JOB_ID = "99999999-9999-4999-8999-999999999999"
RESULT_ID = "88888888-8888-4888-8888-888888888888"

REVISION = {"id": REVISION_ID, "configuration_id": CONFIG_ID, "revision_number": 1}
CONFIGURATION = {
    "id": CONFIG_ID,
    "tenant_id": TENANT_ID,
    "status": "published",
    "type": "extract",
}
JOB = {
    "job_id": JOB_ID,
    "tenant_id": TENANT_ID,
    "status": "queued",
    "created_by": USER_ID,
    "document_ids": [DOCUMENT_ID],
}
RESULT = {
    "id": RESULT_ID,
    "tenant_id": TENANT_ID,
    "job_id": JOB_ID,
    "document_id": DOCUMENT_ID,
    "data": {"sample_name": "LED灯"},
    "field_meta": {},
    "review_state": "pending",
}


def _user(role: str, tenant_id=None):
    from api.dependencies.auth import CurrentUser

    return CurrentUser(
        user_id=USER_ID,
        token="test-token",
        tenant_id=tenant_id,
        role=role,
    )


def _make_client(role: str, tenant_id=TENANT_ID):
    from api.main import app
    from api.dependencies.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: _user(role, tenant_id)
    return TestClient(app)


@pytest.fixture
def user_client():
    from api.main import app

    with _make_client("user") as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def super_admin_client():
    from api.main import app

    with _make_client("super_admin", tenant_id=None) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class TestCreateJob:
    def test_unauthenticated_rejected(self, unauth_client):
        resp = unauth_client.post(
            "/api/jobs",
            json={"configuration_revision_id": REVISION_ID},
        )
        assert resp.status_code == 401

    def test_create_pins_revision_and_tenant(self, user_client):
        with patch("api.routes.jobs.configuration_service") as mock_svc, \
             patch("api.routes.jobs.supabase_service") as mock_supabase, \
             patch("api.routes.jobs.create_job", new_callable=AsyncMock, return_value=JOB_ID) as mock_create, \
             patch("api.routes.jobs.get_job", new_callable=AsyncMock, return_value=JOB):
            mock_svc.get_revision = AsyncMock(return_value=REVISION)
            mock_svc.get_configuration = AsyncMock(return_value=CONFIGURATION)
            mock_supabase.get_document = AsyncMock(
                return_value={"id": DOCUMENT_ID, "tenant_id": TENANT_ID}
            )

            resp = user_client.post(
                "/api/jobs",
                json={"configuration_revision_id": REVISION_ID, "document_ids": [DOCUMENT_ID]},
            )

        assert resp.status_code == 201
        assert resp.json()["data"]["job_id"] == JOB_ID
        kwargs = mock_create.await_args.kwargs
        assert kwargs["tenant_id"] == TENANT_ID
        assert kwargs["configuration_revision_id"] == REVISION_ID
        assert kwargs["created_by"] == USER_ID
        assert kwargs["related_document_ids"] == [DOCUMENT_ID]

    def test_missing_revision_returns_404(self, user_client):
        with patch("api.routes.jobs.configuration_service") as mock_svc:
            mock_svc.get_revision = AsyncMock(return_value=None)
            resp = user_client.post(
                "/api/jobs",
                json={"configuration_revision_id": REVISION_ID},
            )
        assert resp.status_code == 404

    def test_cross_tenant_configuration_forbidden(self, user_client):
        with patch("api.routes.jobs.configuration_service") as mock_svc:
            mock_svc.get_revision = AsyncMock(return_value=REVISION)
            mock_svc.get_configuration = AsyncMock(
                return_value={**CONFIGURATION, "tenant_id": OTHER_TENANT_ID}
            )
            resp = user_client.post(
                "/api/jobs",
                json={"configuration_revision_id": REVISION_ID},
            )
        assert resp.status_code == 403

    def test_archived_configuration_conflict(self, user_client):
        with patch("api.routes.jobs.configuration_service") as mock_svc:
            mock_svc.get_revision = AsyncMock(return_value=REVISION)
            mock_svc.get_configuration = AsyncMock(
                return_value={**CONFIGURATION, "status": "archived"}
            )
            resp = user_client.post(
                "/api/jobs",
                json={"configuration_revision_id": REVISION_ID},
            )
        assert resp.status_code == 409

    def test_classify_configuration_job_is_accepted(self, user_client):
        with patch("api.routes.jobs.configuration_service") as mock_svc, \
             patch("api.routes.jobs.supabase_service") as mock_supabase, \
             patch("api.routes.jobs.create_job", new_callable=AsyncMock, return_value=JOB_ID), \
             patch("api.routes.jobs.get_job", new_callable=AsyncMock, return_value=JOB) as mock_get_job:
            mock_svc.get_revision = AsyncMock(return_value=REVISION)
            mock_svc.get_configuration = AsyncMock(
                return_value={**CONFIGURATION, "type": "classify"}
            )
            mock_supabase.get_document = AsyncMock(
                return_value={"id": DOCUMENT_ID, "tenant_id": TENANT_ID}
            )
            resp = user_client.post(
                "/api/jobs",
                json={"configuration_revision_id": REVISION_ID},
            )
        assert resp.status_code == 201
        assert resp.json()["data"]["job_id"] == JOB_ID
        mock_get_job.assert_awaited_once_with(JOB_ID)

    def test_document_from_other_tenant_returns_404(self, user_client):
        with patch("api.routes.jobs.configuration_service") as mock_svc, \
             patch("api.routes.jobs.supabase_service") as mock_supabase:
            mock_svc.get_revision = AsyncMock(return_value=REVISION)
            mock_svc.get_configuration = AsyncMock(return_value=CONFIGURATION)
            mock_supabase.get_document = AsyncMock(
                return_value={"id": DOCUMENT_ID, "tenant_id": OTHER_TENANT_ID}
            )
            resp = user_client.post(
                "/api/jobs",
                json={"configuration_revision_id": REVISION_ID, "document_ids": [DOCUMENT_ID]},
            )
        assert resp.status_code == 404


class TestGetJob:
    def test_owner_can_read_job(self, user_client):
        with patch("api.routes.jobs.get_job", new_callable=AsyncMock, return_value=JOB):
            resp = user_client.get(f"/api/jobs/{JOB_ID}")
        assert resp.status_code == 200
        assert resp.json()["job_id"] == JOB_ID

    def test_other_tenant_job_hidden(self, user_client):
        job = {**JOB, "tenant_id": OTHER_TENANT_ID}
        with patch("api.routes.jobs.get_job", new_callable=AsyncMock, return_value=job):
            resp = user_client.get(f"/api/jobs/{JOB_ID}")
        assert resp.status_code == 404

    def test_legacy_job_without_tenant_hidden_from_stranger(self, user_client):
        job = {**JOB, "tenant_id": None, "created_by": "someone-else"}
        with patch("api.routes.jobs.get_job", new_callable=AsyncMock, return_value=job):
            resp = user_client.get(f"/api/jobs/{JOB_ID}")
        assert resp.status_code == 404

    def test_super_admin_can_read_any_job(self, super_admin_client):
        job = {**JOB, "tenant_id": OTHER_TENANT_ID}
        with patch("api.routes.jobs.get_job", new_callable=AsyncMock, return_value=job):
            resp = super_admin_client.get(f"/api/jobs/{JOB_ID}")
        assert resp.status_code == 200

    def test_missing_job_returns_404(self, user_client):
        with patch("api.routes.jobs.get_job", new_callable=AsyncMock, return_value=None):
            resp = user_client.get(f"/api/jobs/{JOB_ID}")
        assert resp.status_code == 404


class TestJobResults:
    def test_list_job_results(self, user_client):
        with patch("api.routes.jobs.get_job", new_callable=AsyncMock, return_value=JOB), \
             patch("api.routes.jobs.result_service") as mock_results:
            mock_results.list_results = AsyncMock(return_value=[RESULT])
            resp = user_client.get(f"/api/jobs/{JOB_ID}/results")

        assert resp.status_code == 200
        assert resp.json() == [RESULT]
        assert mock_results.list_results.await_args.kwargs["job_id"] == JOB_ID
        assert mock_results.list_results.await_args.kwargs["tenant_id"] == TENANT_ID

    def test_cross_tenant_job_results_hidden(self, user_client):
        job = {**JOB, "tenant_id": OTHER_TENANT_ID}
        with patch("api.routes.jobs.get_job", new_callable=AsyncMock, return_value=job), \
             patch("api.routes.jobs.result_service") as mock_results:
            resp = user_client.get(f"/api/jobs/{JOB_ID}/results")

        assert resp.status_code == 404
        mock_results.list_results.assert_not_called()


class TestGetResult:
    def test_owner_can_read_result(self, user_client):
        with patch("api.routes.jobs.result_service") as mock_results, \
             patch("api.routes.jobs.supabase_service") as mock_supabase:
            mock_results.get_result = AsyncMock(return_value=RESULT)
            mock_supabase.get_document = AsyncMock(return_value={
                "id": DOCUMENT_ID,
                "tenant_id": TENANT_ID,
                "user_id": USER_ID,
            })
            resp = user_client.get(f"/api/results/{RESULT_ID}")

        assert resp.status_code == 200
        assert resp.json()["id"] == RESULT_ID

    def test_cross_tenant_result_hidden(self, user_client):
        with patch("api.routes.jobs.result_service") as mock_results:
            mock_results.get_result = AsyncMock(
                return_value={**RESULT, "tenant_id": OTHER_TENANT_ID}
            )
            resp = user_client.get(f"/api/results/{RESULT_ID}")

        assert resp.status_code == 404

    def test_missing_result_returns_404(self, user_client):
        with patch("api.routes.jobs.result_service") as mock_results:
            mock_results.get_result = AsyncMock(return_value=None)
            resp = user_client.get(f"/api/results/{RESULT_ID}")

        assert resp.status_code == 404


class TestGetParseResult:
    PARSE_DATA = {
        "pages": [{"page_no": 1, "width": 100, "height": 200, "blocks": []}],
        "markdown": "# Demo",
        "engine": {"name": "mineru", "backend": "pipeline"},
        "warnings": [],
    }

    def test_returns_parse_result_for_job(self, user_client):
        row = {**RESULT, "sample_key": "parse", "data": self.PARSE_DATA}
        with patch("api.routes.jobs.get_job", new_callable=AsyncMock, return_value=JOB), \
             patch("api.routes.jobs.result_service") as mock_results:
            mock_results.list_results = AsyncMock(return_value=[row])
            resp = user_client.get(f"/api/jobs/{JOB_ID}/parse-result")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["result_id"] == RESULT_ID
        assert body["data"] == self.PARSE_DATA
        assert mock_results.list_results.await_args.kwargs["job_id"] == JOB_ID

    def test_returns_404_without_parse_result(self, user_client):
        with patch("api.routes.jobs.get_job", new_callable=AsyncMock, return_value=JOB), \
             patch("api.routes.jobs.result_service") as mock_results:
            mock_results.list_results = AsyncMock(return_value=[])
            mock_results.get_document_parse_result = AsyncMock(return_value=None)
            resp = user_client.get(f"/api/jobs/{JOB_ID}/parse-result")

        assert resp.status_code == 404

    def test_falls_back_to_document_parse_result(self, user_client):
        """抽取内联解析的 Job 无 job_id 结果时，按关联文档取最新 ParseResult。"""
        row = {**RESULT, "job_id": None, "sample_key": "parse", "data": self.PARSE_DATA}
        with patch("api.routes.jobs.get_job", new_callable=AsyncMock, return_value=JOB), \
             patch("api.routes.jobs.result_service") as mock_results:
            mock_results.list_results = AsyncMock(return_value=[])
            mock_results.get_document_parse_result = AsyncMock(return_value=row)
            resp = user_client.get(f"/api/jobs/{JOB_ID}/parse-result")

        assert resp.status_code == 200
        assert resp.json()["data"] == self.PARSE_DATA
        assert mock_results.get_document_parse_result.await_args.args[0] == DOCUMENT_ID
        assert mock_results.get_document_parse_result.await_args.kwargs["tenant_id"] == TENANT_ID

    def test_cross_tenant_job_hidden(self, user_client):
        job = {**JOB, "tenant_id": OTHER_TENANT_ID}
        with patch("api.routes.jobs.get_job", new_callable=AsyncMock, return_value=job), \
             patch("api.routes.jobs.result_service") as mock_results:
            resp = user_client.get(f"/api/jobs/{JOB_ID}/parse-result")

        assert resp.status_code == 404
        mock_results.list_results.assert_not_called()


class TestListJobs:
    def test_lists_jobs_for_current_tenant(self, user_client):
        with patch(
            "api.routes.jobs.list_jobs",
            new_callable=AsyncMock,
            return_value=[JOB],
        ) as mock_list:
            resp = user_client.get("/api/jobs")

        assert resp.status_code == 200
        assert resp.json()["data"] == [JOB]
        assert mock_list.await_args.kwargs["tenant_id"] == TENANT_ID
        assert mock_list.await_args.kwargs["limit"] == 50

    def test_user_without_tenant_gets_empty_list(self):
        from api.main import app
        from api.dependencies.auth import get_current_user

        app.dependency_overrides[get_current_user] = lambda: _user("user", None)
        try:
            with TestClient(app) as client, patch(
                "api.routes.jobs.list_jobs",
                new_callable=AsyncMock,
                return_value=[],
            ) as mock_list:
                resp = client.get("/api/jobs")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        assert resp.json()["data"] == []
        mock_list.assert_not_awaited()

    def test_super_admin_not_scoped_to_tenant(self, super_admin_client):
        with patch(
            "api.routes.jobs.list_jobs",
            new_callable=AsyncMock,
            return_value=[JOB],
        ) as mock_list:
            resp = super_admin_client.get("/api/jobs")

        assert resp.status_code == 200
        assert mock_list.await_args.kwargs["tenant_id"] is None
