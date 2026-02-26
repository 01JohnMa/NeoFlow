# services/tenant_service.py
"""租户服务 - 多租户管理"""

from typing import Optional, Dict, Any, List
from loguru import logger

from config.settings import settings


class TenantService:
    """租户服务封装"""
    
    _instance: Optional['TenantService'] = None
    _client = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def _get_client(self):
        """获取 Supabase 客户端"""
        if self._client is None:
            from services.supabase_service import supabase_service
            self._client = supabase_service.client
        return self._client
    
    # ============ 租户操作 ============
    
    async def get_all_tenants(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """
        获取所有租户列表（注册页下拉用）
        
        Args:
            active_only: 是否只返回启用的租户
            
        Returns:
            租户列表
        """
        try:
            query = self._get_client().table("tenants").select("id, name, code, description")
            
            if active_only:
                query = query.eq("is_active", True)
            
            query = query.order("name")
            result = query.execute()
            
            return result.data or []
        except Exception as e:
            logger.error(f"获取租户列表失败: {e}")
            return []
    
    async def get_tenant(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """
        根据ID获取租户信息
        
        Args:
            tenant_id: 租户ID
            
        Returns:
            租户信息
        """
        try:
            result = self._get_client().table("tenants").select("*").eq("id", tenant_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"获取租户失败: {e}")
            return None
    
    async def get_tenant_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """
        根据代码获取租户信息
        
        Args:
            code: 租户代码（如 "quality", "lighting"）
            
        Returns:
            租户信息
        """
        try:
            result = self._get_client().table("tenants").select("*").eq("code", code).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"获取租户失败: {e}")
            return None
    
    async def create_tenant(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        创建新租户
        
        Args:
            data: 租户数据 {name, code, description}
            
        Returns:
            创建的租户信息
        """
        try:
            result = self._get_client().table("tenants").insert(data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"创建租户失败: {e}")
            raise
    
    async def update_tenant(self, tenant_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        更新租户信息
        
        Args:
            tenant_id: 租户ID
            data: 更新数据
            
        Returns:
            更新后的租户信息
        """
        try:
            result = self._get_client().table("tenants").update(data).eq("id", tenant_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"更新租户失败: {e}")
            raise
    
    # ============ 用户 Profile 操作 ============
    
    async def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        获取用户的 profile 信息（包含租户和角色）
        
        Args:
            user_id: 用户ID
            
        Returns:
            用户 profile 信息
        """
        try:
            # 先查询 profile 基础信息
            result = self._get_client().table("profiles").select("*").eq("id", user_id).execute()
            if not result.data:
                return None
            
            profile = result.data[0]
            
            # 如果有 tenant_id，单独查询租户信息
            if profile.get("tenant_id"):
                tenant_result = self._get_client().table("tenants").select(
                    "id, name, code"
                ).eq("id", profile["tenant_id"]).execute()
                if tenant_result.data:
                    profile["tenants"] = tenant_result.data[0]
            
            return profile
        except Exception as e:
            logger.error(f"获取用户 profile 失败: {e}")
            return None
    
    async def get_tenant_by_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        根据用户ID获取所属租户
        
        Args:
            user_id: 用户ID
            
        Returns:
            租户信息
        """
        try:
            profile = await self.get_user_profile(user_id)
            if profile and profile.get("tenants"):
                return profile["tenants"]
            return None
        except Exception as e:
            logger.error(f"获取用户租户失败: {e}")
            return None
    
    async def get_user_role(self, user_id: str) -> Optional[str]:
        """
        获取用户角色
        
        Args:
            user_id: 用户ID
            
        Returns:
            角色（super_admin / tenant_admin / user）
        """
        try:
            profile = await self.get_user_profile(user_id)
            return profile.get("role") if profile else None
        except Exception as e:
            logger.error(f"获取用户角色失败: {e}")
            return None
    
    async def update_user_profile(
        self, 
        user_id: str, 
        tenant_id: Optional[str] = None,
        role: Optional[str] = None,
        display_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        更新用户 profile
        
        Args:
            user_id: 用户ID
            tenant_id: 租户ID（可选）
            role: 角色（可选）
            display_name: 显示名称（可选）
            
        Returns:
            更新后的 profile
        """
        try:
            data = {}
            if tenant_id is not None:
                data["tenant_id"] = tenant_id
            if role is not None:
                data["role"] = role
            if display_name is not None:
                data["display_name"] = display_name
            
            if not data:
                return await self.get_user_profile(user_id)
            
            result = self._get_client().table("profiles").update(data).eq("id", user_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"更新用户 profile 失败: {e}")
            raise
    
    async def create_user_profile(
        self,
        user_id: str,
        tenant_id: Optional[str] = None,
        role: str = "user",
        display_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        创建用户 profile（注册时调用）
        
        Args:
            user_id: 用户ID
            tenant_id: 租户ID
            role: 角色
            display_name: 显示名称
            
        Returns:
            创建的 profile
        """
        try:
            data = {
                "id": user_id,
                "tenant_id": tenant_id,
                "role": role,
                "display_name": display_name
            }
            
            result = self._get_client().table("profiles").upsert(data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"创建用户 profile 失败: {e}")
            raise
    
    # ============ 租户用户列表 ============
    
    async def get_tenant_users(self, tenant_id: str) -> List[Dict[str, Any]]:
        """
        获取租户下的所有用户
        
        Args:
            tenant_id: 租户ID
            
        Returns:
            用户列表
        """
        try:
            result = self._get_client().table("profiles").select(
                "id, tenant_id, role, display_name, created_at"
            ).eq("tenant_id", tenant_id).order("created_at", desc=True).execute()
            
            return result.data or []
        except Exception as e:
            logger.error(f"获取租户用户列表失败: {e}")
            return []
    
    # ============ 权限检查 ============
    
    async def is_super_admin(self, user_id: str) -> bool:
        """检查用户是否为超级管理员"""
        role = await self.get_user_role(user_id)
        return role == "super_admin"
    
    async def is_tenant_admin(self, user_id: str) -> bool:
        """检查用户是否为租户管理员"""
        role = await self.get_user_role(user_id)
        return role in ("tenant_admin", "super_admin")
    
    async def can_access_tenant(self, user_id: str, tenant_id: str) -> bool:
        """
        检查用户是否可以访问指定租户的数据
        
        Args:
            user_id: 用户ID
            tenant_id: 租户ID
            
        Returns:
            是否有权限
        """
        profile = await self.get_user_profile(user_id)
        if not profile:
            return False
        
        # 超级管理员可以访问所有租户
        if profile.get("role") == "super_admin":
            return True
        
        # 其他用户只能访问自己的租户
        return profile.get("tenant_id") == tenant_id


# 单例实例
tenant_service = TenantService()
