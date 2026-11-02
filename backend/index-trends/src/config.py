"""应用配置。所有环境变量带 INDEX_TRENDS_ 前缀。"""
from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_host: str = "0.0.0.0"
    service_port: int = 8100
    data_dir: Path = Path("data")
    # 周报页面链接前缀（如 https://example.com），空则消息不带链接
    public_site_url: str = ""
    # 周报触发时间（Asia/Shanghai），星期字段用英文名
    report_cron: str = "0 19 * * fri"
    daily_refresh_cron: str = "30 16 * * mon-fri"
    # 理杏仁访问令牌（沪深300 PE-TTM 近10年分位）。空则不启用估值采集。
    # 只在后端读取：SecretStr 不出现在 repr、日志、API 响应与数据库里。
    lixinger_token: SecretStr = SecretStr("")

    model_config = SettingsConfigDict(
        env_prefix="INDEX_TRENDS_", env_file=".env", extra="ignore"
    )


def get_settings() -> Settings:
    return Settings()
