"""
配置加载工具（端口等不硬编码，读环境变量）
"""
import os
from pathlib import Path

# 项目根目录（backend/）
PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = PROJECT_ROOT / "cache"

DEFAULT_SERVER_HOST = "0.0.0.0"
DEFAULT_SERVER_PORT = 8095
DEFAULT_DATABASE_URL = f"sqlite:///{(DATA_DIR / 'funds.db').as_posix()}"
DEFAULT_LOG_LEVEL = "INFO"


def get_server_host() -> str:
    return os.getenv("SERVER_HOST", DEFAULT_SERVER_HOST)


def get_server_port() -> int:
    return int(os.getenv("SERVER_PORT", str(DEFAULT_SERVER_PORT)))


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def get_log_level() -> str:
    return os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL)


def get_funds_config_path() -> Path:
    return CONFIG_DIR / "funds.yaml"


def get_stock_funds_config_path() -> Path:
    """股票基金配置（股票型 + QDII，与债基并列的 demo 名额）

    与 funds.yaml 同结构 (version + funds)，由 refresh_stock_funds_sync 读取。
    """
    return CONFIG_DIR / "funds_stock.yaml"
