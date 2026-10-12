"""Snapshot continuity across week/month/year changes, without network calls."""
import json
import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
import pandas as pd
from apscheduler.triggers.cron import CronTrigger

from src.services.m120_service import M120Service


def snapshot(root, month, suffix, content="日期,股票代码,M120\n2026-10-11,000001,12.5\n"):
    path = root / month / f"M120均线_{suffix}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8-sig")
    return path


@pytest.fixture
def service(tmp_path):
    with patch("src.services.m120_service.DATA_DIR", tmp_path), patch(
        "src.services.base.get_current_date_dir", return_value="2026-10"
    ), patch("src.services.base.datetime") as clock:
        clock.now.return_value = datetime(2026, 10, 12)
        yield M120Service(), tmp_path


@pytest.mark.parametrize("month,suffix", [
    ("2026-10", "10-05-10-11"),
    ("2026-09", "09-28-10-04"),
    ("2025-12", "12-29-01-04"),
])
def test_reads_previous_snapshot_across_boundaries(service, month, suffix):
    svc, root = service
    previous = snapshot(root, month, suffix)
    assert svc.read_m120_data() == {"000001": {"m120": 12.5}}
    assert svc.read_m120_with_deviation()["000001"]["m120"] == 12.5
    assert svc.check_m120_file_exists()
    assert svc.get_m120_file_mtime() == previous.stat().st_mtime
    assert svc.M120_CSV_FILE == root / "2026-10" / "M120均线_10-12-10-18.csv"


@pytest.mark.parametrize("content", ["", "unexpected\nvalue\n", "日期,股票代码,M120\n", "日期,股票代码,M120\n2026-10-12,000001,nan\n"])
def test_invalid_current_snapshot_does_not_hide_previous(service, content):
    svc, root = service
    snapshot(root, "2026-10", "10-05-10-11")
    snapshot(root, "2026-10", "10-12-10-18", content)
    assert svc.read_m120_data() == {"000001": {"m120": 12.5}}


def test_current_snapshot_wins_and_future_is_ignored(service):
    svc, root = service
    snapshot(root, "2026-10", "10-05-10-11")
    snapshot(root, "2026-10", "10-12-10-18", "日期,股票代码,M120\n2026-10-12,000001,15\n")
    snapshot(root, "2026-10", "10-19-10-25", "日期,股票代码,M120\n2026-10-19,000001,99\n")
    assert svc.read_m120_data() == {"000001": {"m120": 15}}


def test_refresh_creates_current_file_and_preserves_previous(service):
    svc, root = service
    previous = snapshot(root, "2026-10", "10-05-10-11")
    original = previous.read_bytes()
    with patch.object(svc, "_get_m120_from_aliyun", return_value={"m120": 16}):
        assert svc.update_m120_data(["000001"], show_progress=False) == 1
    assert previous.read_bytes() == original
    assert svc.M120_CSV_FILE.exists()
    assert svc.read_m120_data() == {"000001": {"m120": 16}}


def test_no_snapshot_reports_missing(service):
    svc, _ = service
    assert svc.read_m120_data() == {}
    assert not svc.check_m120_file_exists()
    assert svc.get_m120_file_mtime() is None


def test_january_reads_december_week(tmp_path):
    snapshot(tmp_path, "2025-12", "12-29-01-04")
    with patch("src.services.m120_service.DATA_DIR", tmp_path), patch(
        "src.services.base.get_current_date_dir", return_value="2026-01"
    ), patch("src.services.base.datetime") as clock:
        clock.now.return_value = datetime(2026, 1, 5)
        svc = M120Service()
        assert svc.read_m120_data() == {"000001": {"m120": 12.5}}
        assert svc.M120_CSV_FILE.parent.name == "2026-01"


def test_failed_refresh_keeps_previous_snapshot(service):
    svc, root = service
    snapshot(root, "2026-10", "10-05-10-11")
    with patch.object(svc, "_get_m120_from_aliyun", return_value=None):
        assert svc.update_m120_data(["000001"], show_progress=False) == 0
    assert not svc.M120_CSV_FILE.exists()
    assert svc.read_m120_data() == {"000001": {"m120": 12.5}}


def test_status_uses_previous_snapshot_timestamp(service):
    from src.api import routes
    from src.utils.timezone import fromtimestamp_shanghai_iso

    svc, root = service
    previous = snapshot(root, "2026-10", "10-05-10-11")
    with patch.object(routes, "m120_service", svc), patch.object(routes, "data_reader") as reader, patch.object(routes, "filter_service"):
        reader.read_csv.return_value = pd.DataFrame({"股票代码": ["000001"]})
        status = asyncio.run(routes.get_m120_status(min_yield=0))
    assert status["needs_update"] is False
    assert status["last_updated"] == fromtimestamp_shanghai_iso(previous.stat().st_mtime)


def test_weekly_job_really_runs_saturday():
    config = json.loads((Path(__file__).parents[1] / "src/scheduler/scheduler.json").read_text(encoding="utf-8"))
    job = next(j for j in config["jobs"] if j["id"] == "weekly_m120")
    trigger = CronTrigger.from_crontab(job["cron"], timezone="Asia/Shanghai")
    next_run = trigger.get_next_fire_time(None, datetime.fromisoformat("2026-10-12T00:00:00+08:00"))
    assert next_run.isoformat() == "2026-10-17T02:00:00+08:00"
