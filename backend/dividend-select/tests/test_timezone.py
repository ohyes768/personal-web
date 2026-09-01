"""last_updated / 文件 mtime 必须带北京时区偏移（+08:00）

容器默认 UTC 时 datetime.fromtimestamp().isoformat() 会写成 naive UTC
（盘后 15:30 变成 07:30），前端再当本地时间显示就会慢 8 小时。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.api.helpers.aux_data import file_mtime_iso
from src.utils.timezone import fromtimestamp_shanghai_iso, now_shanghai_iso

# 2026-09-01 07:30:00 UTC = 北京 15:30（盘后刷新）
_UTC_0730 = datetime(2026, 9, 1, 7, 30, tzinfo=timezone.utc)
_EPOCH = _UTC_0730.timestamp()


def test_fromtimestamp_shanghai_iso_has_plus_08_and_beijing_wall_clock():
    iso = fromtimestamp_shanghai_iso(_EPOCH)
    dt = datetime.fromisoformat(iso)
    assert dt.tzinfo is not None, f"缺少时区: {iso}"
    assert dt.utcoffset() == timedelta(hours=8)
    assert dt.hour == 15 and dt.minute == 30


def test_now_shanghai_iso_has_plus_08_offset():
    iso = now_shanghai_iso()
    dt = datetime.fromisoformat(iso)
    assert dt.tzinfo is not None
    assert dt.utcoffset() == timedelta(hours=8)


def test_file_mtime_iso_is_beijing_even_if_process_tz_is_utc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """进程 TZ=UTC 时，mtime ISO 仍应是北京 15:30+08:00，不能写成 naive 07:30。"""
    monkeypatch.setenv("TZ", "UTC")
    target = tmp_path / "实时价格.csv"
    target.write_text("code\n000001\n", encoding="utf-8")
    target.touch()
    # utime 的 ns/秒是 UTC epoch，与进程 TZ 无关
    import os

    os.utime(target, (_EPOCH, _EPOCH))

    iso = file_mtime_iso(target)
    assert iso is not None
    dt = datetime.fromisoformat(iso)
    assert dt.tzinfo is not None, f"mtime ISO 缺少时区: {iso}"
    assert dt.utcoffset() == timedelta(hours=8)
    assert (dt.hour, dt.minute) == (15, 30), f"应为北京 15:30，实际 {iso}"
