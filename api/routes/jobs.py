# api/routes/jobs.py
"""Job 与 Result API - 创建任务、查询状态、读取结果。

Job 固定创建时选定的 Configuration Revision；执行统一由 JobRunner seam 完成。
租户隔离在应用层校验（API 使用 service_role 客户端，RLS 作为数据库层兜底）。
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.dependencies.auth import get_current_user, CurrentUser
from api.exceptions import AuthorizationError
from api.jobs import create_job, get_job, list_jobs
from services.configuration_service import configuration_service
from services.result_service import PARSE_SAMPLE_KEY, result_service
from services.supabase_service import supabase_service

router = APIRouter(tags=["任务与结果"])


# ============ 请求模型 ============

class CreateJobRequest(BaseModel):
    """创建 Job：固定一个已发布 Configuration Revision。"""

    configuration_revision_id: str
    document_ids: List[str] = Field(default_factory=list)


# ============ 权限辅助 ============

async def _can_access_job(job: Dict[str, Any], user: CurrentUser) -> bool:
    """Job 授权：继承输入文档权限；管理员按租户；历史无租户 Job 按创建人。

    普通成员只有在能访问 Job 的全部输入文档时才可完整读取该 Job。
    """
    if user.is_super_admin():
        return True
    if job.get("tenant_id") and not user.can_access_tenant(job["tenant_id"]):
        return False
    if user.is_tenant_admin():
        return True

    document_ids = [str(doc_id) for doc_id in (job.get("document_ids") or []) if doc_id]
    if not document_ids:
        return job.get("created_by") == user.user_id

    for document_id in document_ids:
        document = await supabase_service.get_document(document_id)
        if not document or not _can_access_document(document, user):
            return False
    return True


async def _load_pinned_configuration(
    revision_id: str,
    user: CurrentUser,
) -> Dict[str, Any]:
    """加载 Revision 及其 Configuration，并校验租户访问权。"""
    revision = await configuration_service.get_revision(revision_id)
    if not revision:
        raise HTTPException(status_code=404, detail="Configuration Revision 不存在")

    configuration = await configuration_service.get_configuration(
        revision["configuration_id"]
    )
    if not configuration:
        raise HTTPException(status_code=404, detail="Configuration 不存在")

    if not user.can_access_tenant(configuration["tenant_id"]):
        raise AuthorizationError("无权使用该 Configuration")
    if configuration.get("status") == "archived":
        raise HTTPException(status_code=409, detail="配置已归档，不能创建新任务")

    if configuration.get("type") == "extract":
        raise HTTPException(
            status_code=409,
            detail="Extract 任务请使用 POST /api/extract/jobs（带 schema 校验与权限检查）",
        )

    from services.job_runner import job_runner

    if configuration.get("type") not in job_runner.handlers:
        raise HTTPException(
            status_code=409,
            detail=f"配置类型 {configuration.get('type')} 尚未实现，无法创建任务",
        )

    return configuration


# ============ Job ============

@router.post("/jobs", status_code=201)
async def create_job_endpoint(
    request: CreateJobRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """创建 Job，固定指定的 Configuration Revision。"""
    configuration = await _load_pinned_configuration(
        request.configuration_revision_id, user
    )

    for document_id in request.document_ids:
        document = await supabase_service.get_document(document_id)
        if not document or document.get("tenant_id") != configuration["tenant_id"]:
            raise HTTPException(status_code=404, detail=f"文档不存在: {document_id}")

    job_id = await create_job(
        created_by=user.user_id,
        related_document_ids=request.document_ids,
        tenant_id=configuration["tenant_id"],
        configuration_revision_id=request.configuration_revision_id,
    )
    job = await get_job(job_id)
    return {"success": True, "data": job}


@router.get("/jobs")
async def list_jobs_endpoint(
    document_id: Optional[str] = None,
    configuration_revision_id: Optional[str] = None,
    created_by: Optional[str] = None,
    capability: Optional[str] = Query(None, description="按执行能力过滤，如 extract"),
    limit: int = 50,
    user: CurrentUser = Depends(get_current_user),
):
    """列出 Job（新→旧）。

    - super_admin：可跨租户，可选 tenant 过滤
    - 租户管理员：本租户全部
    - 普通成员：强制只看自己发起的 Job
    - capability=extract：草稿快照 + Extract 配置的 Revision 均命中
    """
    if user.is_super_admin():
        tenant_id = None
        effective_created_by = created_by
    else:
        if not user.tenant_id:
            return {"success": True, "data": []}
        tenant_id = user.tenant_id
        effective_created_by = created_by
        if not user.is_tenant_admin():
            effective_created_by = user.user_id

    capability_revision_ids: Optional[List[str]] = None
    if capability == "extract":
        capability_revision_ids = await _extract_revision_ids(tenant_id)

    jobs = await list_jobs(
        tenant_id=tenant_id,
        document_id=document_id,
        configuration_revision_id=configuration_revision_id,
        created_by=effective_created_by,
        capability=capability,
        capability_revision_ids=capability_revision_ids,
        limit=max(1, min(limit, 100)),
    )
    return {"success": True, "data": jobs}


async def _extract_revision_ids(tenant_id: Optional[str]) -> List[str]:
    """收集租户下全部 Extract Configuration 的 Revision（含历史修订）。"""
    configurations = await configuration_service.list_configurations(
        tenant_id=tenant_id,
        type="extract",
    )
    configuration_ids = [
        str(item["id"]) for item in configurations if item.get("id")
    ]
    return await configuration_service.list_revision_ids(configuration_ids)


@router.get("/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """查询 Job 状态（tenant 隔离）。"""
    job = await get_job(job_id)
    if not job or not await _can_access_job(job, user):
        raise HTTPException(status_code=404, detail="任务不存在")
    return job


@router.get("/jobs/{job_id}/parse-result")
async def get_job_parse_result(
    job_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """读取 Job 的 ParseResult（data JSONB）。

    parse Job 直接按 job_id 命中；抽取等内联解析的 Job 其 ParseResult
    写入时 job_id 为空，回退按 Job 关联文档取最新 ParseResult。
    """
    job = await get_job(job_id)
    if not job or not await _can_access_job(job, user):
        raise HTTPException(status_code=404, detail="任务不存在")

    results = await result_service.list_results(
        job_id=job_id,
        tenant_id=job.get("tenant_id"),
        limit=50,
    )
    parse_row = next(
        (row for row in results if row.get("sample_key") == PARSE_SAMPLE_KEY),
        None,
    )
    if not parse_row:
        for document_id in job.get("document_ids") or []:
            parse_row = await result_service.get_document_parse_result(
                document_id,
                tenant_id=job.get("tenant_id"),
            )
            if parse_row:
                break
    if not parse_row:
        raise HTTPException(status_code=404, detail="解析结果不存在")

    # 回退路径可能命中其他文档的最新 Parse：仍须通过文档授权
    if parse_row.get("document_id"):
        document = await supabase_service.get_document(str(parse_row["document_id"]))
        if not document or not _can_access_document(document, user):
            raise HTTPException(status_code=404, detail="解析结果不存在")
    elif not user.is_tenant_admin():
        raise HTTPException(status_code=404, detail="解析结果不存在")

    return {
        "success": True,
        "result_id": parse_row.get("id"),
        "data": parse_row.get("data") or {},
    }


# ============ Result ============

def _can_access_document(document: Dict[str, Any], user: CurrentUser) -> bool:
    """文档授权：所有者（需租户一致）/ 租户管理员 / 超级管理员。"""
    if user.is_super_admin():
        return True
    if user.is_tenant_admin() and document.get("tenant_id") == user.tenant_id:
        return True
    if document.get("user_id") != user.user_id:
        return False
    return not user.tenant_id or document.get("tenant_id") == user.tenant_id

