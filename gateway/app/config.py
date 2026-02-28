"""
Gateway 配置管理
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """应用配置"""

    # 服务地址配置
    FINANCIAL_SERVICE_URL: str = "http://localhost:8091"
    NEWS_SERVICE_URL: str = "http://localhost:8092"
    DOUYIN_SERVICE_URL: str = "http://localhost:8093"
    DOUYIN_PROCESSOR_URL: str = "http://localhost:8093"

    # Gateway 配置
    APP_NAME: str = "个人资讯 API Gateway"
    APP_VERSION: str = "1.0.0"
    API_PREFIX: str = "/api"

    # 服务器配置
    HOST: str = "0.0.0.0"
    PORT: int = 8080

    # 日志配置
    LOG_LEVEL: str = "INFO"

    # 超时配置
    REQUEST_TIMEOUT: float = 30.0

    # CORS 配置
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8080"]

    class Config:
        env_file = ".env"
        case_sensitive = True


# 全局配置实例
settings = Settings()
