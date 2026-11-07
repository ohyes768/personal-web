"""
排期日历服务层（只读）：月度按天聚合 + 单日计划/实际槽视图。不改表。

槽来源规则（design.md §2.2）：
- 过去日期：以 runs 记录为准（trigger=scheduled 的 scheduled_at ∪ 漏执行补记
  missed_schedule_at）——cron 可能改过，历史以实际记录为准；
- 未来日期：以 CronTrigger 推算为准（仅 enabled 且 cron 合法的任务）；
- 今天：以 now 为分界拼接；已过触发点但暂无 run 记 → pending
  （漏执行检测每分钟 tick 补记前 ≤1 分钟的窗口）。

时间戳沿用库内 naive 本地字符串（Asia/Shanghai 单机），日期边界用字符串比较。
runs 归日口径：COALESCE(scheduled_at, started_at, missed_schedule_at)，
即 scheduled 触发按计划日归属、manual 按开始日、补记按漏执行时刻。
"""
from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger

from . import db
from .config import get_timezone

# 与前端 statusLabel/statusColor 对齐的七种状态
STATUSES = ("waiting", "running", "success", "failed",
            "timeout", "interrupted", "skipped")

# cron 枚举防御性上限（与 scheduler._detect_missed 一致）
MAX_FIRES = 200


def _parse_date(value: str, name: str) -> date_cls:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValueError(f"{name} 需为 YYYY-MM-DD 格式: {value!r}")


# ---------------------------------------------------------------------------
# 月度聚合
# ---------------------------------------------------------------------------

def summary_days(from_str: str, to_str: str) -> list[dict]:
    d_from = _parse_date(from_str, "from")
    d_to = _parse_date(to_str, "to")
    if d_from > d_to:
        raise ValueError("from 不能晚于 to")
    agg: dict[str, dict] = {}
    for r in db.summary_rows(f"{from_str}T00:00:00", f"{to_str}T23:59:59"):
        day = agg.setdefault(
            r["d"], {"date": r["d"], "total": 0, "missed": 0,
                     **{s: 0 for s in STATUSES}})
        day[r["status"]] += r["n"]
        day["total"] += r["n"]
        if r["missed"]:
            day["missed"] += r["missed"]
            # 漏执行补记也是 interrupted 状态：interrupted 桶扣除 missed，避免重复计数
            day["interrupted"] = max(0, day["interrupted"] - r["missed"])
    return [agg[k] for k in sorted(agg)]


# ---------------------------------------------------------------------------
# 单日槽视图
# ---------------------------------------------------------------------------

def day_view(date_str: str, now: datetime | None = None) -> dict:
    d = _parse_date(date_str, "date")
    now = now or datetime.now()
    today = now.date()
    day = d.isoformat()

    runs_by_task: dict[str, list[dict]] = {}
    for r in db.day_runs(f"{day}T00:00:00", f"{day}T23:59:59"):
        runs_by_task.setdefault(r["task_id"], []).append(r)

    tz = ZoneInfo(get_timezone())
    tasks_out: list[dict] = []
    for t in db.list_tasks():
        runs = runs_by_task.get(t["id"], [])
        cron = t.get("cron") or ""
        enabled = bool(t.get("enabled"))
        trigger = None
        cron_valid = bool(cron)
        if cron:
            try:
                trigger = CronTrigger.from_crontab(cron, timezone=str(tz))
            except ValueError:
                cron_valid = False

        slots, matched = _build_slots(t, runs, d, today, now, tz, trigger, enabled)
        manual = [
            {"at": r["started_at"] or r["scheduled_at"] or "", "run": r}
            for r in runs if r["trigger"] == "manual"
        ]
        slots.sort(key=lambda s: s["at"])
        manual.sort(key=lambda m: m["at"])
        tasks_out.append({
            "id": t["id"],
            "name": t["name"],
            "group": t.get("group_name") or "script",
            "cron": cron,
            "enabled": enabled,
            "cron_valid": cron_valid,
            "slots": slots,
            "manual": manual,
        })
    return {"date": day, "tasks": tasks_out}


def _build_slots(t: dict, runs: list[dict], d: date_cls, today: date_cls,
                 now: datetime, tz: ZoneInfo, trigger: CronTrigger | None,
                 enabled: bool) -> tuple[list[dict], set[str]]:
    """返回 (槽列表, 已被槽占用的 run_id 集合)。manual run 不占槽。"""
    slots: list[dict] = []
    matched: set[str] = set()

    if d < today:
        # 过去：runs 为准（scheduled 触发 + 漏执行补记），与 enabled 无关；
        # 同一计划时刻多条记录（如修复前误补记的假漏执行）只画一个槽
        seen: set[str] = set()
        for r in runs:
            if r["trigger"] == "scheduled" or r.get("missed_schedule_at"):
                at = r["scheduled_at"] or db.naive_local(r["missed_schedule_at"])
                if at and at not in seen:
                    seen.add(at)
                    slots.append({"at": at, "kind": "run", "run": r})
                    matched.add(r["run_id"])
        return slots, matched

    if trigger is None:
        return slots, matched

    # 今天 / 未来：cron 枚举为准，runs 挂靠。
    # 未来时刻不可能已有执行或补记：修复前枚举 bug 写入的"未来漏执行"行在此过滤。
    now_str = now.isoformat(timespec="seconds")

    def _row_at(r: dict) -> str | None:
        return r["scheduled_at"] or db.naive_local(r["missed_schedule_at"])

    past_runs = [r for r in runs if (_at := _row_at(r)) and _at <= now_str]
    for fire in _enumerate_fires(trigger, d, tz):
        f_str = fire.replace(tzinfo=None).isoformat(timespec="seconds")
        hit = _match_run(past_runs, matched, f_str)
        if hit is not None:
            matched.add(hit["run_id"])
            slots.append({"at": f_str, "kind": "run", "run": hit})
        elif fire.replace(tzinfo=None) > now:
            if enabled:
                slots.append({"at": f_str, "kind": "planned"})
        else:
            slots.append({"at": f_str, "kind": "pending"})
    # cron 改过导致不落在枚举点上的历史触发，补进槽列表（同刻去重）
    existing = {s["at"] for s in slots}
    for r in past_runs:
        if r["run_id"] in matched:
            continue
        at = _row_at(r)
        if (r["trigger"] == "scheduled" or r.get("missed_schedule_at")) \
                and at and at not in existing:
            existing.add(at)
            slots.append({"at": at, "kind": "run", "run": r})
            matched.add(r["run_id"])
    return slots, matched


def _match_run(runs: list[dict], matched: set[str], f_str: str) -> dict | None:
    """与 scheduler._has_run_for_schedule 相同的匹配规则（补记归一为 naive）。"""
    for r in runs:
        if r["run_id"] in matched:
            continue
        if db.naive_local(r.get("missed_schedule_at")) == f_str:
            return r
        if r.get("trigger") == "scheduled" and r.get("scheduled_at") == f_str:
            return r
    return None


def _enumerate_fires(trigger: CronTrigger, d: date_cls, tz: ZoneInfo) -> list[datetime]:
    day_start = datetime.combine(d, dtime.min, tzinfo=tz)
    day_end = datetime.combine(d, dtime(23, 59, 59), tzinfo=tz)
    fires: list[datetime] = []
    cur: datetime | None = None
    for _ in range(MAX_FIRES):
        nxt = trigger.get_next_fire_time(cur, cur if cur is not None else day_start)
        if nxt is None or nxt > day_end:
            break
        fires.append(nxt)
        cur = nxt
    return fires
