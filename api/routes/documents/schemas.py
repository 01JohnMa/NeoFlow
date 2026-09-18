# api/routes/documents/schemas.py
"""文档路由 - Pydantic 模型定义"""

from pydantic import BaseModel


class RenameRequest(BaseModel):
    """重命名请求"""
    display_name: str
