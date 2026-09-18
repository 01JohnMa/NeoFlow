# tests/routes/test_documents_result.py
"""文档 Parse 结果读取与受保护删除路由测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from tests.conftest import DOCUMENT_ID, TENANT_ID, USER_ID


def _document(**overrides):
    document = {
        "id": DOCUMENT_ID,
        "user_id": USER_ID,
        "tenant_id": TENANT_ID,
        "status": "pending_review",
        "document_type": "inspection_report",
        "file_path": "/tmp/test.pdf",
        "file_name": "test.pdf",
        "original_file_name": "test.pdf",
        "display_name": None,
    }
    document.update(overrides)
    return document


class TestDocumentParseResult:
    """GET /api/documents/{id}/parse-result 按文档读取 Parse 产物。"""

    def test_reads_parse_result_with_document_access(self, client):
        with patch("api.routes.documents.query._run_supabase", new_callable=AsyncMock) as mock_run, \
             patch("api.routes.documents.query.result_service") as mock_result_service:
            mock_run.return_value = SimpleNamespace(data=[_document()])
            mock_result_service.get_document_parse_result = AsyncMock(return_value={
                "id": "rrrrrrrr-rrrr-4rrr-8rrr-rrrrrrrrpppp",
                "data": {"markdown": "hello", "pages": []},
            })

            response = client.get(f"/api/documents/{DOCUMENT_ID}/parse-result")

        assert response.status_code == 200
        body = response.json()
        assert body["result_id"] == "rrrrrrrr-rrrr-4rrr-8rrr-rrrrrrrrpppp"
        assert body["data"]["markdown"] == "hello"
        mock_result_service.get_document_parse_result.assert_awaited_once_with(
            DOCUMENT_ID, tenant_id=TENANT_ID
        )

    def test_404_when_parse_result_missing(self, client):
        with patch("api.routes.documents.query._run_supabase", new_callable=AsyncMock) as mock_run, \
             patch("api.routes.documents.query.result_service") as mock_result_service:
            mock_run.return_value = SimpleNamespace(data=[_document()])
            mock_result_service.get_document_parse_result = AsyncMock(return_value=None)

            response = client.get(f"/api/documents/{DOCUMENT_ID}/parse-result")

        assert response.status_code == 404

    def test_other_users_document_hidden(self, client):
        with patch("api.routes.documents.query._run_supabase", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = SimpleNamespace(
                data=[_document(user_id="22222222-2222-4222-8222-222222222222")]
            )
            response = client.get(f"/api/documents/{DOCUMENT_ID}/parse-result")

        assert response.status_code == 404


class TestDeleteDocumentGuarded:
    """DELETE /api/documents/{id} 走原子命令：活动占用拒绝、权限隐藏。"""

    def test_conflict_when_document_in_active_job(self, client):
        with patch("api.routes.documents.query._run_supabase", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = SimpleNamespace(data=[{
                "out_status": "conflict",
                "out_file_path": None,
                "out_reason": "document_in_active_job",
            }])
            response = client.delete(f"/api/documents/{DOCUMENT_ID}")

        assert response.status_code == 409

    def test_not_found_hidden(self, client):
        with patch("api.routes.documents.query._run_supabase", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = SimpleNamespace(data=[{
                "out_status": "not_found",
                "out_file_path": None,
                "out_reason": "document_unavailable",
            }])
            response = client.delete(f"/api/documents/{DOCUMENT_ID}")

        assert response.status_code == 404

    def test_deletes_database_row_and_tolerates_missing_file(self, client):
        with patch("api.routes.documents.query._run_supabase", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = SimpleNamespace(data=[{
                "out_status": "ok",
                "out_file_path": "/nonexistent/nf-test-missing.pdf",
                "out_reason": None,
            }])
            response = client.delete(f"/api/documents/{DOCUMENT_ID}")

        assert response.status_code == 200
        assert response.json()["message"] == "文档删除成功"
        # 只调用一次（原子 RPC），不再先查后删
        assert mock_run.await_count == 1
