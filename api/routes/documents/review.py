# api/routes/documents/review.py
"""文档路由 - 审核相关端点"""

from fastapi import APIRouter, Depends
from datetime import datetime
from loguru import logger

import json

from services.supabase_service import supabase_service
from services.feishu_service import feishu_service
from services.template_service import template_service
from api.dependencies.auth import get_current_user, get_user_client, CurrentUser
from api.exceptions import (
    DocumentNotFoundError, 
    DocumentTypeError, 
    ValidationError,
    ProcessingError
)
from .schemas import ValidateRequest, RejectRequest, RenameRequest

router = APIRouter()


def _normalize_review_value(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().casefold()


def _parse_allowed_values(raw_values: object) -> list:
    if raw_values is None:
        return []
    if isinstance(raw_values, list):
        return [str(item) for item in raw_values if item is not None]
    if isinstance(raw_values, str):
        text = raw_values.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if item is not None]
        except json.JSONDecodeError:
            pass
        return [text]
    return [str(raw_values)]


def _validate_review_rules(template: dict, data: dict) -> None:
    fields = template.get("template_fields") or []
    for field in fields:
        if not field or not field.get("review_enforced"):
            continue
        field_key = field.get("field_key") or ""
        if not field_key:
            continue
        allowed_values = _parse_allowed_values(field.get("review_allowed_values"))
        if not allowed_values:
            continue
        current_value = data.get(field_key)
        normalized_current = _normalize_review_value(current_value)
        normalized_allowed = {_normalize_review_value(v) for v in allowed_values}
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
        user_client = get_user_client(user)
        
        # 检查文档是否存在
        doc_result = user_client.table("documents").select("*").eq("id", document_id).execute()
        document = doc_result.data[0] if doc_result.data else None
        
        if not document:
            raise DocumentNotFoundError(document_id)
        
        # 校验强制审核条件（如果配置了字段规则）
        template_id = document.get("template_id")
        tenant_id = document.get("tenant_id")
        template = None
        if template_id:
            template = await template_service.get_template_with_details(template_id)
        elif tenant_id and request.document_type:
            template = await template_service.get_template_by_code(tenant_id, request.document_type)
        if template:
            _validate_review_rules(template, request.data)

        # 准备更新数据
        update_data = {**request.data}
        update_data["is_validated"] = True
        update_data["validated_at"] = datetime.now().isoformat()
        update_data["validated_by"] = user.user_id
        if request.validation_notes:
            update_data["validation_notes"] = request.validation_notes
        
        # 根据文档类型更新对应表
        table_name = supabase_service.get_table_name(request.document_type)
        
        if not table_name:
            raise DocumentTypeError(request.document_type)
        
        result = user_client.table(table_name).update(update_data).eq("document_id", document_id).execute()
        
        if not result.data:
            raise ProcessingError("更新失败")
        
        # 审核通过后，更新文档主表状态为 completed
        user_client.table("documents").update({
            "status": "completed"
        }).eq("id", document_id).execute()
        
        logger.info(f"文档审核通过: {document_id}, 用户: {user.user_id}")
        
        file_name_for_push = (
            (document.get("display_name") or "").strip()
            or (document.get("original_file_name") or "").strip()
            or (document.get("file_name") or "").strip()
        )

        # 审核保存后推送到飞书多维表格
        if request.document_type in ("检测报告", "inspection_report"):
            try:
                await feishu_service.push_inspection_report(
                    result.data[0],
                    attachment_path=document.get("file_path"),
                    file_name=file_name_for_push
                )
                logger.info(f"检测报告飞书推送成功: {document_id}")
            except Exception as feishu_error:
                logger.warning(f"检测报告飞书推送失败（不影响审核结果）: {feishu_error}")
        elif request.document_type in ("照明综合报告", "lighting_combined", "lighting_report"):
            try:
                await feishu_service.push_lighting_report(
                    result.data[0],
                    file_name=file_name_for_push
                )
                logger.info(f"照明报告飞书推送成功: {document_id}")
            except Exception as feishu_error:
                logger.warning(f"照明报告飞书推送失败（不影响审核结果）: {feishu_error}")
        
        return {
            "success": True,
            "message": "审核通过，字段已更新",
            "document_id": document_id
        }
        
    except (DocumentNotFoundError, DocumentTypeError, ProcessingError):
        raise
    except Exception as e:
        logger.error(f"审核失败: {e}")
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
        
        user_client = get_user_client(user)
        
        # 检查文档是否存在
        doc_result = user_client.table("documents").select("*").eq("id", document_id).execute()
        document = doc_result.data[0] if doc_result.data else None
        
        if not document:
            raise DocumentNotFoundError(document_id)
        
        # 更新显示名称
        user_client.table("documents").update({
            "display_name": request.display_name.strip()
        }).eq("id", document_id).execute()
        
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
        logger.error(f"重命名失败: {e}")
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
        user_client = get_user_client(user)
        
        # 检查文档是否存在
        doc_result = user_client.table("documents").select("*").eq("id", document_id).execute()
        document = doc_result.data[0] if doc_result.data else None
        
        if not document:
            raise DocumentNotFoundError(document_id)
        
        # 更新文档状态为失败
        user_client.table("documents").update({
            "status": "failed",
            "error_message": f"审核打回: {request.reason}"
        }).eq("id", document_id).execute()
        
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
        logger.error(f"打回失败: {e}")
        raise ProcessingError(f"打回失败: {str(e)}")
