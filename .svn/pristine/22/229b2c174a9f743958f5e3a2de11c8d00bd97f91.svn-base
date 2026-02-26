# api/routes/documents/__init__.py
"""文档路由模块 - 聚合所有子路由"""

from fastapi import APIRouter

from .upload import router as upload_router
from .process import router as process_router
from .query import router as query_router
from .review import router as review_router

# 创建主路由
router = APIRouter()

# 注册子路由
router.include_router(upload_router, tags=["文档上传"])
router.include_router(process_router, tags=["文档处理"])
router.include_router(query_router, tags=["文档查询"])
router.include_router(review_router, tags=["文档审核"])
