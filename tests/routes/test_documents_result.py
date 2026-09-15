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
             patch("api.routes.documents.query.configuration_service") as mock_configuration_service:
            mock_run.return_value = SimpleNamespace(data=[_document()])
            mock_result_service.get_document_result = AsyncMock(return_value=_result_row())
            mock_configuration_service.get_extraction_configuration = AsyncMock(return_value={
                "id": TEMPLATE_ID,
                "fields": [
                    {
                        "field_key": "sample_name",
                        "field_label": "样品名称",
                        "field_type": "text",
                        "sort_order": 1,
                        "extraction_hint": "位于样品名称标签后",
                    },
                ],
            })

            response = client.get(f"/api/documents/{DOCUMENT_ID}/result")

        assert response.status_code == 200
        body = response.json()
        assert body["extraction_data"]["sample_name"] == "LED灯"
        assert body["extraction_data"]["document_id"] == DOCUMENT_ID
        assert body["extraction_data"]["is_validated"] is True
        assert body["is_validated"] is True
        assert body["created_at"] == "2026-01-02T00:00:00+00:00"
        assert body["ocr_text"] == "OCR 文本"
        assert body["configuration_id"] == TEMPLATE_ID
        assert body["fields"][0]["field_key"] == "sample_name"
        assert body["fields"][0]["extraction_hint"] == "位于样品名称标签后"
        mock_result_service.get_document_result.assert_awaited_once_with(
            DOCUMENT_ID, tenant_id=TENANT_ID
        )
        # 字段白名单来自 Configuration，不再解析旧业务表
        mock_configuration_service.get_extraction_configuration.assert_awaited_once_with(
            TEMPLATE_ID, revision_id=None
        )

    def test_returns_202_when_result_row_not_found(self, client):
        with patch("api.routes.documents.query._run_supabase", new_callable=AsyncMock) as mock_run, \
             patch("api.routes.documents.query.result_service") as mock_result_service, \
             patch("api.routes.documents.query.configuration_service") as mock_configuration_service:
            mock_run.return_value = SimpleNamespace(data=[_document(status="completed")])
            mock_result_service.get_document_result = AsyncMock(return_value=None)
            mock_configuration_service.get_extraction_configuration = AsyncMock(return_value=None)

            response = client.get(f"/api/documents/{DOCUMENT_ID}/result")

        assert response.status_code == 202
        assert response.json()["message"] == "提取结果正在同步中，请稍后重试"


class TestDocumentReviewWrite:
    """PUT validate/reject 只写 Result。"""

    def test_validate_writes_result_and_pushes_result_data(self, client):
        corrected = {"sample_name": "修正后"}
        updated_result = _result_row(data={"sample_name": "修正后", "report_date": "2026-01-01"})

        with patch("api.routes.documents.review._run_supabase", new_callable=AsyncMock) as mock_run, \
             patch("api.routes.documents.review.supabase_service"), \
             patch("api.routes.documents.review.result_service") as mock_result_service, \
             patch("api.routes.documents.review.configuration_service") as mock_configuration_service, \
             patch("api.routes.documents.review.push_to_feishu", new_callable=AsyncMock) as mock_push:
            mock_run.side_effect = [
                SimpleNamespace(data=[_document()]),
                SimpleNamespace(data=[{"id": DOCUMENT_ID}]),
            ]
            mock_result_service.update_result_review = AsyncMock(return_value=updated_result)
            mock_configuration_service.get_extraction_configuration = AsyncMock(return_value={
                "id": TEMPLATE_ID,
                "name": "检测报告",
                "fields": [],
                "feishu": {"bitable_token": "bitable-token", "table_id": "table-id"},
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
        # 只有 document select + status update，不再写旧业务表镜像
        assert mock_run.await_count == 2
        # 飞书推送（含固定 Excel 附件）取 Result 数据
        mock_push.assert_awaited_once()
        assert mock_push.await_args.kwargs["extraction_data"]["sample_name"] == "修正后"
        assert mock_push.await_args.kwargs["extraction_data"]["document_id"] == DOCUMENT_ID

    def test_validate_raises_when_result_missing(self, client):
        with patch("api.routes.documents.review._run_supabase", new_callable=AsyncMock) as mock_run, \
             patch("api.routes.documents.review.supabase_service"), \
             patch("api.routes.documents.review.result_service") as mock_result_service, \
             patch("api.routes.documents.review.configuration_service") as mock_configuration_service, \
             patch("api.routes.documents.review.push_to_feishu", new_callable=AsyncMock) as mock_push:
            mock_run.side_effect = [SimpleNamespace(data=[_document()])]
            mock_result_service.update_result_review = AsyncMock(return_value=None)
            mock_configuration_service.get_extraction_configuration = AsyncMock(return_value=None)

            response = client.put(
                f"/api/documents/{DOCUMENT_ID}/validate",
                json={"document_type": "inspection_report", "data": {}},
            )

        assert response.status_code == 500
        assert "无法审核" in response.json()["error"]
        mock_push.assert_not_awaited()

    def test_reject_marks_result_rejected(self, client):
        with patch("api.routes.documents.review._run_supabase", new_callable=AsyncMock) as mock_run, \
             patch("api.routes.documents.review.supabase_service"), \
             patch("api.routes.documents.review.result_service") as mock_result_service, \
             patch("api.routes.documents.review.configuration_service"):
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
