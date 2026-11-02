"""周线模型计算：10 日历年选样、固定窗口归属、观察期扰动、版本不可变。

用固定 fixture（脱网）与独立数值基准（numpy 生成）交叉校验。
"""
from __future__ import annotations

import dataclasses

import pytest

from src.core.models import (
    KIND_FIXED_WEEKLY,
    KIND_SINCE_INCEPTION_WEEKLY,
    KIND_TRAILING_WEEKLY,
    build_weekly_model_id,
    weekly_data_hash,
)
from src.core.regression import WEEK_ALGORITHM_VERSION
from src.core.weekly import (
    WeeklyModelBuilder,
    build_fixed_weekly_models,
    build_trailing_weekly_model,
    build_since_inception_weekly_model,
)
from src.core.weeks import fixed_windows

TOL = dict(rel=1e-9)


@pytest.fixture()
def series(weekly_series):
    return weekly_series


def test_trailing_model_matches_independent_baseline(series, weekly_baseline):
    """近10年周线模型与独立数值基准一致（系数 + 样本数 + 窗口边界）。"""
    expected = weekly_baseline["current_models"]["trailing_10y_weekly"]
    record = build_trailing_weekly_model(series, "000300")
    assert record.sample_count == expected["sample_count"]
    assert record.fit_start == expected["fit_start"]
    assert record.fit_end == expected["fit_end"]
    assert record.fit_last_trade_date == expected["fit_last_trade_date"]
    assert record.calendar_window_start == expected["calendar_window_start"]
    assert record.calendar_window_end == expected["calendar_window_end"]
    assert record.coefficients.slope == pytest.approx(expected["coefficients"]["slope"], **TOL)
    assert record.coefficients.intercept == pytest.approx(expected["coefficients"]["intercept"], **TOL)
    assert record.coefficients.deviation == pytest.approx(expected["coefficients"]["deviation"], **TOL)
    assert record.data_hash == expected["data_hash"]
    assert record.algorithm_version == WEEK_ALGORITHM_VERSION


def test_since_inception_model_matches_independent_baseline(series, weekly_baseline):
    expected = weekly_baseline["current_models"]["since_inception_weekly"]
    record = build_since_inception_weekly_model(series, "000300")
    assert record.sample_count == expected["sample_count"]
    assert record.fit_start == expected["fit_start"]
    assert record.fit_end == expected["fit_end"]
    assert record.coefficients.slope == pytest.approx(expected["coefficients"]["slope"], **TOL)
    assert record.coefficients.intercept == pytest.approx(expected["coefficients"]["intercept"], **TOL)
    assert record.coefficients.deviation == pytest.approx(expected["coefficients"]["deviation"], **TOL)
    assert record.data_hash == expected["data_hash"]


def test_fixed_windows_match_independent_baseline(series, weekly_baseline):
    expected = weekly_baseline["fixed_windows"]
    records = build_fixed_weekly_models(series, "000300", as_of=date_of("2026-11-02"))
    assert len(records) == len(expected)
    for record, exp in zip(records, expected):
        assert record.kind == KIND_FIXED_WEEKLY
        assert record.sample_count == exp["sample_count"]
        assert record.fit_start == exp["fit_start"]
        assert record.fit_end == exp["fit_end"]
        assert record.fit_last_trade_date == exp["fit_last_trade_date"]
        assert record.calendar_window_start == exp["calendar_window_start"]
        assert record.calendar_window_end == exp["calendar_window_end"]
        assert record.coefficients.slope == pytest.approx(exp["coefficients"]["slope"], **TOL)
        assert record.coefficients.intercept == pytest.approx(exp["coefficients"]["intercept"], **TOL)
        assert record.coefficients.deviation == pytest.approx(exp["coefficients"]["deviation"], **TOL)
        assert record.data_hash == exp["data_hash"]


def date_of(text: str):
    from datetime import date

    return date.fromisoformat(text)


def test_weekly_hash_includes_week_coordinates():
    """哈希必须含周坐标：同样的收盘配不同周坐标 → 不同哈希。"""
    a = weekly_data_hash(["2026-10-19", "2026-10-26"], [100.0, 101.0])
    b = weekly_data_hash(["2026-10-26", "2026-11-02"], [100.0, 101.0])
    assert a != b
    assert weekly_data_hash(["2026-10-19", "2026-10-26"], [100.0, 101.0]) == a


def test_weekly_model_id_contains_week_and_hash():
    mid = build_weekly_model_id("000300", KIND_TRAILING_WEEKLY, "2016-10-31", "2026-10-26", "h123")
    assert "week" in mid
    assert KIND_TRAILING_WEEKLY in mid
    assert "h123" in mid
    assert WEEK_ALGORITHM_VERSION in mid


