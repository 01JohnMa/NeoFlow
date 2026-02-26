# api/routes/health.py
"""健康检查路由"""

from fastapi import APIRouter
from datetime import datetime

from config.settings import settings
from services.ocr_service import ocr_service

router = APIRouter()


@router.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "timestamp": datetime.now().isoformat(),
        "services": {
            "ocr": "ready" if ocr_service.ocr_engine else "not_initialized",
            "supabase_url": settings.SUPABASE_URL
        }
    }


@router.get("/health/ocr")
async def ocr_health():
    """OCR服务健康检查"""
    ocr_ready = ocr_service.ocr_engine is not None
    models_exist = settings.validate_ocr_models()
    
    return {
        "service": "ocr",
        "status": "ready" if ocr_ready else "not_initialized",
        "models_exist": models_exist,
        "models": {
            "det": settings.OCR_DET_MODEL_PATH,
            "rec": settings.OCR_REC_MODEL_PATH,
            "ori": settings.OCR_ORI_MODEL_PATH,
            "doc": settings.OCR_DOC_MODEL_PATH
        }
    }


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





