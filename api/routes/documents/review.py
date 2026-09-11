# api/routes/documents/review.py
"""文档路由 - 审核相关端点"""

from fastapi import APIRouter, Depends
from loguru import logger
import inspect

from services.configuration_service import configuration_service
from services.supabase_service import supabase_service
from services.result_service import (
    APPROVED_REVIEW_STATE,
    REJECTED_REVIEW_STATE,
    result_service,
    result_to_extraction_data,
)
from api.dependencies.auth import get_current_user, CurrentUser
from api.exceptions import (
    DocumentNotFoundError, 
    ValidationError,
    ProcessingError
)
from .schemas import ValidateRequest, RejectRequest, RenameRequest
from .helpers import normalize_review_value, parse_allowed_values, push_to_feishu
from .query import _check_document_access

router = APIRouter()


async def _run_supabase(fn):
    runner = getattr(supabase_service, "_run_sync", None)
    if runner is not None and inspect.iscoroutinefunction(runner):
        return await runner(fn)
    return fn()


def _validate_review_rules(configuration: dict, data: dict) -> None:
    fields = configuration.get("fields") or []
    for field in fields:
        if not field or not field.get("review_enforced"):
            continue
        field_key = field.get("field_key") or ""
        if not field_key:
            continue
        allowed_values = parse_allowed_values(field.get("review_allowed_values"))
        if not allowed_values:
            continue
        current_value = data.get(field_key)
        normalized_current = normalize_review_value(current_value)
        normalized_allowed = {normalize_review_value(v) for v in allowed_values}
        if not normalized_current or normalized_current not in normalized_allowed:
            field_label = field.get("field_label") or field_key
            allowed_text = " / ".join(allowed_values)
            raise ValidationError(f"字段【{field_label}】必须为：{allowed_text}")


@router.put("/{document_id}/validate")
async def validate_document(
    document_id: str,
    request: ValidateRequest,
    user: CurrentUser = Depends(get_current_user)
):
    """
    审核通过并更新字段（需要登录）
    
    - **document_id**: 文档ID
    - **document_type**: 文档类型（检测报告/快递单/抽样单）
    - **data**: 修改后的字段数据
    - **validation_notes**: 审核备注（可选）
    """
    try:
        # 使用 service_role 查询，手动验证权限
        doc_result = await _run_supabase(
            lambda: supabase_service.client.table("documents").select("*").eq("id", document_id).execute()
        )
        document = doc_result.data[0] if doc_result.data else None
        
        if not document:
            raise DocumentNotFoundError(document_id)
        
        # 验证用户权限（只有文档所有者或管理员可以审核）
        _check_document_access(document, user, document_id)
        
        # 校验强制审核条件（如果配置了字段规则）
        template_id = document.get("template_id")
        tenant_id = document.get("tenant_id")
        configuration = None
        if template_id:
            configuration = await configuration_service.get_extraction_configuration(template_id)
        elif tenant_id and request.document_type:
            configuration = await configuration_service.resolve_extraction_configuration(
                tenant_id, request.document_type
            )
        if configuration:
            _validate_review_rules(configuration, request.data)

        # 审核修正写回 Result（唯一数据源）
        updated_result = await result_service.update_result_review(
            document_id=document_id,
            review_state=APPROVED_REVIEW_STATE,
            data=request.data,
            tenant_id=tenant_id,
        )
        if not updated_result:
            raise ProcessingError("提取结果不存在，无法审核")

        # 审核通过后，更新文档主表状态为 completed
        await _run_supabase(
            lambda: supabase_service.client.table("documents").update({
                "status": "completed"
            }).eq("id", document_id).execute()
        )

        logger.info(f"文档审核通过: {document_id}, 用户: {user.user_id}")

        file_name_for_push = (
            (document.get("display_name") or "").strip()
            or (document.get("original_file_name") or "").strip()
            or (document.get("file_name") or "").strip()
        )

        if configuration:
            try:
                push_data = result_to_extraction_data(updated_result, document_id)
                await push_to_feishu(
                    configuration=configuration,
                    extraction_data=push_data,
                    display_name=file_name_for_push,
                    document_id=document_id,
                    source_file_path=document.get("file_path", ""),
                )
            except Exception as feishu_error:
                logger.bind(document_id=document_id).opt(exception=feishu_error).warning("飞书推送失败，不影响审核结果")
        else:
            logger.bind(document_id=document_id).info("配置未配置飞书，跳过推送")
        
        return {
            "success": True,
            "message": "审核通过，字段已更新",
            "document_id": document_id
        }
        
    except (DocumentNotFoundError, ProcessingError):
        raise
    except Exception as e:
        logger.bind(document_id=document_id).opt(exception=e).error("审核失败")
        raise ProcessingError(f"审核失败: {str(e)}")


