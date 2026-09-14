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
    """配置检查接口"""
    return {
        "app_name": settings.APP_NAME,
        "debug": settings.DEBUG,
        "supabase_url": settings.SUPABASE_URL,
        "llm_model": settings.LLM_MODEL_ID,
        "llm_base_url": settings.LLM_BASE_URL,
        "upload_folder": settings.UPLOAD_FOLDER,
        "max_file_size": settings.MAX_FILE_SIZE,
        "allowed_extensions": settings.allowed_extensions_list
    }





