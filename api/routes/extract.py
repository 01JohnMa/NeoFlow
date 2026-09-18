# api/routes/extract.py
"""Extract 能力入口（#32 v3.1 / ADR-0009）。

- POST /extract/jobs：一次提交 = 每个文档一个 Extract Job
  已发布配置 pin Revision；草稿配置冻结 Job 级执行快照
- GET /documents/{id}/extract-result：文档最新正式 Extract 结果
- GET /jobs/{id}/extract-result：指定 Job 的正式 Extract 结果（不回退文档最新）

本轮无 Idempotency-Key / 受理台账（随 #18）。
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies.auth import get_current_user, CurrentUser
from api.exceptions import AuthorizationError
from api.jobs import create_job, get_job
from api.routes.jobs import _can_access_job
from api.routes.documents.query import _check_document_access
from services.configuration_service import configuration_service
from services.extract_service import ExtractFailure, resolve_extract_spec
from services.result_service import result_service
from services.supabase_service import supabase_service

router = APIRouter(tags=["抽取能力"])

EXTRACT_SAMPLE_KEY = "extract"
SPEC_VERSION = "1"


class CreateExtractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    configuration_id: str
    document_ids: List[str] = Field(min_length=1)


def _snapshot_params(definition: Dict[str, Any]) -> Dict[str, Any]:
    """草稿快照：只冻结执行需要的字段（含 legacy fields 回退）。"""
    return {
        "target": definition.get("target") or "per_doc",
        "data_schema": definition.get("data_schema"),
        "fields": definition.get("fields") or [],
    }


async def _load_definition_and_spec(
    configuration: Dict[str, Any],
) -> tuple[Optional[str], Dict[str, Any]]:
    """返回 (revision_id, execution_spec)；两者按配置状态二选一。"""
    if configuration.get("status") == "published":
        revision_id = configuration.get("current_revision_id")
        revision = await configuration_service.get_revision(str(revision_id or ""))
        if not revision:
            raise HTTPException(status_code=409, detail="配置没有可用的已发布修订")
        spec = {
            "capability": "extract",
            "spec_version": SPEC_VERSION,
            "effective_params": _snapshot_params(revision.get("definition") or {}),
        }
        resolve_extract_spec({"execution_spec": spec})
        return revision["id"], spec

    definition = configuration.get("draft_definition") or {}
    spec = {
        "capability": "extract",
        "spec_version": SPEC_VERSION,
        "effective_params": _snapshot_params(definition),
    }
    resolve_extract_spec({"execution_spec": spec})
    return None, spec


@router.post("/extract/jobs", status_code=201)
async def create_extract_jobs(
    request: CreateExtractRequest,
    user: CurrentUser = Depends(get_current_user),
):
    configuration = await configuration_service.get_configuration(request.configuration_id)
    if not configuration:
        raise HTTPException(status_code=404, detail="配置不存在")
    if not user.can_access_tenant(configuration["tenant_id"]):
        raise AuthorizationError("无权使用该 Configuration")
    if configuration.get("type") != "extract":
        raise HTTPException(status_code=409, detail="该配置不是 Extract 类型")
    if configuration.get("status") == "archived":
        raise HTTPException(status_code=409, detail="配置已归档，不能创建新任务")

    document_ids = sorted({str(item).strip() for item in request.document_ids if str(item).strip()})
    if not document_ids:
        raise HTTPException(status_code=422, detail="至少需要一个文档")

    for document_id in document_ids:
        document = await supabase_service.get_document(document_id)
        if not document or document.get("tenant_id") != configuration["tenant_id"]:
            raise HTTPException(status_code=404, detail=f"文档不存在: {document_id}")
        if not user.is_tenant_admin() and document.get("user_id") != user.user_id:
            raise HTTPException(status_code=404, detail=f"文档不存在: {document_id}")

    try:
        revision_id, spec = await _load_definition_and_spec(configuration)
    except ExtractFailure as exc:
        status = 422 if exc.reason in ("schema_invalid", "schema_missing", "target_not_supported") else 409
        raise HTTPException(status_code=status, detail=f"{exc.reason}: {exc.message}")

    job_ids: List[str] = []
    for document_id in document_ids:
        job_id = await create_job(
            created_by=user.user_id,
            related_document_ids=[document_id],
            tenant_id=configuration["tenant_id"],
            configuration_revision_id=revision_id,
            execution_spec=None if revision_id else spec,
        )
        job_ids.append(job_id)

    return {
        "success": True,
        "data": {
            "job_ids": job_ids,
            "configuration_id": configuration["id"],
            "revision_id": revision_id,
            "mode": "published" if revision_id else "draft",
        },
    }


@router.get("/documents/{document_id}/extract-result")
async def get_document_extract_result(
    document_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    document = await supabase_service.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")
    _check_document_access(document, user, document_id)

    rows = await result_service.list_results(
        document_id=document_id,
        tenant_id=document.get("tenant_id"),
        sample_key=EXTRACT_SAMPLE_KEY,
        limit=1,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="抽取结果不存在")
    row = rows[0]
    return {
        "success": True,
        "result_id": row.get("id"),
        "job_id": row.get("job_id"),
        "data": row.get("data"),
        "engine": row.get("engine"),
    }


@router.get("/jobs/{job_id}/extract-result")
async def get_job_extract_result(
    job_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    job = await get_job(job_id)
    if not job or not await _can_access_job(job, user):
        raise HTTPException(status_code=404, detail="任务不存在")

    rows = await result_service.list_results(
        job_id=job_id,
        tenant_id=job.get("tenant_id"),
        sample_key=EXTRACT_SAMPLE_KEY,
        limit=1,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="该任务没有正式抽取结果")
    row = rows[0]
    return {
        "success": True,
        "result_id": row.get("id"),
        "job_id": row.get("job_id"),
        "data": row.get("data"),
        "engine": row.get("engine"),
    }
