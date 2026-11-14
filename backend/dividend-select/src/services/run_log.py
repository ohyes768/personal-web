"""Hermes 分析尝试台账：按股票记录最近一次尝试（成功 / 失败 / 取消）。

失败的尝试也要留下 run_id —— 界面靠它下载失败那次的会话记录（markdown）。
成功的尝试与评分 / 估值文件里的 run_id 一致；取消按「取消」留存，不当作失败。
服务重启后内存队列清空，这个文件是失败会话记录唯一的持久来源。
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from src.utils.atomic_file import atomic_write
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

STATE_COMPLETED = "completed"
STATE_FAILED = "failed"
STATE_CANCELLED = "cancelled"


class RunLog:
    """按股票代码保留最近一次分析尝试的台账（JSON 文件，原子写）。"""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self._entries = self._load()
        # 失败索引：只保留最近一次尝试失败的股票，合并查询走这里（通常很少）
        self._failed = {code: entry for code, entry in self._entries.items()
                        if entry.get("state") == STATE_FAILED}

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(code): entry for code, entry in data.items() if isinstance(entry, dict)}

    def record(self, code: str, *, state: str, run_id: str | None = None, name: str | None = None,
               error: str | None = None, attempt_id: str | None = None, queued_at: str | None = None,
               started_at: str | None = None, finished_at: str | None = None,
               updated_at: str | None = None) -> None:
        """写入一次尝试的终态；同一只股票只保留最近一次。"""
        entry = {
            "code": code,
            "name": name,
            "state": state,
            "run_id": run_id,
            "error": error,
            "attempt_id": attempt_id,
            "queued_at": queued_at,
            "started_at": started_at,
            "finished_at": finished_at,
            "updated_at": updated_at or finished_at,
        }
        with self._lock:
            self._entries[code] = entry
            if state == STATE_FAILED:
                self._failed[code] = entry
            else:
                self._failed.pop(code, None)
            try:
                encoded = json.dumps(self._entries, ensure_ascii=False, allow_nan=False)
                atomic_write(self.path, lambda p: p.write_text(encoded, encoding="utf-8"))
            except (OSError, ValueError):
                logger.exception("分析台账写入失败 %s", code)

    def failed_entries(self) -> dict[str, dict]:
        """最近一次尝试是失败的记录（按股票代码）。"""
        with self._lock:
            return {code: dict(entry) for code, entry in self._failed.items()}
