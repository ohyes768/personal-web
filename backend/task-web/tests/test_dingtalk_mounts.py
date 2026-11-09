"""钉钉脚本任务的公共 CLI 契约：DINGTALK_PUSH_SKILL_DIR 与 /opt/dingtalk-push 挂载成对出现。

背景（2026-11-09）：csi300-brief 盘后推送失败，run 的 .err 是
``ValueError: 未找到公共 dingtalk-push 包：安装后设置 DINGTALK_PUSH_SKILL_DIR 指向其目录``。
3838c73b 批量给 11 条钉钉任务补公共 CLI 时漏了 csi300-brief；而 brief.py 只有在
「当日取数成功且真的要走推送」时才会进 dingtalk_push.delegate → locate_send_script()，
所以漏挂潜伏了两天，直到 11-09 才炸（11-07 那次 run 因为「价格日期不是今天」提前 skipped，
exit 0 是假成功）。

约束只针对直接跑公共 CLI 的脚本任务（group=script）；AI 任务（group=ai）经 Hermes
Runs API 触发，CLI 装在 Hermes 侧，不挂到 stock-info 镜像里。
"""
from __future__ import annotations

import yaml

from src.config import PROJECT_ROOT

TASKS_YAML = PROJECT_ROOT / "tasks.yaml"
CLI_DIR_ENV = "DINGTALK_PUSH_SKILL_DIR"
CLI_MOUNT = "/opt/dingtalk-push"


def _split_volume(spec: str) -> tuple[str, str]:
    """'宿主:容器[:ro|rw]' -> (容器路径, 模式)；格式非法时返回 ("", "")。"""
    parts = str(spec).split(":")
    if len(parts) not in (2, 3):
        return "", ""
    return parts[1], parts[2] if len(parts) == 3 else "rw"


def _script_dingtalk_tasks() -> list[dict]:
    data = yaml.safe_load(TASKS_YAML.read_text(encoding="utf-8")) or {}
    selected = []
    for task in data.get("tasks") or []:
        if task.get("engine", "shell") != "docker":
            continue
        if "dingtalk" not in (task.get("targets") or []):
            continue
        if (task.get("group") or "script") != "script":
            continue
        selected.append(task)
    return selected


def test_registry_has_script_dingtalk_tasks():
    # 防止选择条件写错后测试空跑通过
    assert _script_dingtalk_tasks(), "tasks.yaml 里没有匹配到任何钉钉脚本任务"


def test_each_dingtalk_script_task_pairs_env_and_mount():
    offenders = []
    for task in _script_dingtalk_tasks():
        env = task.get("env") or {}
        volumes = [_split_volume(v) for v in (task.get("volumes") or [])]
        has_env = env.get(CLI_DIR_ENV) == CLI_MOUNT
        has_mount = any(
            container == CLI_MOUNT and mode == "ro" for container, mode in volumes
        )
        if not (has_env and has_mount):
            offenders.append(
                f"{task['id']}(env={CLI_DIR_ENV}:{'有' if has_env else '缺'},"
                f" 挂载:{'有' if has_mount else '缺'})"
            )
    assert not offenders, (
        "钉钉脚本任务的公共 CLI 配置不成对，运行期会 ValueError: "
        + "、".join(offenders)
    )
