# services/result_service.py
"""Result 服务 - append-only 结果存储。

每类执行追加一条 Result：
- `sample_key="parse"`：ParseResult 整体 JSONB（解析契约）
- `sample_key="default"`：其他能力的结构化结果 JSONB（如 classify/split）

Result 是唯一结果事实源，旧业务表镜像已随 #12 移除。
"""

from typing import Any, Dict, List, Optional

from loguru import logger

from services.base import SupabaseClientMixin

RESULTS_TABLE = "results"
DEFAULT_SAMPLE_KEY = "default"
PARSE_SAMPLE_KEY = "parse"


class ResultService(SupabaseClientMixin):
    """Result 读写封装（创建/读取；不提供删除入口）。"""

    _instance: Optional['ResultService'] = None
    _client = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def build_result_row(
        self,
        *,
        tenant_id: str,
        document_id: Optional[str],
        data: Dict[str, Any],
        sample_key: str = DEFAULT_SAMPLE_KEY,
        job_id: Optional[str] = None,
        config_revision_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """构建一条 Result 记录（不含 id/时间戳，由数据库生成）。"""
        return {
            "tenant_id": tenant_id,
            "job_id": job_id,
            "document_id": document_id,
            "config_revision_id": config_revision_id,
            "sample_key": sample_key,
            "data": data or {},
        }

    async def create_result(self, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """追加一条 Result。"""
        try:
            created = await self._run_sync(
                lambda: self._get_client().table(RESULTS_TABLE).insert(result).execute()
            )
        except Exception as e:
            logger.error(f"写入 Result 失败: {e}")
            raise
        return created.data[0] if created.data else None

    async def list_results(
        self,
        *,
        tenant_id: Optional[str] = None,
        job_id: Optional[str] = None,
        document_id: Optional[str] = None,
        sample_key: Optional[str] = None,
        exclude_sample_key: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """列出 Result（按租户/Job/文档/样品类型过滤，新→旧）。

        sample_key / exclude_sample_key 在数据库层过滤（LIMIT 之前），
        避免大量结果把目标类型挤出截断窗口。
        """
        try:
            query = self._get_client().table(RESULTS_TABLE).select("*")
            if tenant_id:
                query = query.eq("tenant_id", tenant_id)
            if job_id:
                query = query.eq("job_id", job_id)
            if document_id:
                query = query.eq("document_id", document_id)
            if sample_key:
                query = query.eq("sample_key", sample_key)
            if exclude_sample_key:
                query = query.neq("sample_key", exclude_sample_key)
            query = query.order("created_at", desc=True).limit(limit)
            result = await self._run_sync(query.execute)
            return result.data or []
        except Exception as e:
            logger.error(f"列出 Result 失败: {e}")
            return []

    async def get_document_parse_result(
        self,
        document_id: str,
        *,
        tenant_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """获取文档最新的 ParseResult 行（sample_key=parse），无则 None。"""
        rows = await self.list_results(
            document_id=document_id,
            tenant_id=tenant_id,
            sample_key=PARSE_SAMPLE_KEY,
            limit=1,
        )
        return rows[0] if rows else None

    async def record_parse_result(
        self,
        *,
        tenant_id: Optional[str],
        document_id: Optional[str],
        parse_data: Dict[str, Any],
        job_id: Optional[str] = None,
        config_revision_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """把一份 ParseResult（整体 JSONB）落成单条 Result。

        sample_key 固定为 parse，供读接口识别。
        """
        if not tenant_id:
            logger.warning(
                f"缺少 tenant_id，跳过 ParseResult 写入: document_id={document_id}"
            )
            return None

        row = self.build_result_row(
            tenant_id=tenant_id,
            document_id=document_id,
            data=parse_data,
            sample_key=PARSE_SAMPLE_KEY,
            job_id=job_id,
            config_revision_id=config_revision_id,
        )
        return await self.create_result(row)


# 单例实例
result_service = ResultService()