@router.put("/{document_id}/rename")
async def rename_document(
    document_id: str,
    request: RenameRequest,
    user: CurrentUser = Depends(get_current_user)
):
    """
    重命名文档（需要登录）
    
    - **document_id**: 文档ID
    - **display_name**: 新的显示名称
    """
    try:
        # 验证名称
        if not request.display_name or not request.display_name.strip():
            raise ValidationError("显示名称不能为空")
        
        if len(request.display_name) > 255:
            raise ValidationError("显示名称不能超过255个字符")
        
        # 使用 service_role 查询，手动验证权限
        doc_result = await _run_supabase(
            lambda: supabase_service.client.table("documents").select("*").eq("id", document_id).execute()
        )
        document = doc_result.data[0] if doc_result.data else None
        
        if not document:
            raise DocumentNotFoundError(document_id)
        
        # 验证用户权限（只有文档所有者或管理员可以重命名）
        _check_document_access(document, user, document_id)
        
        # 更新显示名称
        await _run_supabase(
            lambda: supabase_service.client.table("documents").update({
                "display_name": request.display_name.strip()
            }).eq("id", document_id).execute()
        )
        
        logger.info(f"文档重命名: {document_id} -> {request.display_name}")
        
        return {
            "success": True,
            "message": "重命名成功",
            "document_id": document_id,
            "display_name": request.display_name.strip()
        }
        
    except (ValidationError, DocumentNotFoundError):
        raise
    except Exception as e:
        logger.bind(document_id=document_id).opt(exception=e).error("重命名失败")
        raise ProcessingError(f"重命名失败: {str(e)}")


@router.put("/{document_id}/reject")
async def reject_document(
    document_id: str,
    request: RejectRequest,
    user: CurrentUser = Depends(get_current_user)
):
    """
    打回文档（需要登录）
    
    - **document_id**: 文档ID
    - **reason**: 打回原因
    """
    try:
        # 使用 service_role 查询，手动验证权限
        doc_result = await _run_supabase(
            lambda: supabase_service.client.table("documents").select("*").eq("id", document_id).execute()
        )
        document = doc_result.data[0] if doc_result.data else None
        
        if not document:
            raise DocumentNotFoundError(document_id)
        
        # 验证用户权限（只有文档所有者或管理员可以打回）
        _check_document_access(document, user, document_id)

        # 打回写入 Result 复核状态（旧表镜像不做变更）
        await result_service.update_result_review(
            document_id=document_id,
            review_state=REJECTED_REVIEW_STATE,
            tenant_id=document.get("tenant_id"),
        )

        # 更新文档状态为失败
        await _run_supabase(
            lambda: supabase_service.client.table("documents").update({
                "status": "failed",
                "error_message": f"审核打回: {request.reason}"
            }).eq("id", document_id).execute()
        )
        
        logger.info(f"文档审核打回: {document_id}, 用户: {user.user_id}, 原因: {request.reason}")
        
        return {
            "success": True,
            "message": "文档已打回",
            "document_id": document_id,
            "reason": request.reason
        }
        
    except DocumentNotFoundError:
        raise
    except Exception as e:
        logger.bind(document_id=document_id).opt(exception=e).error("打回失败")
        raise ProcessingError(f"打回失败: {str(e)}")
