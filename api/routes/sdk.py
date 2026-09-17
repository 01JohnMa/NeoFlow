"""AI template generation SDK routes."""

import os
import re
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile

from api.dependencies.auth import CurrentUser, get_current_user
from api.exceptions import AuthorizationError
from api.jobs import get_job
from config.settings import settings
from services.parse_service import normalize_parse_mode
from services.result_service import result_service
from services.supabase_service import supabase_service
from sdk.agents.orchestrator import orchestrator
from sdk.excel_template import scan_excel_placeholders
from sdk.models import (
    CommitSessionRequest,
    ConfirmTemplateRequest,
    DetectedField,
    DocumentAnalysis,
    ExcelTemplatePlaceholder,
    ParseRetryRequest,
    SDKModelProfileRequest,
    SDKSession,
    SDKSessionResponse,
    SDKSessionState,
)
from sdk.session import session_store

router = APIRouter(prefix="/sdk", tags=["AI模板生成"])


def _require_admin(user: CurrentUser) -> None:
    if not user.is_tenant_admin():
        raise AuthorizationError("仅管理员可访问此接口")


async def _rebuild_session(session_id: str, user: CurrentUser):
    """内存缺失（例如服务重启）时，从解析 Job + 文档 + Parse Result 重建会话。"""
    try:
        job = await get_job(session_id)
    except Exception:
        # 非法 id（如非 UUID）等查询失败按“会话不存在”处理
        return None
    if not job:
        return None
    document_ids = job.get("document_ids") or []
    if not document_ids:
        return None

    document = await supabase_service.get_document(str(document_ids[0]))
    if not document:
        return None

    if not user.is_super_admin():
        tenant_ok = bool(document.get("tenant_id")) and document.get("tenant_id") == user.tenant_id
        owner_ok = document.get("user_id") == user.user_id
        if not (tenant_ok or owner_ok):
            return None

    tenant_id = document.get("tenant_id") or job.get("tenant_id") or ""
    # 恢复优先级：执行规格 → 历史 Revision → 默认
    parse_mode = "pipeline"
    spec = job.get("execution_spec")
    if isinstance(spec, dict) and spec:
        effective = spec.get("effective_params") or {}
        parse_mode = normalize_parse_mode(effective.get("model_version"))
    else:
        revision_id = job.get("configuration_revision_id")
        if revision_id:
            from services.configuration_service import configuration_service

            revision = await configuration_service.get_revision(str(revision_id))
            definition = (revision or {}).get("definition") or {}
            parse_mode = normalize_parse_mode((definition.get("parse") or {}).get("model_version"))

    state = SDKSessionState.PARSING
    parse_error = None
    status = job.get("status")
    if status == "failed":
        state = SDKSessionState.PARSE_FAILED
        parse_error = job.get("error") or "解析失败"
    elif status == "completed":
        row = await result_service.get_document_parse_result(
            str(document_ids[0]),
            tenant_id=tenant_id,
        )
        if row:
            state = SDKSessionState.PARSED
            parse_error = None
        else:
            state = SDKSessionState.PARSE_FAILED
            parse_error = "解析结果缺失，请重试"

    excel_name, excel_path, excel_placeholders = _recover_excel_template(str(document_ids[0]))
    created_at = time.time()
    raw_created = job.get("created_at")
    if isinstance(raw_created, str):
        try:
            created_at = datetime.fromisoformat(raw_created).timestamp()
        except ValueError:
            pass

    return SDKSession(
        id=session_id,
        file_name=document.get("original_file_name") or document.get("file_name") or "sample",
        file_path=document.get("file_path") or "",
        tenant_id=tenant_id,
        template_name="",
        template_code="",
        instruction=None,
        document_id=str(document_ids[0]),
        parse_job_id=session_id,
        parse_mode=parse_mode,
        parse_error=parse_error,
        excel_template_file_name=excel_name,
        excel_template_path=excel_path,
        excel_placeholders=excel_placeholders,
        user_id=document.get("user_id") or job.get("created_by") or user.user_id,
        state=state,
        created_at=created_at,
        updated_at=time.time(),
    )


async def _load_session_or_404(session_id: str, user: CurrentUser):
    session = session_store.get(session_id)
    if not session:
        session = await _rebuild_session(session_id, user)
        if session:
            session_store.save(session)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    if session.user_id != user.user_id and not user.is_super_admin():
        raise AuthorizationError("无权访问该 AI 模板会话")
    return session


