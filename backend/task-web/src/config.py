"""
task-web 配置
全部走环境变量，默认值仅用于本地开发。
"""
import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# Hermes profile 目录默认值：与 tasks.yaml 既有约定一致
# （default = gateway 8642；ohyes768 = 8643）。凭证文件在 ~/.hermes 下（NAS 侧
# 从 stock-info checkout 迁出的纯 HERMES_* 键），经 compose 只读挂到 /hermes-home。
_DEFAULT_HERMES_PROFILES: dict[str, dict] = {
    "default": {
        "label": "default 网关（8642）",
        "env_file": "/hermes-home/gw-8642.env",
        "jobs_dir": "/home/ohyes768/.hermes/cron",
    },
    "ohyes768": {
        "label": "ohyes768 网关（8643）",
        "env_file": "/hermes-home/gw-8643.env",
        "jobs_dir": "/home/ohyes768/.hermes/profiles/ohyes768/cron",
    },
}


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


def get_hermes_profiles() -> dict[str, dict]:
    """Hermes profile 目录：name → {label, env_file, jobs_dir}。

    env_file 是该 profile 的凭证来源（BASE_URL/API_KEY 等），jobs_dir 是该 profile
    cron 目录（含 jobs.json 的宿主路径）。TASK_WEB_HERMES_PROFILES 给 JSON 时整体
    覆盖默认值，新增 profile 或换 NAS 路径无需改代码。
    """
    raw = os.getenv("TASK_WEB_HERMES_PROFILES", "").strip()
    if not raw:
        return {name: dict(cfg) for name, cfg in _DEFAULT_HERMES_PROFILES.items()}
    try:
        data = json.loads(raw)
    except ValueError as e:
        raise ValueError(f"TASK_WEB_HERMES_PROFILES 不是合法 JSON: {e}")
    if not isinstance(data, dict) or not data:
        raise ValueError("TASK_WEB_HERMES_PROFILES 必须是 {profile: {env_file, jobs_dir}} 的 JSON 对象")
    profiles: dict[str, dict] = {}
    for name, cfg in data.items():
        if not isinstance(cfg, dict):
            raise ValueError(f"TASK_WEB_HERMES_PROFILES.{name} 必须是对象")
        profiles[str(name)] = {
            "label": cfg.get("label") or str(name),
            "env_file": cfg.get("env_file"),
            "jobs_dir": cfg.get("jobs_dir"),
        }
    return profiles
