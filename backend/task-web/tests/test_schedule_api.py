"""排期日历测试：月度聚合口径 + 单日计划/实际槽来源规则（design.md §7）。"""
from __future__ import annotations

from datetime import datetime

from src import db


def _mk_run(task_id, *, scheduled_at=None, started_at=None, finished_at=None,
            trigger="scheduled", status="success", missed_schedule_at=None,
            duration_ms=1000, exit_code=0):
    run_id = db.new_run_id(task_id)
    db.insert_run({
        "run_id": run_id, "task_id": task_id,
        "scheduled_at": scheduled_at, "started_at": started_at,
        "finished_at": finished_at, "duration_ms": duration_ms,
        "trigger": trigger, "status": status, "exit_code": exit_code,
        "log_path": None, "missed_schedule_at": missed_schedule_at,
    })
    return db.get_run(run_id)


def _day_tasks(date_str, now=None):
    from src.schedule import day_view

    return {t["id"]: t for t in day_view(date_str, now=now)["tasks"]}


# ---------------------------------------------------------------------------
# GET /api/schedule/summary —— 月历按天聚合
# ---------------------------------------------------------------------------

def test_summary_aggregates_by_day(client):
    _mk_run("demo-success", scheduled_at="2026-11-05T09:00:00",
            started_at="2026-11-05T09:00:01", status="success")
    _mk_run("demo-success", scheduled_at="2026-11-05T17:00:00",
            started_at="2026-11-05T17:00:01", status="success")
    _mk_run("demo-failure", scheduled_at="2026-11-05T09:00:00",
            started_at="2026-11-05T09:00:02", status="failed", exit_code=3)
    _mk_run("demo-success", scheduled_at="2026-11-06T09:00:00",
            started_at="2026-11-06T09:00:01", status="success")

    r = client.get("/api/schedule/summary",
                   params={"from": "2026-11-01", "to": "2026-11-30"})
    assert r.status_code == 200
    days = {d["date"]: d for d in r.json()["days"]}
    assert days["2026-11-05"]["total"] == 3
    assert days["2026-11-05"]["success"] == 2
    assert days["2026-11-05"]["failed"] == 1
    assert days["2026-11-06"]["success"] == 1


def test_summary_missed_vs_interrupted(client):
    # 漏执行补记：started_at / scheduled_at 均为空，按 missed_schedule_at 归日
    _mk_run("demo-success", status="interrupted",
            missed_schedule_at="2026-11-04T09:00:00",
            finished_at="2026-11-04T09:02:00")
    # 普通 interrupted（如重启中断）：计入 interrupted，不计入 missed
    _mk_run("demo-failure", trigger="manual", status="interrupted",
            started_at="2026-11-04T12:00:00", finished_at="2026-11-04T12:01:00")

    r = client.get("/api/schedule/summary",
                   params={"from": "2026-11-01", "to": "2026-11-30"})
    day = {d["date"]: d for d in r.json()["days"]}["2026-11-04"]
    assert day["missed"] == 1
    assert day["interrupted"] == 1
    assert day["total"] == 2


def test_summary_bounds_inclusive(client):
    _mk_run("demo-success", scheduled_at="2026-11-01T00:05:00",
            started_at="2026-11-01T00:05:01")
    _mk_run("demo-success", scheduled_at="2026-11-30T23:58:00",
            started_at="2026-11-30T23:58:01")
    r = client.get("/api/schedule/summary",
                   params={"from": "2026-11-01", "to": "2026-11-30"})
    assert [d["date"] for d in r.json()["days"]] == ["2026-11-01", "2026-11-30"]


def test_summary_validates_params(client):
    r = client.get("/api/schedule/summary",
                   params={"from": "2026-11-10", "to": "2026-11-01"})
    assert r.status_code == 400
    r = client.get("/api/schedule/summary",
                   params={"from": "bad", "to": "2026-11-01"})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/schedule/day —— 槽来源规则
# ---------------------------------------------------------------------------

