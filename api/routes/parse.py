# api/routes/parse.py
"""Parse 能力入口 - 参数化提交（ADR-0007）。

对外契约（内部冻结，外部形态由 #18 决定）：
- POST /api/parse/jobs：一次提交 = 原子受理 N 个单文件 Parse Job
- 201 新建；200 复用（幂等重放 / 活动执行复用）；409 冲突；422 参数非法
"""

from typing import List, Literal, Optional
import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies.auth import (
    CurrentUser,
    get_current_user,
    require_platform_scope,
)
from api.exceptions import AuthorizationError, FileSizeError, FileTypeError, ProcessingError
from api.routes.documents.helpers import save_upload_file, validate_file_extension
from config.settings import settings
from services.supabase_service import supabase_service
from services.parse_request_service import (
    ParseRequestError,
    normalize_document_ids,
    normalize_parse_options,
    normalize_target_pages,
    parse_request_service,
)

router = APIRouter(tags=["解析能力"])
_FORBIDDEN_DIRECT_FIELDS = frozenset({
    "configuration_id",
    "configuration_revision_id",
    "tenant_id",
    "department_id",
})


async def reject_forbidden_direct_fields(request: Request) -> None:
    """Reject internal selectors instead of silently ignoring extra form keys."""
    form = await request.form()
    query_params = getattr(request, "query_params", {})
    forbidden = sorted(
        _FORBIDDEN_DIRECT_FIELDS.intersection(
            set(form.keys()) | set(query_params.keys())
        )
    )
    if forbidden:
        raise HTTPException(
            status_code=422,
            detail=f"公共能力不接受内部字段: {', '.join(forbidden)}",
        )


async def save_uploaded_document(file: UploadFile, user: CurrentUser) -> dict:
    """Persist one direct capability upload using the existing UPLOAD_FOLDER."""
    if not user.tenant_id:
        raise AuthorizationError("请求没有有效的租户范围")
    filename = (file.filename or "").strip()
    if not filename or not validate_file_extension(filename):
        raise FileTypeError(settings.ALLOWED_EXTENSIONS)

    document_id = str(uuid.uuid4())
    extension = os.path.splitext(filename)[1].lower()
    os.makedirs(settings.UPLOAD_FOLDER, exist_ok=True)
    stored_filename = f"{document_id}{extension}"
    file_path = os.path.join(settings.UPLOAD_FOLDER, stored_filename)
    try:
        file_size = await save_upload_file(file, file_path)
        if file_size > settings.MAX_FILE_SIZE:
            raise FileSizeError(settings.MAX_FILE_SIZE / 1024 / 1024)
        await supabase_service.create_document({
            "id": document_id,
            "user_id": user.user_id,
            "file_name": stored_filename,
            "original_file_name": filename,
            "file_path": file_path,
            "file_size": file_size,
            "file_type": file.content_type,
            "file_extension": extension,
            "mime_type": file.content_type,
            "status": "uploaded",
            "tenant_id": user.tenant_id,
        })
    except (FileSizeError, FileTypeError):
        if os.path.exists(file_path):
            os.remove(file_path)
        raise
    except Exception as exc:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise ProcessingError(f"文档保存失败，请重试: {exc}") from exc
    return {
        "document_id": document_id,
        "file_path": file_path,
        "file_size": file_size,
        "created_at": datetime.now().isoformat(),
    }


async def _delete_uploaded_document(document_id: str, file_path: str) -> None:
    """Best-effort rollback when admission rejects a newly uploaded document."""
    try:
        await supabase_service.delete_document(document_id)
    except Exception:
        pass
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except OSError:
        pass


class ParsePageRangesModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_pages: Optional[str] = None


class CreateParseRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_ids: List[str] = Field(min_length=1)
    parse_mode: Optional[Literal["pipeline", "vlm"]] = None
    language: Optional[str] = None
    enable_formula: Optional[bool] = None
    enable_table: Optional[bool] = None
    remove_watermark: Optional[bool] = None
    watermark_keywords: Optional[List[str]] = None
    page_ranges: Optional[ParsePageRangesModel] = None


_STATUS_TO_HTTP = {
    "ok": 201,
    "reused": 200,
    "conflict": 409,
    "limit_exceeded": 422,
    "invalid": 422,
    "not_found": 404,
    "forbidden": 403,
}


