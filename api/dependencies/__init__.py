# api/dependencies/__init__.py
"""依赖注入模块"""

from .auth import get_current_user, get_optional_user, CurrentUser

__all__ = ["get_current_user", "get_optional_user", "CurrentUser"]
