import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.tenant_service import TenantService


@pytest.fixture
def svc():
    instance = TenantService()
    instance._client = MagicMock()
    return instance


class TestTenantServiceAsyncOffloading:
    @pytest.mark.asyncio
    async def test_get_user_profile_uses_run_sync_for_profile_and_tenant_queries(self, svc):
        profile_chain = MagicMock()
        profile_chain.select.return_value = profile_chain
        profile_chain.eq.return_value = profile_chain
        profile_chain.execute.return_value = MagicMock(data=[{"id": "user-1", "tenant_id": "tenant-1"}])

        tenant_chain = MagicMock()
        tenant_chain.select.return_value = tenant_chain
        tenant_chain.eq.return_value = tenant_chain
        tenant_chain.execute.return_value = MagicMock(data=[{"id": "tenant-1", "name": "测试部门", "code": "T001"}])

        svc._client.table.side_effect = [profile_chain, tenant_chain]

        with patch.object(svc, "_run_sync", new_callable=AsyncMock) as mock_run_sync:
            mock_run_sync.side_effect = lambda fn, *args, **kwargs: fn(*args, **kwargs)
            result = await svc.get_user_profile("user-1")

        assert result["id"] == "user-1"
        assert result["tenants"]["id"] == "tenant-1"
        assert mock_run_sync.await_count == 2
