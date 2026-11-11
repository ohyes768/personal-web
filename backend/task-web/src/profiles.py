"""Hermes profile 解析：登记推导 + 用户覆盖（DB）+ 执行期应用。

一个 profile 绑定两件事，切换时必须一起换，否则「选了不生效」：

1. 凭证 env_file（BASE_URL / API_KEY 属于哪个网关）；
2. 容器内环境变量 `HERMES_PROFILE`（Runs API 前缀 `/p/<profile>/`）。

（2026-11-11 起 jobs.json 挂载改写已随触发脚本回退一并移除：prompt 唯一来源
是 task-web 登记，profile 切换与 Hermes 侧 cron job 无关。）

profile 目录见 `config.get_hermes_profiles()`；每个任务的生效 profile 优先级：
用户在页面设置的覆盖值（存在 `task_overrides` 表，tasks.yaml 同步不会覆盖）
> tasks.yaml 登记推导（env 显式 HERMES_PROFILE > env_file 与 profile 目录匹配）。
"""
from __future__ import annotations

import json
from pathlib import Path

from .config import get_hermes_profiles

PROFILE_ENV_KEY = "HERMES_PROFILE"
AI_GROUP = "ai"


def catalog() -> dict[str, dict]:
    """profile 目录（name → {label, env_file}）。"""
    return get_hermes_profiles()


def is_ai_task(task: dict) -> bool:
    return (task.get("group_name") or "script") == AI_GROUP


def _task_env_dict(task: dict) -> dict:
    raw = task.get("env")
    if not raw:
        return {}
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def registered_profile(task: dict) -> str | None:
    """tasks.yaml 登记推导的 profile（非 AI 任务恒为 None）。

    - env 显式 `HERMES_PROFILE` → 该值（防漂移，显式声明优先）；
    - env_file 与某 profile 的 env_file 完全一致 / 同名（如 `.env.hermes-default`）
      → 该 profile；
    - 其余（非 Hermes 触发的 AI 任务 / 脚本任务）→ None。
    """
    if not is_ai_task(task):
        return None
    explicit = _task_env_dict(task).get(PROFILE_ENV_KEY)
    if explicit:
        return str(explicit)
    env_file = task.get("env_file") or ""
    if not env_file:
        return None
    cat = catalog()
    for name, cfg in cat.items():
        target = cfg.get("env_file")
        if not target:
            continue
        if env_file == target or Path(env_file).name == Path(target).name:
            return name
    return None


def effective_profile(task: dict, override: str | None = None) -> str | None:
    """生效 profile：用户覆盖 > 登记推导；覆盖值必须是目录内已知 profile。"""
    if not is_ai_task(task):
        return None
    if override and override in catalog():
        return override
    return registered_profile(task)


def profile_source(task: dict, override: str | None = None) -> str | None:
    """生效 profile 的来源：override（页面设置）/ registry（tasks.yaml 登记）/ None。"""
    if not is_ai_task(task):
        return None
    if override and override in catalog():
        return "override"
    return "registry" if registered_profile(task) else None
