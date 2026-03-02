# api/routes/documents/review.py
"""文档路由 - 审核相关端点"""

from fastapi import APIRouter, Depends
from datetime import datetime
from loguru import logger

import json

from services.supabase_service import supabase_service
from services.feishu_service import feishu_service
from services.template_service import template_service
from api.dependencies.auth import get_current_user, CurrentUser
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
        # 使用 service_role 查询，手动验证权限
        doc_result = supabase_service.client.table("documents").select("*").eq("id", document_id).execute()
        document = doc_result.data[0] if doc_result.data else None
        
        if not document:
            raise DocumentNotFoundError(document_id)
        
        # 验证用户权限（只有文档所有者或管理员可以审核）
        doc_user_id = document.get("user_id")
        doc_tenant_id = document.get("tenant_id")
        if not user.is_super_admin():
            if user.is_tenant_admin():
                if doc_tenant_id != user.tenant_id:
                    raise DocumentNotFoundError(document_id)
            elif doc_user_id != user.user_id:
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
        
        result = supabase_service.client.table(table_name).update(update_data).eq("document_id", document_id).execute()
        
        if not result.data:
            raise ProcessingError("更新失败")
        
        # 审核通过后，更新文档主表状态为 completed
        supabase_service.client.table("documents").update({
            "status": "completed"
        }).eq("id", document_id).execute()
        
        logger.info(f"文档审核通过: {document_id}, 用户: {user.user_id}")
        
        file_name_for_push = (
            (document.get("display_name") or "").strip()
            or (document.get("original_file_name") or "").strip()
            or (document.get("file_name") or "").strip()
        )

        # 审核保存后推送到飞书多维表格（统一使用模板配置）
        try:
            bitable_token = template.get("feishu_bitable_token") if template else None
            table_id = template.get("feishu_table_id") if template else None
            
            if template and bitable_token and table_id:
                field_mapping = template_service.build_field_mapping(template)
                
                logger.info(f"使用模板配置推送飞书: template_id={template.get('id')}, bitable_token={bitable_token}, table_id={table_id}")
                
                # 准备推送数据
                push_data = {**result.data[0]}
                
                # 处理文件名字段
                if file_name_for_push:
                    file_name_field = next(
                        (k for k, v in field_mapping.items() if v == "文件名"),
                        None
                    )
                    if file_name_field:
                        push_data[file_name_field] = file_name_for_push
                    elif "file_name" not in push_data:
                        push_data["file_name"] = file_name_for_push
                        field_mapping["file_name"] = "文件名"
                
                # 处理附件：模板开启 push_attachment 且文档有本地文件时，上传并写入飞书附件列
                file_path = document.get("file_path", "")
                if template.get("push_attachment", True) and file_path:
                    file_token = await feishu_service._upload_file_to_feishu(file_path, bitable_token)
                    if file_token:
                        push_data["attachment"] = [{"file_token": file_token}]
                        field_mapping["attachment"] = "附件"
                
                success = await feishu_service.push_by_template(
                    push_data,
                    field_mapping,
                    bitable_token,
                    table_id
                )
                
                if success:
                    logger.info(f"飞书推送成功: {document_id}")
                else:
                    logger.warning(f"飞书推送失败: {document_id}")
            else:
                logger.info(f"模板未配置飞书，跳过推送: {document_id}")
        except Exception as feishu_error:
            logger.warning(f"飞书推送失败（不影响审核结果）: {feishu_error}")
        
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
        
        # 使用 service_role 查询，手动验证权限
        doc_result = supabase_service.client.table("documents").select("*").eq("id", document_id).execute()
        document = doc_result.data[0] if doc_result.data else None
        
        if not document:
            raise DocumentNotFoundError(document_id)
        
        # 验证用户权限（只有文档所有者或管理员可以重命名）
        doc_user_id = document.get("user_id")
        doc_tenant_id = document.get("tenant_id")
        if not user.is_super_admin():
            if user.is_tenant_admin():
                if doc_tenant_id != user.tenant_id:
                    raise DocumentNotFoundError(document_id)
            elif doc_user_id != user.user_id:
                raise DocumentNotFoundError(document_id)
        
        # 更新显示名称
        supabase_service.client.table("documents").update({
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
        # 使用 service_role 查询，手动验证权限
        doc_result = supabase_service.client.table("documents").select("*").eq("id", document_id).execute()
        document = doc_result.data[0] if doc_result.data else None
        
        if not document:
            raise DocumentNotFoundError(document_id)
        
        # 验证用户权限（只有文档所有者或管理员可以打回）
        doc_user_id = document.get("user_id")
        doc_tenant_id = document.get("tenant_id")
        if not user.is_super_admin():
            if user.is_tenant_admin():
                if doc_tenant_id != user.tenant_id:
                    raise DocumentNotFoundError(document_id)
            elif doc_user_id != user.user_id:
                raise DocumentNotFoundError(document_id)
        
        # 更新文档状态为失败
        supabase_service.client.table("documents").update({
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
