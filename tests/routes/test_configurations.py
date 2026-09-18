# tests/routes/test_configurations.py
"""配置管理路由测试 — 权限、租户隔离、生命周期映射。"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from services.configuration_service import ConfigurationStateError
from tests.conftest import TENANT_ID, USER_ID

OTHER_TENANT_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
CONFIG_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
REVISION_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
OTHER_REVISION_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"

OWN_CONFIG = {
    "id": CONFIG_ID,
    "tenant_id": TENANT_ID,
    "project_id": "pppppppp-pppp-4ppp-8ppp-pppppppppppp",
    "name": "检测报告",
    "status": "published",
    "type": "extract",
    "current_revision_id": REVISION_ID,
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
def admin_client():
    from api.main import app

    with _make_client("tenant_admin") as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def super_admin_client():
    from api.main import app

    with _make_client("super_admin", tenant_id=None) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _patch_service():
    return patch("api.routes.configurations.configuration_service")


class TestPermissions:
    def test_viewer_cannot_list(self, client):
        resp = client.get("/api/admin/configurations")
        assert resp.status_code == 403

    def test_viewer_cannot_create(self, client):
        resp = client.post("/api/admin/configurations", json={"name": "配置"})
        assert resp.status_code == 403

    def test_unauthenticated_rejected(self, unauth_client):
        resp = unauth_client.get("/api/admin/configurations")
        assert resp.status_code == 401

    def test_invalid_type_rejected(self, admin_client):
        resp = admin_client.post(
            "/api/admin/configurations",
            json={"name": "配置", "type": "unknown"},
        )
        assert resp.status_code == 422


class TestCreate:
    def test_tenant_admin_forced_to_own_tenant(self, admin_client):
        with _patch_service() as mock_svc:
            mock_svc.create_configuration = AsyncMock(return_value={"id": CONFIG_ID, "status": "draft"})
            resp = admin_client.post(
                "/api/admin/configurations",
                json={
                    "name": "检测报告",
                    "definition": {"extraction_prompt": "抽取字段"},
                },
            )

        assert resp.status_code == 201
        payload = mock_svc.create_configuration.await_args.args[0]
        assert payload["tenant_id"] == TENANT_ID
        assert payload["definition"]["extraction_prompt"] == "抽取字段"
        assert mock_svc.create_configuration.await_args.kwargs["created_by"] == USER_ID

    def test_tenant_admin_cannot_target_other_tenant(self, admin_client):
        with _patch_service():
            resp = admin_client.post(
                "/api/admin/configurations",
                json={"name": "检测报告", "tenant_id": OTHER_TENANT_ID},
            )
        assert resp.status_code == 403

    def test_super_admin_without_tenant_rejected(self, super_admin_client):
        with _patch_service():
            resp = super_admin_client.post(
                "/api/admin/configurations",
                json={"name": "配置"},
            )
        assert resp.status_code == 400

    def test_super_admin_can_target_tenant(self, super_admin_client):
        with _patch_service() as mock_svc:
            mock_svc.create_configuration = AsyncMock(return_value={"id": CONFIG_ID})
            resp = super_admin_client.post(
                "/api/admin/configurations",
                json={"name": "配置", "tenant_id": OTHER_TENANT_ID},
            )

        assert resp.status_code == 201
        payload = mock_svc.create_configuration.await_args.args[0]
        assert payload["tenant_id"] == OTHER_TENANT_ID


class TestListAndGet:
    def test_tenant_admin_scope_ignores_query_tenant(self, admin_client):
        with _patch_service() as mock_svc:
            mock_svc.list_configurations = AsyncMock(return_value=[OWN_CONFIG])
            resp = admin_client.get(f"/api/admin/configurations?tenant_id={OTHER_TENANT_ID}")

        assert resp.status_code == 200
        assert resp.json() == [OWN_CONFIG]
        assert mock_svc.list_configurations.await_args.kwargs["tenant_id"] == TENANT_ID

    def test_super_admin_can_filter_tenant(self, super_admin_client):
        with _patch_service() as mock_svc:
            mock_svc.list_configurations = AsyncMock(return_value=[])
            super_admin_client.get(f"/api/admin/configurations?tenant_id={OTHER_TENANT_ID}")

        assert mock_svc.list_configurations.await_args.kwargs["tenant_id"] == OTHER_TENANT_ID

    def test_cross_tenant_get_forbidden(self, admin_client):
        with _patch_service() as mock_svc:
            mock_svc.get_configuration = AsyncMock(
                return_value={**OWN_CONFIG, "tenant_id": OTHER_TENANT_ID}
            )
            resp = admin_client.get(f"/api/admin/configurations/{CONFIG_ID}")

        assert resp.status_code == 403

    def test_missing_get_returns_404(self, admin_client):
        with _patch_service() as mock_svc:
            mock_svc.get_configuration = AsyncMock(return_value=None)
            resp = admin_client.get(f"/api/admin/configurations/{CONFIG_ID}")

        assert resp.status_code == 404

    def test_get_returns_detail_with_revision(self, admin_client):
        revision = {"id": REVISION_ID, "revision_number": 1, "definition": {}}
        with _patch_service() as mock_svc:
            mock_svc.get_configuration = AsyncMock(return_value=OWN_CONFIG)
            mock_svc.get_configuration_detail = AsyncMock(
                return_value={**OWN_CONFIG, "current_revision": revision}
            )
            resp = admin_client.get(f"/api/admin/configurations/{CONFIG_ID}")

        assert resp.status_code == 200
        assert resp.json()["current_revision"] == revision


class TestUpdatePublishArchive:
    def test_update_requires_body(self, admin_client):
        with _patch_service() as mock_svc:
            mock_svc.get_configuration = AsyncMock(return_value=OWN_CONFIG)
            resp = admin_client.put(f"/api/admin/configurations/{CONFIG_ID}", json={})

        assert resp.status_code == 400

    def test_update_archived_conflict(self, admin_client):
        with _patch_service() as mock_svc:
            mock_svc.get_configuration = AsyncMock(return_value=OWN_CONFIG)
            mock_svc.update_configuration = AsyncMock(
                side_effect=ConfigurationStateError("已归档的配置不可修改")
            )
            resp = admin_client.put(
                f"/api/admin/configurations/{CONFIG_ID}",
                json={"name": "新名字"},
            )

        assert resp.status_code == 409

    def test_publish_returns_configuration_and_revision(self, admin_client):
        revision = {"id": REVISION_ID, "revision_number": 1}
        with _patch_service() as mock_svc:
            mock_svc.get_configuration = AsyncMock(return_value={**OWN_CONFIG, "status": "draft"})
            mock_svc.publish_configuration = AsyncMock(
                return_value={"configuration": {**OWN_CONFIG, "status": "published"}, "revision": revision}
            )
            resp = admin_client.post(f"/api/admin/configurations/{CONFIG_ID}/publish")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["configuration"]["status"] == "published"
        assert data["revision"]["revision_number"] == 1
        assert mock_svc.publish_configuration.await_args.kwargs["created_by"] == USER_ID

    def test_publish_already_published_conflict(self, admin_client):
        with _patch_service() as mock_svc:
            mock_svc.get_configuration = AsyncMock(return_value=OWN_CONFIG)
            mock_svc.publish_configuration = AsyncMock(
                side_effect=ConfigurationStateError("配置已发布且无待发布的修改")
            )
            resp = admin_client.post(f"/api/admin/configurations/{CONFIG_ID}/publish")

        assert resp.status_code == 409

    def test_archive_returns_configuration(self, admin_client):
        with _patch_service() as mock_svc:
            mock_svc.get_configuration = AsyncMock(return_value=OWN_CONFIG)
            mock_svc.archive_configuration = AsyncMock(
                return_value={**OWN_CONFIG, "status": "archived"}
            )
            resp = admin_client.post(f"/api/admin/configurations/{CONFIG_ID}/archive")

        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "archived"


class TestRevisions:
    def test_list_revisions(self, admin_client):
        revisions = [
            {"id": REVISION_ID, "configuration_id": CONFIG_ID, "revision_number": 2},
            {"id": OTHER_REVISION_ID, "configuration_id": CONFIG_ID, "revision_number": 1},
        ]
        with _patch_service() as mock_svc:
            mock_svc.get_configuration = AsyncMock(return_value=OWN_CONFIG)
            mock_svc.list_revisions = AsyncMock(return_value=revisions)
            resp = admin_client.get(f"/api/admin/configurations/{CONFIG_ID}/revisions")

        assert resp.status_code == 200
        assert [r["revision_number"] for r in resp.json()] == [2, 1]

    def test_get_revision(self, admin_client):
        revision = {"id": REVISION_ID, "configuration_id": CONFIG_ID, "definition": {"a": 1}}
        with _patch_service() as mock_svc:
            mock_svc.get_configuration = AsyncMock(return_value=OWN_CONFIG)
            mock_svc.get_revision = AsyncMock(return_value=revision)
            resp = admin_client.get(
                f"/api/admin/configurations/{CONFIG_ID}/revisions/{REVISION_ID}"
            )

        assert resp.status_code == 200
        assert resp.json()["definition"] == {"a": 1}

    def test_get_revision_from_other_configuration_404(self, admin_client):
        revision = {"id": OTHER_REVISION_ID, "configuration_id": "other-config"}
        with _patch_service() as mock_svc:
            mock_svc.get_configuration = AsyncMock(return_value=OWN_CONFIG)
            mock_svc.get_revision = AsyncMock(return_value=revision)
            resp = admin_client.get(
                f"/api/admin/configurations/{CONFIG_ID}/revisions/{OTHER_REVISION_ID}"
            )

        assert resp.status_code == 404
