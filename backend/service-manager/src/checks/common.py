"""统一检查 envelope（design §6 通用状态）。

一条检查结果同时承担两件事：
- check_status：这次请求本身有没有跑完（never/success/error）
- current_state：该维度观测到的状态（各维度自己的枚举）

失败时只更新 last_attempt / error / next_due_at，绝不清除 last_success，
页面据 last_success_at 显示旧值时间并标 stale。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from src.db import Store
from src.models import CheckStatus, CheckView

# stale 阈值：超过 2 个检查周期未成功
STALE_PERIODS = 2

CHECK_KINDS = ("url", "tls", "releases", "docker_scan")


@dataclass
class CheckOutcome:
    check_status: CheckStatus
    current_state: str
    payload: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


class CheckStore:
    """check_results 表读写。"""

    def __init__(self, store: Store) -> None:
        self.store = store

    def record(
        self,
        *,
        target_type: str,
        target_id: str,
        check_kind: str,
        outcome: CheckOutcome,
        interval_seconds: int,
        now: datetime | None = None,
    ) -> None:
        moment = now or _now()
        next_due = moment + timedelta(seconds=max(30, interval_seconds))
        with self.store.transaction() as conn:
            row = conn.execute(
                "SELECT last_success_at, last_success_payload FROM check_results"
                " WHERE target_type = ? AND target_id = ? AND check_kind = ?",
                (target_type, target_id, check_kind),
            ).fetchone()
            payload_json = json.dumps(outcome.payload, ensure_ascii=False)
            if outcome.check_status == CheckStatus.SUCCESS:
                last_success_at = _iso(moment)
                last_success_payload = payload_json
            else:
                last_success_at = row["last_success_at"] if row else None
                last_success_payload = row["last_success_payload"] if row else None
            conn.execute(
                "INSERT INTO check_results(target_type, target_id, check_kind,"
                " check_status, current_state, last_attempt_at, last_success_at,"
                " last_success_payload, error_code, error_message, next_due_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(target_type, target_id, check_kind) DO UPDATE SET"
                " check_status = excluded.check_status,"
                " current_state = excluded.current_state,"
                " last_attempt_at = excluded.last_attempt_at,"
                " last_success_at = excluded.last_success_at,"
                " last_success_payload = excluded.last_success_payload,"
                " error_code = excluded.error_code,"
                " error_message = excluded.error_message,"
                " next_due_at = excluded.next_due_at",
                (
                    target_type,
                    target_id,
                    check_kind,
                    outcome.check_status.value,
                    outcome.current_state,
                    _iso(moment),
                    last_success_at,
                    last_success_payload,
                    outcome.error_code,
                    outcome.error_message,
                    _iso(next_due),
                ),
            )

    def get(
        self, *, target_type: str, target_id: str, check_kind: str
    ) -> CheckView | None:
        with self.store.read() as conn:
            row = conn.execute(
                "SELECT * FROM check_results WHERE target_type = ? AND"
                " target_id = ? AND check_kind = ?",
                (target_type, target_id, check_kind),
            ).fetchone()
        return _row_to_view(row) if row else None

    def list_for(self, *, target_type: str, target_id: str) -> dict[str, CheckView]:
        with self.store.read() as conn:
            rows = conn.execute(
                "SELECT * FROM check_results WHERE target_type = ? AND target_id = ?",
                (target_type, target_id),
            ).fetchall()
        return {row["check_kind"]: _row_to_view(row) for row in rows}

    def all_rows(self, *, target_type: str) -> dict[str, dict[str, CheckView]]:
        with self.store.read() as conn:
            rows = conn.execute(
                "SELECT * FROM check_results WHERE target_type = ?", (target_type,)
            ).fetchall()
        result: dict[str, dict[str, CheckView]] = {}
        for row in rows:
            result.setdefault(row["target_id"], {})[row["check_kind"]] = _row_to_view(row)
        return result

    def clear_target(self, target_type: str, target_id: str) -> None:
        with self.store.transaction() as conn:
            conn.execute(
                "DELETE FROM check_results WHERE target_type = ? AND target_id = ?",
                (target_type, target_id),
            )

    def due(
        self, *, target_type: str, check_kind: str, now: datetime | None = None
    ) -> list[str]:
        """返回已到期（或从未跑过）的 target_id 列表。

        用 last_attempt 判定周期，避免失败后每轮都重试。
        """
        moment = now or _now()
        with self.store.read() as conn:
            rows = conn.execute(
                "SELECT target_id, last_attempt_at, next_due_at FROM check_results"
                " WHERE target_type = ? AND check_kind = ?",
                (target_type, check_kind),
            ).fetchall()
        due: list[str] = []
        for row in rows:
            next_due = row["next_due_at"]
            if not next_due:
                due.append(row["target_id"])
                continue
            parsed = datetime.fromisoformat(next_due)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            if parsed <= moment:
                due.append(row["target_id"])
        return due


def _row_to_view(row) -> CheckView:
    last_success = _parse_dt(row["last_success_at"])
    next_due = _parse_dt(row["next_due_at"])
    stale = False
    if last_success is not None and next_due is not None:
        last_attempt = _parse_dt(row["last_attempt_at"])
        if last_attempt is not None and row["check_status"] == "error":
            # 距上次成功已超过 2 个周期
            period = (next_due - last_attempt).total_seconds()
            if period > 0 and (_now() - last_success).total_seconds() > period * STALE_PERIODS:
                stale = True
    payload = None
    if row["last_success_payload"]:
        try:
            payload = json.loads(row["last_success_payload"])
        except json.JSONDecodeError:
            payload = None
    return CheckView(
        check_kind=row["check_kind"],
        check_status=CheckStatus(row["check_status"]),
        current_state=row["current_state"],
        last_attempt_at=row["last_attempt_at"],
        last_success_at=row["last_success_at"],
        error_code=row["error_code"],
        error_message=row["error_message"],
        next_due_at=row["next_due_at"],
        stale=stale,
        payload=payload,
    )


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
