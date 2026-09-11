# services/result_service.py
"""Result 服务 - append-only 抽取结果存储。

每次抽取都会为每个逻辑样品追加一条 Result：
- data：抽取字段值
- field_meta：逐字段 provenance/source/confidence 与复核状态
- review_state：样品级复核状态

旧业务表在本阶段仍以镜像方式写入（见 handle_processing_success），
读取侧迁移见后续票。
"""

from typing import Any, Dict, List, Optional

from loguru import logger

from services.base import SupabaseClientMixin

RESULTS_TABLE = "results"
DEFAULT_SAMPLE_KEY = "default"
DEFAULT_REVIEW_STATE = "pending"


def build_field_meta(
    data: Optional[Dict[str, Any]],
    source: Optional[str] = None,
    confidence: Optional[float] = None,
    review_state: str = DEFAULT_REVIEW_STATE,
) -> Dict[str, Any]:
    """为每个字段构建 provenance/复核元数据。

    confidence 无法按字段获得时保持 None（不伪造数字）。
    """
    return {
        key: {
            "source": source,
            "confidence": confidence,
            "review_state": review_state,
        }
        for key in (data or {})
    }


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
        source: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> Dict[str, Any]:
        """构建一条 Result 记录（不含 id/时间戳，由数据库生成）。"""
        return {
            "tenant_id": tenant_id,
            "job_id": job_id,
            "document_id": document_id,
            "config_revision_id": config_revision_id,
            "sample_key": sample_key,
            "data": data or {},
            "field_meta": build_field_meta(data, source=source, confidence=confidence),
            "review_state": DEFAULT_REVIEW_STATE,
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

    async def get_result(self, result_id: str) -> Optional[Dict[str, Any]]:
        """按 ID 获取 Result。"""
        try:
            result = await self._run_sync(
                lambda: self._get_client().table(RESULTS_TABLE).select("*")
                .eq("id", result_id)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"获取 Result 失败: {e}")
            return None

    async def list_results(
        self,
        *,
        tenant_id: Optional[str] = None,
        job_id: Optional[str] = None,
        document_id: Optional[str] = None,
        review_state: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """列出 Result（按租户/Job/文档/复核状态过滤，新→旧）。"""
        try:
            query = self._get_client().table(RESULTS_TABLE).select("*")
            if tenant_id:
                query = query.eq("tenant_id", tenant_id)
            if job_id:
                query = query.eq("job_id", job_id)
            if document_id:
                query = query.eq("document_id", document_id)
            if review_state:
                query = query.eq("review_state", review_state)
            query = query.order("created_at", desc=True).limit(limit)
            result = await self._run_sync(query.execute)
            return result.data or []
        except Exception as e:
            logger.error(f"列出 Result 失败: {e}")
            return []

    async def record_extraction_result(
        self,
        *,
        tenant_id: Optional[str],
        document_id: Optional[str],
        result: Dict[str, Any],
        job_id: Optional[str] = None,
        config_revision_id: Optional[str] = None,
        source: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """把一次抽取输出写成 Result（逐页抽取时每个样品一行）。

        缺少 tenant_id 时跳过（历史数据兜底），避免破坏旧流程。
        """
        if not tenant_id:
            logger.warning(
                f"缺少 tenant_id，跳过 Result 写入: document_id={document_id}"
            )
            return []

        samples = result.get("extraction_results") or []
        rows: List[Dict[str, Any]] = []

        if samples:
            for index, sample in enumerate(samples, 1):
                sample_data = sample.get("data") or {}
                rows.append(self.build_result_row(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    data=sample_data,
                    sample_key=str(sample.get("sample_index") or index),
                    job_id=job_id,
                    config_revision_id=config_revision_id,
                    source=source,
                ))
        else:
            rows.append(self.build_result_row(
                tenant_id=tenant_id,
                document_id=document_id,
                data=result.get("extraction_data") or {},
                sample_key=DEFAULT_SAMPLE_KEY,
                job_id=job_id,
                config_revision_id=config_revision_id,
                source=source,
            ))

        created: List[Dict[str, Any]] = []
        for row in rows:
            stored = await self.create_result(row)
            if stored:
                created.append(stored)
        return created


# 单例实例
result_service = ResultService()
