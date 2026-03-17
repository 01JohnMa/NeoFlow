# tests/routes/test_documents_upload.py
"""文档上传路由测试 — POST /api/documents/upload"""

import io
import pytest
from unittest.mock import patch, AsyncMock, MagicMock


def _pdf_file(filename="test.pdf"):
    """构造一个假 PDF 文件"""
    return ("file", (filename, io.BytesIO(b"%PDF-1.4 fake content"), "application/pdf"))


class TestDocumentUpload:
    """POST /api/documents/upload"""

    def test_upload_success(self, client):
        """合法 PDF 上传成功，返回 document_id"""
        with patch("api.routes.documents.upload.validate_file_extension", return_value=True), \
             patch("api.routes.documents.upload.save_upload_file", new_callable=AsyncMock, return_value=1024), \
             patch("api.routes.documents.upload.supabase_service.create_document", new_callable=AsyncMock), \
             patch("os.path.exists", return_value=False):
            resp = client.post(
                "/api/documents/upload",
                files=[_pdf_file()],
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "document_id" in data
        assert data["status"] == "uploaded"

    def test_upload_returns_file_name(self, client):
        """响应体包含原始文件名"""
        with patch("api.routes.documents.upload.validate_file_extension", return_value=True), \
             patch("api.routes.documents.upload.save_upload_file", new_callable=AsyncMock, return_value=512), \
             patch("api.routes.documents.upload.supabase_service.create_document", new_callable=AsyncMock), \
             patch("os.path.exists", return_value=False):
            resp = client.post(
                "/api/documents/upload",
                files=[_pdf_file("report.pdf")],
            )
        assert resp.status_code == 200
        assert resp.json()["file_name"] == "report.pdf"

    def test_upload_unsupported_extension_returns_400(self, client):
        """不支持的文件格式返回 400"""
        with patch("api.routes.documents.upload.validate_file_extension", return_value=False):
            resp = client.post(
                "/api/documents/upload",
                files=[("file", ("test.exe", io.BytesIO(b"binary"), "application/octet-stream"))],
            )
        assert resp.status_code == 400

    def test_upload_unauthenticated_returns_401(self, unauth_client):
        """未认证请求返回 401"""
        resp = unauth_client.post(
            "/api/documents/upload",
            files=[_pdf_file()],
        )
        assert resp.status_code == 401

    def test_upload_user_without_tenant_returns_500(self, app):
        """用户未关联租户时返回 500（ProcessingError）"""
        from api.dependencies.auth import get_current_user, CurrentUser
        no_tenant_user = CurrentUser(
            user_id="user-no-tenant",
            token="mock-token",
            tenant_id=None,
            role="user",
        )
        app.dependency_overrides[get_current_user] = lambda: no_tenant_user
        from fastapi.testclient import TestClient
        with TestClient(app, raise_server_exceptions=False) as c:
            with patch("api.routes.documents.upload.validate_file_extension", return_value=True):
                resp = c.post(
                    "/api/documents/upload",
                    files=[_pdf_file()],
                )
        app.dependency_overrides.clear()
        assert resp.status_code == 500

    def test_upload_db_failure_cleans_up_file(self, client):
        """数据库保存失败时清理已上传文件"""
        with patch("api.routes.documents.upload.validate_file_extension", return_value=True), \
             patch("api.routes.documents.upload.save_upload_file", new_callable=AsyncMock, return_value=1024), \
             patch("api.routes.documents.upload.supabase_service.create_document",
                   new_callable=AsyncMock, side_effect=Exception("DB error")), \
             patch("os.path.exists", return_value=True), \
             patch("os.remove") as mock_remove:
            resp = client.post(
                "/api/documents/upload",
                files=[_pdf_file()],
            )
        assert resp.status_code == 500
        mock_remove.assert_called_once()

    def test_upload_with_template_id(self, client):
        """携带 template_id 参数上传成功"""
        with patch("api.routes.documents.upload.validate_file_extension", return_value=True), \
             patch("api.routes.documents.upload.save_upload_file", new_callable=AsyncMock, return_value=1024), \
             patch("api.routes.documents.upload.supabase_service.create_document", new_callable=AsyncMock), \
             patch("os.path.exists", return_value=False):
            resp = client.post(
                "/api/documents/upload",
                files=[_pdf_file()],
                data={"template_id": "11111111-1111-1111-1111-111111111111"},
            )
        assert resp.status_code == 200
