# tests/routes/test_admin.py
"""管理员路由测试 — /api/admin/templates、/api/admin/fields"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from tests.conftest import (
    TEMPLATE_ID, FIELD_ID, EXAMPLE_ID, TENANT_ID,
    MOCK_TEMPLATE, MOCK_FIELD, MOCK_EXAMPLE,
)


# ============ 权限测试 ============

class TestAdminPermissions:
    """非管理员访问管理接口应返回 403"""

    def test_list_templates_as_regular_user_returns_403(self, client):
        """普通用户访问模板列表返回 403"""
        resp = client.get("/api/admin/templates")
        assert resp.status_code == 403

    def test_create_field_as_regular_user_returns_403(self, client):
        """普通用户创建字段返回 403"""
        resp = client.post(
            f"/api/admin/templates/{TEMPLATE_ID}/fields",
            json={"field_key": "test", "field_label": "测试"},
        )
        assert resp.status_code == 403

    def test_delete_field_as_regular_user_returns_403(self, client):
        """普通用户删除字段返回 403"""
        resp = client.delete(f"/api/admin/fields/{FIELD_ID}")
        assert resp.status_code == 403

    def test_unauthenticated_returns_401(self, unauth_client):
        """未认证请求返回 401"""
        resp = unauth_client.get("/api/admin/templates")
        assert resp.status_code == 401


# ============ 模板列表 ============

class TestListAdminTemplates:
    """GET /api/admin/templates"""

    def test_admin_can_list_templates(self, admin_client):
        """租户管理员可以获取模板列表"""
        with patch("api.routes.admin.template_service.get_admin_templates",
                   new_callable=AsyncMock, return_value=[MOCK_TEMPLATE]):
            resp = admin_client.get("/api/admin/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["id"] == TEMPLATE_ID

    def test_admin_gets_empty_list(self, admin_client):
        """无模板时返回空列表"""
        with patch("api.routes.admin.template_service.get_admin_templates",
                   new_callable=AsyncMock, return_value=[]):
            resp = admin_client.get("/api/admin/templates")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_super_admin_can_filter_by_tenant(self, super_admin_client):
        """超级管理员可以按 tenant_id 过滤"""
        with patch("api.routes.admin.template_service.get_admin_templates",
                   new_callable=AsyncMock, return_value=[MOCK_TEMPLATE]) as mock_get:
            resp = super_admin_client.get(f"/api/admin/templates?tenant_id={TENANT_ID}")
        assert resp.status_code == 200


# ============ 更新模板配置 ============

class TestUpdateTemplateConfig:
    """PUT /api/admin/templates/{template_id}"""

    def test_admin_updates_template_config(self, admin_client):
        """管理员可以更新模板飞书配置"""
        updated = {**MOCK_TEMPLATE, "feishu_bitable_token": "new-token"}
        with patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=MOCK_TEMPLATE), \
             patch("api.routes.admin.template_service.update_template_config",
                   new_callable=AsyncMock, return_value=updated):
            resp = admin_client.put(
                f"/api/admin/templates/{TEMPLATE_ID}",
                json={"feishu_bitable_token": "new-token"},
            )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_update_template_not_found_returns_404(self, admin_client):
        """模板不存在时返回 404"""
        with patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=None):
            resp = admin_client.put(
                f"/api/admin/templates/{TEMPLATE_ID}",
                json={"feishu_bitable_token": "token"},
            )
        assert resp.status_code == 404

    def test_update_template_empty_body_returns_400(self, admin_client):
        """空请求体返回 400"""
        with patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=MOCK_TEMPLATE):
            resp = admin_client.put(
                f"/api/admin/templates/{TEMPLATE_ID}",
                json={},
            )
        assert resp.status_code == 400


# ============ 字段列表 ============

class TestListFields:
    """GET /api/admin/templates/{template_id}/fields"""

    def test_admin_lists_fields(self, admin_client):
        """管理员可以获取字段列表"""
        with patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=MOCK_TEMPLATE), \
             patch("api.routes.admin.template_service.get_template_fields",
                   new_callable=AsyncMock, return_value=[MOCK_FIELD]):
            resp = admin_client.get(f"/api/admin/templates/{TEMPLATE_ID}/fields")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["field_key"] == "sample_no"


# ============ 创建字段 ============

class TestCreateField:
    """POST /api/admin/templates/{template_id}/fields"""

    def test_admin_creates_field_returns_201(self, admin_client):
        """管理员创建字段返回 201"""
        with patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=MOCK_TEMPLATE), \
             patch("api.routes.admin.template_service.create_field",
                   new_callable=AsyncMock, return_value=MOCK_FIELD):
            resp = admin_client.post(
                f"/api/admin/templates/{TEMPLATE_ID}/fields",
                json={
                    "field_key": "sample_no",
                    "field_label": "样品编号",
                    "field_type": "text",
                },
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["field_key"] == "sample_no"

    def test_create_field_schema_error_returns_422(self, admin_client):
        """DDL 失败（SchemaError）时返回 422"""
        from services.schema_sync_service import SchemaError
        with patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=MOCK_TEMPLATE), \
             patch("api.routes.admin.template_service.create_field",
                   new_callable=AsyncMock, side_effect=SchemaError("列名冲突")):
            resp = admin_client.post(
                f"/api/admin/templates/{TEMPLATE_ID}/fields",
                json={"field_key": "bad_col", "field_label": "冲突列"},
            )
        assert resp.status_code == 422

    def test_create_field_template_not_found_returns_404(self, admin_client):
        """模板不存在时返回 404"""
        with patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=None):
            resp = admin_client.post(
                f"/api/admin/templates/{TEMPLATE_ID}/fields",
                json={"field_key": "f1", "field_label": "字段1"},
            )
        assert resp.status_code == 404

    def test_create_field_missing_required_field_returns_422(self, admin_client):
        """缺少必填字段 field_label 时 Pydantic 返回 422"""
        with patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=MOCK_TEMPLATE):
            resp = admin_client.post(
                f"/api/admin/templates/{TEMPLATE_ID}/fields",
                json={"field_key": "f1"},  # 缺少 field_label
            )
        assert resp.status_code == 422


# ============ 更新字段 ============

class TestUpdateField:
    """PUT /api/admin/fields/{field_id}"""

    def test_admin_updates_field(self, admin_client):
        """管理员可以更新字段"""
        updated = {**MOCK_FIELD, "field_label": "新标签"}
        with patch("api.routes.admin.template_service.get_field_by_id",
                   new_callable=AsyncMock, return_value=MOCK_FIELD), \
             patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=MOCK_TEMPLATE), \
             patch("api.routes.admin.template_service.update_field",
                   new_callable=AsyncMock, return_value=updated):
            resp = admin_client.put(
                f"/api/admin/fields/{FIELD_ID}",
                json={"field_label": "新标签"},
            )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_update_field_schema_conflict_returns_409(self, admin_client):
        """列名冲突（SchemaError）时返回 409"""
        from services.schema_sync_service import SchemaError
        with patch("api.routes.admin.template_service.get_field_by_id",
                   new_callable=AsyncMock, return_value=MOCK_FIELD), \
             patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=MOCK_TEMPLATE), \
             patch("api.routes.admin.template_service.update_field",
                   new_callable=AsyncMock, side_effect=SchemaError("列名已存在")):
            resp = admin_client.put(
                f"/api/admin/fields/{FIELD_ID}",
                json={"field_key": "existing_col"},
            )
        assert resp.status_code == 409

    def test_update_field_not_found_returns_404(self, admin_client):
        """字段不存在时返回 404"""
        with patch("api.routes.admin.template_service.get_field_by_id",
                   new_callable=AsyncMock, return_value=None):
            resp = admin_client.put(
                f"/api/admin/fields/{FIELD_ID}",
                json={"field_label": "x"},
            )
        assert resp.status_code == 404

    def test_update_field_empty_body_returns_400(self, admin_client):
        """空请求体返回 400"""
        with patch("api.routes.admin.template_service.get_field_by_id",
                   new_callable=AsyncMock, return_value=MOCK_FIELD), \
             patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=MOCK_TEMPLATE):
            resp = admin_client.put(
                f"/api/admin/fields/{FIELD_ID}",
                json={},
            )
        assert resp.status_code == 400


# ============ 删除字段 ============

class TestDeleteField:
    """DELETE /api/admin/fields/{field_id}"""

    def test_admin_deletes_field(self, admin_client):
        """管理员可以删除字段"""
        with patch("api.routes.admin.template_service.get_field_by_id",
                   new_callable=AsyncMock, return_value=MOCK_FIELD), \
             patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=MOCK_TEMPLATE), \
             patch("api.routes.admin.template_service.delete_field",
                   new_callable=AsyncMock, return_value=True):
            resp = admin_client.delete(f"/api/admin/fields/{FIELD_ID}")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_delete_field_with_data_returns_409(self, admin_client):
        """有历史数据且 force=False 时返回 409"""
        from services.schema_sync_service import SchemaError
        with patch("api.routes.admin.template_service.get_field_by_id",
                   new_callable=AsyncMock, return_value=MOCK_FIELD), \
             patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=MOCK_TEMPLATE), \
             patch("api.routes.admin.template_service.delete_field",
                   new_callable=AsyncMock,
                   side_effect=SchemaError("列有历史数据", non_null_count=10)):
            resp = admin_client.delete(f"/api/admin/fields/{FIELD_ID}")
        assert resp.status_code == 409
        error = resp.json()["error"]
        assert error["non_null_count"] == 10

    def test_force_delete_field(self, admin_client):
        """force=True 时强制删除成功"""
        with patch("api.routes.admin.template_service.get_field_by_id",
                   new_callable=AsyncMock, return_value=MOCK_FIELD), \
             patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=MOCK_TEMPLATE), \
             patch("api.routes.admin.template_service.delete_field",
                   new_callable=AsyncMock, return_value=True):
            resp = admin_client.delete(f"/api/admin/fields/{FIELD_ID}?force=true")
        assert resp.status_code == 200

    def test_delete_field_not_found_returns_404(self, admin_client):
        """字段不存在时返回 404"""
        with patch("api.routes.admin.template_service.get_field_by_id",
                   new_callable=AsyncMock, return_value=None):
            resp = admin_client.delete(f"/api/admin/fields/{FIELD_ID}")
        assert resp.status_code == 404


# ============ 字段排序 ============

class TestReorderFields:
    """PUT /api/admin/templates/{template_id}/fields/reorder"""

    def test_admin_reorders_fields(self, admin_client):
        """管理员可以批量排序字段"""
        with patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=MOCK_TEMPLATE), \
             patch("api.routes.admin.template_service.reorder_fields",
                   new_callable=AsyncMock, return_value=True):
            resp = admin_client.put(
                f"/api/admin/templates/{TEMPLATE_ID}/fields/reorder",
                json={"items": [
                    {"id": FIELD_ID, "sort_order": 0},
                    {"id": "another-id", "sort_order": 1},
                ]},
            )
        assert resp.status_code == 200
        assert resp.json()["success"] is True


# ============ 示例 CRUD ============

class TestExampleCrud:
    """示例 CRUD 接口"""

    def test_list_examples(self, admin_client):
        """管理员可以获取示例列表"""
        with patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=MOCK_TEMPLATE), \
             patch("api.routes.admin.template_service.get_template_examples",
                   new_callable=AsyncMock, return_value=[MOCK_EXAMPLE]):
            resp = admin_client.get(f"/api/admin/templates/{TEMPLATE_ID}/examples")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_list_examples_active_only(self, admin_client):
        """active_only=true 时只返回启用的示例"""
        with patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=MOCK_TEMPLATE), \
             patch("api.routes.admin.template_service.get_template_examples",
                   new_callable=AsyncMock, return_value=[MOCK_EXAMPLE]) as mock_get:
            resp = admin_client.get(
                f"/api/admin/templates/{TEMPLATE_ID}/examples?active_only=true"
            )
        assert resp.status_code == 200
        mock_get.assert_called_once_with(TEMPLATE_ID, active_only=True)

    def test_create_example_returns_201(self, admin_client):
        """创建示例返回 201"""
        with patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=MOCK_TEMPLATE), \
             patch("api.routes.admin.template_service.create_example",
                   new_callable=AsyncMock, return_value=MOCK_EXAMPLE):
            resp = admin_client.post(
                f"/api/admin/templates/{TEMPLATE_ID}/examples",
                json={
                    "example_input": "样品编号：SN-001",
                    "example_output": {"sample_no": "SN-001"},
                },
            )
        assert resp.status_code == 201
        assert resp.json()["success"] is True

    def test_create_example_missing_output_returns_422(self, admin_client):
        """缺少 example_output 时 Pydantic 返回 422"""
        with patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=MOCK_TEMPLATE):
            resp = admin_client.post(
                f"/api/admin/templates/{TEMPLATE_ID}/examples",
                json={"example_input": "只有输入"},
            )
        assert resp.status_code == 422

    def test_update_example(self, admin_client):
        """管理员可以更新示例"""
        updated = {**MOCK_EXAMPLE, "example_input": "新输入文本"}
        with patch("api.routes.admin.template_service.get_example_by_id",
                   new_callable=AsyncMock, return_value=MOCK_EXAMPLE), \
             patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=MOCK_TEMPLATE), \
             patch("api.routes.admin.template_service.update_example",
                   new_callable=AsyncMock, return_value=updated):
            resp = admin_client.put(
                f"/api/admin/examples/{EXAMPLE_ID}",
                json={"example_input": "新输入文本"},
            )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["data"]["example_input"] == "新输入文本"

    def test_update_example_empty_body_returns_400(self, admin_client):
        """空请求体返回 400"""
        with patch("api.routes.admin.template_service.get_example_by_id",
                   new_callable=AsyncMock, return_value=MOCK_EXAMPLE), \
             patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=MOCK_TEMPLATE):
            resp = admin_client.put(f"/api/admin/examples/{EXAMPLE_ID}", json={})
        assert resp.status_code == 400

    def test_update_example_not_found_returns_404(self, admin_client):
        """示例不存在时返回 404"""
        with patch("api.routes.admin.template_service.get_example_by_id",
                   new_callable=AsyncMock, return_value=None):
            resp = admin_client.put(
                f"/api/admin/examples/{EXAMPLE_ID}",
                json={"example_input": "x"},
            )
        assert resp.status_code == 404

    def test_delete_example(self, admin_client):
        """删除示例成功"""
        with patch("api.routes.admin.template_service.get_example_by_id",
                   new_callable=AsyncMock, return_value=MOCK_EXAMPLE), \
             patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=MOCK_TEMPLATE), \
             patch("api.routes.admin.template_service.delete_example",
                   new_callable=AsyncMock, return_value=True):
            resp = admin_client.delete(f"/api/admin/examples/{EXAMPLE_ID}")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_delete_example_not_found_returns_404(self, admin_client):
        """示例不存在时返回 404"""
        with patch("api.routes.admin.template_service.get_example_by_id",
                   new_callable=AsyncMock, return_value=None):
            resp = admin_client.delete(f"/api/admin/examples/{EXAMPLE_ID}")
        assert resp.status_code == 404


# ============ 跨租户权限边界 ============

class TestCrossTenantAccess:
    """超级管理员与跨租户访问场景"""

    def test_super_admin_can_access_any_tenant_template(self, super_admin_client):
        """超级管理员可以访问任意租户的模板字段"""
        other_tenant_template = {**MOCK_TEMPLATE, "tenant_id": "other-tenant"}
        with patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=other_tenant_template), \
             patch("api.routes.admin.template_service.get_template_fields",
                   new_callable=AsyncMock, return_value=[MOCK_FIELD]):
            resp = super_admin_client.get(f"/api/admin/templates/{TEMPLATE_ID}/fields")
        assert resp.status_code == 200

    def test_admin_cannot_access_other_tenant_template(self, admin_client):
        """租户管理员不能访问其他租户的模板"""
        other_tenant_template = {**MOCK_TEMPLATE, "tenant_id": "other-tenant-999"}
        with patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=other_tenant_template):
            resp = admin_client.get(f"/api/admin/templates/{TEMPLATE_ID}/fields")
        assert resp.status_code == 403

    def test_admin_cannot_delete_field_of_other_tenant(self, admin_client):
        """租户管理员不能删除其他租户模板的字段"""
        other_tenant_template = {**MOCK_TEMPLATE, "tenant_id": "other-tenant-999"}
        with patch("api.routes.admin.template_service.get_field_by_id",
                   new_callable=AsyncMock, return_value=MOCK_FIELD), \
             patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=other_tenant_template):
            resp = admin_client.delete(f"/api/admin/fields/{FIELD_ID}")
        assert resp.status_code == 403

    def test_super_admin_list_templates_without_tenant_filter(self, super_admin_client):
        """超级管理员不传 tenant_id 时返回全部模板"""
        with patch("api.routes.admin.template_service.get_admin_templates",
                   new_callable=AsyncMock, return_value=[MOCK_TEMPLATE]) as mock_get:
            resp = super_admin_client.get("/api/admin/templates")
        assert resp.status_code == 200
        # 不传 tenant_id 时 effective_tenant_id 为 None
        mock_get.assert_called_once_with(tenant_id=None)


# ============ 模板配置扩展字段 ============

class TestUpdateTemplateConfigExtended:
    """更新模板配置的扩展场景"""

    def test_update_auto_approve(self, admin_client):
        """可以单独更新 auto_approve"""
        updated = {**MOCK_TEMPLATE, "auto_approve": True}
        with patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=MOCK_TEMPLATE), \
             patch("api.routes.admin.template_service.update_template_config",
                   new_callable=AsyncMock, return_value=updated):
            resp = admin_client.put(
                f"/api/admin/templates/{TEMPLATE_ID}",
                json={"auto_approve": True},
            )
        assert resp.status_code == 200
        assert resp.json()["data"]["auto_approve"] is True

    def test_update_extraction_mode(self, admin_client):
        """可以更新 extraction_mode"""
        updated = {**MOCK_TEMPLATE, "extraction_mode": "vlm"}
        with patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=MOCK_TEMPLATE), \
             patch("api.routes.admin.template_service.update_template_config",
                   new_callable=AsyncMock, return_value=updated):
            resp = admin_client.put(
                f"/api/admin/templates/{TEMPLATE_ID}",
                json={"extraction_mode": "vlm"},
            )
        assert resp.status_code == 200

    def test_update_feishu_table_id(self, admin_client):
        """可以单独更新 feishu_table_id"""
        updated = {**MOCK_TEMPLATE, "feishu_table_id": "tbl_abc123"}
        with patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=MOCK_TEMPLATE), \
             patch("api.routes.admin.template_service.update_template_config",
                   new_callable=AsyncMock, return_value=updated):
            resp = admin_client.put(
                f"/api/admin/templates/{TEMPLATE_ID}",
                json={"feishu_table_id": "tbl_abc123"},
            )
        assert resp.status_code == 200
        assert resp.json()["data"]["feishu_table_id"] == "tbl_abc123"


# ============ 字段审核配置 ============

class TestFieldReviewConfig:
    """字段 review_enforced / review_allowed_values 相关场景"""

    def test_create_field_with_review_enforced(self, admin_client):
        """创建带审核约束的字段"""
        field_with_review = {
            **MOCK_FIELD,
            "review_enforced": True,
            "review_allowed_values": ["合格", "不合格"],
        }
        with patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=MOCK_TEMPLATE), \
             patch("api.routes.admin.template_service.create_field",
                   new_callable=AsyncMock, return_value=field_with_review):
            resp = admin_client.post(
                f"/api/admin/templates/{TEMPLATE_ID}/fields",
                json={
                    "field_key": "result",
                    "field_label": "检测结论",
                    "review_enforced": True,
                    "review_allowed_values": ["合格", "不合格"],
                },
            )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["review_enforced"] is True
        assert data["review_allowed_values"] == ["合格", "不合格"]

    def test_update_field_review_allowed_values(self, admin_client):
        """更新字段的允许值列表"""
        updated = {**MOCK_FIELD, "review_allowed_values": ["通过", "驳回", "待定"]}
        with patch("api.routes.admin.template_service.get_field_by_id",
                   new_callable=AsyncMock, return_value=MOCK_FIELD), \
             patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=MOCK_TEMPLATE), \
             patch("api.routes.admin.template_service.update_field",
                   new_callable=AsyncMock, return_value=updated):
            resp = admin_client.put(
                f"/api/admin/fields/{FIELD_ID}",
                json={"review_allowed_values": ["通过", "驳回", "待定"]},
            )
        assert resp.status_code == 200
        assert resp.json()["data"]["review_allowed_values"] == ["通过", "驳回", "待定"]

    def test_create_field_with_feishu_column(self, admin_client):
        """创建字段时可以指定飞书列名"""
        field_with_feishu = {**MOCK_FIELD, "feishu_column": "检测结论"}
        with patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=MOCK_TEMPLATE), \
             patch("api.routes.admin.template_service.create_field",
                   new_callable=AsyncMock, return_value=field_with_feishu):
            resp = admin_client.post(
                f"/api/admin/templates/{TEMPLATE_ID}/fields",
                json={
                    "field_key": "conclusion",
                    "field_label": "检测结论",
                    "feishu_column": "检测结论",
                },
            )
        assert resp.status_code == 201
        assert resp.json()["data"]["feishu_column"] == "检测结论"


# ============ 字段排序扩展 ============

class TestReorderFieldsExtended:

    def test_reorder_empty_items(self, admin_client):
        """空排序列表也返回成功"""
        with patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=MOCK_TEMPLATE), \
             patch("api.routes.admin.template_service.reorder_fields",
                   new_callable=AsyncMock, return_value=True):
            resp = admin_client.put(
                f"/api/admin/templates/{TEMPLATE_ID}/fields/reorder",
                json={"items": []},
            )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_reorder_template_not_found_returns_404(self, admin_client):
        """模板不存在时返回 404"""
        with patch("api.routes.admin.template_service.get_template",
                   new_callable=AsyncMock, return_value=None):
            resp = admin_client.put(
                f"/api/admin/templates/{TEMPLATE_ID}/fields/reorder",
                json={"items": [{"id": FIELD_ID, "sort_order": 0}]},
            )
        assert resp.status_code == 404
