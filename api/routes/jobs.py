# api/routes/jobs.py
"""Job 与 Result API - 创建任务、查询状态、读取结果。

Job 固定创建时选定的 Configuration Revision；执行统一由 JobRunner seam 完成。
租户隔离在应用层校验（API 使用 service_role 客户端，RLS 作为数据库层兜底）。
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependencies.auth import get_current_user, CurrentUser
from api.exceptions import AuthorizationError
from api.jobs import create_job, get_job
from services.configuration_service import configuration_service
from services.result_service import PARSE_SAMPLE_KEY, result_service
from services.supabase_service import supabase_service

router = APIRouter(tags=["任务与结果"])


# ============ 请求模型 ============

class CreateJobRequest(BaseModel):
    """创建 Job：固定一个已发布 Configuration Revision。"""

    configuration_revision_id: str
    document_ids: List[str] = Field(default_factory=list)
    job_type: str = "batch"


# ============ 权限辅助 ============

def _can_access_job(job: Dict[str, Any], user: CurrentUser) -> bool:
    """租户隔离：优先看 job.tenant_id；历史 job 无租户时按创建人。"""
    if user.is_super_admin():
        return True
    if job.get("tenant_id"):
        return user.can_access_tenant(job["tenant_id"])
    return job.get("created_by") == user.user_id


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
        job_type=request.job_type,
        created_by=user.user_id,
        related_document_ids=request.document_ids,
        tenant_id=configuration["tenant_id"],
        configuration_revision_id=request.configuration_revision_id,
    )
    job = await get_job(job_id)
    return {"success": True, "data": job}


@router.get("/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """查询 Job 状态（tenant 隔离）。"""
    job = await get_job(job_id)
    if not job or not _can_access_job(job, user):
        raise HTTPException(status_code=404, detail="任务不存在")
    return job


@router.get("/jobs/{job_id}/results")
async def list_job_results(
    job_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """读取某个 Job 产生的全部 Result（新→旧）。"""
    job = await get_job(job_id)
    if not job or not _can_access_job(job, user):
        raise HTTPException(status_code=404, detail="任务不存在")

    return await result_service.list_results(
        job_id=job_id,
        tenant_id=job.get("tenant_id"),
    )


@router.get("/jobs/{job_id}/parse-result")
async def get_job_parse_result(
    job_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """读取 parse Job 的 ParseResult（data JSONB）。"""
    job = await get_job(job_id)
    if not job or not _can_access_job(job, user):
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
        raise HTTPException(status_code=404, detail="解析结果不存在")

    return {
        "success": True,
        "result_id": parse_row.get("id"),
        "data": parse_row.get("data") or {},
    }


# ============ Result ============

@router.get("/results/{result_id}")
async def get_result(
    result_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """读取单条 Result（租户隔离）。"""
    result = await result_service.get_result(result_id)
    if not result or not user.can_access_tenant(result.get("tenant_id")):
        raise HTTPException(status_code=404, detail="结果不存在")
    return result
