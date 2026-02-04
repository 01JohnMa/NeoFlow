# api/routes/tenants.py
"""租户相关API路由"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from loguru import logger

from services.tenant_service import tenant_service
from services.template_service import template_service
from api.dependencies.auth import get_current_user, get_optional_user, CurrentUser

router = APIRouter(prefix="/tenants", tags=["租户管理"])


# ============ 请求/响应模型 ============

class TenantResponse(BaseModel):
    """租户响应"""
    id: str
    name: str
    code: str
    description: Optional[str] = None


class TemplateResponse(BaseModel):
    """模板响应"""
    id: str
    name: str
    code: str
    description: Optional[str] = None
    process_mode: str = "single"
    required_doc_count: int = 1


class MergeRuleResponse(BaseModel):
    """合并规则响应"""
    id: str
    template_id: str
    doc_type_a: str
    doc_type_b: str
    sub_template_a_id: Optional[str] = None
    sub_template_b_id: Optional[str] = None


class UpdateProfileRequest(BaseModel):
    """更新用户信息请求"""
    tenant_id: Optional[str] = None
    display_name: Optional[str] = None


class UserProfileResponse(BaseModel):
    """用户信息响应"""
    user_id: str
    tenant_id: Optional[str] = None
    tenant_name: Optional[str] = None
    tenant_code: Optional[str] = None
    role: str = "user"
    display_name: Optional[str] = None


# ============ 公开接口（无需登录） ============

@router.get("", response_model=List[TenantResponse])
async def list_tenants():
    """
    获取所有可用租户列表（注册页下拉用）
    
    无需登录，只返回启用的租户
    """
    tenants = await tenant_service.get_all_tenants(active_only=True)
    return tenants


@router.get("/{tenant_id}")
async def get_tenant(tenant_id: str):
    """
    获取租户详情
    """
    tenant = await tenant_service.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="租户不存在")
    return tenant


# ============ 需要登录的接口 ============

@router.get("/me/profile", response_model=UserProfileResponse)
async def get_my_profile(user: CurrentUser = Depends(get_current_user)):
    """
    获取当前用户的 profile 信息（含租户和角色）
    """
    return UserProfileResponse(
        user_id=user.user_id,
        tenant_id=user.tenant_id,
        tenant_name=user.tenant_name,
        tenant_code=user.tenant_code,
        role=user.role,
        display_name=user.display_name
    )


@router.put("/me/profile")
async def update_my_profile(
    request: UpdateProfileRequest,
    user: CurrentUser = Depends(get_current_user)
):
    """
    更新当前用户的 profile（租户、显示名称）
    
    注意：普通用户只能在首次设置时选择租户，之后不能更改
    """
    # 如果用户已有租户，不允许更改（除非是超级管理员或设置相同的租户）
    if request.tenant_id and user.tenant_id and not user.is_super_admin():
        # 如果设置的是相同的租户，视为幂等操作，直接返回成功
        if request.tenant_id == user.tenant_id:
            logger.debug(f"用户 {user.user_id} 尝试设置相同的租户，幂等返回")
            return {
                "success": True,
                "message": "部门设置未变更",
                "profile": {
                    "user_id": user.user_id,
                    "tenant_id": user.tenant_id,
                    "display_name": user.display_name
                }
            }
        raise HTTPException(
            status_code=403, 
            detail="已有所属部门，不能更改。如需更改请联系管理员"
        )
    
    try:
        profile = await tenant_service.update_user_profile(
            user_id=user.user_id,
            tenant_id=request.tenant_id,
            display_name=request.display_name
        )
        
        return {
            "success": True,
            "message": "更新成功",
            "profile": profile
        }
    except Exception as e:
        logger.error(f"更新用户 profile 失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/me/templates", response_model=List[TemplateResponse])
async def get_my_templates(user: CurrentUser = Depends(get_current_user)):
    """
    获取当前用户所属租户的文档模板列表
    """
    if not user.tenant_id:
        return []
    
    templates = await template_service.get_tenant_templates(user.tenant_id)
    return templates


@router.get("/me/templates/{template_code}")
async def get_my_template_detail(
    template_code: str,
    user: CurrentUser = Depends(get_current_user)
):
    """
    获取指定模板的详细信息（含字段定义）
    """
    if not user.tenant_id:
        raise HTTPException(status_code=400, detail="请先选择所属部门")
    
    template = await template_service.get_template_by_code(user.tenant_id, template_code)
    
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    
    return template


@router.get("/me/merge-rules", response_model=List[MergeRuleResponse])
async def get_my_merge_rules(user: CurrentUser = Depends(get_current_user)):
    """
    获取当前用户所属租户的合并规则列表
    
    用于前端 merge 模式上传页面，了解每个合并模板需要哪些文档类型
    """
    if not user.tenant_id:
        return []
    
    # 获取该租户的所有 merge 模式模板
    templates = await template_service.get_tenant_templates(user.tenant_id)
    merge_templates = [t for t in templates if t.get("process_mode") == "merge"]
    
    # 获取每个 merge 模板的合并规则
    rules = []
    for template in merge_templates:
        rule = await template_service.get_merge_rule(template["id"])
        if rule:
            rules.append(MergeRuleResponse(
                id=rule.get("id"),
                template_id=template["id"],
                doc_type_a=rule.get("doc_type_a", ""),
                doc_type_b=rule.get("doc_type_b", ""),
                sub_template_a_id=rule.get("sub_template_a_id"),
                sub_template_b_id=rule.get("sub_template_b_id"),
            ))
    
    return rules
