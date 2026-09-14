# services package
# 惰性加载：避免 import 子模块时拉起重依赖

def __getattr__(name: str):
    if name == "feishu_service":
        from .feishu_service import feishu_service
        return feishu_service
    if name == "supabase_service":
        from .supabase_service import supabase_service
        return supabase_service
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["supabase_service", "feishu_service"]
