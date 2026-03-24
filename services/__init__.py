# services package
# 惰性加载：避免 import services.schema_sync_service 等子模块时拉起重依赖（如 paddleocr）

def __getattr__(name: str):
    if name == "ocr_service":
        from .ocr_service import ocr_service
        return ocr_service
    if name == "feishu_service":
        from .feishu_service import feishu_service
        return feishu_service
    if name == "supabase_service":
        from .supabase_service import supabase_service
        return supabase_service
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["ocr_service", "supabase_service", "feishu_service"]
