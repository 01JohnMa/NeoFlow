# tests/conftest.py
"""公共测试 fixtures — mock Supabase、mock 认证、FastAPI TestClient"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

# TestClient 惰性导入：纯单元测试（不拉起 app）可不装 fastapi 也能收集 conftest


# ============ 用户 fixtures ============

def _make_user(role: str = "user", tenant_id: str = "tenant-001", user_id: str = "user-001"):
    """构造 CurrentUser 对象（不依赖真实 JWT）"""
    from api.dependencies.auth import CurrentUser
    return CurrentUser(
        user_id=user_id,
        token="mock-token",
        tenant_id=tenant_id,
        tenant_code="T001",
        tenant_name="测试部门",
        role=role,
        display_name="测试用户",
    )


@pytest.fixture
def mock_user():
    """普通用户"""
    return _make_user(role="user")


@pytest.fixture
def mock_admin():
    """租户管理员"""
    return _make_user(role="tenant_admin")


@pytest.fixture
def mock_super_admin():
    """超级管理员"""
    return _make_user(role="super_admin", tenant_id=None)


# ============ Supabase mock ============

def _make_supabase_result(data=None, count=None):
    """构造 Supabase execute() 返回值"""
    result = MagicMock()
    result.data = data if data is not None else []
    result.count = count
    return result


def _make_supabase_chain(return_data=None, count=None):
    """
    构造 Supabase 链式调用 mock：
    .table().select().eq().order().range().execute()
    所有中间方法均返回自身，execute() 返回 result。
    """
    chain = MagicMock()
    result = _make_supabase_result(return_data, count)
    # 所有链式方法返回 chain 本身
    for method in ("select", "eq", "neq", "order", "range", "limit",
                   "insert", "update", "delete", "upsert", "filter"):
        getattr(chain, method).return_value = chain
    chain.execute.return_value = result
    return chain, result


@pytest.fixture
def mock_supabase_client():
    """返回一个可配置的 Supabase client mock"""
    client = MagicMock()
    chain = MagicMock()
    for method in ("select", "eq", "neq", "order", "range", "limit",
                   "insert", "update", "delete", "upsert", "filter"):
        getattr(chain, method).return_value = chain
    chain.execute.return_value = _make_supabase_result()
    client.table.return_value = chain
    return client


# ============ FastAPI TestClient fixtures ============

@pytest.fixture
def app():
    """创建测试用 FastAPI app（不触发 lifespan 初始化）"""
    # 在导入 app 之前先 patch 掉重量级服务的初始化
    import importlib
    supa_mod = importlib.import_module("services.supabase_service")
    ocr_mod = importlib.import_module("services.ocr_service")
    with patch.object(supa_mod.supabase_service, "initialize", new=AsyncMock()), \
         patch.object(ocr_mod.ocr_service, "initialize", new=AsyncMock()), \
         patch.object(ocr_mod.ocr_service, "close", new=AsyncMock()):
        from api.main import app as _app
        yield _app


@pytest.fixture
def client(app, mock_user):
    """
    TestClient，已覆盖 get_current_user 依赖为普通用户。
    路由测试中如需其他角色，可在测试内再次 override。
    """
    from fastapi.testclient import TestClient
    from api.dependencies.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: mock_user
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def admin_client(app, mock_admin):
    """TestClient，已覆盖 get_current_user 依赖为租户管理员"""
    from fastapi.testclient import TestClient
    from api.dependencies.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: mock_admin
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def super_admin_client(app, mock_super_admin):
    """TestClient，已覆盖 get_current_user 依赖为超级管理员"""
    from fastapi.testclient import TestClient
    from api.dependencies.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: mock_super_admin
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def unauth_client(app):
    """TestClient，不覆盖认证依赖（模拟未登录请求）"""
    from fastapi.testclient import TestClient
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ============ 通用测试数据 ============

TEMPLATE_ID = "11111111-1111-1111-1111-111111111111"
FIELD_ID = "22222222-2222-2222-2222-222222222222"
EXAMPLE_ID = "33333333-3333-3333-3333-333333333333"
DOCUMENT_ID = "44444444-4444-4444-4444-444444444444"
TENANT_ID = "tenant-001"
USER_ID = "user-001"


MOCK_TEMPLATE = {
    "id": TEMPLATE_ID,
    "tenant_id": TENANT_ID,
    "name": "检测报告",
    "code": "inspection_report",
    "description": "检测报告模板",
    "process_mode": "single",
    "is_active": True,
    "sort_order": 1,
    "feishu_bitable_token": None,
    "feishu_table_id": None,
    "auto_approve": False,
}

MOCK_FIELD = {
    "id": FIELD_ID,
    "template_id": TEMPLATE_ID,
    "field_key": "sample_no",
    "field_label": "样品编号",
    "field_type": "text",
    "extraction_hint": "样品编号或检测编号",
    "feishu_column": "样品编号",
    "sort_order": 1,
    "review_enforced": False,
    "review_allowed_values": None,
}

MOCK_EXAMPLE = {
    "id": EXAMPLE_ID,
    "template_id": TEMPLATE_ID,
    "example_input": "样品编号：SN-2024-001",
    "example_output": {"sample_no": "SN-2024-001"},
    "sort_order": 1,
    "is_active": True,
}

MOCK_DOCUMENT = {
    "id": DOCUMENT_ID,
    "user_id": USER_ID,
    "tenant_id": TENANT_ID,
    "file_name": f"{DOCUMENT_ID}.pdf",
    "original_file_name": "test.pdf",
    "file_path": f"/uploads/{DOCUMENT_ID}.pdf",
    "file_size": 1024,
    "file_type": "application/pdf",
    "file_extension": ".pdf",
    "mime_type": "application/pdf",
    "status": "completed",
    "document_type": "检测报告",
    "template_id": TEMPLATE_ID,
    "ocr_text": "样品编号：SN-2024-001",
    "ocr_confidence": 0.95,
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T00:01:00",
    "processed_at": "2024-01-01T00:01:00",
}
