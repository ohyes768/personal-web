"""Hermes Runs API 精简客户端（基本面评级任务用）。

接口契约（同 stock-info-dingding/hermes_client.py）：
- POST {base}/p/{profile}/v1/runs 提交任务（Bearer 鉴权，Idempotency-Key 防重复提交）
- GET {base}/p/{profile}/v1/runs/{run_id} 轮询，终态 completed/failed/cancelled/interrupted

与 dingding 版的差异：评分结果为短 JSON（含 report_md），只走 run.output 交付，
不做共享产物目录 / run 绑定 / 产物校验。
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

import requests

HTTP_TIMEOUT = 60  # 单次 HTTP 请求超时（秒）

TERMINAL_FAILED_STATUSES = {"failed", "interrupted"}


class HermesError(Exception):
    """Hermes 链路错误基类。"""


class HermesApiError(HermesError):
    """HTTP 层错误（非 2xx / 响应结构异常）。"""


class HermesTimeout(HermesError):
    """轮询超过总超时。"""


class HermesRunFailed(HermesError):
    """run 到达失败终态或输出为空。"""


class HermesRunCancelled(HermesRunFailed):
    """run 被 stop 确认后进入 cancelled。轮询超时或 stopping 不是这个结果。"""


@dataclass(frozen=True)
class HermesConfig:
    """Hermes 连接配置（全部来自 env）。"""

    base_url: str
    api_key: str
    profile: str
    poll_interval: int
    timeout: int
    max_concurrent: int

    @classmethod
    def from_env(cls) -> HermesConfig:
        return cls(
            base_url=os.environ.get("HERMES_BASE_URL", "").rstrip("/"),
            api_key=os.environ.get("HERMES_API_KEY", ""),
            profile=os.environ.get("HERMES_PROFILE", "ohyes768"),
            poll_interval=int(os.environ.get("HERMES_POLL_INTERVAL", "30")),
            timeout=int(os.environ.get("HERMES_TIMEOUT", "3600")),
            max_concurrent=int(os.environ.get("HERMES_MAX_CONCURRENT", "4")),
        )

    @property
    def is_configured(self) -> bool:
        """base_url 与 api_key 齐全才算已配置；缺失时上层应拒绝受理 analyze。"""
        return bool(self.base_url and self.api_key)


def _runs_url(cfg: HermesConfig, run_id: str = "") -> str:
    prefix = f"/p/{cfg.profile}" if cfg.profile else ""
    return f"{cfg.base_url}{prefix}/v1/runs/{run_id}".rstrip("/")


def _auth_headers(cfg: HermesConfig, idempotency_key: str = "") -> dict[str, str]:
    headers = {"Authorization": f"Bearer {cfg.api_key}"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def submit_run(cfg: HermesConfig, prompt: str, idempotency_key: str) -> str:
    """提交 run，返回 run_id。网络异常/非 2xx/响应缺 run_id 抛 HermesApiError。"""
    try:
        resp = requests.post(
            _runs_url(cfg),
            json={"input": prompt},
            headers=_auth_headers(cfg, idempotency_key),
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise HermesApiError(f"提交请求异常: {exc}") from exc
    if not 200 <= resp.status_code < 300:
        raise HermesApiError(f"提交失败 HTTP {resp.status_code}: {resp.text[:300]}")
    run_id = str(resp.json().get("run_id", ""))
    if not run_id:
        raise HermesApiError(f"提交响应缺少 run_id: {resp.text[:300]}")
    return run_id


def get_run(cfg: HermesConfig, run_id: str) -> dict:
    """单次查询 run 状态。网络异常或非 2xx 抛 HermesApiError，不把超时当成终态。"""
    try:
        resp = requests.get(_runs_url(cfg, run_id), headers=_auth_headers(cfg), timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        raise HermesApiError(f"查询请求异常: {exc}") from exc
    if not 200 <= resp.status_code < 300:
        raise HermesApiError(f"查询失败 HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    if not isinstance(data, dict):
        raise HermesApiError(f"查询响应不是 JSON 对象: {resp.text[:300]}")
    return data


def stop_run(cfg: HermesConfig, run_id: str) -> str:
    """请求停止运行中的 run。

    官方契约是 POST {base}/p/{profile}/v1/runs/{run_id}/stop，Bearer 鉴权，无请求体。
    HTTP 2xx 且 status=stopping 只表示已受理，执行器仍在跑；终态以随后的 GET 为准
    （cancelled 才是确认停止，completed 表示停之前已经跑完）。4xx/5xx 抛 HermesApiError。
    """
    try:
        resp = requests.post(
            f"{_runs_url(cfg, run_id)}/stop",
            headers=_auth_headers(cfg),
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise HermesApiError(f"停止请求异常: {exc}") from exc
    if not 200 <= resp.status_code < 300:
        raise HermesApiError(f"停止失败 HTTP {resp.status_code}: {resp.text[:300]}")
    try:
        data = resp.json()
    except ValueError as exc:
        raise HermesApiError(f"停止响应不是 JSON: {resp.text[:300]}") from exc
    if not isinstance(data, dict):
        raise HermesApiError(f"停止响应不是 JSON 对象: {resp.text[:300]}")
    status = str(data.get("status") or "")
    # 2xx 且 status=stopping 才是受理；cancelled 仍不是本地成功，调用方继续轮询确认。
    if status not in {"stopping", "cancelled"}:
        raise HermesApiError(f"停止响应未确认受理: {resp.text[:300]}")
    return status


def poll_run(cfg: HermesConfig, run_id: str) -> str:
    """轮询至终态；completed 返回 output，失败终态/空输出抛错，超时抛 HermesTimeout。

    cancelled 抛 HermesRunCancelled（HermesRunFailed 的子类）。stopping / unknown 继续等，
    不能把它们或轮询超时当成已取消。
    """
    deadline = time.monotonic() + cfg.timeout
    while True:
        data = get_run(cfg, run_id)
        status = str(data.get("status", ""))
        if status == "completed":
            output = str(data.get("output") or "")
            if not output:
                raise HermesRunFailed(f"run {run_id} completed 但 output 为空")
            return output
        if status == "cancelled":
            raise HermesRunCancelled(f"run {run_id} 终态 cancelled")
        if status in TERMINAL_FAILED_STATUSES:
            raise HermesRunFailed(f"run {run_id} 终态 {status}")
        if time.monotonic() >= deadline:
            raise HermesTimeout(f"run {run_id} 超过 {cfg.timeout}s 未完成（最后状态 {status or 'unknown'}）")
        time.sleep(cfg.poll_interval)
