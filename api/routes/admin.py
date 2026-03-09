# api/routes/admin.py
"""管理员配置 API 路由 - 仅 tenant_admin / super_admin 可访问"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Any, Dict
from loguru import logger

from services.template_service import template_service
from api.dependencies.auth import get_current_user, CurrentUser
from api.exceptions import AuthorizationError

router = APIRouter(prefix="/admin", tags=["管理员配置"])


# ============ 请求体模型 ============

class UpdateTemplateConfigRequest(BaseModel):
    feishu_bitable_token: Optional[str] = None
    feishu_table_id: Optional[str] = None
    auto_approve: Optional[bool] = None


class CreateFieldRequest(BaseModel):
    field_key: str
    field_label: str
    field_type: str = "text"
    extraction_hint: Optional[str] = ""
    feishu_column: Optional[str] = ""
    sort_order: int = 0
    review_enforced: bool = False
    review_allowed_values: Optional[List[str]] = None


class UpdateFieldRequest(BaseModel):
    field_key: Optional[str] = None
    field_label: Optional[str] = None
    field_type: Optional[str] = None
    extraction_hint: Optional[str] = None
    feishu_column: Optional[str] = None
    sort_order: Optional[int] = None
    review_enforced: Optional[bool] = None
    review_allowed_values: Optional[List[str]] = None


class ReorderItem(BaseModel):
    id: str
    sort_order: int


class ReorderFieldsRequest(BaseModel):
    items: List[ReorderItem]


class CreateExampleRequest(BaseModel):
    example_input: str
    example_output: Dict[str, Any]
    sort_order: int = 0
    is_active: bool = True


class UpdateExampleRequest(BaseModel):
    example_input: Optional[str] = None
    example_output: Optional[Dict[str, Any]] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


# ============ 权限辅助 ============

def _require_admin(user: CurrentUser) -> None:
    """要求管理员角色，否则抛出 403"""
    if not user.is_tenant_admin():
        raise AuthorizationError("仅管理员可访问此接口")


async def _require_template_access(template_id: str, user: CurrentUser) -> Dict[str, Any]:
    """
    获取模板并校验当前用户是否有权访问。
    返回模板数据，校验失败抛出 403/404。
    """
    template = await template_service.get_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    if not user.can_access_tenant(template["tenant_id"]):
        raise AuthorizationError("无权访问该模板")
    return template


async def _require_field_access(field_id: str, user: CurrentUser) -> Dict[str, Any]:
    """获取字段并校验模板归属权限"""
    field = await template_service.get_field_by_id(field_id)
    if not field:
        raise HTTPException(status_code=404, detail="字段不存在")
    await _require_template_access(field["template_id"], user)
    return field


async def _require_example_access(example_id: str, user: CurrentUser) -> Dict[str, Any]:
    """获取示例并校验模板归属权限"""
    example = await template_service.get_example_by_id(example_id)
    if not example:
        raise HTTPException(status_code=404, detail="示例不存在")
    await _require_template_access(example["template_id"], user)
    return example


# ============ 模板列表 & 配置 ============

@router.get("/templates")
async def list_admin_templates(
    tenant_id: Optional[str] = Query(None, description="按部门过滤（仅 super_admin 有效）"),
    user: CurrentUser = Depends(get_current_user),
):
    """
    获取可管理的模板列表。
    - tenant_admin：只返回自己部门的模板，忽略 tenant_id 参数。
    - super_admin：可按 tenant_id 参数过滤，不传则返回全部。
    """
    _require_admin(user)

    effective_tenant_id = tenant_id if user.is_super_admin() else user.tenant_id
    templates = await template_service.get_admin_templates(tenant_id=effective_tenant_id)
    return templates


@router.put("/templates/{template_id}")
async def update_template_config(
    template_id: str,
    request: UpdateTemplateConfigRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """更新模板飞书配置和自动审批开关"""
    _require_admin(user)
    await _require_template_access(template_id, user)

    data = request.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="无有效更新字段")

    updated = await template_service.update_template_config(template_id, data)
    return {"success": True, "data": updated}


# ============ 字段 CRUD ============

@router.get("/templates/{template_id}/fields")
async def list_fields(
    template_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """获取模板字段列表"""
    _require_admin(user)
    await _require_template_access(template_id, user)

    fields = await template_service.get_template_fields(template_id)
    return fields


@router.post("/templates/{template_id}/fields", status_code=201)
async def create_field(
    template_id: str,
    request: CreateFieldRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """新增模板字段"""
    _require_admin(user)
    await _require_template_access(template_id, user)

    field = await template_service.create_field(template_id, request.model_dump())
    return {"success": True, "data": field}


@router.put("/fields/{field_id}")
async def update_field(
    field_id: str,
    request: UpdateFieldRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """更新模板字段"""
    _require_admin(user)
    await _require_field_access(field_id, user)

    data = request.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="无有效更新字段")

    updated = await template_service.update_field(field_id, data)
    return {"success": True, "data": updated}


@router.delete("/fields/{field_id}", status_code=200)
async def delete_field(
    field_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """删除模板字段"""
    _require_admin(user)
    await _require_field_access(field_id, user)

    await template_service.delete_field(field_id)
    return {"success": True}


@router.put("/templates/{template_id}/fields/reorder")
async def reorder_fields(
    template_id: str,
    request: ReorderFieldsRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """批量更新字段排序"""
    _require_admin(user)
    await _require_template_access(template_id, user)

    order_list = [item.model_dump() for item in request.items]
    await template_service.reorder_fields(template_id, order_list)
    return {"success": True}


# ============ Few-shot 示例 CRUD ============

@router.get("/templates/{template_id}/examples")
async def list_examples(
    template_id: str,
    active_only: bool = Query(False),
    user: CurrentUser = Depends(get_current_user),
):
    """获取模板 few-shot 示例列表（管理员视图，默认返回全部含禁用的）"""
    _require_admin(user)
    await _require_template_access(template_id, user)

    examples = await template_service.get_template_examples(template_id, active_only=active_only)
    return examples


@router.post("/templates/{template_id}/examples", status_code=201)
async def create_example(
    template_id: str,
    request: CreateExampleRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """新增 few-shot 示例"""
    _require_admin(user)
    await _require_template_access(template_id, user)

    example = await template_service.create_example(template_id, request.model_dump())
    return {"success": True, "data": example}


@router.put("/examples/{example_id}")
async def update_example(
    example_id: str,
    request: UpdateExampleRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """更新 few-shot 示例"""
    _require_admin(user)
    await _require_example_access(example_id, user)

    data = request.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="无有效更新字段")

    updated = await template_service.update_example(example_id, data)
    return {"success": True, "data": updated}


@router.delete("/examples/{example_id}", status_code=200)
async def delete_example(
    example_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """删除 few-shot 示例"""
    _require_admin(user)
    await _require_example_access(example_id, user)

    await template_service.delete_example(example_id)
    return {"success": True}
