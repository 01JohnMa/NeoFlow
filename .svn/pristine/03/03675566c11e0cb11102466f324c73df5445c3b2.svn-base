# api/routes/documents/schemas.py
"""文档路由 - Pydantic 模型定义"""

from pydantic import BaseModel
from typing import Dict, Any, Optional


class ValidateRequest(BaseModel):
    """审核验证请求"""
    document_type: str
    data: Dict[str, Any]
    validation_notes: Optional[str] = None


class RejectRequest(BaseModel):
    """打回请求"""
    reason: str


class RenameRequest(BaseModel):
    """重命名请求"""
    display_name: str
