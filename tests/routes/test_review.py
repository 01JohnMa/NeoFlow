# tests/routes/test_review.py
"""文档审核路由测试 — PUT /api/documents/{id}/validate、/reject、/rename"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from tests.conftest import DOCUMENT_ID, TENANT_ID, USER_ID, MOCK_DOCUMENT


def _patch_supabase():
    return patch("api.routes.documents.review.supabase_service")


def _mock_doc_query(mock_svc, doc=None):
    """配置 supabase_service.client.table("documents").select().eq().execute()"""
    result = MagicMock()
    result.data = [doc] if doc else []
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.update.return_value = chain
    chain.execute.return_value = result
    mock_svc.client.table.return_value = chain
    return chain


# ============ validate ============

class TestValidateDocument:
    """PUT /api/documents/{document_id}/validate"""

    def test_validate_success(self, client):
        """文档所有者审核通过"""
        with _patch_supabase() as mock_svc, \
             patch("api.routes.documents.review.template_service") as mock_ts:
            chain = _mock_doc_query(mock_svc, MOCK_DOCUMENT)
            mock_svc.get_table_name.return_value = "inspection_reports"
            mock_ts.get_template_with_details = AsyncMock(return_value=None)
            mock_ts.get_template_by_code = AsyncMock(return_value=None)
            resp = client.put(
                f"/api/documents/{DOCUMENT_ID}/validate",
                json={
                    "document_type": "inspection_report",
                    "data": {"sample_name": "LED灯", "is_validated": True},
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_id"] == DOCUMENT_ID

    def test_validate_not_found(self, client):
        """文档不存在返回 404"""
        with _patch_supabase() as mock_svc:
            _mock_doc_query(mock_svc, None)
            resp = client.put(
                f"/api/documents/{DOCUMENT_ID}/validate",
                json={"document_type": "inspection_report", "data": {}},
            )
        assert resp.status_code == 404

    def test_validate_other_user_denied(self, client):
        """普通用户无法审核他人文档"""
        other_doc = {**MOCK_DOCUMENT, "user_id": "other-user-999", "tenant_id": "other-tenant"}
        with _patch_supabase() as mock_svc:
            _mock_doc_query(mock_svc, other_doc)
            resp = client.put(
                f"/api/documents/{DOCUMENT_ID}/validate",
                json={"document_type": "inspection_report", "data": {}},
            )
        assert resp.status_code == 404

    def test_validate_unauthenticated(self, unauth_client):
        """未认证返回 401"""
        resp = unauth_client.put(
            f"/api/documents/{DOCUMENT_ID}/validate",
            json={"document_type": "inspection_report", "data": {}},
        )
        assert resp.status_code == 401


# ============ reject ============

class TestRejectDocument:
    """PUT /api/documents/{document_id}/reject"""

    def test_reject_success(self, client):
        """文档所有者打回"""
        with _patch_supabase() as mock_svc:
            _mock_doc_query(mock_svc, MOCK_DOCUMENT)
            resp = client.put(
                f"/api/documents/{DOCUMENT_ID}/reject",
                json={"reason": "数据有误"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_id"] == DOCUMENT_ID

    def test_reject_not_found(self, client):
        """文档不存在返回 404"""
        with _patch_supabase() as mock_svc:
            _mock_doc_query(mock_svc, None)
            resp = client.put(
                f"/api/documents/{DOCUMENT_ID}/reject",
                json={"reason": "数据有误"},
            )
        assert resp.status_code == 404

    def test_reject_unauthenticated(self, unauth_client):
        """未认证返回 401"""
        resp = unauth_client.put(
            f"/api/documents/{DOCUMENT_ID}/reject",
            json={"reason": "数据有误"},
        )
        assert resp.status_code == 401


# ============ rename ============

class TestRenameDocument:
    """PUT /api/documents/{document_id}/rename"""

    def test_rename_success(self, client):
        """重命名成功"""
        with _patch_supabase() as mock_svc:
            _mock_doc_query(mock_svc, MOCK_DOCUMENT)
            mock_svc.update_display_name = AsyncMock(return_value=MOCK_DOCUMENT)
            resp = client.put(
                f"/api/documents/{DOCUMENT_ID}/rename",
                json={"display_name": "新名称"},
            )
        assert resp.status_code == 200

    def test_rename_not_found(self, client):
        """文档不存在返回 404"""
        with _patch_supabase() as mock_svc:
            _mock_doc_query(mock_svc, None)
            resp = client.put(
                f"/api/documents/{DOCUMENT_ID}/rename",
                json={"display_name": "新名称"},
            )
        assert resp.status_code == 404

    def test_rename_unauthenticated(self, unauth_client):
        """未认证返回 401"""
        resp = unauth_client.put(
            f"/api/documents/{DOCUMENT_ID}/rename",
            json={"display_name": "新名称"},
        )
        assert resp.status_code == 401
