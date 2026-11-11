#!/usr/bin/env python3
"""Hermes AI 任务统一触发器（task-web 调用入口）。

用途：到点给 Hermes 发消息——经 Runs API 提交 prompt 并轮询到终态。

prompt 唯一来源（2026-11-11 起）：env HERMES_PROMPT（task-web 登记注入：
tasks.yaml `prompt:` 字段 → tasks.prompt 列 → executor._task_env）。
缺失即登记配置错误，exit 2。jobs.json 回退与 --job-id 已移除——Hermes 侧
cron job 与 task-web 调度彻底解耦，不再作为 prompt 来源。

接口契约（与 hermes_client.py 同源，实证于生产）：
- POST {base}/p/{profile}/v1/runs   body {"input": prompt}，Bearer + Idempotency-Key
- GET  {base}/p/{profile}/v1/runs/{run_id}  → status/output，终态 completed/failed/cancelled/interrupted

退出码：0=completed；1=run 失败终态；2=配置/提交错误；3=轮询超时。
env：HERMES_PROMPT（必填）/ HERMES_BASE_URL / HERMES_API_KEY / HERMES_PROFILE /
HERMES_POLL_INTERVAL / HERMES_TIMEOUT
API key 只经 env 使用，任何输出不得包含。
"""
from __future__ import annotations

import os
import sys
import time
import uuid

try:
    import requests
except ImportError:  # 允许在无依赖环境明确报错而非误判
    print("缺少依赖 requests：请在 hermes-trigger 镜像内运行", file=sys.stderr)
    sys.exit(2)

HTTP_TIMEOUT = 60
TERMINAL_FAILED = {"failed", "cancelled", "interrupted"}


def submit(base_url: str, api_key: str, profile: str, prompt: str) -> tuple[str, str]:
    url = f"{base_url.rstrip('/')}/p/{profile}/v1/runs".rstrip("/")
    key = uuid.uuid4().hex
    resp = requests.post(
        url,
        json={"input": prompt},
        headers={"Authorization": f"Bearer {api_key}", "Idempotency-Key": key},
        timeout=HTTP_TIMEOUT,
    )
    if not 200 <= resp.status_code < 300:
        raise ValueError(f"提交失败 HTTP {resp.status_code}: {resp.text[:300]}")
    run_id = str(resp.json().get("run_id", ""))
    if not run_id:
        raise ValueError(f"提交响应缺少 run_id: {resp.text[:300]}")
    return run_id, key


def poll(base_url: str, api_key: str, profile: str, run_id: str,
         interval: int, total_timeout: int) -> tuple[str, str]:
    """轮询至终态，返回 (status, output)。"""
    url = f"{base_url.rstrip('/')}/p/{profile}/v1/runs/{run_id}"
    headers = {"Authorization": f"Bearer {api_key}"}
    deadline = time.monotonic() + total_timeout
    while True:
        resp = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT)
        if not 200 <= resp.status_code < 300:
            raise ValueError(f"查询失败 HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        status = str(data.get("status", ""))
        if status == "completed":
            return status, str(data.get("output") or "")
        if status in TERMINAL_FAILED:
            detail = str(data.get("error") or data.get("output") or "")[:500]
            return status, detail
        if time.monotonic() >= deadline:
            raise TimeoutError(f"超过 {total_timeout}s 未完成（最后状态 {status or 'unknown'}）")
        time.sleep(interval)


def main() -> int:
    base_url = os.environ.get("HERMES_BASE_URL", "").rstrip("/")
    api_key = os.environ.get("HERMES_API_KEY", "")
    profile = os.environ.get("HERMES_PROFILE", "ohyes768")
    interval = int(os.environ.get("HERMES_POLL_INTERVAL", "30"))
    total_timeout = int(os.environ.get("HERMES_TIMEOUT", "1800"))
    prompt = os.environ.get("HERMES_PROMPT", "").strip()

    if not prompt:
        print("env 缺失 HERMES_PROMPT：prompt 唯一来源是 task-web 登记"
              "（tasks.yaml `prompt:` 字段），请在该任务的登记里补齐", file=sys.stderr)
        return 2
    if not base_url or not api_key:
        print("env 缺失：HERMES_BASE_URL / HERMES_API_KEY（检查 env_file 注入）", file=sys.stderr)
        return 2

    started = time.strftime("%Y-%m-%dT%H:%M:%S")
    try:
        run_id, _ = submit(base_url, api_key, profile, prompt)
        print(f"[trigger] {started} profile={profile} run_id={run_id} 已提交，轮询中…")
        status, output = poll(base_url, api_key, profile, run_id, interval, total_timeout)
    except TimeoutError as exc:
        print(f"[trigger] {exc}", file=sys.stderr)
        return 3
    except (ValueError, requests.RequestException) as exc:
        print(f"[trigger] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    tail = output[-500:] if output else "(无输出)"
    print(f"[trigger] 终态: {status}\n[trigger] 产出摘要:\n{tail}")
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
