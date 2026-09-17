# api/routes/documents/query.py
"""文档路由 - 查询相关端点"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from typing import Optional
from loguru import logger
import inspect
import os

from services.configuration_service import configuration_service
from services.supabase_service import supabase_service
from services.result_service import result_service, result_to_extraction_data
from api.dependencies.auth import get_current_user, get_crm_current_user, CurrentUser
from api.exceptions import DocumentNotFoundError, FileNotFoundError, ProcessingError
from .helpers import parse_allowed_values, raise_auth_or_processing_error

router = APIRouter()


async def _run_supabase(fn):
    runner = getattr(supabase_service, "_run_sync", None)
    if runner is not None and inspect.iscoroutinefunction(runner):
        return await runner(fn)
    return fn()


@router.get("/{document_id}/status")
async def get_document_status(
    document_id: str,
    user: CurrentUser = Depends(get_crm_current_user)
):
    """
    获取文档处理状态（需要登录）
    
    使用 service_role 查询，手动验证用户权限：
    - 普通用户只能访问自己的文档
    - 租户管理员可以访问本租户所有文档
    - 超级管理员可以访问所有文档
    """
    try:
        # 使用 service_role 查询（绕过 RLS）
        result = await _run_supabase(
            lambda: supabase_service.client.table("documents").select("*").eq("id", document_id).execute()
        )
        document = result.data[0] if result.data else None
        
        if not document:
            raise DocumentNotFoundError(document_id)
        
        # 手动验证权限
        doc_user_id = document.get("user_id")
        doc_tenant_id = document.get("tenant_id")
        
        # 超级管理员可以访问所有文档
        if user.is_super_admin():
            pass  # 允许访问
        # 租户管理员可以访问本租户的文档
        elif user.is_tenant_admin() and doc_tenant_id == user.tenant_id:
            pass  # 允许访问
        # 普通用户只能访问自己的文档
        elif doc_user_id != user.user_id:
            raise DocumentNotFoundError(document_id)
        
        return {
            "document_id": document_id,
            "status": document.get("status", "unknown"),
            "document_type": document.get("document_type"),
            "display_name": document.get("display_name"),
            "original_file_name": document.get("original_file_name"),
            "error_message": document.get("error_message"),
            "created_at": document.get("created_at"),
            "updated_at": document.get("updated_at"),
            "processed_at": document.get("processed_at")
        }
        
    except DocumentNotFoundError:
        raise
    except Exception as e:
        raise_auth_or_processing_error(e, "获取状态失败")


def _check_document_access(document: dict, user: CurrentUser, document_id: str):
    """
    验证用户是否有权访问文档
    
    权限规则：
    - 超级管理员可以访问所有文档
    - 租户管理员可以访问本租户的文档
    - 普通用户只能访问自己的文档
    """
    doc_user_id = document.get("user_id")
    doc_tenant_id = document.get("tenant_id")
    
    if user.is_super_admin():
        return  # 超级管理员可以访问所有文档
    if user.is_tenant_admin() and doc_tenant_id == user.tenant_id:
        return  # 租户管理员可以访问本租户的文档
    if doc_user_id == user.user_id:
        return  # 普通用户可以访问自己的文档
    
    raise DocumentNotFoundError(document_id)


@router.get("/{document_id}/result")
async def get_extraction_result(
    document_id: str,
    user: CurrentUser = Depends(get_crm_current_user)
):
    """
    获取提取结果（需要登录）
    
    返回状态码：
    - 200: 成功返回结果
    - 202: 文档正在处理中（前端应继续轮询）
    - 404: 文档不存在或无权访问
    """
    try:
        # 使用 service_role 查询（绕过 RLS），手动验证权限
        doc_result = await _run_supabase(
            lambda: supabase_service.client.table("documents").select("*").eq("id", document_id).execute()
        )
        document = doc_result.data[0] if doc_result.data else None
        
        if not document:
            raise DocumentNotFoundError(document_id)
        
        # 验证用户权限
        _check_document_access(document, user, document_id)
        
        document_type = document.get("document_type")
        doc_status = document.get("status")

        # 读取侧唯一数据源：文档最新一批抽取的 Result 主样品行
        result_row = await result_service.get_document_result(
            document_id,
            tenant_id=document.get("tenant_id"),
        )
        
        if not result_row:
            if doc_status in ("completed", "pending_review"):
                logger.warning(f"文档 {document_id} 状态为 {doc_status} 但 Result 尚未查询到")
                return JSONResponse(
                    status_code=202,
                    content={
                        "document_id": document_id,
                        "status": doc_status,
                        "message": "提取结果正在同步中，请稍后重试"
                    }
                )
            elif doc_status == "failed":
                raise HTTPException(status_code=422, detail=document.get("error_message") or "文档处理失败")
            else:
                message = "文档正在排队中，请稍后重试" if doc_status == "queued" else "文档尚未完成处理，请稍后重试"
                return JSONResponse(
                    status_code=202,
                    content={
                        "document_id": document_id,
                        "status": doc_status or "unknown",
                        "message": message
                    }
                )
        
        # 兼容旧业务表行的响应形状：字段值 + document_id + is_validated
        extraction_data = result_to_extraction_data(result_row, document_id)
        ocr_text = document.get("ocr_text") or ""

        # 从配置字段中收集：
        #   1. review_hint_fields — 有 review_allowed_values 的字段，用于前端保存前提示
        #   2. fields             — 完整白名单字段列表，供前端详情页纯配置驱动渲染
        review_hint_fields = []
        fields_payload = []
        configuration_id: Optional[str] = None
        template_id = document.get("template_id")
        tenant_id = document.get("tenant_id")
        try:
            fields_list: list = []
            configuration = None
            if template_id:
                configuration = await configuration_service.get_extraction_configuration(
                    template_id,
                    revision_id=result_row.get("config_revision_id"),
                )
            elif tenant_id and document_type:
                configuration = await configuration_service.resolve_extraction_configuration(
                    tenant_id, document_type
                )
            if configuration:
                configuration_id = configuration.get("id")
                fields_list = configuration.get("fields") or []
            for field in fields_list:
                allowed = parse_allowed_values(field.get("review_allowed_values"))
                if allowed:
                    review_hint_fields.append({
                        "field_key": field.get("field_key"),
                        "field_label": field.get("field_label") or field.get("field_key"),
                        "allowed_values": allowed,
                    })
            # 构造前端渲染所需白名单字段列表（按 sort_order 升序）
            fields_payload = [
                {
                    "field_key": f.get("field_key"),
                    "field_label": f.get("field_label") or f.get("field_key"),
                    "field_type": f.get("field_type", "text"),
                    "is_required": bool(f.get("is_required", False)),
                    "sort_order": f.get("sort_order", 0),
                    "review_enforced": bool(f.get("review_enforced", False)),
                    "review_allowed_values": parse_allowed_values(f.get("review_allowed_values")),
                    "extraction_hint": f.get("extraction_hint") or "",
                }
                for f in sorted(fields_list, key=lambda x: x.get("sort_order", 0))
            ]
        except Exception as hint_err:
            logger.warning(f"获取配置字段失败（不影响主流程）: {hint_err}")

        return {
            "document_id": document_id,
            "document_type": document_type,
            "configuration_id": configuration_id,
            "extraction_data": extraction_data,
            "ocr_text": ocr_text[:1000] if ocr_text else "",
            "ocr_confidence": document.get("ocr_confidence"),
            "created_at": result_row.get("created_at"),
            "is_validated": result_row.get("review_state") == "approved",
            "review_hint_fields": review_hint_fields,
            "fields": fields_payload,
        }
        
    except (DocumentNotFoundError, HTTPException):
        raise
    except Exception as e:
        raise_auth_or_processing_error(e, "获取结果失败")


@router.get("/{document_id}/parse-result")
async def get_document_parse_result(
    document_id: str,
    user: CurrentUser = Depends(get_current_user)
):
    """读取文档最新的 Parse Result（权限同提取结果）。"""
    try:
        doc_result = await _run_supabase(
            lambda: supabase_service.client.table("documents").select("*").eq("id", document_id).execute()
        )
        document = doc_result.data[0] if doc_result.data else None

        if not document:
            raise DocumentNotFoundError(document_id)

        _check_document_access(document, user, document_id)

        row = await result_service.get_document_parse_result(
            document_id,
            tenant_id=document.get("tenant_id"),
        )
        if not row:
            raise HTTPException(status_code=404, detail="解析结果不存在")

        return {
            "success": True,
            "result_id": row.get("id"),
            "data": row.get("data") or {},
        }

    except (DocumentNotFoundError, HTTPException):
        raise
    except Exception as e:
        raise_auth_or_processing_error(e, "获取解析结果失败")


@router.get("/{document_id}/download")
async def download_document(
    document_id: str,
    user: CurrentUser = Depends(get_current_user)
):
    """
    下载原始文档（需要登录）
    """
    try:
        # 使用 service_role 查询，手动验证权限
        result = await _run_supabase(
            lambda: supabase_service.client.table("documents").select("*").eq("id", document_id).execute()
        )
        document = result.data[0] if result.data else None
        
        if not document:
            raise DocumentNotFoundError(document_id)
        
        # 验证用户权限
        _check_document_access(document, user, document_id)
        
        file_path = document.get("file_path")
        if not os.path.exists(file_path):
            raise FileNotFoundError(file_path)
        
        return FileResponse(
            path=file_path,
            filename=document.get("original_file_name", document.get("file_name")),
            media_type=document.get("mime_type", "application/octet-stream")
        )
        
    except (DocumentNotFoundError, FileNotFoundError):
        raise
    except Exception as e:
        raise_auth_or_processing_error(e, "下载失败")


@router.get("/")
async def list_documents(
    page: int = 1,
    limit: int = 20,
    status: Optional[str] = None,
    document_type: Optional[str] = None,
    user: CurrentUser = Depends(get_current_user)
):
    """
    列出文档（需要登录）
    
    权限过滤：
    - 超级管理员可以看到所有文档
    - 租户管理员可以看到本租户的文档
    - 普通用户只能看到自己的文档
    """
    try:
        # 使用 service_role 查询，手动添加权限过滤
        query = supabase_service.client.table("documents").select("*")
        
        # 根据用户角色添加过滤条件
        if user.is_super_admin():
            pass  # 超级管理员可以看到所有文档
        elif user.is_tenant_admin() and user.tenant_id:
            query = query.eq("tenant_id", user.tenant_id)
        else:
            query = query.eq("user_id", user.user_id)
        
        if status:
            query = query.eq("status", status)
        if document_type:
            query = query.eq("document_type", document_type)
        
        offset = (page - 1) * limit
        result = await _run_supabase(
            lambda: query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        )
        
        # 统计总数（使用相同的权限过滤）
        count_query = supabase_service.client.table("documents").select("id", count="exact")
        
        # 根据用户角色添加过滤条件（与上面保持一致）
        if user.is_super_admin():
            pass
        elif user.is_tenant_admin() and user.tenant_id:
            count_query = count_query.eq("tenant_id", user.tenant_id)
        else:
            count_query = count_query.eq("user_id", user.user_id)
        
        if status:
            count_query = count_query.eq("status", status)
        if document_type:
            count_query = count_query.eq("document_type", document_type)
        count_result = await _run_supabase(count_query.execute)
        
        total = count_result.count or 0
        
        return {
            "items": result.data or [],
            "total": total,
            "page": page,
            "limit": limit,
            "has_more": (page * limit) < total
        }
        
    except Exception as e:
        logger.error(f"查询文档失败: {e}")
        raise_auth_or_processing_error(e, "查询失败")


@router.delete("/{document_id}")
async def _delete_document_guarded(document_id: str, user: CurrentUser) -> dict:
    """原子删除（迁移 024 RPC）：租户锁内校验权限与活动占用后删除数据库行。"""
    result = await _run_supabase(
        lambda: supabase_service.client.rpc(
            "delete_document_guarded",
            {
                "p_document_id": document_id,
                "p_requester_id": user.user_id,
                "p_is_admin": user.is_tenant_admin(),
            },
        ).execute()
    )
    data = result.data or []
    row = data if isinstance(data, dict) else (data[0] if data else None)
    return row or {}


async def delete_document(
    document_id: str,
    user: CurrentUser = Depends(get_current_user)
):
    """
    删除文档（需要登录）。

    数据库删除由原子命令完成（活动任务占用时拒绝）；文件清理由数据库
    事务提交后执行，失败只记日志，不影响删除结果。
    """
    try:
        outcome = await _delete_document_guarded(document_id, user)
        status = outcome.get("out_status")

        if status == "not_found":
            raise DocumentNotFoundError(document_id)
        if status == "conflict":
            raise HTTPException(status_code=409, detail="文档正在处理中，暂不能删除")
        if status != "ok":
            raise ProcessingError("删除失败")

        file_path = outcome.get("out_file_path")
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError as file_err:
                logger.warning(f"删除文档文件失败（不影响数据库删除）: {file_path} - {file_err}")

        return {
            "document_id": document_id,
            "message": "文档删除成功"
        }

    except (DocumentNotFoundError, HTTPException):
        raise
    except Exception as e:
        raise_auth_or_processing_error(e, "删除失败")
