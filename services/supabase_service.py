# services/supabase_service.py
"""Supabase 数据库服务 - 本地部署版"""

from datetime import datetime
from typing import Optional, Dict, Any, List

from loguru import logger
from postgrest import SyncPostgrestClient

from config.settings import settings
from services.base import SupabaseClientMixin


class SupabaseService(SupabaseClientMixin):
    """Supabase 服务封装"""
    
    _instance: Optional['SupabaseService'] = None
    _client: Optional[SyncPostgrestClient] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def _build_rest_client(
        self,
        api_key: str,
        authorization: Optional[str] = None,
    ) -> SyncPostgrestClient:
        """构建 PostgREST 客户端（数据访问直连，不经过网关）"""
        return SyncPostgrestClient(
            settings.SUPABASE_URL,
            headers={
                "apikey": api_key,
                "Authorization": authorization or f"Bearer {api_key}",
            },
        )

    async def initialize(self):
        """初始化 PostgREST 客户端"""
        try:
            self._client = self._build_rest_client(settings.SUPABASE_SERVICE_ROLE_KEY)
            logger.info(f"✓ PostgREST 客户端已创建: {settings.SUPABASE_URL}")
            return True
        except Exception as e:
            logger.error(f"✗ PostgREST 客户端创建失败: {e}")
            raise
    
    @property
    def client(self) -> SyncPostgrestClient:
        if not self._client:
            raise RuntimeError("Supabase未初始化，请先调用initialize()")
        return self._client
    
    def get_user_client(self, user_token: str) -> SyncPostgrestClient:
        """
        根据用户 JWT token 创建 PostgREST client（应用 RLS 策略）
        
        Args:
            user_token: 用户的 JWT access token
            
        Returns:
            配置了用户身份的客户端，自动应用 RLS 策略
        """
        return self._build_rest_client(
            settings.SUPABASE_ANON_KEY,
            authorization=f"Bearer {user_token}",
        )
    
    # ============ 文档操作 ============
    
    async def create_document(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建文档记录"""
        try:
            result = await self._run_sync(
                lambda: self.client.table("documents").insert(data).execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error("创建文档失败: {}", e)
            raise
    
    async def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        """获取文档"""
        try:
            result = await self._run_sync(
                lambda: self.client.table("documents").select("*").eq("id", document_id).execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"获取文档失败: {e}")
            raise
    
    async def update_document(self, document_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """更新文档"""
        try:
            result = await self._run_sync(
                lambda: self.client.table("documents").update(data).eq("id", document_id).execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"更新文档失败: {e}")
            raise
    
    async def delete_document(self, document_id: str) -> bool:
        """删除文档"""
        try:
            await self._run_sync(
                lambda: self.client.table("documents").delete().eq("id", document_id).execute()
            )
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
        if error_message is not None:
            data["error_message"] = error_message
        elif status in ("queued", "processing", "completed", "pending_review"):
            data["error_message"] = None
        if status == "completed":
            data["processed_at"] = datetime.now().isoformat()
        
        return await self.update_document(document_id, data)

    async def reset_stuck_processing_documents(self, timeout_minutes: int = 30) -> int:
        """
        将超过 timeout_minutes 分钟仍处于 processing 状态的文档重置为 failed。
        返回受影响的文档数量。
        """
        from datetime import timedelta

        cutoff = (
            datetime.utcnow() - timedelta(minutes=timeout_minutes)
        ).isoformat()

        result = await self._run_sync(
            lambda: self.client.table("documents")
            .select("id")
            .eq("status", "processing")
            .lt("updated_at", cutoff)
            .execute()
        )
        stuck_docs = result.data or []
        if not stuck_docs:
            return 0

        stuck_ids = [doc["id"] for doc in stuck_docs]
        error_msg = f"处理超时（超过 {timeout_minutes} 分钟），已自动重置"

        await self._run_sync(
            lambda: self.client.table("documents")
            .update({"status": "failed", "error_message": error_msg, "updated_at": datetime.utcnow().isoformat()})
            .in_("id", stuck_ids)
            .execute()
        )

        logger.warning(f"已重置 {len(stuck_ids)} 个超时 processing 文档: {stuck_ids}")
        return len(stuck_ids)

    async def get_job_metrics(self) -> Dict[str, Any]:
        """获取当前任务观测指标。"""
        try:
            pending_result = await self._run_sync(
                lambda: self.client.table("processing_jobs").select("job_id", count="exact").in_("status", ["queued", "pending", "processing"]).execute()
            )
            failed_result = await self._run_sync(
                lambda: self.client.table("processing_jobs").select("job_id", count="exact").eq("status", "failed").execute()
            )
            completed_result = await self._run_sync(
                lambda: self.client.table("processing_jobs").select("job_id", count="exact").eq("status", "completed").execute()
            )
            recent_queue_result = await self._run_sync(
                lambda: self.client.table("processing_jobs").select("created_at,updated_at,status").order("created_at", desc=True).limit(20).execute()
            )

            queue_durations = []
            for row in recent_queue_result.data or []:
                if row.get("status") in ("processing", "completed", "failed") and row.get("created_at") and row.get("updated_at"):
                    try:
                        created_at = datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00"))
                        updated_at = datetime.fromisoformat(str(row["updated_at"]).replace("Z", "+00:00"))
                        queue_durations.append(max(0, int((updated_at - created_at).total_seconds())))
                    except ValueError:
                        continue

            avg_queue_seconds = int(sum(queue_durations) / len(queue_durations)) if queue_durations else 0
            active_jobs = pending_result.count or 0
            failed_jobs = failed_result.count or 0
            completed_jobs = completed_result.count or 0

            escalation_reasons: list[str] = []
            recommended_action = "stay_on_current_architecture"
            if avg_queue_seconds >= 300:
                escalation_reasons.append("任务平均排队时长已超过 5 分钟")
            if active_jobs > max(4, settings.DOC_PROCESS_MAX_CONCURRENCY * 2):
                escalation_reasons.append("当前活跃任务数持续高于 API 进程可舒适承载范围")
            if failed_jobs > completed_jobs and failed_jobs > 0:
                escalation_reasons.append("失败任务数量已超过完成任务数量")

            if len(escalation_reasons) >= 2:
                recommended_action = "consider_half_worker"
            if avg_queue_seconds >= 600 and active_jobs > max(6, settings.DOC_PROCESS_MAX_CONCURRENCY * 3):
                recommended_action = "consider_full_worker"

            return {
                "active_jobs": active_jobs,
                "failed_jobs": failed_jobs,
                "completed_jobs": completed_jobs,
                "avg_queue_seconds": avg_queue_seconds,
                "sample_size": len(queue_durations),
                "recommended_action": recommended_action,
                "escalation_reasons": escalation_reasons,
                "observed_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"获取任务指标失败: {e}")
            return {
                "active_jobs": 0,
                "failed_jobs": 0,
                "completed_jobs": 0,
                "avg_queue_seconds": 0,
                "sample_size": 0,
                "recommended_action": "stay_on_current_architecture",
                "escalation_reasons": [],
                "observed_at": datetime.now().isoformat(),
            }
    
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
            
            result = await self._run_sync(query.execute)
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
            
            result = await self._run_sync(query.execute)
            return result.count or 0
        except Exception as e:
            logger.error(f"统计文档失败: {e}")
            return 0
    
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
            result = await self._run_sync(
                lambda: self.client.table("processing_logs").insert(data).execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"记录处理日志失败: {e}")
            return None
    
    async def get_processing_logs(self, document_id: str) -> List[Dict[str, Any]]:
        """获取处理日志"""
        try:
            result = await self._run_sync(
                lambda: self.client.table("processing_logs").select("*").eq("document_id", document_id).order("created_at").execute()
            )
            return result.data or []
        except Exception as e:
            logger.error(f"获取处理日志失败: {e}")
            return []


    async def update_display_name(self, document_id: str, display_name: str) -> Optional[Dict[str, Any]]:
        """更新文档的显示名称"""
        return await self.update_document(document_id, {"display_name": display_name})


# 单例实例
supabase_service = SupabaseService()



