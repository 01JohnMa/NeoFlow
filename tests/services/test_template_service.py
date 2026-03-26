# tests/services/test_template_service.py
"""TemplateService 单元测试 — 使用 mock Supabase client，不依赖真实数据库"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from loguru import logger

from tests.conftest import (
    TEMPLATE_ID, FIELD_ID, EXAMPLE_ID, TENANT_ID,
    MOCK_TEMPLATE, MOCK_FIELD, MOCK_EXAMPLE,
)


# ============ fixtures ============

@pytest.fixture
def svc(mock_supabase_client):
    """
    返回一个注入了 mock client 的 TemplateService 实例。
    每次测试重置单例的 _client，避免测试间污染。
    """
    from services.template_service import TemplateService
    instance = TemplateService()
    instance._client = mock_supabase_client
    return instance


def _chain(client, data=None, count=None):
    """快捷方式：配置 client.table() 链式调用的 execute() 返回值"""
    result = MagicMock()
    result.data = data if data is not None else []
    result.count = count
    chain = client.table.return_value
    chain.execute.return_value = result
    return chain, result


class TestLogSafety:

    @pytest.mark.asyncio
    async def test_update_template_config_logs_exception_with_braces_without_secondary_error(self, svc, mock_supabase_client):
        """模板配置更新失败时，异常消息含大括号也不会触发日志二次报错"""
        mock_supabase_client.table.side_effect = Exception(
            "{'code': 'PGRST204', 'message': \"Column push_attachment does not exist\"}"
        )

        with patch.object(logger, "error") as mock_logger_error:
            with pytest.raises(Exception, match="PGRST204"):
                await svc.update_template_config(TEMPLATE_ID, {"push_attachment": True})

        mock_logger_error.assert_called_once()


# ============ get_tenant_templates ============

class TestGetTenantTemplates:

    @pytest.mark.asyncio
    async def test_returns_templates(self, svc, mock_supabase_client):
        """正常情况：返回模板列表"""
        _chain(mock_supabase_client, data=[MOCK_TEMPLATE])
        result = await svc.get_tenant_templates(TENANT_ID)
        assert len(result) == 1
        assert result[0]["id"] == TEMPLATE_ID

    @pytest.mark.asyncio
    async def test_returns_empty_list(self, svc, mock_supabase_client):
        """无模板时返回空列表"""
        _chain(mock_supabase_client, data=[])
        result = await svc.get_tenant_templates(TENANT_ID)
        assert result == []

    @pytest.mark.asyncio
    async def test_db_exception_returns_empty(self, svc, mock_supabase_client):
        """数据库异常时返回空列表（不抛出）"""
        mock_supabase_client.table.side_effect = Exception("DB connection failed")
        result = await svc.get_tenant_templates(TENANT_ID)
        assert result == []

    @pytest.mark.asyncio
    async def test_active_only_filter_applied(self, svc, mock_supabase_client):
        """active_only=True 时应调用 .eq('is_active', True)"""
        chain, _ = _chain(mock_supabase_client, data=[MOCK_TEMPLATE])
        await svc.get_tenant_templates(TENANT_ID, active_only=True)
        # 验证链式调用中包含 is_active 过滤
        calls = [str(c) for c in chain.eq.call_args_list]
        assert any("is_active" in c for c in calls)

    @pytest.mark.asyncio
    async def test_all_templates_when_active_only_false(self, svc, mock_supabase_client):
        """active_only=False 时不应过滤 is_active"""
        chain, _ = _chain(mock_supabase_client, data=[MOCK_TEMPLATE])
        await svc.get_tenant_templates(TENANT_ID, active_only=False)
        calls = [str(c) for c in chain.eq.call_args_list]
        assert not any("is_active" in c for c in calls)


# ============ get_template ============

class TestGetTemplate:

    @pytest.mark.asyncio
    async def test_returns_template_by_id(self, svc, mock_supabase_client):
        """合法 UUID → 返回模板"""
        _chain(mock_supabase_client, data=[MOCK_TEMPLATE])
        result = await svc.get_template(TEMPLATE_ID)
        assert result is not None
        assert result["id"] == TEMPLATE_ID

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, svc, mock_supabase_client):
        """UUID 合法但数据库无记录 → 返回 None"""
        _chain(mock_supabase_client, data=[])
        result = await svc.get_template(TEMPLATE_ID)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_invalid_uuid(self, svc, mock_supabase_client):
        """非 UUID 格式 → 直接返回 None，不查数据库"""
        result = await svc.get_template("not-a-uuid")
        mock_supabase_client.table.assert_not_called()
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_string(self, svc, mock_supabase_client):
        """空字符串 → 返回 None"""
        result = await svc.get_template("")
        assert result is None

    @pytest.mark.asyncio
    async def test_db_exception_returns_none(self, svc, mock_supabase_client):
        """数据库异常 → 返回 None（不抛出）"""
        mock_supabase_client.table.side_effect = Exception("timeout")
        result = await svc.get_template(TEMPLATE_ID)
        assert result is None


# ============ build_extraction_prompt ============

class TestBuildExtractionPrompt:

    def _make_template(self, fields=None, examples=None):
        return {
            "name": "检测报告",
            "template_fields": fields or [],
            "template_examples": examples or [],
        }

    def test_contains_doc_type(self, svc):
        """Prompt 中包含文档类型名称"""
        template = self._make_template()
        prompt = svc.build_extraction_prompt(template, "OCR文本")
        assert "检测报告" in prompt

    def test_contains_ocr_text(self, svc):
        """Prompt 中包含 OCR 文本"""
        template = self._make_template()
        prompt = svc.build_extraction_prompt(template, "样品编号：SN-001")
        assert "样品编号：SN-001" in prompt

    def test_field_key_in_prompt(self, svc):
        """字段 key 出现在 Prompt 中"""
        fields = [{"field_key": "sample_no", "field_label": "样品编号",
                   "field_type": "text", "extraction_hint": ""}]
        template = self._make_template(fields=fields)
        prompt = svc.build_extraction_prompt(template, "")
        assert "sample_no" in prompt
        assert "样品编号" in prompt

    def test_date_field_type_hint(self, svc):
        """日期类型字段包含格式提示"""
        fields = [{"field_key": "test_date", "field_label": "检测日期",
                   "field_type": "date", "extraction_hint": ""}]
        template = self._make_template(fields=fields)
        prompt = svc.build_extraction_prompt(template, "")
        assert "YYYY-MM-DD" in prompt

    def test_number_field_type_hint(self, svc):
        """数值类型字段包含类型提示"""
        fields = [{"field_key": "weight", "field_label": "重量",
                   "field_type": "number", "extraction_hint": ""}]
        template = self._make_template(fields=fields)
        prompt = svc.build_extraction_prompt(template, "")
        assert "数值类型" in prompt

    def test_examples_included_in_prompt(self, svc):
        """有示例时 Prompt 中包含示例内容"""
        examples = [{"example_input": "样品编号：SN-001",
                     "example_output": {"sample_no": "SN-001"}}]
        template = self._make_template(examples=examples)
        prompt = svc.build_extraction_prompt(template, "")
        assert "SN-001" in prompt
        assert "示例1" in prompt

    def test_no_examples_section_when_empty(self, svc):
        """无示例时 Prompt 中不含示例标题"""
        template = self._make_template(examples=[])
        prompt = svc.build_extraction_prompt(template, "")
        assert "参考示例" not in prompt

    def test_multiple_fields_all_present(self, svc):
        """多个字段都出现在 Prompt 中"""
        fields = [
            {"field_key": "f1", "field_label": "字段1", "field_type": "text", "extraction_hint": ""},
            {"field_key": "f2", "field_label": "字段2", "field_type": "text", "extraction_hint": ""},
        ]
        template = self._make_template(fields=fields)
        prompt = svc.build_extraction_prompt(template, "")
        assert "f1" in prompt and "f2" in prompt


# ============ build_field_mapping ============

class TestBuildFieldMapping:

    def test_maps_field_key_to_feishu_column(self, svc):
        template = {
            "template_fields": [
                {"field_key": "sample_no", "feishu_column": "样品编号"},
                {"field_key": "test_date", "feishu_column": "检测日期"},
            ]
        }
        mapping = svc.build_field_mapping(template)
        assert mapping == {"sample_no": "样品编号", "test_date": "检测日期"}

    def test_skips_fields_without_feishu_column(self, svc):
        template = {
            "template_fields": [
                {"field_key": "sample_no", "feishu_column": ""},
                {"field_key": "test_date", "feishu_column": "检测日期"},
            ]
        }
        mapping = svc.build_field_mapping(template)
        assert "sample_no" not in mapping
        assert "test_date" in mapping

    def test_empty_fields_returns_empty_dict(self, svc):
        assert svc.build_field_mapping({"template_fields": []}) == {}


# ============ get_field_keys ============

class TestGetFieldKeys:

    def test_returns_all_keys(self, svc):
        template = {
            "template_fields": [
                {"field_key": "a"},
                {"field_key": "b"},
            ]
        }
        assert svc.get_field_keys(template) == ["a", "b"]

    def test_skips_fields_without_key(self, svc):
        template = {
            "template_fields": [
                {"field_key": "a"},
                {"field_label": "无key字段"},
            ]
        }
        assert svc.get_field_keys(template) == ["a"]


# ============ create_field ============

class TestCreateField:

    @pytest.mark.asyncio
    async def test_creates_field_successfully(self, svc, mock_supabase_client):
        """正常创建字段，返回新字段数据"""
        _chain(mock_supabase_client, data=[MOCK_FIELD])
        with patch.object(svc, "_get_result_table_for_template", new_callable=AsyncMock, return_value=None):
            result = await svc.create_field(TEMPLATE_ID, {
                "field_key": "sample_no",
                "field_label": "样品编号",
                "field_type": "text",
            })
        assert result["field_key"] == "sample_no"

    @pytest.mark.asyncio
    async def test_schema_error_propagates(self, svc, mock_supabase_client):
        """DDL 失败时 SchemaError 向上传播"""
        from services.schema_sync_service import SchemaError
        with patch.object(svc, "_get_result_table_for_template", new_callable=AsyncMock, return_value="inspection_reports"), \
             patch("services.schema_sync_service.schema_sync_service.add_column", new_callable=AsyncMock, side_effect=SchemaError("列名冲突")):
            with pytest.raises(SchemaError):
                await svc.create_field(TEMPLATE_ID, {
                    "field_key": "duplicate_col",
                    "field_label": "重复列",
                })


# ============ update_field ============

class TestUpdateField:

    @pytest.mark.asyncio
    async def test_updates_field_label(self, svc, mock_supabase_client):
        """更新字段标签（不改 key），返回更新后数据"""
        updated = {**MOCK_FIELD, "field_label": "新标签"}
        _chain(mock_supabase_client, data=[updated])
        with patch.object(svc, "get_field_by_id", new_callable=AsyncMock, return_value=MOCK_FIELD):
            result = await svc.update_field(FIELD_ID, {"field_label": "新标签"})
        assert result["field_label"] == "新标签"

    @pytest.mark.asyncio
    async def test_rename_triggers_schema_rename(self, svc, mock_supabase_client):
        """field_key 改变时触发 rename_column"""
        _chain(mock_supabase_client, data=[{**MOCK_FIELD, "field_key": "new_key"}])
        with patch.object(svc, "get_field_by_id", new_callable=AsyncMock, return_value=MOCK_FIELD), \
             patch.object(svc, "_get_result_table_for_template", new_callable=AsyncMock, return_value="inspection_reports"), \
             patch("services.schema_sync_service.schema_sync_service.rename_column", new_callable=AsyncMock) as mock_rename:
            await svc.update_field(FIELD_ID, {"field_key": "new_key"})
            mock_rename.assert_awaited_once_with("inspection_reports", "sample_no", "new_key")

    @pytest.mark.asyncio
    async def test_field_not_found_raises(self, svc, mock_supabase_client):
        """字段不存在时抛出 ValueError"""
        with patch.object(svc, "get_field_by_id", new_callable=AsyncMock, return_value=None):
            with pytest.raises(ValueError, match="字段不存在"):
                await svc.update_field(FIELD_ID, {"field_label": "x"})


# ============ delete_field ============

class TestDeleteField:

    @pytest.mark.asyncio
    async def test_deletes_field_successfully(self, svc, mock_supabase_client):
        """正常删除字段"""
        _chain(mock_supabase_client, data=[])
        with patch.object(svc, "get_field_by_id", new_callable=AsyncMock, return_value=MOCK_FIELD), \
             patch.object(svc, "_get_result_table_for_template", new_callable=AsyncMock, return_value=None):
            result = await svc.delete_field(FIELD_ID)
        assert result is True

    @pytest.mark.asyncio
    async def test_schema_error_on_non_null_data(self, svc, mock_supabase_client):
        """有历史数据且 force=False 时 SchemaError 向上传播"""
        from services.schema_sync_service import SchemaError
        with patch.object(svc, "get_field_by_id", new_callable=AsyncMock, return_value=MOCK_FIELD), \
             patch.object(svc, "_get_result_table_for_template", new_callable=AsyncMock, return_value="inspection_reports"), \
             patch("services.schema_sync_service.schema_sync_service.drop_column",
                   new_callable=AsyncMock, side_effect=SchemaError("列有历史数据", non_null_count=5)):
            with pytest.raises(SchemaError) as exc_info:
                await svc.delete_field(FIELD_ID, force=False)
            assert exc_info.value.non_null_count == 5

    @pytest.mark.asyncio
    async def test_force_delete_bypasses_schema_error(self, svc, mock_supabase_client):
        """force=True 时 drop_column 被调用且带 force=True"""
        _chain(mock_supabase_client, data=[])
        with patch.object(svc, "get_field_by_id", new_callable=AsyncMock, return_value=MOCK_FIELD), \
             patch.object(svc, "_get_result_table_for_template", new_callable=AsyncMock, return_value="inspection_reports"), \
             patch("services.schema_sync_service.schema_sync_service.drop_column", new_callable=AsyncMock) as mock_drop:
            await svc.delete_field(FIELD_ID, force=True)
            mock_drop.assert_awaited_once_with("inspection_reports", "sample_no", force=True)

    @pytest.mark.asyncio
    async def test_returns_true_when_field_not_found(self, svc, mock_supabase_client):
        """字段已不存在时视为成功，返回 True"""
        with patch.object(svc, "get_field_by_id", new_callable=AsyncMock, return_value=None):
            result = await svc.delete_field(FIELD_ID)
        assert result is True


# ============ reorder_fields ============

class TestReorderFields:

    @pytest.mark.asyncio
    async def test_calls_update_for_each_item(self, svc, mock_supabase_client):
        """每个排序项都触发一次 update"""
        chain = mock_supabase_client.table.return_value
        chain.update.return_value = chain
        chain.eq.return_value = chain
        chain.execute.return_value = MagicMock(data=[])

        order_list = [
            {"id": "id-1", "sort_order": 0},
            {"id": "id-2", "sort_order": 1},
            {"id": "id-3", "sort_order": 2},
        ]
        result = await svc.reorder_fields(TEMPLATE_ID, order_list)
        assert result is True
        assert chain.update.call_count == 3

    @pytest.mark.asyncio
    async def test_empty_order_list(self, svc, mock_supabase_client):
        """空排序列表不报错"""
        result = await svc.reorder_fields(TEMPLATE_ID, [])
        assert result is True


# ============ merge_extraction_results ============

# ============ 管理端模板配置 ==========

class TestAdminTemplateConfig:

    @pytest.mark.asyncio
    async def test_get_admin_templates_selects_push_attachment(self, svc, mock_supabase_client):
        """管理端模板列表查询应包含 push_attachment 字段"""
        chain, _ = _chain(mock_supabase_client, data=[{**MOCK_TEMPLATE, "push_attachment": True}])
        result = await svc.get_admin_templates(TENANT_ID)
        assert result[0]["push_attachment"] is True
        select_arg = chain.select.call_args.args[0]
        assert "push_attachment" in select_arg

    @pytest.mark.asyncio
    async def test_update_template_config_updates_push_attachment(self, svc, mock_supabase_client):
        """更新模板配置时应写入并回读 push_attachment"""
        chain = mock_supabase_client.table.return_value
        chain.update.return_value = chain
        chain.eq.return_value = chain
        chain.select.return_value = chain
        chain.execute.side_effect = [
            MagicMock(data=[]),
            MagicMock(data=[{**MOCK_TEMPLATE, "push_attachment": False}]),
        ]

        result = await svc.update_template_config(TEMPLATE_ID, {"push_attachment": False})

        assert result["push_attachment"] is False
        chain.update.assert_called_once_with({"push_attachment": False})
        select_calls = [call.args[0] for call in chain.select.call_args_list]
        assert any("push_attachment" in call for call in select_calls)


# ============ merge_extraction_results ============

class TestMergeExtractionResults:

    def test_merges_two_results(self, svc):
        """两份结果合并，B 覆盖 A 的同名字段"""
        a = {"field1": "val_a", "field2": "val_a2"}
        b = {"field2": "val_b2", "field3": "val_b3"}
        merged = svc.merge_extraction_results(a, b)
        assert merged["field1"] == "val_a"
        assert merged["field2"] == "val_b2"  # B 覆盖 A
        assert merged["field3"] == "val_b3"

    def test_result_a_none(self, svc):
        """A 为 None 时只返回 B"""
        b = {"key": "value"}
        merged = svc.merge_extraction_results(None, b)
        assert merged == {"key": "value"}

    def test_result_b_none(self, svc):
        """B 为 None 时只返回 A"""
        a = {"key": "value"}
        merged = svc.merge_extraction_results(a, None)
        assert merged == {"key": "value"}

    def test_both_none(self, svc):
        """两者都为 None 时返回空字典"""
        merged = svc.merge_extraction_results(None, None)
        assert merged == {}

    def test_both_empty(self, svc):
        """两者都为空字典时返回空字典"""
        merged = svc.merge_extraction_results({}, {})
        assert merged == {}