def _response(session, job=None) -> SDKSessionResponse:
    parse_progress = None
    if job is not None and session.state == SDKSessionState.PARSING:
        parse_progress = int(job.get("progress") or 0)
    return SDKSessionResponse(
        id=session.id,
        file_name=session.file_name,
        tenant_id=session.tenant_id,
        template_name=session.template_name,
        template_code=session.template_code,
        instruction=session.instruction,
        document_id=session.document_id,
        parse_job_id=session.parse_job_id,
        parse_mode=session.parse_mode,
        parse_error=session.parse_error,
        parse_progress=parse_progress,
        state=session.state,
        excel_template_file_name=session.excel_template_file_name,
        excel_placeholders=session.excel_placeholders,
        analysis=session.analysis,
        confirmed_template=session.confirmed_template,
        prompt=session.prompt,
        commit_result=session.commit_result,
    )


def _safe_file_name(file_name: str) -> str:
    base_name = Path(file_name).name
    return re.sub(r"[^A-Za-z0-9._-]+", "_", base_name) or "upload.bin"


async def _save_excel_template(file: UploadFile, document_id: str) -> str:
    """Excel 模板按「文档 id + 原名」落盘，便于服务重启后重建会话时找回。"""
    upload_dir = Path(settings.UPLOAD_FOLDER) / "sdk_sessions"
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / f"{document_id}__{_safe_file_name(file.filename or 'template.xlsx')}"
    async with aiofiles.open(file_path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            await out.write(chunk)
    return str(file_path)


def _recover_excel_template(document_id: str) -> tuple[str | None, str | None, list]:
    """按命名约定找回样例的 Excel 模板（服务重启后重建会话用）。"""
    upload_dir = Path(settings.UPLOAD_FOLDER) / "sdk_sessions"
    matches = sorted(upload_dir.glob(f"{document_id}__*")) if upload_dir.exists() else []
    if not matches:
        return None, None, []
    path = matches[0]
    name = path.name.split("__", 1)[1] if "__" in path.name else path.name
    try:
        placeholders = [
            ExcelTemplatePlaceholder(**placeholder.__dict__)
            for placeholder in scan_excel_placeholders(str(path))
        ]
    except Exception:
        placeholders = []
    return name, str(path), placeholders


async def _save_document_file(file: UploadFile, document_id: str) -> tuple[str, int]:
    """把样例文件存为普通文档文件（标准 uploads 目录），返回 (路径, 大小)。"""
    upload_dir = Path(settings.UPLOAD_FOLDER)
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_ext = os.path.splitext(file.filename or "")[1]
    file_path = upload_dir / f"{document_id}{file_ext}"
    size = 0
    async with aiofiles.open(file_path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            await out.write(chunk)
            size += len(chunk)
    return str(file_path), size


async def _existing_markdown(session, parse_mode: str) -> str | None:
    """同一文档已有匹配模式的 Parse Result 时直接复用，避免重复解析。"""
    row = await result_service.get_document_parse_result(
        session.document_id,
        tenant_id=session.tenant_id,
    )
    if not row:
        return None
    data = row.get("data") or {}
    engine = data.get("engine") or {}
    if normalize_parse_mode(engine.get("model_version")) != parse_mode:
        return None
    return data.get("markdown") or None


async def _create_parse_job(
    *,
    tenant_id: str,
    document_id: str,
    parse_mode: str,
    created_by: str,
) -> str:
    """参数化提交 Parse（ADR-0007）：一文档一 Job，返回 job_id。"""
    from services.parse_request_service import parse_request_service

    result = await parse_request_service.admit(
        tenant_id=tenant_id,
        requester_id=created_by,
        is_admin=True,  # SDK 会话仅管理员可用
        document_ids=[document_id],
        parse_mode=parse_mode,
        target_pages=None,
        idempotency_key=None,
    )

    status = result.get("status")
    if status in ("ok", "reused"):
        job_ids = result.get("job_ids") or []
        if job_ids:
            return str(job_ids[0])
        raise HTTPException(status_code=500, detail="解析任务创建失败")
    if status == "conflict":
        raise HTTPException(status_code=409, detail="该文档正在解析中，请稍后重试")
    if status == "limit_exceeded":
        raise HTTPException(status_code=422, detail="解析任务数量超出限制，请稍后重试")
    if status == "not_found":
        raise HTTPException(status_code=404, detail="文档不存在或无权访问")
    raise HTTPException(status_code=500, detail="解析任务创建失败")


async def _sync_parse_state(session, job=None):
    """按解析 Job 实际状态推进会话；返回 (session, job)。"""
    if session.state != SDKSessionState.PARSING or not session.parse_job_id:
        return session, job

    job = job or await get_job(session.parse_job_id)
    if not job:
        return session, None

    status = job.get("status")
    if status == "failed":
        session.state = SDKSessionState.PARSE_FAILED
        session.parse_error = job.get("error") or "解析失败"
        session_store.save(session)
    elif status == "completed":
        row = await result_service.get_document_parse_result(
            session.document_id,
            tenant_id=session.tenant_id,
        )
        if row:
            # Parse 成功但内容可能不足以草拟字段；由 analyze 明确报"输入不足"
            session.state = SDKSessionState.PARSED
            session.parse_error = None
        else:
            session.state = SDKSessionState.PARSE_FAILED
            session.parse_error = "解析结果缺失，请重试"
        session_store.save(session)
    return session, job


@router.post("/sessions", response_model=SDKSessionResponse, status_code=201)
async def create_session(
    file: UploadFile = File(...),
    excel_template: UploadFile | None = File(default=None),
    template_name: str | None = Form(default=None),
    template_code: str | None = Form(default=None),
    parse_mode: str | None = Form(default=None),
    instruction: str | None = Form(default=None),
    tenant_id: str | None = Form(default=None),
    user: CurrentUser = Depends(get_current_user),
):
    """上传样例文档并启动 MinerU 解析。

    所属租户、文档类型（配置名/编码）与解析模式由操作者在第一步选定，接口负责校验；
    解析模式默认快速解析，可带一句可选说明引导字段建议。
    """
    _require_admin(user)
    resolved_tenant_id = (tenant_id or user.tenant_id or "").strip()
    if not resolved_tenant_id:
        raise HTTPException(status_code=400, detail="请先选择所属租户（部门）")
    if not user.can_access_tenant(resolved_tenant_id):
        raise AuthorizationError("无权在该租户下创建模板")

    kind_name = (template_name or "").strip()
    kind_code = (template_code or "").strip()
    if not kind_name or not kind_code:
        raise HTTPException(status_code=400, detail="请填写文档类型名称与编码")

    mode = normalize_parse_mode(parse_mode)
    document_id = str(uuid4())
    file_path, file_size = await _save_document_file(file, document_id)
    excel_template_path = None
    excel_placeholders: list[ExcelTemplatePlaceholder] = []
    try:
        if excel_template and excel_template.filename:
            excel_template_path = await _save_excel_template(excel_template, document_id)
            excel_placeholders = [
                ExcelTemplatePlaceholder(**placeholder.__dict__)
                for placeholder in scan_excel_placeholders(excel_template_path)
            ]

        stored_name = Path(file_path).name
        await supabase_service.create_document(
            {
                "id": document_id,
                "user_id": user.user_id,
                "file_name": stored_name,
                "original_file_name": file.filename,
                "file_path": file_path,
                "file_size": file_size,
                "file_type": file.content_type,
                "file_extension": os.path.splitext(file.filename or "")[1],
                "mime_type": file.content_type,
                "status": "uploaded",
                "tenant_id": resolved_tenant_id,
            }
        )
    except Exception:
        if os.path.exists(file_path):
            os.remove(file_path)
        if excel_template_path and os.path.exists(excel_template_path):
            os.remove(excel_template_path)
        raise

    job_id = await _create_parse_job(
        tenant_id=resolved_tenant_id,
        document_id=document_id,
        parse_mode=mode,
        created_by=user.user_id,
    )
    session = session_store.create(
        session_id=job_id,
        file_name=file.filename or Path(file_path).name,
        file_path=file_path,
        tenant_id=resolved_tenant_id,
        template_name=kind_name,
        template_code=kind_code,
        instruction=(instruction or "").strip() or None,
        document_id=document_id,
        parse_job_id=job_id,
        parse_mode=mode,
        state=SDKSessionState.PARSING,
        excel_template_file_name=excel_template.filename if excel_template else None,
        excel_template_path=excel_template_path,
        excel_placeholders=excel_placeholders,
        user_id=user.user_id,
    )
    return _response(session, {"job_id": job_id, "status": "queued", "progress": 0})


@router.get("/sessions/{session_id}", response_model=SDKSessionResponse)
async def get_session(
    session_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    _require_admin(user)
    session = await _load_session_or_404(session_id, user)
    session, job = await _sync_parse_state(session)
    return _response(session, job)


@router.post("/sessions/{session_id}/parse", response_model=SDKSessionResponse)
async def retry_parse(
    session_id: str,
    request: ParseRetryRequest | None = Body(default=None),
    user: CurrentUser = Depends(get_current_user),
):
    """重试解析（可切换解析模式）；同模式且已有解析结果时直接复用。"""
    _require_admin(user)
    session = await _load_session_or_404(session_id, user)
    session, job = await _sync_parse_state(session)
    if session.state == SDKSessionState.PARSING:
        raise HTTPException(status_code=409, detail="解析正在进行中，请稍后重试")
    if session.state == SDKSessionState.COMMITTED:
        raise HTTPException(status_code=409, detail="会话已完成，无法重新解析")

    mode = normalize_parse_mode((request.parse_mode if request else None) or session.parse_mode)
    markdown = await _existing_markdown(session, mode)
    if markdown:
        session.parse_mode = mode
        session.parse_error = None
        session.state = SDKSessionState.PARSED
        session_store.save(session)
        return _response(session)

    job_id = await _create_parse_job(
        tenant_id=session.tenant_id,
        document_id=session.document_id,
        parse_mode=mode,
        created_by=user.user_id,
    )
    session_store.delete(session.id)
    session.id = job_id
    session.parse_job_id = job_id
    session.parse_mode = mode
    session.parse_error = None
    session.state = SDKSessionState.PARSING
    session_store.save(session)
    return _response(session, {"job_id": job_id, "status": "queued", "progress": 0})


@router.post("/sessions/{session_id}/analyze")
async def analyze_session(
    session_id: str,
    request: SDKModelProfileRequest | None = Body(default=None),
    user: CurrentUser = Depends(get_current_user),
):
    _require_admin(user)
    session = await _load_session_or_404(session_id, user)
    session, _ = await _sync_parse_state(session)
    if session.state == SDKSessionState.PARSING:
        raise HTTPException(status_code=409, detail="文档仍在解析中，请稍后再试")
    if session.state == SDKSessionState.PARSE_FAILED:
        raise HTTPException(status_code=409, detail=session.parse_error or "解析失败，请重试")

    row = await result_service.get_document_parse_result(
        session.document_id,
        tenant_id=session.tenant_id,
    )
    markdown = ((row or {}).get("data") or {}).get("markdown")
    if not markdown:
        raise HTTPException(status_code=409, detail="解析结果内容不足，无法生成字段建议；请尝试高精度解析后重试")

    analysis = await orchestrator.analyze_document(
        session,
        markdown,
        model_profile=request.model_profile if request else None,
    )
    if not isinstance(analysis, DocumentAnalysis):
        analysis = DocumentAnalysis.model_validate(analysis)
    _merge_excel_placeholder_fields(analysis, session.excel_placeholders)
    session.analysis = analysis
    session.state = SDKSessionState.ANALYZED
    session_store.save(session)
    return {"success": True, "analysis": analysis}


@router.post("/sessions/{session_id}/confirm-template", response_model=SDKSessionResponse)
async def confirm_template(
    session_id: str,
    request: ConfirmTemplateRequest,
    user: CurrentUser = Depends(get_current_user),
):
    _require_admin(user)
    session = await _load_session_or_404(session_id, user)
    session.confirmed_template = request
    session.state = SDKSessionState.TEMPLATE_CONFIRMED
    session_store.save(session)
    return _response(session)


@router.post("/sessions/{session_id}/prompt")
async def generate_prompt(
    session_id: str,
    request: SDKModelProfileRequest | None = Body(default=None),
    user: CurrentUser = Depends(get_current_user),
):
    _require_admin(user)
    session = await _load_session_or_404(session_id, user)
    prompt = await orchestrator.generate_prompt(
        session,
        model_profile=request.model_profile if request else None,
    )
    session.prompt = prompt
    session.state = SDKSessionState.PROMPT_GENERATED
    session_store.save(session)
    return {"success": True, "prompt": prompt}


@router.post("/sessions/{session_id}/commit")
async def commit_session(
    session_id: str,
    request: CommitSessionRequest | None = Body(default=None),
    user: CurrentUser = Depends(get_current_user),
):
    _require_admin(user)
    session = await _load_session_or_404(session_id, user)
    if request:
        if request.prompt is not None:
            session.prompt = request.prompt
    result = await orchestrator.commit(session)
    session.commit_result = result
    session.state = SDKSessionState.COMMITTED
    session_store.save(session)
    return {"success": True, "commit_result": result}


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    _require_admin(user)
    session = await _load_session_or_404(session_id, user)
    # 样例文档本身保留（它是一条普通 Document），只清理会话级的 Excel 模板文件
    if session.excel_template_path and os.path.exists(session.excel_template_path):
        os.remove(session.excel_template_path)
    deleted = session_store.delete(session_id)
    return {"success": deleted}


def _merge_excel_placeholder_fields(
    analysis: DocumentAnalysis,
    placeholders: list[ExcelTemplatePlaceholder],
) -> None:
    existing_keys = {field.field_key for field in analysis.detected_fields}
    for placeholder in placeholders:
        if placeholder.field_key in existing_keys:
            continue
        analysis.detected_fields.append(
            DetectedField(
                field_key=placeholder.field_key,
                field_label=placeholder.field_key,
                field_type="text",
                extraction_hint=(
                    f"从待识别图片/文档中提取 {placeholder.field_key}，"
                    f"并填入 Excel 模板槽位 {{{{{placeholder.field_key}}}}}。"
                ),
                review_enforced=True,
            )
        )
        existing_keys.add(placeholder.field_key)
