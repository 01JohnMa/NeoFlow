# api/routes/health.py
"""健康检查路由"""

from fastapi import APIRouter
from datetime import datetime

from config.settings import settings
from services.supabase_service import supabase_service

router = APIRouter()


@router.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "timestamp": datetime.now().isoformat(),
        "services": {
            "supabase_url": settings.SUPABASE_URL
        }
    }


@router.get("/health/jobs")
async def jobs_health():
    """任务观测指标接口"""
    return await supabase_service.get_job_metrics()


@router.get("/health/config")
async def config_check():
    """配置检查接口。

    只回显模式与模型名，不回显任何端点地址或凭据（Relay 地址属于平台
    内部拓扑，不进入 readiness 响应）。
    """
    from services.platform_model_client import model_access_mode

    return {
        "app_name": settings.APP_NAME,
        "debug": settings.DEBUG,
        "supabase_url": settings.SUPABASE_URL,
        "llm_model": settings.LLM_MODEL_ID,
        "llm_provider": model_access_mode(settings),
        "upload_folder": settings.UPLOAD_FOLDER,
        "max_file_size": settings.MAX_FILE_SIZE,
        "allowed_extensions": settings.allowed_extensions_list
    }



