# tests/services/test_schema_sync_service.py
"""SchemaSyncService 单元测试 — mock Supabase RPC，不依赖真实数据库"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.schema_sync_service import SchemaSyncService, SchemaError


# ============ fixtures ============

@pytest.fixture
def svc():
    """返回注入了 mock client 的 SchemaSyncService 实例"""
    instance = SchemaSyncService()
    instance._client = MagicMock()
    instance._columns_cache = {}
    return instance


def _make_rpc_result(data):
    result = MagicMock()
    result.data = data
    rpc_chain = MagicMock()
    rpc_chain.execute.return_value = result
    return rpc_chain, result


# ============ _parse_rpc_response ============

class TestParseRpcResponse:
    """_parse_rpc_response 对各种 supabase-py 返回格式的解析"""

    def test_dict_returned_directly(self):
        """直接返回 dict 时原样返回"""
        raw = {"success": True, "message": "ok"}
        assert SchemaSyncService._parse_rpc_response(raw) == raw

    def test_list_with_plain_dict(self):
        """list 中第一个元素是普通 dict 时返回该 dict"""
        raw = [{"success": True, "columns": ["id", "name"]}]
        result = SchemaSyncService._parse_rpc_response(raw)
        assert result == {"success": True, "columns": ["id", "name"]}

    def test_list_with_nested_func_name_key(self):
        """supabase-py 将函数名作为 key 的嵌套格式应被正确解包"""
        raw = [{"add_result_column": {"success": True, "message": "列已存在，无需新增"}}]
        result = SchemaSyncService._parse_rpc_response(raw)
        assert result["success"] is True
        assert "列已存在" in result["message"]

    def test_list_with_nested_rename_func_key(self):
        """rename_result_column 嵌套格式解包"""
        raw = [{"rename_result_column": {"success": True, "message": "列已重命名"}}]
        result = SchemaSyncService._parse_rpc_response(raw)
        assert result["success"] is True

    def test_list_with_nested_drop_func_key(self):
        """drop_result_column 嵌套格式解包"""
        raw = [{"drop_result_column": {"success": False, "error": "列有历史数据", "non_null_count": 5}}]
        result = SchemaSyncService._parse_rpc_response(raw)
        assert result["success"] is False
        assert result["non_null_count"] == 5

    def test_empty_list_returns_empty_dict(self):
        """空 list 返回空 dict"""
        assert SchemaSyncService._parse_rpc_response([]) == {}

    def test_none_returns_empty_dict(self):
        """None 返回空 dict"""
        assert SchemaSyncService._parse_rpc_response(None) == {}

    def test_list_with_non_dict_first_element(self):
        """list 第一个元素不是 dict 时返回空 dict"""
        assert SchemaSyncService._parse_rpc_response(["not_a_dict"]) == {}

    def test_multi_key_dict_not_unwrapped(self):
        """list 中 dict 有多个 key 时不做解包，直接返回"""
        raw = [{"key1": "v1", "key2": "v2"}]
        result = SchemaSyncService._parse_rpc_response(raw)
        assert result == {"key1": "v1", "key2": "v2"}


# ============ SchemaError ============

class TestSchemaError:

    def test_message_accessible(self):
        err = SchemaError("列名冲突")
        assert str(err) == "列名冲突"

    def test_non_null_count_default_none(self):
        err = SchemaError("有历史数据")
        assert err.non_null_count is None

    def test_non_null_count_set(self):
        err = SchemaError("有历史数据", non_null_count=42)
        assert err.non_null_count == 42

    def test_is_exception(self):
        with pytest.raises(SchemaError, match="测试错误"):
            raise SchemaError("测试错误")


# ============ add_column ============

class TestAddColumn:

    @pytest.mark.asyncio
    async def test_success_plain_dict(self, svc):
        """RPC 直接返回 dict 且 success=True 时正常完成"""
        rpc_chain, _ = _make_rpc_result({"success": True, "message": "列已新增"})
        svc._client.rpc.return_value = rpc_chain
        await svc.add_column("test_table", "new_col")  # 不抛异常即通过

    @pytest.mark.asyncio
    async def test_success_nested_format(self, svc):
        """RPC 返回嵌套函数名格式时正常完成（修复 bug 的核心场景）"""
        rpc_chain, _ = _make_rpc_result(
            [{"add_result_column": {"success": True, "message": "列 no 已存在于 sampling_forms，无需新增"}}]
        )
        svc._client.rpc.return_value = rpc_chain
        await svc.add_column("sampling_forms", "no")  # 不抛异常即通过

    @pytest.mark.asyncio
    async def test_column_already_exists_is_idempotent(self, svc):
        """列已存在时（success=True）幂等通过，不抛 SchemaError"""
        rpc_chain, _ = _make_rpc_result({"success": True, "message": "列已存在，无需新增"})
        svc._client.rpc.return_value = rpc_chain
        await svc.add_column("test_table", "existing_col")  # 不抛异常

    @pytest.mark.asyncio
    async def test_failure_raises_schema_error(self, svc):
        """RPC 返回 success=False 时抛出 SchemaError"""
        rpc_chain, _ = _make_rpc_result({"success": False, "error": "列名不合法"})
        svc._client.rpc.return_value = rpc_chain
        with pytest.raises(SchemaError, match="列名不合法"):
            await svc.add_column("test_table", "bad col")

    @pytest.mark.asyncio
    async def test_rpc_exception_raises_schema_error(self, svc):
        """RPC 调用本身抛异常时包装为 SchemaError"""
        svc._client.rpc.side_effect = Exception("network error")
        with pytest.raises(SchemaError, match="新增列.*时遇到异常"):
            await svc.add_column("test_table", "col")

    @pytest.mark.asyncio
    async def test_invalidates_cache_on_success(self, svc):
        """成功后缓存应被清除"""
        svc._columns_cache["test_table"] = {"id", "old_col"}
        rpc_chain, _ = _make_rpc_result({"success": True, "message": "ok"})
        svc._client.rpc.return_value = rpc_chain
        await svc.add_column("test_table", "new_col")
        assert "test_table" not in svc._columns_cache


# ============ rename_column ============

class TestRenameColumn:

    @pytest.mark.asyncio
    async def test_same_key_is_noop(self, svc):
        """新旧 key 相同时不调用 RPC"""
        await svc.rename_column("test_table", "col", "col")
        svc._client.rpc.assert_not_called()

    @pytest.mark.asyncio
    async def test_success(self, svc):
        """正常重命名成功"""
        rpc_chain, _ = _make_rpc_result({"success": True, "message": "列已重命名"})
        svc._client.rpc.return_value = rpc_chain
        await svc.rename_column("test_table", "old_col", "new_col")  # 不抛异常

    @pytest.mark.asyncio
    async def test_target_exists_raises_schema_error(self, svc):
        """目标列名已存在时抛出 SchemaError"""
        rpc_chain, _ = _make_rpc_result({"success": False, "error": "目标列名已存在"})
        svc._client.rpc.return_value = rpc_chain
        with pytest.raises(SchemaError, match="目标列名已存在"):
            await svc.rename_column("test_table", "old_col", "existing_col")

    @pytest.mark.asyncio
    async def test_nested_format_success(self, svc):
        """嵌套函数名格式也能正确解析"""
        rpc_chain, _ = _make_rpc_result(
            [{"rename_result_column": {"success": True, "message": "ok"}}]
        )
        svc._client.rpc.return_value = rpc_chain
        await svc.rename_column("test_table", "a", "b")  # 不抛异常

    @pytest.mark.asyncio
    async def test_invalidates_cache_on_success(self, svc):
        """成功后缓存应被清除"""
        svc._columns_cache["test_table"] = {"id", "old_col"}
        rpc_chain, _ = _make_rpc_result({"success": True, "message": "ok"})
        svc._client.rpc.return_value = rpc_chain
        await svc.rename_column("test_table", "old_col", "new_col")
        assert "test_table" not in svc._columns_cache


# ============ drop_column ============

class TestDropColumn:

    @pytest.mark.asyncio
    async def test_success(self, svc):
        """正常删除成功"""
        rpc_chain, _ = _make_rpc_result({"success": True, "message": "列已删除"})
        svc._client.rpc.return_value = rpc_chain
        await svc.drop_column("test_table", "old_col")  # 不抛异常

    @pytest.mark.asyncio
    async def test_has_data_raises_schema_error_with_count(self, svc):
        """有历史数据且 force=False 时抛出 SchemaError 并携带 non_null_count"""
        rpc_chain, _ = _make_rpc_result({
            "success": False,
            "error": "列有历史数据",
            "non_null_count": 7,
        })
        svc._client.rpc.return_value = rpc_chain
        with pytest.raises(SchemaError) as exc_info:
            await svc.drop_column("test_table", "data_col", force=False)
        assert exc_info.value.non_null_count == 7

    @pytest.mark.asyncio
    async def test_force_true_passes_param_to_rpc(self, svc):
        """force=True 时 RPC 调用参数中包含 p_force=True"""
        rpc_chain, _ = _make_rpc_result({"success": True, "message": "强制删除成功"})
        svc._client.rpc.return_value = rpc_chain
        await svc.drop_column("test_table", "col", force=True)
        call_params = svc._client.rpc.call_args[0][1]
        assert call_params["p_force"] is True

    @pytest.mark.asyncio
    async def test_nested_format_with_non_null_count(self, svc):
        """嵌套格式下 non_null_count 也能正确解析"""
        rpc_chain, _ = _make_rpc_result(
            [{"drop_result_column": {"success": False, "error": "有数据", "non_null_count": 3}}]
        )
        svc._client.rpc.return_value = rpc_chain
        with pytest.raises(SchemaError) as exc_info:
            await svc.drop_column("test_table", "col")
        assert exc_info.value.non_null_count == 3

    @pytest.mark.asyncio
    async def test_invalidates_cache_on_success(self, svc):
        """成功后缓存应被清除"""
        svc._columns_cache["test_table"] = {"id", "old_col"}
        rpc_chain, _ = _make_rpc_result({"success": True, "message": "ok"})
        svc._client.rpc.return_value = rpc_chain
        await svc.drop_column("test_table", "old_col")
        assert "test_table" not in svc._columns_cache


# ============ get_columns ============

class TestGetColumns:

    @pytest.mark.asyncio
    async def test_returns_columns_from_rpc(self, svc):
        """正常情况：从 RPC 返回列名集合"""
        rpc_chain, _ = _make_rpc_result({"success": True, "columns": ["id", "name", "value"]})
        svc._client.rpc.return_value = rpc_chain
        cols = await svc.get_columns("test_table")
        assert cols == {"id", "name", "value"}

    @pytest.mark.asyncio
    async def test_caches_result(self, svc):
        """第二次调用命中缓存，不再查 RPC"""
        rpc_chain, _ = _make_rpc_result({"success": True, "columns": ["id"]})
        svc._client.rpc.return_value = rpc_chain
        await svc.get_columns("test_table")
        await svc.get_columns("test_table")
        assert svc._client.rpc.call_count == 1

    @pytest.mark.asyncio
    async def test_rpc_failure_returns_empty_set(self, svc):
        """RPC 失败时返回空集合，不抛异常"""
        svc._client.rpc.side_effect = Exception("timeout")
        cols = await svc.get_columns("test_table")
        assert cols == set()

    @pytest.mark.asyncio
    async def test_rpc_success_false_returns_empty_set(self, svc):
        """RPC 返回 success=False 时返回空集合"""
        rpc_chain, _ = _make_rpc_result({"success": False})
        svc._client.rpc.return_value = rpc_chain
        cols = await svc.get_columns("test_table")
        assert cols == set()

    @pytest.mark.asyncio
    async def test_invalidate_cache_clears_entry(self, svc):
        """invalidate_cache 后下次调用重新查 RPC"""
        rpc_chain, _ = _make_rpc_result({"success": True, "columns": ["id"]})
        svc._client.rpc.return_value = rpc_chain
        await svc.get_columns("test_table")
        svc.invalidate_cache("test_table")
        await svc.get_columns("test_table")
        assert svc._client.rpc.call_count == 2
