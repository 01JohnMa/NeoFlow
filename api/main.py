
# api/main.py
"""FastAPI 主应用"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from loguru import logger
import os

from config.settings import settings
from services.ocr_service import ocr_service
from services.supabase_service import supabase_service
from api.routes import documents_router, health_router
from api.routes.tenants import router as tenants_router


# 配置日志
logger.add(
    settings.LOG_FILE,
    rotation="10 MB",
    retention="7 days",
    level=settings.LOG_LEVEL
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化服务
    logger.info("=" * 50)
    logger.info(f"正在启动 {settings.APP_NAME}...")
    logger.info("=" * 50)
    
    # 创建必要的目录
    os.makedirs(settings.UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(os.path.dirname(settings.LOG_FILE), exist_ok=True)
    logger.info(f"✓ 上传目录: {settings.UPLOAD_FOLDER}")
    
    # 初始化OCR服务
    if settings.OCR_ENABLED:
        try:
            await ocr_service.initialize()
            logger.info("✓ OCR服务初始化成功")
        except Exception as e:
            logger.warning(f"⚠ OCR服务初始化失败（可稍后重试）: {e}")
    else:
        logger.warning("⚠ OCR服务已禁用（OCR_ENABLED=false）")
    
    # 初始化Supabase服务
    try:
        await supabase_service.initialize()
        logger.info("✓ Supabase服务初始化成功")
    except Exception as e:
        logger.warning(f"⚠ Supabase服务初始化失败（请检查配置）: {e}")
    
    logger.info("=" * 50)
    logger.info(f"✓ {settings.APP_NAME} 启动完成")
    logger.info(f"  API文档: http://{settings.HOST}:{settings.PORT}/docs")
    logger.info(f"  健康检查: http://{settings.HOST}:{settings.PORT}/api/health")
    logger.info("=" * 50)
    
    yield
    
    # 关闭时清理
    logger.info("正在关闭服务...")
    await ocr_service.close()
    logger.info("服务已关闭")


# 创建FastAPI应用
app = FastAPI(
    title=settings.APP_NAME,
    description="NeoFlow 智能文档处理平台",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(health_router, prefix="/api", tags=["健康检查"])
app.include_router(documents_router, prefix="/api/documents", tags=["文档处理"])
app.include_router(tenants_router, prefix="/api", tags=["租户管理"])


# 全局异常处理
from api.exceptions import AppException


@app.exception_handler(AppException)
async def app_exception_handler(request, exc: AppException):
    """处理业务异常 - 返回统一格式"""
    logger.warning(f"业务异常 [{exc.code}]: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "code": exc.code,
            "status_code": exc.status_code
        }
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """处理 HTTP 异常"""
    logger.error(f"HTTP异常: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "code": "HTTP_ERROR",
            "status_code": exc.status_code
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """处理未捕获异常"""
    logger.error(f"未处理异常: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "内部服务器错误",
            "code": "INTERNAL_ERROR",
            "detail": str(exc)
        }
    )


# 根路由
@app.get("/")
async def root():
    """根路由 - 显示API信息"""
    return {
        "app": settings.APP_NAME,
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/api/health",
        "endpoints": {
            "upload": "POST /api/documents/upload",
            "process": "POST /api/documents/{document_id}/process",
            "status": "GET /api/documents/{document_id}/status",
            "result": "GET /api/documents/{document_id}/result"
        }
    }


# 启动入口
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )


