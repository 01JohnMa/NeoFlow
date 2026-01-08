# services/supabase_service.py
"""Supabase 数据库服务 - 本地部署版"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from supabase import create_client, Client
from loguru import logger

from config.settings import settings


class SupabaseService:
    """Supabase 服务封装"""
    
    _instance: Optional['SupabaseService'] = None
    _client: Optional[Client] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def initialize(self):
        """初始化Supabase客户端"""
        try:
            self._client = create_client(
                settings.SUPABASE_URL,
                settings.SUPABASE_SERVICE_ROLE_KEY
            )
            logger.info(f"✓ Supabase连接成功: {settings.SUPABASE_URL}")
            return True
        except Exception as e:
            logger.error(f"✗ Supabase连接失败: {e}")
            raise
    
    @property
    def client(self) -> Client:
        if not self._client:
            raise RuntimeError("Supabase未初始化，请先调用initialize()")
        return self._client
    
    # ============ 文档操作 ============
    
    async def create_document(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建文档记录"""
        try:
            result = self.client.table("documents").insert(data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"创建文档失败: {e}")
            raise
    
    async def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        """获取文档"""
        try:
            result = self.client.table("documents").select("*").eq("id", document_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"获取文档失败: {e}")
            raise
    
    async def update_document(self, document_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """更新文档"""
        try:
            result = self.client.table("documents").update(data).eq("id", document_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"更新文档失败: {e}")
            raise
    
    async def delete_document(self, document_id: str) -> bool:
        """删除文档"""
        try:
            self.client.table("documents").delete().eq("id", document_id).execute()
            return True
        except Exception as e:
            logger.error(f"删除文档失败: {e}")
            return False
    
    async def update_document_status(
        self, 
        document_id: str, 
        status: str, 
        error_message: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """更新文档状态"""
        data = {"status": status}
        if error_message:
            data["error_message"] = error_message
        if status == "completed":
            data["processed_at"] = datetime.now().isoformat()
        
        return await self.update_document(document_id, data)
    
    async def list_documents(
        self,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
        document_type: Optional[str] = None,
        page: int = 1,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """列出文档"""
        try:
            query = self.client.table("documents").select("*")
            
            if user_id:
                query = query.eq("user_id", user_id)
            if status:
                query = query.eq("status", status)
            if document_type:
                query = query.eq("document_type", document_type)
            
            offset = (page - 1) * limit
            query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
            
            result = query.execute()
            return result.data or []
        except Exception as e:
            logger.error(f"列出文档失败: {e}")
            return []
    
    async def count_documents(
        self,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
        document_type: Optional[str] = None
    ) -> int:
        """统计文档数量"""
        try:
            query = self.client.table("documents").select("id", count="exact")
            
            if user_id:
                query = query.eq("user_id", user_id)
            if status:
                query = query.eq("status", status)
            if document_type:
                query = query.eq("document_type", document_type)
            
            result = query.execute()
            return result.count or 0
        except Exception as e:
            logger.error(f"统计文档失败: {e}")
            return 0
    
    # ============ 检验报告操作 ============
    
    async def save_inspection_report(self, document_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """保存检验报告"""
        try:
            data["document_id"] = document_id
            data["raw_extraction_data"] = data.copy()
            result = self.client.table("inspection_reports").upsert(data, on_conflict="document_id").execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"保存检验报告失败: {e}")
            raise
    
    async def get_inspection_report(self, document_id: str) -> Optional[Dict[str, Any]]:
        """获取检验报告"""
        try:
            result = self.client.table("inspection_reports").select("*").eq("document_id", document_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"获取检验报告失败: {e}")
            return None
    
    # ============ 快递单操作 ============
    
    async def save_express(self, document_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """保存快递单"""
        try:
            data["document_id"] = document_id
            data["raw_extraction_data"] = data.copy()
            result = self.client.table("expresses").upsert(data, on_conflict="document_id").execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"保存快递单失败: {e}")
            raise
    
    async def get_express(self, document_id: str) -> Optional[Dict[str, Any]]:
        """获取快递单"""
        try:
            result = self.client.table("expresses").select("*").eq("document_id", document_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"获取快递单失败: {e}")
            return None
    
    # ============ 抽样单操作 ============
    
    async def save_sampling_form(self, document_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """保存抽样单"""
        try:
            data["document_id"] = document_id
            data["raw_extraction_data"] = data.copy()
            result = self.client.table("sampling_forms").upsert(data, on_conflict="document_id").execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"保存抽样单失败: {e}")
            raise
    
    async def get_sampling_form(self, document_id: str) -> Optional[Dict[str, Any]]:
        """获取抽样单"""
        try:
            result = self.client.table("sampling_forms").select("*").eq("document_id", document_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"获取抽样单失败: {e}")
            return None
    
    # ============ 通用保存方法 ============
    
    async def save_extraction_result(
        self, 
        document_id: str, 
        document_type: str, 
        extraction_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """根据文档类型保存提取结果"""
        if document_type == "测试单":
            return await self.save_inspection_report(document_id, extraction_data)
        elif document_type == "快递单":
            return await self.save_express(document_id, extraction_data)
        elif document_type == "抽样单":
            return await self.save_sampling_form(document_id, extraction_data)
        else:
            logger.warning(f"未知文档类型: {document_type}")
            return None
    
    async def get_extraction_result(
        self, 
        document_id: str, 
        document_type: str
    ) -> Optional[Dict[str, Any]]:
        """根据文档类型获取提取结果"""
        if document_type == "测试单" or document_type == "inspection_report":
            return await self.get_inspection_report(document_id)
        elif document_type == "快递单" or document_type == "express":
            return await self.get_express(document_id)
        elif document_type == "抽样单" or document_type == "sampling_form":
            return await self.get_sampling_form(document_id)
        else:
            return None
    
    # ============ 处理日志 ============
    
    async def log_processing(
        self,
        document_id: str,
        step: str,
        status: str,
        message: Optional[str] = None,
        duration_ms: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """记录处理日志"""
        try:
            data = {
                "document_id": document_id,
                "step": step,
                "status": status,
                "message": message,
                "duration_ms": duration_ms
            }
            result = self.client.table("processing_logs").insert(data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"记录处理日志失败: {e}")
            return None
    
    async def get_processing_logs(self, document_id: str) -> List[Dict[str, Any]]:
        """获取处理日志"""
        try:
            result = self.client.table("processing_logs").select("*").eq("document_id", document_id).order("created_at").execute()
            return result.data or []
        except Exception as e:
            logger.error(f"获取处理日志失败: {e}")
            return []


# 单例实例
supabase_service = SupabaseService()


