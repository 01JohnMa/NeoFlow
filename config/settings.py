# config/settings.py
"""应用配置管理"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional, List
import os


class Settings(BaseSettings):
    """应用配置类"""
    
    # ============ 基础配置 ============
    APP_NAME: str = "NeoFlow"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8080
    
    # ============ 安全配置 ============
    SECRET_KEY: str = "your-secret-key"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # ============ Supabase配置 (本地部署) ============
    SUPABASE_URL: str = "http://localhost:8000"
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    DATABASE_URL: Optional[str] = None
    
    # ============ LLM配置 ============
    LLM_MODEL_ID: str = "gpt-4o-mini"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_TEMPERATURE: float = 0.7
    
    # ============ OCR模型路径 ============
    OCR_DET_MODEL_PATH: str = "./model/PP-OCRv5_server_det_infer"
    OCR_REC_MODEL_PATH: str = "./model/PP-OCRv5_server_rec_infer"
    OCR_ORI_MODEL_PATH: str = "./model/PP-LCNet_x1_0_textline_ori_infer"
    OCR_DOC_MODEL_PATH: str = "./model/PP-LCNet_x1_0_doc_ori_infer"
    OCR_ENABLED: bool = True
    OCR_IR_OPTIM: bool = False
    OCR_USE_MKLDNN: bool = False
    
    # ============ 文件存储 ============
    UPLOAD_FOLDER: str = "./uploads"
    MAX_FILE_SIZE: int = 20971520  # 20MB
    ALLOWED_EXTENSIONS: str = ".pdf,.png,.jpg,.jpeg,.tiff,.bmp"
    
    # ============ 日志配置 ============
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "./logs/app.log"
    
    # ============ CORS配置 ============
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:3001,http://localhost:8080"
    ALLOWED_HOSTS: str = "localhost,127.0.0.1"
    
    # ============ 飞书配置 ============
    FEISHU_APP_ID: str = ""
    FEISHU_APP_SECRET: str = ""
    FEISHU_BITABLE_APP_TOKEN: str = ""  # 多维表格 app_token
    FEISHU_BITABLE_TABLE_ID: str = ""   # 数据表 table_id
    FEISHU_PUSH_ENABLED: bool = False   # 是否启用推送
    
    @property
    def allowed_extensions_list(self) -> List[str]:
        """获取允许的文件扩展名列表"""
        return [ext.strip() for ext in self.ALLOWED_EXTENSIONS.split(",")]
    
    @property
    def cors_origins_list(self) -> List[str]:
        """获取CORS允许的源列表"""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]
    
    @property
    def allowed_hosts_list(self) -> List[str]:
        """获取允许的主机列表"""
        return [host.strip() for host in self.ALLOWED_HOSTS.split(",")]
    
    def validate_ocr_models(self) -> bool:
        """验证OCR模型路径是否存在"""
        paths = [
            self.OCR_DET_MODEL_PATH,
            self.OCR_REC_MODEL_PATH,
            self.OCR_ORI_MODEL_PATH,
            self.OCR_DOC_MODEL_PATH
        ]
        for path in paths:
            if not os.path.exists(path):
                return False
        return True
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # 忽略未定义的环境变量


# 单例实例
settings = Settings()





