# services/result_service.py
"""Result 服务 - append-only 抽取结果存储。

每次抽取都会为每个逻辑样品追加一条 Result：
- data：抽取字段值
- field_meta：逐字段 provenance/source/confidence 与复核状态
- review_state：样品级复核状态

读取侧统一走 get_document_result（共享访问器）；Result 是唯一结果事实源，
旧业务表镜像已随 #12 移除。
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger

from services.base import SupabaseClientMixin

RESULTS_TABLE = "results"
DEFAULT_SAMPLE_KEY = "default"
PARSE_SAMPLE_KEY = "parse"
DEFAULT_REVIEW_STATE = "pending"
APPROVED_REVIEW_STATE = "approved"
REJECTED_REVIEW_STATE = "rejected"

# 无 job_id 的同步抽取按时间窗口归批（逐样品写入发生在同一次处理内）。
RESULT_BATCH_WINDOW_SECONDS = 120


def result_to_extraction_data(
    row: Dict[str, Any],
    document_id: Optional[str] = None,
) -> Dict[str, Any]:
    """把 Result 行适配为旧业务表行的形状，保持 API/推送响应兼容。"""
    data = dict(row.get("data") or {})
    data["document_id"] = document_id or row.get("document_id")
    data["is_validated"] = row.get("review_state") == APPROVED_REVIEW_STATE
    return data


def _sample_sort_key(row: Dict[str, Any]) -> tuple:
    """逐页抽取时第一页为主样品；非数字 key 排在数字之后。"""
    key = str(row.get("sample_key") or DEFAULT_SAMPLE_KEY)
    if key.isdigit():
        return (0, int(key))
    return (1, key)


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _latest_batch(samples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """把 desc 排序的样品行切成“最新一批”。"""
    newest = samples[0]
    newest_job_id = newest.get("job_id")
    if newest_job_id:
        return [row for row in samples if row.get("job_id") == newest_job_id]

    newest_time = _parse_timestamp(newest.get("created_at"))
    if newest_time is None:
        return [newest]

    batch: List[Dict[str, Any]] = []
    for row in samples:
        row_time = _parse_timestamp(row.get("created_at"))
        if (
            row_time is None
            or abs((newest_time - row_time).total_seconds()) > RESULT_BATCH_WINDOW_SECONDS
        ):
            break
        batch.append(row)
    return batch


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
    """Result 读写封装（创建/读取/复核；不提供删除入口）。"""

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
        field_meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """构建一条 Result 记录（不含 id/时间戳，由数据库生成）。

        field_meta 缺省按 data 逐字段生成；parse 结果不是字段表，显式传 {}。
        """
        return {
            "tenant_id": tenant_id,
            "job_id": job_id,
            "document_id": document_id,
            "config_revision_id": config_revision_id,
            "sample_key": sample_key,
            "data": data or {},
            "field_meta": (
                field_meta
                if field_meta is not None
                else build_field_meta(data, source=source, confidence=confidence)
            ),
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

    async def get_document_result(
        self,
        document_id: str,
        *,
        tenant_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """获取文档最新一批抽取的 Result 主样品行（排除 parse 结果）。

        这是读取侧的唯一入口：详情、审核、飞书/Excel、CRM 都从这里取数据。
        逐页抽取时主样品为 sample_key 最小（第一页）的那条，
        与旧业务表镜像写入的 extraction_data 保持一致。
        """
        rows = await self.list_results(
            document_id=document_id,
            tenant_id=tenant_id,
            limit=200,
        )
        samples = [
            row for row in rows if row.get("sample_key") != PARSE_SAMPLE_KEY
        ]
        if not samples:
            return None

        batch = _latest_batch(samples)
        return min(batch, key=_sample_sort_key)

    async def update_result_review(
        self,
        *,
        document_id: str,
        review_state: str,
        data: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """把审核结果写回文档最新的 Result 行。

        - data：字段修正，合并进原 JSONB（不整行覆盖）
        - field_meta：逐字段保留 source/confidence，更新 review_state
        - review_state：样品级复核状态（approved / rejected）

        文档没有 Result（历史数据）时返回 None，由调用方决定是否走镜像兜底。
        """
        row = await self.get_document_result(document_id, tenant_id=tenant_id)
        if not row:
            logger.warning(f"审核写回时未找到 Result: document_id={document_id}")
            return None

        merged_data = {**(row.get("data") or {})}
        if data:
            merged_data.update(data)

        existing_meta = row.get("field_meta") or {}
        merged_meta: Dict[str, Any] = {}
        for field_key in merged_data:
            meta = {
                "source": None,
                "confidence": None,
                **(existing_meta.get(field_key) or {}),
            }
            meta["review_state"] = review_state
            merged_meta[field_key] = meta

        payload = {
            "data": merged_data,
            "field_meta": merged_meta,
            "review_state": review_state,
        }
        try:
            updated = await self._run_sync(
                lambda: self._get_client().table(RESULTS_TABLE)
                .update(payload)
                .eq("id", row["id"])
                .execute()
            )
        except Exception as e:
            logger.error(f"更新 Result 复核状态失败: {e}")
            raise
        return updated.data[0] if updated.data else None

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

        parse 结果不是字段表，field_meta 保持空对象；
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
            field_meta={},
        )
        return await self.create_result(row)


# 单例实例
result_service = ResultService()
