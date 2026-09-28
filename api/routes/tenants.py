# api/routes/tenants.py
"""租户相关API路由"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from typing import Optional
from loguru import logger

from services.tenant_service import tenant_service
from api.dependencies.auth import get_current_user, CurrentUser, invalidate_profile_cache

router = APIRouter(prefix="/tenants", tags=["租户管理"])


# ============ 请求/响应模型 ============

class UpdateProfileRequest(BaseModel):
    """更新用户信息请求"""
    model_config = ConfigDict(extra="forbid")

    display_name: Optional[str] = None


class UserProfileResponse(BaseModel):
    """用户信息响应"""
    user_id: str
    tenant_id: Optional[str] = None
    tenant_name: Optional[str] = None
    tenant_code: Optional[str] = None
    role: str = "user"
    display_name: Optional[str] = None


# ============ 需要登录的接口 ============

@router.get("/me/profile", response_model=UserProfileResponse, include_in_schema=False)
async def get_my_profile(user: CurrentUser = Depends(get_current_user)):
    """
    获取当前用户的 profile 信息（含租户、角色）
    """
    return UserProfileResponse(
        user_id=user.user_id,
        tenant_id=user.tenant_id,
        tenant_name=user.tenant_name,
        tenant_code=user.tenant_code,
        role=user.role,
        display_name=user.display_name,
    )


@router.put("/me/profile", include_in_schema=False)
async def update_my_profile(
    request: UpdateProfileRequest,
    user: CurrentUser = Depends(get_current_user)
):
    """更新显示名称。租户范围由平台或已绑定的 profile 决定，不接受调用方修改。"""
    try:
        profile = await tenant_service.update_user_profile(
            user_id=user.user_id,
            display_name=request.display_name
        )
        invalidate_profile_cache(user.user_id)
        
        return {
            "success": True,
            "message": "更新成功",
            "profile": profile
        }
    except Exception as e:
        logger.error(f"更新用户 profile 失败: {e}")
        raise HTTPException(status_code=500, detail="更新失败，请稍后重试")


@router.get("/me/templates/{configuration_key}", include_in_schema=False)
async def get_my_template_detail(
    configuration_key: str,
    user: CurrentUser = Depends(get_current_user)
):
    """
    获取指定配置的详细信息（含字段定义）
    """
    if not user.tenant_id:
        raise HTTPException(status_code=400, detail="请求缺少有效租户范围")

    configuration = await configuration_service.resolve_extraction_configuration(
        user.tenant_id, configuration_key
    )

    if not configuration:
        raise HTTPException(status_code=404, detail="配置不存在")

    return configuration
