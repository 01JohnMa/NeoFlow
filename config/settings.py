# config/settings.py
"""应用配置管理"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List
import os


class Settings(BaseSettings):
    """应用配置类"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ============ 基础配置 ============
    APP_NAME: str = "NeoFlow"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8080

    # ============ 安全配置 ============
    SECRET_KEY: str = "your-secret-key"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    CRM_API_TOKEN: str = ""

    # ============ Supabase配置 (本地部署) ============
    SUPABASE_URL: str = "http://localhost:8000"
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    # GoTrue 签发的 JWT 密钥（与 supabase/docker-compose.yml 的 JWT_SECRET 一致）。
    # 留空时 API 拒绝所有 Bearer token（fail closed）。
    JWT_SECRET: str = ""
    # Supabase 云项目 JWKS 地址（如 https://<project>.supabase.co/auth/v1/.well-known/jwks.json）。
    # 配置后支持 ES256/RS256 非对称 token；与 JWT_SECRET 按 token alg 自动选择。
    JWKS_URL: str = ""
    DATABASE_URL: Optional[str] = None

    # ============ LLM配置 ============
    LLM_MODEL_ID: str = "deepseek-v4-flash"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.deepseek.com"
    LLM_TEMPERATURE: float = 0.5

    # ============ OpenAI Agents SDK 配置 ============
    SDK_MODEL_ID: str = ""
    SDK_API_KEY: str = ""
    SDK_BASE_URL: str = ""
    SDK_TEMPERATURE: float = 0.2

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
    # 以下两项已废弃，运行时推送目标统一从 Configuration definition
    # 的 feishu.bitable_token / feishu.table_id 读取，不再使用环境变量。
    FEISHU_BITABLE_APP_TOKEN: str = ""  # 已废弃，保留供参考
    FEISHU_BITABLE_TABLE_ID: str = ""   # 已废弃，保留供参考
    FEISHU_PUSH_ENABLED: bool = False

    # ============ 文档处理并发控制 ============
    DOC_PROCESS_MAX_CONCURRENCY: int = 2
    DOC_WORKER_POLL_INTERVAL_SECONDS: float = 2.0
    DOC_WORKER_STALE_LOCK_SECONDS: int = 1800
    DOC_WORKER_ID: str = ""

    # ============ Parse 策略（服务端写死 + 版本号；环境变量可按部署调整） ============
    PARSE_POLICY_VERSION: str = "parse-policy-1"
    PARSE_MAX_FILES_PER_REQUEST: int = 50
    PARSE_MAX_ACTIVE_JOBS_PER_TENANT: int = 30
    PARSE_MAX_TARGET_PAGES: int = 500
    # 水印自动识别阈值：同文本在全文出现 >= 该次数即视为水印（未指定关键词时生效）
    PARSE_WATERMARK_REPEAT_THRESHOLD: int = 3

    # ============ MinerU 解析（#8；key 由本地 .env 提供，不入库） ============
    MINERU_API_KEY: str = ""
    MINERU_BASE_URL: str = "https://mineru.net"
    MINERU_POLL_INTERVAL_SECONDS: float = 5.0
    MINERU_PARSE_TIMEOUT_SECONDS: int = 900

    @property
    def allowed_extensions_list(self) -> List[str]:
        return [ext.strip() for ext in self.ALLOWED_EXTENSIONS.split(",")]

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    @property
    def allowed_hosts_list(self) -> List[str]:
        return [host.strip() for host in self.ALLOWED_HOSTS.split(",")]

# 单例实例
settings = Settings()
