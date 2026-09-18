# tests/services/test_supabase_service.py
"""SupabaseService 单元测试 — 异常日志稳定性、异步卸载、卡死文档重置。"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from datetime import datetime

from loguru import logger

from services.supabase_service import SupabaseService


@pytest.fixture
def svc():
    """返回一个注入了 mock client 的 SupabaseService 实例"""
    instance = SupabaseService()
    instance._client = MagicMock()
    return instance


# ============ _validate_and_fix_date ============

class TestLoggingSafety:
    """异常日志稳定性"""

    @pytest.mark.asyncio
    async def test_create_document_logs_exception_with_braces_without_secondary_error(self, svc):
        """创建文档失败时，异常消息含大括号也不会触发日志二次报错"""
        svc._client.table.side_effect = Exception(
            "{'code': 'PGRST204', 'message': \"Column push_attachment does not exist\"}"
        )

        with patch.object(logger, "error") as mock_logger_error:
            with pytest.raises(Exception, match="PGRST204"):
                await svc.create_document({"id": "doc-001", "push_attachment": True})

        mock_logger_error.assert_called_once()


class TestAsyncOffloading:
    @pytest.mark.asyncio
    async def test_get_document_uses_run_sync_for_blocking_execute(self, svc):
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.execute.return_value = MagicMock(data=[{"id": "doc-1"}])
        svc._client.table.return_value = chain

        with patch.object(svc, "_run_sync", new_callable=AsyncMock) as mock_run_sync:
            mock_run_sync.side_effect = lambda fn, *args, **kwargs: fn(*args, **kwargs)
            result = await svc.get_document("doc-1")

        assert result == {"id": "doc-1"}
        mock_run_sync.assert_awaited_once()

class TestResetStuckProcessing:
    @pytest.mark.asyncio
    async def test_reset_stuck_returns_count_of_affected_documents(self):
        """超过超时阈值的 processing 文档应被重置为 failed，返回受影响数量"""
        from services.supabase_service import SupabaseService
        svc = SupabaseService()

        fake_stuck = [
            {"id": "doc-stuck-1", "status": "processing"},
            {"id": "doc-stuck-2", "status": "processing"},
        ]

        # select 返回两条卡死记录
        select_chain = MagicMock()
        select_chain.select.return_value = select_chain
        select_chain.eq.return_value = select_chain
        select_chain.lt.return_value = select_chain
        select_chain.execute.return_value = MagicMock(data=fake_stuck)
        # update 返回空
        update_chain = MagicMock()
        update_chain.update.return_value = update_chain
        update_chain.in_.return_value = update_chain
        update_chain.execute.return_value = MagicMock(data=[])

        mock_client = MagicMock()
        mock_client.table.side_effect = [select_chain, update_chain]
        svc._client = mock_client

        with patch.object(svc, "_run_sync", side_effect=lambda fn: fn()):
            count = await svc.reset_stuck_processing_documents(timeout_minutes=30)

        assert count == 2
        # 确认调了 update，并且状态改为 failed
        update_chain.update.assert_called_once()
        payload = update_chain.update.call_args.args[0]
        assert payload["status"] == "failed"
        assert "error_message" in payload
