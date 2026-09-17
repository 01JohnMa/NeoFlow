# tests/routes/test_results_access.py
"""Result 读取授权：继承文档权限；脱链结果仅管理员可读。"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.conftest import DOCUMENT_ID, TENANT_ID, USER_ID

RESULT_ID = "rrrrrrrr-rrrr-4rrr-8rrr-rrrrrrrrrrrr"
OTHER_USER_ID = "22222222-2222-4222-8222-222222222222"


def _result(**overrides):
    row = {
        "id": RESULT_ID,
        "tenant_id": TENANT_ID,
        "document_id": DOCUMENT_ID,
        "sample_key": "default",
        "data": {"sample_name": "kept"},
    }
    row.update(overrides)
    return row


def _document(**overrides):
    document = {
        "id": DOCUMENT_ID,
        "tenant_id": TENANT_ID,
        "user_id": USER_ID,
    }
    document.update(overrides)
    return document


@pytest.fixture
def admin_client():
    from api.main import app
    from api.dependencies.auth import CurrentUser, get_current_user

    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=USER_ID, token="t", tenant_id=TENANT_ID, role="tenant_admin"
    )
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class TestResultAccess:
    def test_owner_reads_linked_result(self, client):
        with patch("api.routes.jobs.result_service") as mock_result, \
             patch("api.routes.jobs.supabase_service") as mock_supabase:
            mock_result.get_result = AsyncMock(return_value=_result())
            mock_supabase.get_document = AsyncMock(return_value=_document())

            resp = client.get(f"/api/results/{RESULT_ID}")

        assert resp.status_code == 200
        assert resp.json()["data"]["sample_name"] == "kept"

    def test_non_owner_same_tenant_hidden(self, client):
        with patch("api.routes.jobs.result_service") as mock_result, \
             patch("api.routes.jobs.supabase_service") as mock_supabase:
            mock_result.get_result = AsyncMock(return_value=_result())
            mock_supabase.get_document = AsyncMock(
                return_value=_document(user_id=OTHER_USER_ID)
            )

            resp = client.get(f"/api/results/{RESULT_ID}")

        assert resp.status_code == 404

    def test_cross_tenant_hidden(self, client):
        with patch("api.routes.jobs.result_service") as mock_result:
            mock_result.get_result = AsyncMock(
                return_value=_result(tenant_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
            )
            resp = client.get(f"/api/results/{RESULT_ID}")

        assert resp.status_code == 404

    def test_detached_result_hidden_from_members(self, client):
        with patch("api.routes.jobs.result_service") as mock_result:
            mock_result.get_result = AsyncMock(return_value=_result(document_id=None))
            resp = client.get(f"/api/results/{RESULT_ID}")

        assert resp.status_code == 404

    def test_detached_result_readable_by_admin(self, admin_client):
        with patch("api.routes.jobs.result_service") as mock_result:
            mock_result.get_result = AsyncMock(return_value=_result(document_id=None))
            resp = admin_client.get(f"/api/results/{RESULT_ID}")

        assert resp.status_code == 200
