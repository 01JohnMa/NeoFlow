# api/dependencies/auth.py
"""认证依赖注入 - FastAPI Depends 实现（支持多租户）"""

import asyncio
import time
from typing import Optional, Tuple, Dict, Any
from fastapi import Header, Depends
from pydantic import BaseModel
from loguru import logger
import jwt
from jwt import PyJWKClient

from services.supabase_service import supabase_service
from api.exceptions import AuthenticationError
from config.settings import settings

_PROFILE_CACHE_TTL = 60  # seconds
_profile_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}

_JWKS_KEY_LIFESPAN = 86400  # PyJWKClient 内部公钥缓存时长；遇到未知 kid 会自动重新拉取
_ASYMMETRIC_ALGORITHMS = ("ES256", "RS256")
_jwks_client: Optional[Tuple[str, PyJWKClient]] = None


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


def _extract_bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization[7:].strip()


def _get_jwks_client() -> Optional[PyJWKClient]:
    """按 JWKS_URL 懒加载公钥客户端（进程内单例，未知 kid 时自动刷新）。"""
    global _jwks_client
    url = settings.JWKS_URL
    if not url:
        return None
    if _jwks_client and _jwks_client[0] == url:
        return _jwks_client[1]
    client = PyJWKClient(url, cache_keys=True, lifespan=_JWKS_KEY_LIFESPAN)
    _jwks_client = (url, client)
    return client


async def warm_jwks_cache() -> None:
    """启动时预热 JWKS，避免首个请求在验签路径上等待拉取公钥。"""
    client = _get_jwks_client()
    if client is None:
        return
    try:
        await asyncio.to_thread(client.fetch_data)
        logger.info("✓ JWKS 公钥已预热")
    except Exception as e:
        logger.warning(f"JWKS 预热失败（首个请求将重试）: {e}")


async def _extract_token_and_user_id(
    authorization: Optional[str],
) -> Tuple[Optional[str], Optional[str]]:
    """
    从 Authorization header 提取 token，按 token alg 选择验签方式：

    - HS256：GoTrue 对称密钥（JWT_SECRET，适用于自建/本地部署）
    - ES256/RS256：Supabase 云项目 JWKS 公钥（JWKS_URL）

    对应密钥缺失或签名/有效期/aud 校验失败时一律返回 (None, None)，
    由调用方按未认证处理（fail closed）。

    Args:
        authorization: Authorization header 值 (Bearer xxx)

    Returns:
        (token, user_id) 元组，如果验签或解析失败则返回 (None, None)
    """
    token = _extract_bearer_token(authorization)
    if not token:
        return None, None

    try:
        algorithm = jwt.get_unverified_header(token).get("alg") or ""
    except Exception as e:
        logger.warning(f"JWT 头部解析失败: {e}")
        return None, None

    try:
        if algorithm == settings.JWT_ALGORITHM:
            if not settings.JWT_SECRET:
                logger.error("JWT_SECRET 未配置，拒绝 Bearer token（fail closed）")
                return None, None
            payload = jwt.decode(
                token,
                settings.JWT_SECRET,
                algorithms=[settings.JWT_ALGORITHM],
                audience="authenticated",
            )
        elif algorithm in _ASYMMETRIC_ALGORITHMS:
            jwks_client = _get_jwks_client()
            if jwks_client is None:
                logger.error("JWKS_URL 未配置，拒绝非对称 Bearer token（fail closed）")
                return None, None
            signing_key = await asyncio.to_thread(
                jwks_client.get_signing_key_from_jwt, token
            )
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=list(_ASYMMETRIC_ALGORITHMS),
                audience="authenticated",
            )
        else:
            logger.warning(f"不支持的 JWT 算法: {algorithm}")
            return None, None
    except Exception as e:
        logger.warning(f"JWT 验签失败: {e}")
        return None, None

    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id:
        logger.warning("JWT 校验通过但缺少 sub 声明")
        return None, None
    return token, user_id


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
    token, user_id = await _extract_token_and_user_id(authorization)
    
    if not token or not user_id:
        raise AuthenticationError()
    
    # 获取用户的 profile 信息（含租户和角色），优先读缓存
    user_data = CurrentUser(user_id=user_id, token=token)
    
    try:
        now = time.monotonic()
        cached = _profile_cache.get(user_id)
        if cached and (now - cached[0]) < _PROFILE_CACHE_TTL:
            profile = cached[1]
        else:
            from services.tenant_service import tenant_service
            profile = await tenant_service.get_user_profile(user_id)
            if profile:
                _profile_cache[user_id] = (now, profile)
            logger.debug(f"获取用户 profile (DB): user_id={user_id}")
        
        if profile:
            user_data.tenant_id = profile.get("tenant_id")
            user_data.role = profile.get("role", "user")
            user_data.display_name = profile.get("display_name")
            
            tenant = profile.get("tenants")
            if tenant:
                user_data.tenant_code = tenant.get("code")
                user_data.tenant_name = tenant.get("name")
            
            if not user_data.tenant_id:
                logger.warning(f"用户 {user_id} 的 profile 存在但 tenant_id 为空，可能是注册时触发器未正确写入或前端未补写")
        else:
            logger.warning(f"用户 {user_id} 没有 profile 记录，可能是 handle_new_user 触发器未执行")
    except Exception as e:
        logger.error(f"获取用户 profile 失败: user_id={user_id}, error={e}")
    
    return user_data


def invalidate_profile_cache(user_id: str) -> None:
    """清除指定用户的 profile 缓存（在 profile 更新后调用）"""
    _profile_cache.pop(user_id, None)


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
    token, user_id = await _extract_token_and_user_id(authorization)
    
    if not token or not user_id:
        return None
    
    return CurrentUser(user_id=user_id, token=token)