def test_day_past_uses_runs(client):
    """过去日期：以 runs 记录为准；禁用任务也显示历史槽。"""
    _mk_run("demo-success", scheduled_at="2026-11-03T09:00:00",
            started_at="2026-11-03T09:00:01", status="success")
    _mk_run("demo-failure", status="interrupted",
            missed_schedule_at="2026-11-03T09:00:00",
            finished_at="2026-11-03T09:02:00")

    r = client.get("/api/schedule/day", params={"date": "2026-11-03"})
    assert r.status_code == 200
    tasks = {t["id"]: t for t in r.json()["tasks"]}
    s = tasks["demo-success"]
    assert [(x["at"], x["kind"]) for x in s["slots"]] == [
        ("2026-11-03T09:00:00", "run")]
    assert s["slots"][0]["run"]["status"] == "success"
    f = tasks["demo-failure"]
    assert [(x["at"], x["kind"]) for x in f["slots"]] == [
        ("2026-11-03T09:00:00", "run")]
    assert f["slots"][0]["run"]["status"] == "interrupted"
    assert f["slots"][0]["run"]["missed_schedule_at"] == "2026-11-03T09:00:00"


def test_day_future_uses_cron(client):
    """未来日期：以 cron 推算为准；未启用任务保留行但无计划槽。"""
    r = client.put("/api/tasks/demo-success/schedule", json={"enabled": True})
    assert r.status_code == 200

    r = client.get("/api/schedule/day", params={"date": "2026-12-01"})
    tasks = {t["id"]: t for t in r.json()["tasks"]}
    s = tasks["demo-success"]
    assert s["enabled"] is True
    assert [(x["at"], x["kind"]) for x in s["slots"]] == [
        ("2026-12-01T09:00:00", "planned")]
    f = tasks["demo-failure"]
    assert f["enabled"] is False
    assert f["slots"] == []


def test_day_future_multiple_fires(client):
    client.put("/api/tasks/demo-success/schedule",
               json={"enabled": True, "cron": "0 9,22 * * *"})
    r = client.get("/api/schedule/day", params={"date": "2026-12-01"})
    s = next(t for t in r.json()["tasks"] if t["id"] == "demo-success")
    assert [(x["at"], x["kind"]) for x in s["slots"]] == [
        ("2026-12-01T09:00:00", "planned"),
        ("2026-12-01T22:00:00", "planned"),
    ]


def test_day_invalid_cron_marked(client):
    """绕过 API 校验直接写库，模拟历史遗留非法 cron：无未来槽并标记。"""
    db.update_schedule("demo-success", cron="bad-cron", enabled=True)
    r = client.get("/api/schedule/day", params={"date": "2026-12-01"})
    s = next(t for t in r.json()["tasks"] if t["id"] == "demo-success")
    assert s["cron_valid"] is False
    assert s["slots"] == []


def test_day_invalid_params(client):
    r = client.get("/api/schedule/day", params={"date": "not-a-date"})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# 服务层：今天的分界拼接（now 注入，不走 API）
# ---------------------------------------------------------------------------

def test_day_today_splits_at_now(client):
    _mk_run("demo-success", scheduled_at="2026-11-07T09:00:00",
            started_at="2026-11-07T09:00:01", status="success")
    db.update_schedule("demo-success", cron="0 9,22 * * *", enabled=True)
    s = _day_tasks("2026-11-07", now=datetime(2026, 11, 7, 20, 30, 0))["demo-success"]
    assert [(x["at"], x["kind"]) for x in s["slots"]] == [
        ("2026-11-07T09:00:00", "run"),
        ("2026-11-07T22:00:00", "planned"),
    ]


def test_day_today_pending_before_miss_detection(client):
    """已过触发点但暂无 run（漏执行补记 1 分钟窗口内）→ pending。"""
    db.update_schedule("demo-success", cron="0 21 * * *", enabled=True)
    s = _day_tasks("2026-11-07", now=datetime(2026, 11, 7, 21, 0, 30))["demo-success"]
    assert [(x["at"], x["kind"]) for x in s["slots"]] == [
        ("2026-11-07T21:00:00", "pending")]


