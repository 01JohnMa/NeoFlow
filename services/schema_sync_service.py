# services/schema_sync_service.py
"""Schema 同步服务 - 前端字段配置变更时自动同步数据库列

通过调用 migration 005 中定义的 PostgreSQL RPC 函数（SECURITY DEFINER）
执行 ADD / RENAME / DROP COLUMN，并维护本地列名缓存，
避免每次入库都查询 information_schema。
"""

import threading
from typing import Optional, Set, Dict, Any
from loguru import logger


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


class SchemaSyncService:
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

    def _get_client(self):
        """懒加载 Supabase 客户端（避免循环导入）"""
        if self._client is None:
            from services.supabase_service import supabase_service
            self._client = supabase_service.client
        return self._client

    # ── 缓存管理 ──────────────────────────────────────────────────────

    def invalidate_cache(self, table_name: str) -> None:
        """使指定表的列名缓存失效（DDL 执行后调用）"""
        with self._cache_lock:
            self._columns_cache.pop(table_name, None)
        logger.debug(f"列名缓存已失效: {table_name}")

    def get_columns(self, table_name: str) -> Set[str]:
        """
        获取结果表的实际物理列名集合（带本地缓存）。

        缓存命中直接返回；未命中则通过 RPC 查询 information_schema。
        查询失败时返回空集合（调用方应做降级处理，不直接抛异常）。
        """
        with self._cache_lock:
            if table_name in self._columns_cache:
                return self._columns_cache[table_name]

        try:
            result = self._get_client().rpc(
                "get_result_table_columns", {"p_table": table_name}
            ).execute()

            data = self._parse_rpc_response(result.data)

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
    def _parse_rpc_response(raw: Any) -> Dict[str, Any]:
        """
        将 supabase-py RPC 返回的 data 统一解析为 dict。

        supabase-py 2.x 对 JSONB 返回函数的响应格式可能是：
        - dict（直接）
        - list 中的第一个 dict
        """
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, list) and raw:
            first = raw[0]
            return first if isinstance(first, dict) else {}
        return {}

    def _call_ddl_rpc(self, func_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行 DDL 类 RPC 并返回解析后的结果 dict"""
        result = self._get_client().rpc(func_name, params).execute()
        return self._parse_rpc_response(result.data)

    # ── DDL 操作 ──────────────────────────────────────────────────────

    def add_column(self, table_name: str, field_key: str) -> None:
        """
        向结果表新增 TEXT 列。

        列已存在时幂等返回（不报错）。
        失败时抛出 SchemaError，调用方收到后应阻止字段配置写入。
        """
        logger.info(f"DDL ADD COLUMN: {table_name}.{field_key}")
        try:
            data = self._call_ddl_rpc("add_result_column", {
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

    def rename_column(self, table_name: str, old_key: str, new_key: str) -> None:
        """
        重命名结果表列。

        新旧相同时幂等跳过。
        目标名称已存在时抛出 SchemaError（防止数据覆盖）。
        """
        if old_key == new_key:
            return
        logger.info(f"DDL RENAME COLUMN: {table_name}.{old_key} -> {new_key}")
        try:
            data = self._call_ddl_rpc("rename_result_column", {
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

    def drop_column(self, table_name: str, field_key: str, force: bool = False) -> None:
        """
        删除结果表列。

        force=False（默认）：若该列存在非空历史数据，抛出 SchemaError
            （SchemaError.non_null_count 包含受影响行数，供前端展示确认弹窗）。
        force=True：忽略数据直接删除（数据永久丢失，不可恢复）。
        """
        logger.info(f"DDL DROP COLUMN: {table_name}.{field_key} (force={force})")
        try:
            data = self._call_ddl_rpc("drop_result_column", {
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
