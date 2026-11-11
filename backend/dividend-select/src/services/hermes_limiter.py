"""Hermes 跨 service 全局并发闸：quality + valuation 合计 ≤ HERMES_MAX_CONCURRENT。

背景：两个编排服务此前各自用 HERMES_MAX_CONCURRENT 限流，RefreshJobManager 执行器
（max_workers=2）允许两类 job 并行，对同一 Hermes profile 的实际并发是 2×limit。
本限流器在进程内共享，让配置回归字面语义。单进程部署，进程内信号量足够。

接入方式：main.py 构造一个实例注入两个 service；测试可传 None（不限流）或自行
构造小 limit 实例。acquire/release 必须在编排服务的锁外调用，覆盖「提交 run →
轮询到终态」整段，异常路径由调用方 finally 释放。
"""
from __future__ import annotations

import os
import threading


class HermesLimiter:
    """BoundedSemaphore + 活跃计数（供测试与观测）。"""

    def __init__(self, limit: int):
        self._limit = max(1, int(limit))
        self._sem = threading.BoundedSemaphore(self._limit)
        self._lock = threading.Lock()
        self._active = 0

    @classmethod
    def from_env(cls) -> "HermesLimiter":
        return cls(int(os.environ.get("HERMES_MAX_CONCURRENT", "1")))

    @property
    def limit(self) -> int:
        return self._limit

    @property
    def active(self) -> int:
        """当前持有名额的 run 数（观测用）。"""
        with self._lock:
            return self._active

    def acquire(self, timeout: float | None = None) -> bool:
        """获取一个全局名额；timeout 内拿不到返回 False。"""
        acquired = self._sem.acquire(timeout=timeout) if timeout is not None else self._sem.acquire()
        if acquired:
            with self._lock:
                self._active += 1
        return acquired

    def release(self) -> None:
        with self._lock:
            if self._active <= 0:
                return  # 防御：不过度释放（BoundedSemaphore 会抛 ValueError）
            self._active -= 1
        self._sem.release()