def test_day_manual_runs_separate(client):
    """手动 run 不占计划槽，进 manual 列表。"""
    _mk_run("demo-success", trigger="manual", status="success",
            started_at="2026-11-07T15:12:00", finished_at="2026-11-07T15:12:30")
    db.update_schedule("demo-success", cron="0 9 * * *", enabled=True)
    s = _day_tasks("2026-11-07", now=datetime(2026, 11, 7, 20, 30, 0))["demo-success"]
    assert [(x["at"], x["kind"]) for x in s["slots"]] == [
        ("2026-11-07T09:00:00", "pending")]
    assert [(m["at"], m["run"]["trigger"]) for m in s["manual"]] == [
        ("2026-11-07T15:12:00", "manual")]


# ---------------------------------------------------------------------------
# 调度器回归：missed_schedule_at 时区格式（naive 统一口径）
# ---------------------------------------------------------------------------

def test_miss_detection_no_false_miss_for_ran_fires(client):
    """回归：手动 run 使扫描窗口回退 24h 后，已成功执行的时刻不得补记为漏执行。"""
    from src.scheduler import TaskScheduler

    db.update_schedule("demo-success", cron="0 6 * * *", enabled=True)
    today = db.now_str()[:10]
    _mk_run("demo-success", scheduled_at=f"{today}T06:00:00",
            started_at=f"{today}T06:00:01")
    _mk_run("demo-success", trigger="manual",
            started_at=f"{today}T07:00:00", finished_at=f"{today}T07:00:01")

    TaskScheduler(timezone="Asia/Shanghai")._detect_missed()
    missed = [r for r in db.list_runs(task_id="demo-success", limit=200)
              if r["missed_schedule_at"]]
    # 06:00 已有成功 run：无论 naive 还是带时区格式都不得补记
    assert all(r["missed_schedule_at"][:16] != f"{today}T06:0" for r in missed)


def test_miss_record_uses_naive_format(client):
    """回归：新补记的 missed_schedule_at 必须是 naive 本地串（19 字符，无时区后缀）。"""
    from src.scheduler import TaskScheduler

    db.update_schedule("demo-success", cron="30 7 * * *", enabled=True)
    TaskScheduler(timezone="Asia/Shanghai")._detect_missed()
    missed = [r for r in db.list_runs(task_id="demo-success", limit=200)
              if r["missed_schedule_at"]]
    assert missed, "应至少补记一次漏执行（无历史 → 24h 窗口）"
    for r in missed:
        assert len(r["missed_schedule_at"]) == 19, r["missed_schedule_at"]


def test_day_legacy_aware_missed_row_dedup(client):
    """回归：修复前误补记的带时区漏执行行与真实 run 同刻时，只显示一个槽。"""
    _mk_run("demo-success", scheduled_at="2026-11-03T09:00:00",
            started_at="2026-11-03T09:00:01", status="success")
    _mk_run("demo-success", status="interrupted",
            missed_schedule_at="2026-11-03T09:00:00+08:00",
            finished_at="2026-11-03T09:05:00")
    s = _day_tasks("2026-11-03")["demo-success"]
    assert [(x["at"], x["kind"]) for x in s["slots"]] == [
        ("2026-11-03T09:00:00", "run")]


def test_miss_detection_stops_at_now(client):
    """回归：漏执行枚举到 now 为止，不得给未来触发点补记。"""
    from src.scheduler import TaskScheduler

    db.update_schedule("demo-success", cron="0 9 * * *", enabled=True)
    TaskScheduler(timezone="Asia/Shanghai")._detect_missed()
    today = db.now_str()[:10]
    missed = [r for r in db.list_runs(task_id="demo-success", limit=500)
              if r["missed_schedule_at"]]
    assert missed, "24h 窗口内应至少补记昨天的漏执行"
    assert all(m["missed_schedule_at"][:10] <= today for m in missed)


def test_day_future_ignores_legacy_missed_rows(client):
    """回归：修复前误补记到未来时刻的漏执行行，不得出现在未来日视图。"""
    db.update_schedule("demo-success", cron="0 9 * * *", enabled=True)
    _mk_run("demo-success", status="interrupted",
            missed_schedule_at="2026-12-01T09:00:00+08:00",
            finished_at="2026-11-07T21:14:00")
    s = _day_tasks("2026-12-01")["demo-success"]
    assert [(x["at"], x["kind"]) for x in s["slots"]] == [
        ("2026-12-01T09:00:00", "planned")]
