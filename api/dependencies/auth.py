# api/dependencies/auth.py
"""认证依赖注入 - FastAPI Depends 实现（支持多租户）"""

from typing import Optional, Tuple
from fastapi import Header, Depends
from pydantic import BaseModel
from supabase import Client
from loguru import logger
import jwt

from services.supabase_service import supabase_service
from api.exceptions import AuthenticationError


class CurrentUser(BaseModel):
    """当前用户信息（含租户）"""
    user_id: str
    token: str
    tenant_id: Optional[str] = None
    tenant_code: Optional[str] = None
    tenant_name: Optional[str] = None
    role: str = "user"  # super_admin / tenant_admin / user
    display_name: Optional[str] = None
    
    class Config:
        arbitrary_types_allowed = True
    
    def is_super_admin(self) -> bool:
        """是否为超级管理员"""
        return self.role == "super_admin"
    
    def is_tenant_admin(self) -> bool:
        """是否为租户管理员或更高"""
        return self.role in ("tenant_admin", "super_admin")
    
    def can_access_tenant(self, tenant_id: str) -> bool:
        """是否可以访问指定租户的数据"""
        if self.is_super_admin():
            return True
        return self.tenant_id == tenant_id


def _extract_token_and_user_id(authorization: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    从 Authorization header 提取 token 并解析 user_id
    
    Args:
        authorization: Authorization header 值 (Bearer xxx)
        
    Returns:
        (token, user_id) 元组，如果解析失败则返回 (None, None)
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None, None
    
    token = authorization[7:]  # 移除 "Bearer " 前缀
    
    try:
        # 解码 JWT（不验证签名，仅提取信息）
        # Supabase 的用户 ID 存储在 "sub" 字段
        payload = jwt.decode(token, options={"verify_signature": False})
        user_id = payload.get("sub")
        return token, user_id
    except Exception as e:
        logger.warning(f"JWT 解析失败: {e}")
        return token, None


async def get_current_user(
    authorization: Optional[str] = Header(None)
) -> CurrentUser:
    """
    获取当前登录用户（必需认证，含租户和角色信息）
    
    用法:
        @router.get("/protected")
        async def protected_endpoint(user: CurrentUser = Depends(get_current_user)):
            print(user.user_id, user.tenant_id, user.role)
    
    Raises:
        AuthenticationError: 未登录或 token 无效
    """
    token, user_id = _extract_token_and_user_id(authorization)
    
    if not token or not user_id:
        raise AuthenticationError()
    
    # 获取用户的 profile 信息（含租户和角色）
    user_data = CurrentUser(user_id=user_id, token=token)
    
    try:
        from services.tenant_service import tenant_service
        profile = await tenant_service.get_user_profile(user_id)
        
        if profile:
            user_data.tenant_id = profile.get("tenant_id")
            user_data.role = profile.get("role", "user")
            user_data.display_name = profile.get("display_name")
            
            # 获取租户信息
            tenant = profile.get("tenants")
            if tenant:
                user_data.tenant_code = tenant.get("code")
                user_data.tenant_name = tenant.get("name")
    except Exception as e:
        logger.warning(f"获取用户 profile 失败: {e}")
    
    return user_data


async def get_optional_user(
    authorization: Optional[str] = Header(None)
) -> Optional[CurrentUser]:
    """
    获取当前用户（可选认证）
    
    未登录时返回 None，不抛出异常
    
    用法:
        @router.get("/public")
        async def public_endpoint(user: Optional[CurrentUser] = Depends(get_optional_user)):
            if user:
                print(f"已登录: {user.user_id}")
            else:
                print("匿名访问")
    """
    token, user_id = _extract_token_and_user_id(authorization)
    
    if not token or not user_id:
        return None
    
    return CurrentUser(user_id=user_id, token=token)


def get_user_client(user: CurrentUser) -> Client:
    """
    根据用户创建带 RLS 的 Supabase 客户端
    
    用法:
        @router.get("/documents")
        async def list_docs(user: CurrentUser = Depends(get_current_user)):
            client = get_user_client(user)
            result = client.table("documents").select("*").execute()
    """
    return supabase_service.get_user_client(user.token)
