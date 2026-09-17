# api/routes/parse.py
"""Parse 能力入口 - 参数化提交（ADR-0007）。

对外契约（内部冻结，外部形态由 #18 决定）：
- POST /api/parse/jobs：一次提交 = 原子受理 N 个单文件 Parse Job
- 201 新建；200 复用（幂等重放 / 活动执行复用）；409 冲突；422 参数非法
"""

from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies.auth import get_current_user, CurrentUser
from api.exceptions import AuthorizationError
from services.parse_request_service import (
    ParseRequestError,
    normalize_document_ids,
    normalize_target_pages,
    parse_request_service,
)

router = APIRouter(tags=["解析能力"])


class ParsePageRangesModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_pages: Optional[str] = None


class CreateParseRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_ids: List[str] = Field(min_length=1)
    parse_mode: Optional[Literal["pipeline", "vlm"]] = None
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


@router.post("/parse/jobs")
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
