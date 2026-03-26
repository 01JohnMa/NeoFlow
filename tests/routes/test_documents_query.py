# tests/routes/test_documents_query.py
"""文档查询路由测试 — GET /api/documents/{id}/status、/result、/、DELETE"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock

from tests.conftest import DOCUMENT_ID, TENANT_ID, USER_ID, MOCK_DOCUMENT, TEMPLATE_ID


def _mock_supabase_doc(doc=None):
    """构造 supabase_service.client.table().select()...execute() 的 mock"""
    result = MagicMock()
    result.data = [doc] if doc else []
    result.count = 1 if doc else 0
    chain = MagicMock()
    for m in ("select", "eq", "neq", "order", "range", "limit", "filter", "update", "delete"):
        getattr(chain, m).return_value = chain
    chain.execute.return_value = result
    return chain


def _patch_supabase():
    """patch 路由引用处的 supabase_service，绕过 @property client"""
    return patch("api.routes.documents.query.supabase_service")


class TestGetDocumentStatus:
    """GET /api/documents/{document_id}/status"""

    def test_returns_status_for_own_document(self, client):
        """普通用户可以查询自己的文档状态"""
        chain = _mock_supabase_doc(MOCK_DOCUMENT)
        with _patch_supabase() as mock_svc:
            mock_svc.client.table.return_value = chain
            resp = client.get(f"/api/documents/{DOCUMENT_ID}/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_id"] == DOCUMENT_ID
        assert data["status"] == "completed"

    def test_returns_404_for_nonexistent_document(self, client):
        """文档不存在时返回 404"""
        chain = _mock_supabase_doc(None)
        with _patch_supabase() as mock_svc:
            mock_svc.client.table.return_value = chain
            resp = client.get(f"/api/documents/{DOCUMENT_ID}/status")
        assert resp.status_code == 404

    def test_returns_404_for_other_users_document(self, client):
        """普通用户无法查询他人文档（返回 404）"""
        other_doc = {**MOCK_DOCUMENT, "user_id": "other-user-999"}
        chain = _mock_supabase_doc(other_doc)
        with _patch_supabase() as mock_svc:
            mock_svc.client.table.return_value = chain
            resp = client.get(f"/api/documents/{DOCUMENT_ID}/status")
        assert resp.status_code == 404

    def test_admin_can_access_tenant_document(self, admin_client):
        """租户管理员可以查询本租户任意文档"""
        doc = {**MOCK_DOCUMENT, "user_id": "other-user-in-tenant"}
        chain = _mock_supabase_doc(doc)
        with _patch_supabase() as mock_svc:
            mock_svc.client.table.return_value = chain
            resp = admin_client.get(f"/api/documents/{DOCUMENT_ID}/status")
        assert resp.status_code == 200

    def test_unauthenticated_returns_401(self, unauth_client):
        """未认证请求返回 401"""
        resp = unauth_client.get(f"/api/documents/{DOCUMENT_ID}/status")
        assert resp.status_code == 401

    def test_status_response_fields(self, client):
        """响应体包含必要字段"""
        chain = _mock_supabase_doc(MOCK_DOCUMENT)
        with _patch_supabase() as mock_svc:
            mock_svc.client.table.return_value = chain
            resp = client.get(f"/api/documents/{DOCUMENT_ID}/status")
        data = resp.json()
        for field in ("document_id", "status", "document_type", "created_at"):
            assert field in data, f"缺少字段: {field}"


class TestGetExtractionResult:
    """GET /api/documents/{document_id}/result"""

    def _setup_result_mock(self, mock_svc, doc=None, result_data=None):
        """配置 supabase_service 的两次 table() 调用"""
        doc_chain = _mock_supabase_doc(doc or MOCK_DOCUMENT)
        result_chain = _mock_supabase_doc(result_data or {"id": "r1", "document_id": DOCUMENT_ID,
                                                           "is_validated": False})
        mock_svc.client.table.side_effect = [doc_chain, result_chain, doc_chain]
        mock_svc.get_table_name.return_value = "inspection_reports"

    def test_returns_result_for_completed_document(self, client):
        """已完成文档返回 200 和提取结果"""
        with _patch_supabase() as mock_svc, \
             patch("api.routes.documents.query.template_service.get_template_fields",
                   new_callable=AsyncMock, return_value=[]):
            self._setup_result_mock(mock_svc)
            resp = client.get(f"/api/documents/{DOCUMENT_ID}/result")
        assert resp.status_code == 200
        data = resp.json()
        assert "document_id" in data
        assert "extraction_data" in data

    def test_returns_202_for_processing_document(self, client):
        """处理中文档返回 202"""
        processing_doc = {**MOCK_DOCUMENT, "status": "processing", "document_type": None}
        chain = _mock_supabase_doc(processing_doc)
        with _patch_supabase() as mock_svc:
            mock_svc.client.table.return_value = chain
            mock_svc.resolve_table_name.return_value = None
            resp = client.get(f"/api/documents/{DOCUMENT_ID}/result")
        assert resp.status_code == 202

    def test_returns_202_for_queued_document(self, client):
        """排队中文档返回 202"""
        queued_doc = {**MOCK_DOCUMENT, "status": "queued", "document_type": None}
        chain = _mock_supabase_doc(queued_doc)
        with _patch_supabase() as mock_svc:
            mock_svc.client.table.return_value = chain
            mock_svc.resolve_table_name.return_value = None
            resp = client.get(f"/api/documents/{DOCUMENT_ID}/result")
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "queued"

    def test_returns_result_for_pending_review_document(self, client):
        """待审核文档也应返回 200 和提取结果"""
        pending_doc = {**MOCK_DOCUMENT, "status": "pending_review", "document_type": "检测报告"}
        with _patch_supabase() as mock_svc, \
             patch("api.routes.documents.query.template_service.get_template_fields",
                   new_callable=AsyncMock, return_value=[]):
            self._setup_result_mock(mock_svc, doc=pending_doc)
            mock_svc.resolve_table_name.return_value = "inspection_reports"
            resp = client.get(f"/api/documents/{DOCUMENT_ID}/result")
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_id"] == DOCUMENT_ID
        assert "extraction_data" in data

    def test_returns_404_for_nonexistent_document(self, client):
        """文档不存在返回 404"""
        chain = _mock_supabase_doc(None)
        with _patch_supabase() as mock_svc:
            mock_svc.client.table.return_value = chain
            resp = client.get(f"/api/documents/{DOCUMENT_ID}/result")
        assert resp.status_code == 404

    def test_unauthenticated_returns_401(self, unauth_client):
        """未认证请求返回 401"""
        resp = unauth_client.get(f"/api/documents/{DOCUMENT_ID}/result")
        assert resp.status_code == 401


class TestListDocuments:
    """GET /api/documents/"""

    def _setup_list_mock(self, mock_svc, items=None, total=0):
        """配置列表查询和计数查询的 mock"""
        list_result = MagicMock()
        list_result.data = items or []
        count_result = MagicMock()
        count_result.data = items or []
        count_result.count = total

        chain = MagicMock()
        for m in ("select", "eq", "order", "range", "limit", "filter"):
            getattr(chain, m).return_value = chain
        chain.execute.side_effect = [list_result, count_result]
        mock_svc.client.table.return_value = chain

    def test_returns_document_list(self, client):
        """返回文档列表"""
        with _patch_supabase() as mock_svc:
            self._setup_list_mock(mock_svc, items=[MOCK_DOCUMENT], total=1)
            resp = client.get("/api/documents/")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data

    def test_empty_list(self, client):
        """无文档时返回空列表"""
        with _patch_supabase() as mock_svc:
            self._setup_list_mock(mock_svc, items=[], total=0)
            resp = client.get("/api/documents/")
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_pagination_params(self, client):
        """分页参数正确传递"""
        with _patch_supabase() as mock_svc:
            self._setup_list_mock(mock_svc, items=[], total=0)
            resp = client.get("/api/documents/?page=2&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 2
        assert data["limit"] == 10

    def test_has_more_flag(self, client):
        """has_more 字段正确计算"""
        with _patch_supabase() as mock_svc:
            self._setup_list_mock(mock_svc, items=[MOCK_DOCUMENT] * 20, total=50)
            resp = client.get("/api/documents/?page=1&limit=20")
        data = resp.json()
        assert data["has_more"] is True

    def test_unauthenticated_returns_401(self, unauth_client):
        """未认证请求返回 401"""
        resp = unauth_client.get("/api/documents/")
        assert resp.status_code == 401

    def test_filter_by_status(self, client):
        """按 status 过滤"""
        with _patch_supabase() as mock_svc:
            self._setup_list_mock(mock_svc, items=[MOCK_DOCUMENT], total=1)
            resp = client.get("/api/documents/?status=completed")
        assert resp.status_code == 200


class TestDeleteDocument:
    """DELETE /api/documents/{document_id}"""

    def test_delete_own_document(self, client):
        """用户可以删除自己的文档"""
        chain = _mock_supabase_doc(MOCK_DOCUMENT)
        with _patch_supabase() as mock_svc, \
             patch("os.path.exists", return_value=False):
            mock_svc.client.table.return_value = chain
            resp = client.delete(f"/api/documents/{DOCUMENT_ID}")
        assert resp.status_code == 200
        assert resp.json()["document_id"] == DOCUMENT_ID

    def test_delete_nonexistent_returns_404(self, client):
        """删除不存在的文档返回 404"""
        chain = _mock_supabase_doc(None)
        with _patch_supabase() as mock_svc:
            mock_svc.client.table.return_value = chain
            resp = client.delete(f"/api/documents/{DOCUMENT_ID}")
        assert resp.status_code == 404

    def test_delete_unauthenticated_returns_401(self, unauth_client):
        """未认证请求返回 401"""
        resp = unauth_client.delete(f"/api/documents/{DOCUMENT_ID}")
        assert resp.status_code == 401

    def test_delete_removes_file(self, client):
        """删除文档时同时删除磁盘文件"""
        chain = _mock_supabase_doc(MOCK_DOCUMENT)
        with _patch_supabase() as mock_svc, \
             patch("os.path.exists", return_value=True), \
             patch("os.remove") as mock_remove:
            mock_svc.client.table.return_value = chain
            client.delete(f"/api/documents/{DOCUMENT_ID}")
        mock_remove.assert_called_once()
