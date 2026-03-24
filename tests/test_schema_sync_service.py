"""schema_sync_service RPC 解析与 DDL 路径单元测试。"""
import json
from unittest.mock import MagicMock, patch

import pytest

from services.schema_sync_service import SchemaSyncService, SchemaError


class TestParseRpcResponse:
    def test_python_repr_string_as_raw(self):
        inner = {"success": True, "message": "ok"}
        s = str(inner)
        assert SchemaSyncService._parse_rpc_response(s) == inner

    def test_dict_passthrough(self):
        raw = {"success": True, "message": "ok"}
        assert SchemaSyncService._parse_rpc_response(raw) == raw

    def test_none_returns_empty(self):
        assert SchemaSyncService._parse_rpc_response(None) == {}

    def test_json_string_recursive(self):
        inner = {"success": True, "columns": ["a", "b"]}
        s = json.dumps(inner)
        assert SchemaSyncService._parse_rpc_response(s) == inner

    def test_list_nested_function_key(self):
        raw = [{"add_result_column": {"success": True, "message": "done"}}]
        assert SchemaSyncService._parse_rpc_response(raw) == {
            "success": True,
            "message": "done",
        }


class TestTryExtractJsonbBodyFromException:
    def test_args_dict_with_success(self):
        e = Exception()
        e.args = ({"success": True, "message": "列已存在"},)
        out = SchemaSyncService._try_extract_jsonb_body_from_exception(e)
        assert out["success"] is True

    def test_args_json_string(self):
        e = Exception()
        e.args = ('{"success": false, "error": "bad"}',)
        out = SchemaSyncService._try_extract_jsonb_body_from_exception(e)
        assert out["success"] is False
        assert out["error"] == "bad"

    def test_no_match_returns_none(self):
        e = Exception("network down")
        assert SchemaSyncService._try_extract_jsonb_body_from_exception(e) is None

    def test_args_python_repr_string_not_json(self):
        """生产常见：args[0] 为 dict 的 repr 字符串（单引号、True），json.loads 无法解析。"""
        body = str(
            {
                "success": True,
                "message": "已成功向 inspection_reports 新增列 test",
            }
        )
        e = Exception(body)
        out = SchemaSyncService._try_extract_jsonb_body_from_exception(e)
        assert out is not None
        assert out["success"] is True
        assert "新增列 test" in out["message"]


class TestExecuteRpcJsonb:
    def test_success_from_execute_exception_body(self):
        """模拟 supabase-py 将 JSONB 成功结果放在异常 args[0]。"""
        svc = SchemaSyncService.__new__(SchemaSyncService)
        mock_client = MagicMock()
        exc = Exception()
        exc.args = (
            {
                "success": True,
                "message": "列 x 已存在于 inspection_reports，无需新增",
            },
        )
        mock_client.rpc.return_value.execute.side_effect = exc

        with patch.object(svc, "_get_client", return_value=mock_client):
            data = svc._execute_rpc_jsonb(
                "add_result_column",
                {"p_table": "inspection_reports", "p_column": "x", "p_col_type": "TEXT"},
            )
        assert data["success"] is True
        assert "无需新增" in data["message"]

    def test_normal_result_data_dict(self):
        svc = SchemaSyncService.__new__(SchemaSyncService)
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.data = {"success": True, "message": "ok"}
        mock_client.rpc.return_value.execute.return_value = mock_result

        with patch.object(svc, "_get_client", return_value=mock_client):
            data = svc._execute_rpc_jsonb("add_result_column", {})
        assert data["success"] is True

    def test_real_failure_reraises(self):
        svc = SchemaSyncService.__new__(SchemaSyncService)
        mock_client = MagicMock()
        mock_client.rpc.return_value.execute.side_effect = OSError("boom")

        with patch.object(svc, "_get_client", return_value=mock_client):
            with pytest.raises(OSError, match="boom"):
                svc._execute_rpc_jsonb("add_result_column", {})

    def test_success_when_execute_raises_repr_string(self):
        """与线上一致：execute 抛出，args[0] 为 Python repr 字符串。"""
        svc = SchemaSyncService.__new__(SchemaSyncService)
        mock_client = MagicMock()
        body = str(
            {
                "success": True,
                "message": "已成功向 inspection_reports 新增列 test",
            }
        )
        mock_client.rpc.return_value.execute.side_effect = Exception(body)

        with patch.object(svc, "_get_client", return_value=mock_client):
            data = svc._execute_rpc_jsonb("add_result_column", {})
        assert data["success"] is True


class TestAddColumnIntegration:
    def test_add_column_success_after_exception_body(self):
        svc = SchemaSyncService.__new__(SchemaSyncService)
        mock_client = MagicMock()
        exc = Exception()
        exc.args = (
            {"success": True, "message": "列 t 已存在于 inspection_reports，无需新增"},
        )
        mock_client.rpc.return_value.execute.side_effect = exc

        with patch.object(svc, "_get_client", return_value=mock_client):
            with patch.object(svc, "invalidate_cache"):
                svc.add_column("inspection_reports", "t")

    def test_add_column_success_after_repr_string_exception(self):
        svc = SchemaSyncService.__new__(SchemaSyncService)
        mock_client = MagicMock()
        mock_client.rpc.return_value.execute.side_effect = Exception(
            str(
                {
                    "success": True,
                    "message": "已成功向 inspection_reports 新增列 test",
                }
            )
        )
        with patch.object(svc, "_get_client", return_value=mock_client):
            with patch.object(svc, "invalidate_cache"):
                svc.add_column("inspection_reports", "test")

    def test_add_column_schema_error_when_success_false(self):
        svc = SchemaSyncService.__new__(SchemaSyncService)
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.data = {"success": False, "error": "字段键名不合法"}
        mock_client.rpc.return_value.execute.return_value = mock_result

        with patch.object(svc, "_get_client", return_value=mock_client):
            with pytest.raises(SchemaError, match="字段键名不合法"):
                svc.add_column("inspection_reports", "BAD")
