"""AI Center 网关租户映射（tenants.ai_center_tenant_id）单测。

覆盖 _canonical_platform_tenant_id 的合同：
- 网关传来的原值只经映射列精确匹配解析，不预设格式、不特判具体值；
- 未映射一律 AuthenticationError，UUID 也不例外（没有直通分支）。
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from api.dependencies.auth import (
    AuthenticationError,
    _canonical_platform_tenant_id,
    require_platform_scope,
)
from services.supabase_service import supabase_service

WETRIAL_TENANT_ID = "a0000000-0000-0000-0000-000000000001"


def _install_mapping(monkeypatch, rows):
    """把 tenants 查询替换为按 ai_center_tenant_id 过滤的内存实现。"""

    class _Query:
        def __init__(self, table):
            self.table = table

        def select(self, *_):
            return self

        def eq(self, column, value):
            if self.table != "tenants" or column != "ai_center_tenant_id":
                raise AssertionError(f"查询了非映射列: {self.table}.{column}")
            self.matched = [row for row in rows if row["ai_center_tenant_id"] == value]
            return self

        def limit(self, _n):
            return self

        def execute(self):
            return SimpleNamespace(data=list(self.matched))

    captured = {}

    async def fake_run_sync(fn, *args, **kwargs):
        captured["ran_sync"] = True
        return fn()

    monkeypatch.setattr(
        supabase_service, "_client", SimpleNamespace(table=lambda name: _Query(name))
    )
    monkeypatch.setattr(supabase_service, "_run_sync", fake_run_sync)
    return captured


@pytest.mark.asyncio
async def test_mapped_gateway_tenant_resolves_to_tenant_uuid(monkeypatch):
    _install_mapping(
        monkeypatch,
        [{"id": WETRIAL_TENANT_ID, "ai_center_tenant_id": "default"}],
    )
    assert await _canonical_platform_tenant_id("default") == WETRIAL_TENANT_ID


@pytest.mark.asyncio
async def test_unmapped_gateway_tenant_is_rejected(monkeypatch):
    captured = _install_mapping(monkeypatch, [])
    with pytest.raises(AuthenticationError, match="未映射"):
        await _canonical_platform_tenant_id("some-other-platform-tenant")


@pytest.mark.asyncio
async def test_platform_tenant_uuid_has_no_pass_through(monkeypatch):
    """网关值恰好是 UUID 也必须走映射列，不允许绕过映射直通。"""
    captured = _install_mapping(
        monkeypatch,
        [{"id": WETRIAL_TENANT_ID, "ai_center_tenant_id": "default"}],
    )
    random_uuid = str(uuid4())
    with pytest.raises(AuthenticationError, match="未映射"):
        await _canonical_platform_tenant_id(random_uuid)
    assert captured["ran_sync"], "UUID 直通会跳过数据库映射查询"


@pytest.mark.asyncio
async def test_mapping_runs_off_event_loop(monkeypatch):
    """回归：同步 PostgREST 客户端必须经 _run_sync，不允许直接 await。"""
    _install_mapping(monkeypatch, [])
    with pytest.raises(AuthenticationError):
        await _canonical_platform_tenant_id("default")


@pytest.mark.asyncio
async def test_require_platform_scope_builds_user_from_mapping(monkeypatch):
    _install_mapping(
        monkeypatch,
        [{"id": WETRIAL_TENANT_ID, "ai_center_tenant_id": "default"}],
    )
    dependency = require_platform_scope("parse")

    user = await dependency(
        tenant_id="default",
        application_id="app-1",
        version_id="ver-1",
        invocation_id="inv-1",
        caller_id="caller-99999999-9999-4999-8999-999999999999",
        raw_scope="parse",
    )

    assert user.tenant_id == WETRIAL_TENANT_ID
    assert user.platform_context.invocation_id == "inv-1"
    assert user.user_id == "99999999-9999-4999-8999-999999999999"
