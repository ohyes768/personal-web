"""
task-web 配置
全部走环境变量，默认值仅用于本地开发。
"""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def get_server_host() -> str:
    return os.getenv("TASK_WEB_HOST", "0.0.0.0")


def get_server_port() -> int:
    return int(os.getenv("TASK_WEB_PORT", "8101"))


def get_admin_password() -> str:
    """手动执行密码；未配置时手动执行一律拒绝（fail closed）。"""
    return os.getenv("TASK_WEB_ADMIN_PASSWORD", "")


def get_db_path() -> Path:
    return Path(os.getenv("TASK_WEB_DB_PATH", PROJECT_ROOT / "data" / "taskweb.sqlite3"))


def get_log_dir() -> Path:
    return Path(os.getenv("TASK_WEB_LOG_DIR", PROJECT_ROOT / "data" / "logs"))


def get_tasks_yaml() -> Path:
    return Path(os.getenv("TASK_WEB_TASKS_YAML", PROJECT_ROOT / "tasks.yaml"))


def get_log_retention_days() -> int:
    return int(os.getenv("TASK_WEB_LOG_RETENTION_DAYS", "30"))


def get_timezone() -> str:
    """调度时区，固定上海（PRD 决策）。"""
    return os.getenv("TASK_WEB_TIMEZONE", "Asia/Shanghai")


def get_workspace_root() -> Path | None:
    """业务仓库在容器内的挂载根（cwd 相对路径基于它解析）。"""
    v = os.getenv("TASK_WEB_WORKSPACE_ROOT", "")
    return Path(v) if v else None
