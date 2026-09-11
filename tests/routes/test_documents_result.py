# tests/routes/test_documents_result.py
"""文档详情/审核的 Result 读写路由测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from tests.conftest import DOCUMENT_ID, TEMPLATE_ID, TENANT_ID, USER_ID


def _document(**overrides):
    document = {
        "id": DOCUMENT_ID,
        "user_id": USER_ID,
        "tenant_id": TENANT_ID,
        "status": "pending_review",
        "document_type": "inspection_report",
        "template_id": TEMPLATE_ID,
        "file_path": "/tmp/test.pdf",
        "file_name": "test.pdf",
        "original_file_name": "test.pdf",
        "display_name": None,
        "custom_push_name": None,
        "ocr_text": "OCR 文本",
        "ocr_confidence": 0.92,
    }
    document.update(overrides)
    return document


def _result_row(**overrides):
    row = {
        "id": "rrrrrrrr-rrrr-4rrr-8rrr-rrrrrrrrrrrr",
        "document_id": DOCUMENT_ID,
        "sample_key": "default",
        "review_state": "approved",
        "created_at": "2026-01-02T00:00:00+00:00",
        "data": {"sample_name": "LED灯", "report_date": "2026-01-01"},
        "field_meta": {
            "sample_name": {
                "source": "ocr_llm",
                "confidence": None,
                "review_state": "approved",
            },
        },
    }
    row.update(overrides)
    return row


class TestDocumentResultRead:
    """GET /api/documents/{id}/result 从 Result 读取。"""

    def test_reads_result_store_and_keeps_response_shape(self, client):
        with patch("api.routes.documents.query._run_supabase", new_callable=AsyncMock) as mock_run, \
             patch("api.routes.documents.query.result_service") as mock_result_service, \
             patch("api.routes.documents.query.template_service") as mock_template_service, \
             patch("api.routes.documents.query.supabase_service") as mock_supabase:
            mock_run.return_value = SimpleNamespace(data=[_document()])
            mock_result_service.get_document_result = AsyncMock(return_value=_result_row())
            mock_template_service.get_template_fields = AsyncMock(return_value=[
                {
                    "field_key": "sample_name",
                    "field_label": "样品名称",
                    "field_type": "text",
                    "sort_order": 1,
                },
            ])
            mock_supabase.resolve_table_name = AsyncMock()

            response = client.get(f"/api/documents/{DOCUMENT_ID}/result")

        assert response.status_code == 200
        body = response.json()
        assert body["extraction_data"]["sample_name"] == "LED灯"
        assert body["extraction_data"]["document_id"] == DOCUMENT_ID
        assert body["extraction_data"]["is_validated"] is True
        assert body["is_validated"] is True
        assert body["created_at"] == "2026-01-02T00:00:00+00:00"
        assert body["ocr_text"] == "OCR 文本"
        assert body["template_fields"][0]["field_key"] == "sample_name"
        mock_result_service.get_document_result.assert_awaited_once_with(
            DOCUMENT_ID, tenant_id=TENANT_ID
        )
        # 读取侧不再解析/查询旧业务表
        mock_supabase.resolve_table_name.assert_not_awaited()

    def test_returns_202_when_result_row_not_found(self, client):
        with patch("api.routes.documents.query._run_supabase", new_callable=AsyncMock) as mock_run, \
             patch("api.routes.documents.query.result_service") as mock_result_service, \
             patch("api.routes.documents.query.template_service") as mock_template_service:
            mock_run.return_value = SimpleNamespace(data=[_document(status="completed")])
            mock_result_service.get_document_result = AsyncMock(return_value=None)
            mock_template_service.get_template_fields = AsyncMock(return_value=[])

            response = client.get(f"/api/documents/{DOCUMENT_ID}/result")

        assert response.status_code == 202
        assert response.json()["message"] == "提取结果正在同步中，请稍后重试"


class TestDocumentReviewWrite:
    """PUT validate/reject 写 Result 且保留旧表镜像。"""

    def test_validate_writes_result_then_legacy_mirror_and_pushes_result_data(self, client):
        corrected = {"sample_name": "修正后"}
        updated_result = _result_row(data={"sample_name": "修正后", "report_date": "2026-01-01"})

        with patch("api.routes.documents.review._run_supabase", new_callable=AsyncMock) as mock_run, \
             patch("api.routes.documents.review.supabase_service") as mock_supabase, \
             patch("api.routes.documents.review.result_service") as mock_result_service, \
             patch("api.routes.documents.review.template_service") as mock_template_service, \
             patch("api.routes.documents.review.push_to_feishu", new_callable=AsyncMock) as mock_push:
            mock_run.side_effect = [
                SimpleNamespace(data=[_document()]),
                SimpleNamespace(data=[{**corrected, "is_validated": True}]),
                SimpleNamespace(data=[{"id": DOCUMENT_ID}]),
            ]
            mock_supabase.resolve_table_name = AsyncMock(return_value="inspection_reports")
            mock_result_service.update_result_review = AsyncMock(return_value=updated_result)
            mock_template_service.get_template_with_details = AsyncMock(return_value={
                "id": TEMPLATE_ID,
                "name": "检测报告",
                "template_fields": [],
                "feishu_bitable_token": "bitable-token",
                "feishu_table_id": "table-id",
            })

            response = client.put(
                f"/api/documents/{DOCUMENT_ID}/validate",
                json={"document_type": "inspection_report", "data": corrected},
            )

        assert response.status_code == 200
        mock_result_service.update_result_review.assert_awaited_once_with(
            document_id=DOCUMENT_ID,
            review_state="approved",
            data=corrected,
            tenant_id=TENANT_ID,
        )
        # Result 与旧业务表镜像都写（document select + mirror update + status update）
        assert mock_run.await_count == 3
        # 飞书推送（含固定 Excel 附件）取 Result 数据
        mock_push.assert_awaited_once()
        assert mock_push.await_args.kwargs["extraction_data"]["sample_name"] == "修正后"
        assert mock_push.await_args.kwargs["extraction_data"]["document_id"] == DOCUMENT_ID

    def test_reject_marks_result_rejected(self, client):
        with patch("api.routes.documents.review._run_supabase", new_callable=AsyncMock) as mock_run, \
             patch("api.routes.documents.review.supabase_service"), \
             patch("api.routes.documents.review.result_service") as mock_result_service, \
             patch("api.routes.documents.review.template_service"):
            mock_run.side_effect = [
                SimpleNamespace(data=[_document()]),
                SimpleNamespace(data=[{"id": DOCUMENT_ID}]),
            ]
            mock_result_service.update_result_review = AsyncMock(return_value=_result_row(
                review_state="rejected"
            ))

            response = client.put(
                f"/api/documents/{DOCUMENT_ID}/reject",
                json={"reason": "字段有误"},
            )

        assert response.status_code == 200
        mock_result_service.update_result_review.assert_awaited_once_with(
            document_id=DOCUMENT_ID,
            review_state="rejected",
            tenant_id=TENANT_ID,
        )
