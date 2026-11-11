"""hermes_trigger 触发脚本契约（2026-11-11 起）。

- prompt 唯一来源 = env HERMES_PROMPT（task-web 登记注入），缺失 exit 2；
- 无 CLI 参数：--job-id / --jobs-json 已移除，历史残留参数被忽略（滚动部署兼容）；
- 凭证缺失（HERMES_BASE_URL / HERMES_API_KEY）exit 2。

用 subprocess 直跑脚本验证，不 mock 网络（缺 env 时脚本在网络调用前就退出）。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

TRIGGER = Path(__file__).resolve().parents[1] / "trigger" / "hermes_trigger.py"


def _run(env_overrides: dict[str, str], extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("HERMES_")}
    env.update(env_overrides)
    # Windows 契约（testing-environment.md 同源）：父子进程编码显式钉死 UTF-8，
    # 否则 locale(GBK) 解码中文 stderr 会 UnicodeDecodeError → stderr=None
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(TRIGGER), *(extra_args or [])],
        env=env, capture_output=True, timeout=30,
        encoding="utf-8", errors="replace",
    )


def test_missing_prompt_exits_2():
    """无 HERMES_PROMPT → exit 2，报错指向 task-web 登记（不再回退 jobs.json）。"""
    r = _run({"HERMES_BASE_URL": "http://gw:8642", "HERMES_API_KEY": "k"})
    assert r.returncode == 2
    assert "HERMES_PROMPT" in r.stderr
    assert "tasks.yaml" in r.stderr


def test_missing_credentials_exits_2():
    """有 prompt、无凭证 → exit 2。"""
    r = _run({"HERMES_PROMPT": "汇报一个词：ok"})
    assert r.returncode == 2
    assert "HERMES_BASE_URL" in r.stderr


def test_legacy_cli_args_ignored():
    """历史命令残留 --job-id/--jobs-json 时静默忽略（无 argparse 解析），按 env 判定。"""
    r = _run({"HERMES_PROMPT": "hi"}, extra_args=["--job-id", "deadbeef", "--jobs-json", "/nope"])
    assert r.returncode == 2
    assert "HERMES_BASE_URL" in r.stderr  # 走到凭证校验而非参数报错
