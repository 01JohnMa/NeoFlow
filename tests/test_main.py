# tests/test_main.py
"""api.main 后台恢复任务测试 — 超时文档重置。"""

from unittest.mock import AsyncMock, patch

import pytest


class TestStuckDocumentRecovery:
    """超时恢复任务集成测试"""

    @pytest.mark.asyncio
    async def test_recovery_task_resets_stuck_documents(self):
        """定时任务调用 reset_stuck_processing_documents 并记录结果"""
        from api.main import _run_stuck_document_recovery

        with patch("api.main.supabase_service") as mock_svc:
            mock_svc.reset_stuck_processing_documents = AsyncMock(return_value=3)
            await _run_stuck_document_recovery()

        mock_svc.reset_stuck_processing_documents.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_recovery_task_handles_db_error_gracefully(self):
        """定时任务异常时不应崩溃"""
        from api.main import _run_stuck_document_recovery

        with patch("api.main.supabase_service") as mock_svc, \
             patch("api.main.logger") as mock_logger:
            mock_svc.reset_stuck_processing_documents = AsyncMock(
                side_effect=Exception("DB 不可用")
            )
            # 不应抛异常
            await _run_stuck_document_recovery()

        # 必须有 warning/error 日志
        assert mock_logger.error.called or mock_logger.warning.called
