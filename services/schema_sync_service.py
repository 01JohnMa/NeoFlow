# services/schema_sync_service.py
"""Schema 同步服务 - 前端字段配置变更时自动同步数据库列

通过调用 migration 005 中定义的 PostgreSQL RPC 函数（SECURITY DEFINER）
执行 ADD / RENAME / DROP COLUMN，并维护本地列名缓存，
避免每次入库都查询 information_schema。
"""

import ast
import json
import threading
from typing import Optional, Set, Dict, Any
from loguru import logger

from services.base import SupabaseClientMixin


# 系统保留列：这些列在所有结果表中都存在，禁止通过字段配置增删改
SYSTEM_COLUMNS: Set[str] = {
    "id", "document_id", "extraction_confidence", "extraction_version",
    "raw_extraction_data", "is_validated", "validated_by", "validated_at",
    "validation_notes", "created_at", "updated_at",
}


class SchemaError(Exception):
    """DDL 操作失败异常，包含面向用户的错误信息"""

    def __init__(self, message: str, non_null_count: Optional[int] = None):
        super().__init__(message)
        self.non_null_count = non_null_count


class SchemaSyncService(SupabaseClientMixin):
    """
    通过 Supabase RPC 调用 PostgreSQL 函数对结果表执行 DDL。

    维护本地线程安全的列名缓存（{table_name: set[column_name]}），
    DDL 执行后自动使缓存失效，下次查询重新从数据库读取。
    """

    _instance: Optional["SchemaSyncService"] = None
    _client = None

    # 列名缓存（表名 -> 列名集合）
    _columns_cache: Dict[str, Set[str]] = {}
    _cache_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ── 缓存管理 ──────────────────────────────────────────────────────

    def invalidate_cache(self, table_name: str) -> None:
        """使指定表的列名缓存失效（DDL 执行后调用）"""
        with self._cache_lock:
            self._columns_cache.pop(table_name, None)
        logger.debug(f"列名缓存已失效: {table_name}")

    async def get_columns(self, table_name: str) -> Set[str]:
        """
        获取结果表的实际物理列名集合（带本地缓存）。

        缓存命中直接返回；未命中则通过 RPC 查询 information_schema。
        查询失败时返回空集合（调用方应做降级处理，不直接抛异常）。
        """
        with self._cache_lock:
            if table_name in self._columns_cache:
                return self._columns_cache[table_name]

        try:
            data = await self._execute_rpc_jsonb(
                "get_result_table_columns", {"p_table": table_name}
            )

            if data.get("success") and data.get("columns") is not None:
                cols: Set[str] = set(data["columns"]) if data["columns"] else set()
            else:
                logger.warning(f"get_result_table_columns 响应异常: {data}")
                cols = set()

            with self._cache_lock:
                self._columns_cache[table_name] = cols
            logger.debug(f"列名缓存已加载: {table_name} ({len(cols)} 列)")
            return cols

        except Exception as e:
            logger.error(f"查询表 {table_name} 列名失败: {e}")
            return set()

    # ── RPC 辅助 ──────────────────────────────────────────────────────

    @staticmethod
    def _parse_dict_from_str(s: str) -> Optional[Dict[str, Any]]:
        """
        解析可能是 JSON 或 Python repr 的 dict 字符串（如单引号、True/False）。
        """
        s = s.strip()
        if not s.startswith("{"):
            return None
        try:
            parsed = json.loads(s)
            if isinstance(parsed, dict) and "success" in parsed:
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            parsed = ast.literal_eval(s)
            if isinstance(parsed, dict) and "success" in parsed:
                return parsed
        except (ValueError, SyntaxError, TypeError):
            pass
        return None

    @staticmethod
    def _try_extract_jsonb_body_from_exception(e: BaseException) -> Optional[Dict[str, Any]]:
        """
        从 postgrest / supabase-py 抛出的异常中提取 JSONB 函数返回体。

        supabase-py 2.11 + PostgREST 11.x 下，部分 JSONB 返回值会被包装成异常，
        实际结果可能在 e.args[0]（dict 或 **Python repr 字符串**）、或整段 str(e) 中。
        仅当提取到含 `success` 键的 dict 时才返回，避免误判真实网络错误。
        """
        for arg in e.args:
            if isinstance(arg, dict) and "success" in arg:
                return arg
            if isinstance(arg, str):
                parsed = SchemaSyncService._parse_dict_from_str(arg)
                if parsed is not None:
                    return parsed

        for attr in ("json", "details", "body", "message"):
            if not hasattr(e, attr):
                continue
            val = getattr(e, attr)
            if isinstance(val, dict) and "success" in val:
                return val
            if isinstance(val, str):
                parsed = SchemaSyncService._parse_dict_from_str(val)
                if parsed is not None:
                    return parsed

        # 整段 str(e) 可能仅为 dict 的 repr（单引号、True），或前面带前缀文案
        whole = str(e).strip()
        if "success" in whole:
            candidates = [whole]
            i, j = whole.find("{"), whole.rfind("}")
            if 0 <= i < j:
                candidates.insert(0, whole[i : j + 1])
            for cand in candidates:
                parsed = SchemaSyncService._parse_dict_from_str(cand)
                if parsed is not None:
                    return parsed

        return None

    @staticmethod
    def _parse_rpc_response(raw: Any) -> Dict[str, Any]:
        """
        将 supabase-py RPC 返回的 data 统一解析为 dict。

        supabase-py 2.x 对 JSONB 返回函数的响应格式可能是：
        - dict（直接）
        - list 中的第一个 dict
        - list 中的第一个 dict，其唯一 value 才是真正结果（函数名作为 key 的嵌套格式）
        - str：JSON 字符串
        """
        if raw is None:
            logger.debug("RPC 响应 data 为 None")
            return {}

        if isinstance(raw, str):
            s = raw.strip()
            if s.startswith(("{", "[")):
                try:
                    loaded = json.loads(s)
                    return SchemaSyncService._parse_rpc_response(loaded)
                except json.JSONDecodeError:
                    try:
                        loaded = ast.literal_eval(s)
                        return SchemaSyncService._parse_rpc_response(loaded)
                    except (ValueError, SyntaxError, TypeError):
                        logger.warning(f"RPC 响应字符串解析失败: {s[:200]}")
                        return {}
            return {}

        out: Dict[str, Any] = {}
        if isinstance(raw, dict):
            out = raw
        elif isinstance(raw, list) and raw:
            first = raw[0]
            if not isinstance(first, dict):
                out = {}
            else:
                # 处理 supabase-py 将函数名作为 key 的嵌套格式：
                # [{'func_name': {'success': True, ...}}]
                values = list(first.values())
                if len(first) == 1 and isinstance(values[0], dict):
                    out = values[0]
                else:
                    out = first
        else:
            out = {}

        if not isinstance(out, dict):
            logger.warning(
                f"RPC 解析结果非 dict；raw_type={type(raw).__name__} "
                f"repr={repr(raw)[:200]}"
            )
            return {}

        if "success" not in out and raw is not None:
            logger.warning(
                f"RPC 解析结果缺少 success 键；raw_type={type(raw).__name__} "
                f"repr={repr(raw)[:200]}"
            )
        return out

    async def _execute_rpc_jsonb(self, func_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行返回 JSONB 的 RPC，并统一处理 execute() 正常返回与「异常体即结果」的情况。
        """
        try:
            result = await self._run_sync(
                lambda: self._get_client().rpc(func_name, params).execute()
            )
            data = self._parse_rpc_response(result.data)
            if data == {} and result.data is not None:
                logger.warning(
                    f"RPC {func_name} 解析为空 dict；"
                    f"raw_type={type(result.data).__name__} "
                    f"raw_repr={repr(result.data)[:400]}"
                )
            return data
        except Exception as e:
            body = self._try_extract_jsonb_body_from_exception(e)
            if isinstance(body, dict) and "success" in body:
                logger.debug(f"RPC {func_name} 从 execute() 异常体解析出 JSONB: {body}")
                return body
            raise

    async def _call_ddl_rpc(self, func_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行 DDL 类 RPC 并返回解析后的结果 dict"""
        return await self._execute_rpc_jsonb(func_name, params)

    # ── DDL 操作 ──────────────────────────────────────────────────────

    async def add_column(self, table_name: str, field_key: str) -> None:
        """
        向结果表新增 TEXT 列。

        列已存在时幂等返回（不报错）。
        失败时抛出 SchemaError，调用方收到后应阻止字段配置写入。
        """
        logger.info(f"DDL ADD COLUMN: {table_name}.{field_key}")
        try:
            data = await self._call_ddl_rpc("add_result_column", {
                "p_table": table_name,
                "p_column": field_key,
                "p_col_type": "TEXT",
            })
            if not data.get("success"):
                raise SchemaError(data.get("error", "新增列失败"))
            logger.info(f"DDL 完成: {data.get('message')}")
            self.invalidate_cache(table_name)
        except SchemaError:
            raise
        except Exception as e:
            raise SchemaError(f"新增列 {field_key} 时遇到异常: {e}")

    async def rename_column(self, table_name: str, old_key: str, new_key: str) -> None:
        """
        重命名结果表列。

        新旧相同时幂等跳过。
        目标名称已存在时抛出 SchemaError（防止数据覆盖）。
        """
        if old_key == new_key:
            return
        logger.info(f"DDL RENAME COLUMN: {table_name}.{old_key} -> {new_key}")
        try:
            data = await self._call_ddl_rpc("rename_result_column", {
                "p_table": table_name,
                "p_old_col": old_key,
                "p_new_col": new_key,
            })
            if not data.get("success"):
                raise SchemaError(data.get("error", "列改名失败"))
            logger.info(f"DDL 完成: {data.get('message')}")
            self.invalidate_cache(table_name)
        except SchemaError:
            raise
        except Exception as e:
            raise SchemaError(f"重命名列 {old_key} -> {new_key} 时遇到异常: {e}")

    async def drop_column(self, table_name: str, field_key: str, force: bool = False) -> None:
        """
        删除结果表列。

        force=False（默认）：若该列存在非空历史数据，抛出 SchemaError
            （SchemaError.non_null_count 包含受影响行数，供前端展示确认弹窗）。
        force=True：忽略数据直接删除（数据永久丢失，不可恢复）。
        """
        logger.info(f"DDL DROP COLUMN: {table_name}.{field_key} (force={force})")
        try:
            data = await self._call_ddl_rpc("drop_result_column", {
                "p_table": table_name,
                "p_column": field_key,
                "p_force": force,
            })
            if not data.get("success"):
                non_null_count = data.get("non_null_count")
                raise SchemaError(
                    data.get("error", "删除列失败"),
                    non_null_count=int(non_null_count) if non_null_count is not None else None,
                )
            logger.info(f"DDL 完成: {data.get('message')}")
            self.invalidate_cache(table_name)
        except SchemaError:
            raise
        except Exception as e:
            raise SchemaError(f"删除列 {field_key} 时遇到异常: {e}")


# 单例实例
schema_sync_service = SchemaSyncService()
