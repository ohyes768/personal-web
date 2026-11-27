"""
daily-review 配置
全部走环境变量，默认值仅用于本地开发。
"""
from pathlib import Path

from dotenv import load_dotenv

import os

PROJECT_ROOT = Path(__file__).parent.parent

load_dotenv(PROJECT_ROOT / ".env.local")


def get_server_host() -> str:
    return os.getenv("DAILY_REVIEW_HOST", "0.0.0.0")


def get_server_port() -> int:
    return int(os.getenv("DAILY_REVIEW_PORT", "8103"))


def get_db_path() -> Path:
    return Path(os.getenv("DAILY_REVIEW_DB", PROJECT_ROOT / "data" / "daily-review.sqlite3"))


def get_ingest_token() -> str:
    """ingest 鉴权 token；未配置时 ingest 端点一律 503（fail closed）。"""
    return os.getenv("DAILY_REVIEW_INGEST_TOKEN", "").strip()


def get_dsh_dir() -> Path | None:
    """NAS 本机 ~/.dsh 只读挂载点；为空表示跳过 NAS 本机解析（sync-nas no-op）。"""
    v = os.getenv("DAILY_REVIEW_DSH_DIR", "").strip()
    return Path(v) if v else None


def get_deepseek_api_key() -> str:
    return os.getenv("DEEPSEEK_API_KEY", "").strip()


def get_deepseek_base_url() -> str:
    return os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")


def get_deepseek_model() -> str:
    return os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


def get_deepseek_timeout() -> float:
    """LLM 调用超时秒数。"""
    return float(os.getenv("DEEPSEEK_TIMEOUT", "120"))