def test_same_week_price_change_does_not_change_model(series):
    """同一完整周内价格变化（未完成周的点位）不改系数与模型 ID。"""
    baseline = build_trailing_weekly_model(series, "000300")
    # 进行中周（2026-11-02）的价格变化不影响拟合
    mutated = dataclasses.replace(
        series, partial_bars={k: dataclasses.replace(v, close=v.close + 100) for k, v in series.partial_bars.items()}
    )
    after = build_trailing_weekly_model(mutated, "000300")
    assert after.model_id == baseline.model_id
    assert after.coefficients == baseline.coefficients


def test_new_complete_week_creates_new_version(series):
    """新完整周 → 新模型版本；旧版本不可覆盖。"""
    from src.core.weeks import WeeklySample

    baseline = build_trailing_weekly_model(series, "000300")
    extra = WeeklySample(
        week_start="2026-11-02", trade_date="2026-11-06",
        open=4005.94, close=4012.46, high=4038.82, low=3988.17,
    )
    extended = dataclasses.replace(
        series, samples=series.samples + [extra]
    )
    after = build_trailing_weekly_model(extended, "000300")
    assert after.model_id != baseline.model_id
    assert after.fit_end == "2026-11-02"


def test_observation_period_does_not_affect_training(series):
    """观察期价格扰动不改变固定窗口的拟合系数。"""
    records = build_fixed_weekly_models(series, "000300", as_of=date_of("2026-11-02"))
    window = records[0]
    # 该窗口训练区间为 2005-04-01 ~ 2015-04-01；把其后的价格全部翻倍
    mutated_samples = [
        dataclasses.replace(s, close=s.close * 2) if s.week_start > "2015-03-23" else s
        for s in series.samples
    ]
    mutated = dataclasses.replace(series, samples=mutated_samples)
    after = build_fixed_weekly_models(mutated, "000300", as_of=date_of("2026-11-02"))
    assert after[0].coefficients == window.coefficients
    assert after[0].model_id == window.model_id


def test_fixed_window_model_id_is_stable_across_new_data(series):
    """固定窗口 ID 终身稳定（训练数据定死），不随新数据变化。"""
    first = build_fixed_weekly_models(series, "000300", as_of=date_of("2026-11-02"))
    later = build_fixed_weekly_models(series, "000300", as_of=date_of("2027-05-01"))
    by_id = {r.stable_id: r for r in later}
    for record in first:
        assert by_id[record.stable_id].model_id == record.model_id


def test_fixed_windows_use_nominal_calendar_intervals():
    """固定窗口按名义日历区间归属（与月线 120 月窗口不同的口径）。"""
    windows = fixed_windows(date_of("2026-11-02"))
    assert [w.stable_id for w in windows] == [
        "fixed-2005-04", "fixed-2008-04", "fixed-2011-04", "fixed-2014-04",
    ]


def test_builder_produces_all_kinds(series):
    builder = WeeklyModelBuilder(series, "000300", as_of=date_of("2026-11-02"))
    kinds = {r.kind for r in builder.build_all()}
    assert kinds == {
        KIND_TRAILING_WEEKLY, KIND_SINCE_INCEPTION_WEEKLY, KIND_FIXED_WEEKLY,
    }


def test_fixed_window_observation_end(series):
    """观察期实际截止周：名义区间后 3 年内、已有完整数据的最后一周。"""
    from src.core.weekly import fixed_window_observation_end

    windows = fixed_windows(date_of("2026-11-02"))
    # 窗口 1：名义区间 2005-04-01 ~ 2015-04-01，观察期到 2018-04-01
    end = fixed_window_observation_end(series, windows[0])
    assert end is not None
    assert "2015-04-01" <= end < "2018-04-01"
    # 最后一个窗口：观察期名义到 2027-04-01，但当前数据只到 2026-10-26
    last = fixed_window_observation_end(series, windows[-1])
    assert last == "2026-10-26"


def test_fixed_window_observation_end_none_when_no_observation(series):
    """窗口在数据末尾之后、还没有观察期数据时返回 None。"""
    from src.core.weekly import fixed_window_observation_end
    from src.core.weeks import FixedWindow
    from datetime import date as _date

    # 训练区间结束于 2027 年（远超当前数据 2026-10-26）→ 没有观察期
    future_window = FixedWindow(
        index=99,
        start_inclusive=_date(2026, 1, 1),
        end_exclusive=_date(2027, 1, 1),
    )
    assert fixed_window_observation_end(series, future_window) is None