@router.post("/parse/jobs", include_in_schema=False)
async def create_parse_jobs(
    request: CreateParseRequestModel,
    response: Response,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    user: CurrentUser = Depends(get_current_user),
):
    """
    提交 Parse 能力：一次请求为每个文档创建一个 Job。

    - Idempotency-Key（可选）：同键同请求返回原 Job（终态后仍成立）
    - 活动复用：相同发起人 + 相同文档集合 + 相同冻结规格返回原 Job
    - 输入与活动请求重叠但规格不同 → 409
    """
    if not user.tenant_id:
        raise AuthorizationError("当前用户未关联租户，无法提交解析")

    key = (idempotency_key or "").strip() or None

    try:
        document_ids = normalize_document_ids(request.document_ids)
        target_pages = normalize_target_pages(
            request.page_ranges.target_pages if request.page_ranges else None
        )
        options = normalize_parse_options(
            language=request.language,
            enable_formula=request.enable_formula,
            enable_table=request.enable_table,
            remove_watermark=request.remove_watermark,
            watermark_keywords=request.watermark_keywords,
        )
    except ParseRequestError as exc:
        raise HTTPException(status_code=422, detail=exc.message)

    result = await parse_request_service.admit(
        tenant_id=user.tenant_id,
        requester_id=user.user_id,
        is_admin=user.is_tenant_admin(),
        document_ids=document_ids,
        parse_mode=request.parse_mode,
        target_pages=target_pages,
        idempotency_key=key,
        options=options,
    )

    status = result.get("status") or "invalid"
    http_status = _STATUS_TO_HTTP.get(status, 422)
    if http_status >= 400:
        raise HTTPException(
            status_code=http_status,
            detail=result.get("reason") or "解析提交失败",
        )

    response.status_code = http_status
    return {
        "success": True,
        "data": {
            "request_id": result.get("request_id"),
            "job_ids": result.get("job_ids") or [],
            "status": status,
            "reused": status == "reused",
            "reuse_reason": result.get("reason") if status == "reused" else None,
        },
    }


@router.post("/parse", status_code=202)
async def create_direct_parse(
    request: Request,
    file: UploadFile = File(...),
    parse_mode: Optional[Literal["pipeline", "vlm"]] = Form(None),
    language: Optional[str] = Form(None),
    enable_formula: Optional[bool] = Form(None),
    enable_table: Optional[bool] = Form(None),
    remove_watermark: Optional[bool] = Form(None),
    watermark_keywords: Optional[str] = Form(None),
    target_pages: Optional[str] = Form(None),
    user: CurrentUser = Depends(require_platform_scope("parse")),
):
    """Direct platform capability: upload one file and enqueue Parse."""
    await reject_forbidden_direct_fields(request)
    uploaded = await save_uploaded_document(file, user)
    try:
        document_ids = normalize_document_ids([uploaded["document_id"]])
        normalized_pages = normalize_target_pages(target_pages)
        keywords = None
        if watermark_keywords:
            keywords = [item.strip() for item in watermark_keywords.split(",") if item.strip()]
        options = normalize_parse_options(
            language=language,
            enable_formula=enable_formula,
            enable_table=enable_table,
            remove_watermark=remove_watermark,
            watermark_keywords=keywords,
        )
        result = await parse_request_service.admit(
            tenant_id=user.tenant_id,
            requester_id=user.user_id,
            is_admin=user.is_tenant_admin(),
            document_ids=document_ids,
            parse_mode=parse_mode,
            target_pages=normalized_pages,
            idempotency_key=None,
            options=options,
        )
    except ParseRequestError as exc:
        await _delete_uploaded_document(uploaded["document_id"], uploaded["file_path"])
        raise HTTPException(status_code=422, detail=exc.message)

    status = result.get("status") or "invalid"
    http_status = _STATUS_TO_HTTP.get(status, 422)
    if http_status >= 400:
        await _delete_uploaded_document(uploaded["document_id"], uploaded["file_path"])
        raise HTTPException(status_code=http_status, detail=result.get("reason") or "解析提交失败")
    return {
        "success": True,
        "data": {
            "document_id": uploaded["document_id"],
            "job_ids": result.get("job_ids") or [],
            "job_id": (result.get("job_ids") or [None])[0],
            "status": status,
        },
    }
