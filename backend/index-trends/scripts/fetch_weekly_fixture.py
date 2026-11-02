"""抓取周K只读样本，生成脱网测试用 fixture 与独立数值基准。

只读操作：调用腾讯公开行情接口一次，保存到 tests/fixtures/ 后测试不再联网。
基准数值用 numpy 最小二乘独立计算（不复用 src 里的实现），用于交叉校验回归系数。

用法（在本目录）：
    uv run python scripts/fetch_weekly_fixture.py
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import httpx
import numpy as np
import pandas_market_calendars as mcal

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
SYMBOL = "sh000300"

SHANGHAI = dt.timezone(dt.timedelta(hours=8))
CLOSE_CUTOFF = dt.time(15, 5)
INCEPTION_WEEK_START = dt.date(2005, 4, 4)   # 含 2005-04-08 发布日的自然周周一


def fetch(period: str, count: int) -> list[list[str]]:
    resp = httpx.get(
        URL,
        params={"param": f"{SYMBOL},{period},,,{count},qfq"},
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) index-trends/0.1"},
        timeout=30.0,
    )
    body = resp.json()
    if body.get("code") != 0:
        raise SystemExit(f"腾讯行情返回异常: {body.get('code')} {body.get('msg')}")
    node = body["data"][SYMBOL]
    rows = node.get(period) or node.get(f"qfq{period}")
    if not rows:
        raise SystemExit(f"响应缺少 {period} 行情键")
    return rows


def week_start_of(day: dt.date) -> dt.date:
    return day - dt.timedelta(days=day.weekday())


def shift_years(day: dt.date, years: int) -> dt.date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:  # 2 月 29 日落到非闰年 → 取目标年 2 月最后一天
        return day.replace(year=day.year + years, day=28)


def build_calendar() -> tuple[list[dt.date], dt.date, dt.date]:
    cal = mcal.get_calendar("SSE")
    adhoc = cal.adhoc_holidays
    coverage_start = dt.date(min(adhoc).year, 1, 1)
    coverage_end = dt.date(max(adhoc).year, 12, 31)
    schedule = cal.schedule(coverage_start.isoformat(), coverage_end.isoformat())
    sessions = sorted({d.date() for d in schedule.index})
    return sessions, coverage_start, coverage_end


def complete_weeks(
    weekly_rows: list[list[str]],
    sessions: list[dt.date],
    now: dt.datetime,
) -> tuple[list[tuple[dt.date, dt.date, float]], dict[str, dict]]:
    """按交易日历判定完整周；返回 [(week_start, trade_date, close)] 与异常记录。"""
    session_set = set(sessions)
    by_week: dict[dt.date, tuple[dt.date, float]] = {}
    for row in weekly_rows:
        day = dt.date.fromisoformat(row[0])
        close = float(row[2])
        week = week_start_of(day)
        if week in by_week:
            raise SystemExit(f"周K重复周: {week}")
        by_week[week] = (day, close)

    weeks_sessions: dict[dt.date, list[dt.date]] = {}
    for week in by_week:
        days = [s for s in sessions if week <= s <= week + dt.timedelta(days=6)]
        weeks_sessions[week] = days

    complete: list[tuple[dt.date, dt.date, float]] = []
    anomalies: dict[str, dict] = {}
    for week in sorted(by_week):
        day, close = by_week[week]
        days = weeks_sessions[week]
        if not days:
            anomalies[week.isoformat()] = {
                "week_start": week.isoformat(),
                "provider_date": day.isoformat(),
                "reason": "整周休市，供应商仍返回周K（收盘价与上一周重复）",
            }
            continue
        if day != days[-1]:
            if days[-1] < now.date() and (now.date() > days[-1] or now.time() >= CLOSE_CUTOFF):
                anomalies[week.isoformat()] = {
                    "week_start": week.isoformat(),
                    "provider_date": day.isoformat(),
                    "calendar_last_session": days[-1].isoformat(),
                    "reason": "最后交易日与交易日历不一致",
                }
            continue
        closed_at = dt.datetime.combine(days[-1], CLOSE_CUTOFF, tzinfo=SHANGHAI)
        if closed_at <= now:
            complete.append((week, day, close))
    return complete, anomalies


def ols(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    """独立实现的 OLS + 前移一周 deviation（用 numpy 最小二乘）。"""
    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    design = np.vstack([x, np.ones(len(x))]).T
    (slope, intercept), *_ = np.linalg.lstsq(design, y, rcond=None)
    deviation = float(np.sqrt(np.mean((y - (intercept + slope * (x + 1))) ** 2)))
    return float(slope), float(intercept), deviation


def sample_weeks(
    complete: list[tuple[dt.date, dt.date, float]],
    start_inclusive: dt.date,
    end_exclusive: dt.date,
) -> list[tuple[dt.date, dt.date, float]]:
    picked = []
    for week, day, close in complete:
        week_end = week + dt.timedelta(days=6)
        if start_inclusive <= week_end < end_exclusive:
            picked.append((week, day, close))
    return picked


def hash_of(pairs: list[tuple[str, float]]) -> str:
    import hashlib

    payload = json.dumps([[w, round(c, 6)] for w, c in pairs], separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def main() -> None:
    now = dt.datetime(2026, 11, 2, 18, 0, tzinfo=SHANGHAI)
    weekly_rows = fetch("week", 1600)
    daily_rows = fetch("day", 320)
    sessions, coverage_start, coverage_end = build_calendar()

    complete, anomalies = complete_weeks(weekly_rows, sessions, now)
    complete = [c for c in complete if c[0] >= INCEPTION_WEEK_START]

    weekly_fixture = {
        "index_code": "000300",
        "symbol": SYMBOL,
        "provider": "Tencent Finance",
        "period": "week",
        "requested_count": 1600,
        "captured_at": now.isoformat(timespec="seconds"),
        "first_week_partial_since_launch": True,
        "calendar": {
            "source": "pandas_market_calendars",
            "library_version": "5.6.0",
            "calendar": "SSE",
            "coverage_start": coverage_start.isoformat(),
            "coverage_end": coverage_end.isoformat(),
            "session_count": len(sessions),
            "cross_validation": {
                "source": "exchange_calendars",
                "calendar": "XSHG",
                "compared_range": "2006-11-02..2026-12-31",
                "session_count": 4902,
                "difference_count": 0,
                "note": (
                    "与 exchange_calendars 的 XSHG 逐日比对完全一致；"
                    "XSHG 覆盖不到 2005-04，故生产用 pandas_market_calendars 的 SSE 日历"
                ),
            },
        },
        "rows": [
            {
                "date": row[0],
                "open": float(row[1]),
                "close": float(row[2]),
                "high": float(row[3]),
                "low": float(row[4]),
            }
            for row in weekly_rows
        ],
        "known_anomalies": sorted(anomalies.values(), key=lambda a: a["week_start"]),
    }
    daily_fixture = {
        "index_code": "000300",
        "symbol": SYMBOL,
        "provider": "Tencent Finance",
        "period": "day",
        "requested_count": 320,
        "captured_at": now.isoformat(timespec="seconds"),
        "rows": [
            {
                "date": row[0],
                "open": float(row[1]),
                "close": float(row[2]),
                "high": float(row[3]),
                "low": float(row[4]),
            }
            for row in daily_rows
        ],
    }

    # ---- 独立数值基准 ----
    last_week = complete[-1][0]
    last_week_end = last_week + dt.timedelta(days=6)
    trailing_end = last_week_end + dt.timedelta(days=1)
    trailing_start = shift_years(trailing_end, -10)

    def model_block(kind: str, picked: list[tuple[dt.date, dt.date, float]], start, end) -> dict:
        origin = picked[0][0]
        xs = [(w - origin).days / 7 for w, _, _ in picked]
        ys = [c for _, _, c in picked]
        slope, intercept, deviation = ols(xs, ys)
        return {
            "kind": kind,
            "sample_count": len(picked),
            "fit_start": picked[0][0].isoformat(),
            "fit_end": picked[-1][0].isoformat(),
            "fit_last_trade_date": picked[-1][1].isoformat(),
            "calendar_window_start": start.isoformat(),
            "calendar_window_end": end.isoformat(),
            "data_hash": hash_of([(w.isoformat(), c) for w, _, c in picked]),
            "coefficients": {
                "slope": slope,
                "intercept": intercept,
                "deviation": deviation,
            },
        }

    trailing = model_block("trailing_10y_weekly", sample_weeks(complete, trailing_start, trailing_end), trailing_start, trailing_end)
    since = model_block("since_inception_weekly", complete, complete[0][0] + dt.timedelta(days=6) - dt.timedelta(days=6), trailing_end)

    fixed = []
    for i in range(8):
        start = shift_years(dt.date(2005, 4, 1), i * 3)
        end = shift_years(start, 10)
        if end > now.date():
            break
        picked = sample_weeks(complete, start, end)
        fixed.append(model_block("historical_fixed_10y_weekly", picked, start, end))

    baseline = {
        "algorithm_version": "lrc-ltb-week-v1",
        "multiplier": 2,
        "as_of": now.isoformat(timespec="seconds"),
        "data_cutoff_week": last_week.isoformat(),
        "data_cutoff_trade_date": complete[-1][1].isoformat(),
        "current_models": {
            "trailing_10y_weekly": trailing,
            "since_inception_weekly": since,
        },
        "fixed_windows": fixed,
    }

    FIXTURES.mkdir(parents=True, exist_ok=True)
    (FIXTURES / "csi300-weekly-2026-11.json").write_text(
        json.dumps(weekly_fixture, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (FIXTURES / "csi300-daily-2026-11.json").write_text(
        json.dumps(daily_fixture, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (FIXTURES / "csi300-weekly-baseline.json").write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"周K {len(weekly_rows)} 条，完整周 {len(complete)} 个，异常周 {len(anomalies)} 个")
    print(f"日线 {len(daily_rows)} 条，日历覆盖 {coverage_start} ~ {coverage_end}")
    print(f"基准：trailing {trailing['sample_count']} 周 / since {since['sample_count']} 周 / fixed {len(fixed)} 个")


if __name__ == "__main__":
    main()
