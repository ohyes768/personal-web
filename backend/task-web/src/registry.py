"""
任务登记：tasks.yaml 是唯一任务来源（PRD 决策：预登记制，Web 端不能新增任意命令）。

yaml 格式：
tasks:
  - id: a-stock-push
    name: A股新股通知
    description: ...
    command: bash run_a_stock.sh
    cwd: stock-info-dingding        # 相对 workspace root；空 = 不切目录
    group: ai                       # script(默认) | ai
    skills: [gold-price-brief]      # 涉及的 Hermes skill 名（可多个，仅页面展示用）
    cron: "0 9 * * *"               # 默认计划（导入后可在页面改）
    timeout: 600
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import json

import yaml

from . import db
from .config import get_tasks_yaml

logger = logging.getLogger("task-web.registry")

VALID_ENGINES = ("shell", "docker")
# 分组原则：script=纯脚本实现（维护在 stock-info-dingding）；ai=用到 AI 能力
# （Hermes skill 实现，task-web 只管触发时间；或脚本内置 LLM 调用）
VALID_GROUPS = ("script", "ai")
_LEGACY_GROUPS = {"hermes": "ai"}  # 旧值兼容
# 输出目的（多选）：钉钉 / 微信 / RSS 中转服务
VALID_TARGETS = ("dingtalk", "wechat", "rss", "web")
# 涉及的 skill 名：Hermes skill 目录名（如 gold-price-brief）。只允许目录名安全字符，
# 免得写进 yaml 的是说明文字/路径，页面上展示出来也没法对应到真实 skill。
_SKILL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]*$")


def _parse_skills(raw) -> list[str] | None:
    """skills: [gold-price-brief, dingtalk-push] 或 "gold-price-brief,dingtalk-push"。

    纯 prompt 驱动的 AI 任务（Hermes job 的 skill=None）不写该字段 → None。
    """
    if raw is None or raw == "" or raw == []:
        return None
    if isinstance(raw, str):
        items = [s.strip() for s in raw.split(",")]
    elif isinstance(raw, list):
        items = [str(s).strip() for s in raw]
    else:
        raise ValueError(f"skills 必须是字符串或字符串列表: {raw!r}")
    items = [s for s in items if s]
    for name in items:
        if not _SKILL_NAME_RE.match(name):
            raise ValueError(f"skills 条目非法（应为 skill 目录名，如 gold-price-brief）: {name!r}")
    return items or None


def _parse_volumes(raw) -> list[str] | None:
    """volumes: ['宿主:容器', '宿主:容器:rw|ro']；登记时即校验，避免运行期才炸。"""
    if not raw:
        return None
    if not isinstance(raw, list):
        raise ValueError(f"volumes 必须是字符串列表: {raw!r}")
    for item in raw:
        parts = str(item).split(":")
        if len(parts) not in (2, 3) or not parts[0] or not parts[1]:
            raise ValueError(f"volumes 条目非法（应为 宿主路径:容器路径[:rw|ro]）: {item!r}")
        if len(parts) == 3 and parts[2] not in ("rw", "ro"):
            raise ValueError(f"volumes 挂载模式只支持 rw/ro: {item!r}")
    return [str(v) for v in raw]


def load_registry() -> list[dict]:
    path: Path = get_tasks_yaml()
    if not path.exists():
        logger.warning("tasks.yaml 不存在: %s", path)
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    tasks = data.get("tasks") or []
    seen: set[str] = set()
    for t in tasks:
        if not t.get("id") or not t.get("command"):
            raise ValueError(f"tasks.yaml 条目缺少 id 或 command: {t}")
        if t["id"] in seen:
            raise ValueError(f"tasks.yaml 重复 id: {t['id']}")
        seen.add(t["id"])
    return tasks


def sync_registry() -> list[str]:
    """把 tasks.yaml 同步进 DB：登记任务 + 首次创建 schedule（默认禁用）。
    返回登记的任务 id 列表。已存在的 schedule（用户改过的 cron/启停）不覆盖。"""
    ids: list[str] = []
    for t in load_registry():
        engine = t.get("engine", "shell")
        if engine not in VALID_ENGINES:
            raise ValueError(f"任务 {t['id']} engine 非法: {engine}（可选 {VALID_ENGINES}）")
        env = t.get("env") or {}
        volumes = _parse_volumes(t.get("volumes"))
        group = _LEGACY_GROUPS.get(t.get("group") or "script") or (t.get("group") or "script")
        if group not in VALID_GROUPS:
            raise ValueError(f"任务 {t['id']} group 非法: {group}（可选 {VALID_GROUPS}）")
        targets = t.get("targets") or []
        if not isinstance(targets, list) or any(x not in VALID_TARGETS for x in targets):
            raise ValueError(f"任务 {t['id']} targets 非法: {targets}（可选 {VALID_TARGETS}，可多选）")
        skills = _parse_skills(t.get("skills"))
        prompt = t.get("prompt")
        prompt = prompt.strip() if isinstance(prompt, str) and prompt.strip() else None
        db.upsert_task({
            "id": t["id"],
            "name": t.get("name", t["id"]),
            "description": t.get("description", ""),
            "command": t["command"],
            "cwd": t.get("cwd", ""),
            "default_cron": t.get("cron", ""),
            "default_timeout": int(t.get("timeout", 600)),
            "engine": engine,
            "image": t.get("image"),
            "env_file": t.get("env_file"),
            "env": json.dumps(env, ensure_ascii=False) if env else None,
            "volumes": json.dumps(volumes, ensure_ascii=False) if volumes else None,
            "network": t.get("network") or None,
            "run_user": t.get("user") or None,
            "group_name": group,
            "targets": json.dumps(targets, ensure_ascii=False),
            "skills": json.dumps(skills, ensure_ascii=False) if skills else None,
            "prompt": prompt,
        })
        db.ensure_schedule(t["id"], t.get("cron", ""), int(t.get("timeout", 600)))
        ids.append(t["id"])
    # 登记修剪：yaml 里已移除的任务清理出库（运行历史保留，仅删任务与调度）
    known = set(ids)
    existing = {t["id"] for t in db.list_tasks()}
    for gone in existing - known:
        db.delete_task(gone)
        logger.info("登记修剪：移除已不在 tasks.yaml 的任务 %s", gone)
    return ids
