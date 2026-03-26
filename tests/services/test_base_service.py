import pytest
import asyncio
from unittest.mock import patch

from services.base import SupabaseClientMixin


class DummyService(SupabaseClientMixin):
    pass


class TestSupabaseClientMixin:
    @pytest.mark.asyncio
    async def test_run_sync_uses_executor_and_returns_result(self):
        service = DummyService()

        class DummyLoop:
            def __init__(self):
                self.called = False
                self.executor = object()
                self.func = None

            async def run_in_executor(self, executor, func):
                self.called = True
                self.executor = executor
                self.func = func
                return func()

        loop = DummyLoop()

        with patch.object(asyncio, 'get_running_loop', return_value=loop):
            result = await service._run_sync(lambda: 'ok')

        assert result == 'ok'
        assert loop.called is True
        assert loop.executor is None
