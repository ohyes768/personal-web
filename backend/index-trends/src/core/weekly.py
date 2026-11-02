"""周线模型计算：选样、拟合、模型版本。

与月线（src/core/models.py + trend_service）分离：
- 坐标是自然周坐标（整周休市留间隔），不是等间距序号
- 窗口按名义日历区间归属，样本数按实际有交易周计
- 算法版本独立（lrc-ltb-week-v1），不改旧月线算法与基准

纯计算层：不依赖网络与数据库。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.core.models import (
    KIND_FIXED_WEEKLY,
    KIND_SINCE_INCEPTION_WEEKLY,
    KIND_TRAILING_WEEKLY,
    TIMEFRAME_WEEK,
    WeeklyModelRecord,
    build_weekly_model_id,
    position_pct as _position_pct,
    weekly_data_hash,
)
from src.core.regression import WEEK_ALGORITHM_VERSION, channel_at, fit_weekly_channel
from src.core.weeks import (
    FixedWindow,
    WeeklySample,
    WeeklySeries,
    fixed_windows,
    trailing_window_bounds,
    week_end_in_window,
    week_end_of,
)

DEFAULT_MULTIPLIER = 2.0

# 沪深300 价格指数发布日（2005-04-08）所在自然周的周一
INCEPTION_WEEK_START = "2005-04-04"


@dataclass(frozen=True)
class _FittedModel:
    """一次拟合的结果（拟合输入 + 系数 + 窗口边界）。"""

    kind: str
    weeks: list[str]
    closes: list[float]
    fit_start: str
    fit_end: str
    fit_last_trade_date: str
    calendar_window_start: str
    calendar_window_end: str
    slope: float
    intercept: float
    deviation: float

    @property
    def data_hash(self) -> str:
        return weekly_data_hash(self.weeks, self.closes)


def _fit(
    kind: str,
    samples: list[WeeklySample],
    calendar_window_start: str,
    calendar_window_end: str,
    multiplier: float = DEFAULT_MULTIPLIER,
) -> _FittedModel:
    """对一段周样本拟合通道（显式 x 坐标）。"""
    if not samples:
        raise ValueError(f"{kind} 没有可用样本")
    origin = samples[0].week_start
    xs = [
        (date.fromisoformat(s.week_start) - date.fromisoformat(origin)).days / 7
        for s in samples
    ]
    closes = [s.close for s in samples]
    coeff = fit_weekly_channel(xs, closes, multiplier)
    return _FittedModel(
        kind=kind,
        weeks=[s.week_start for s in samples],
        closes=closes,
        fit_start=samples[0].week_start,
        fit_end=samples[-1].week_start,
        fit_last_trade_date=samples[-1].trade_date,
        calendar_window_start=calendar_window_start,
        calendar_window_end=calendar_window_end,
        slope=coeff.slope,
        intercept=coeff.intercept,
        deviation=coeff.deviation,
    )


def _to_record(
    fitted: _FittedModel,
    index_code: str,
    data_cutoff_week: str,
    multiplier: float = DEFAULT_MULTIPLIER,
    calculated_at: str | None = None,
) -> WeeklyModelRecord:
    from src.core.regression import Coefficients

    data_hash = fitted.data_hash
    model_id = build_weekly_model_id(
        index_code, fitted.kind, fitted.fit_start, fitted.fit_end, data_hash
    )
    return WeeklyModelRecord(
        model_id=model_id,
        index_code=index_code,
        kind=fitted.kind,
        timeframe=TIMEFRAME_WEEK,
        sample_count=len(fitted.closes),
        fit_start=fitted.fit_start,
        fit_end=fitted.fit_end,
        fit_last_trade_date=fitted.fit_last_trade_date,
        calendar_window_start=fitted.calendar_window_start,
        calendar_window_end=fitted.calendar_window_end,
        data_cutoff_week=data_cutoff_week,
        algorithm_version=WEEK_ALGORITHM_VERSION,
        data_hash=data_hash,
        multiplier=multiplier,
        coefficients=Coefficients(fitted.slope, fitted.intercept, fitted.deviation),
        calculated_at=calculated_at or "",
    )


def _cutoff_week(series: WeeklySeries) -> str:
    """最近完整周的周一（数据截止周）。"""
    if not series.samples:
        raise ValueError("没有完整周样本")
    return series.samples[-1].week_start


def _samples_in_window(
    series: WeeklySeries,
    start_inclusive: date,
    end_exclusive: date,
) -> list[WeeklySample]:
    """取 week_end 落入 [start, end) 的完整有交易周。

    周归属按 week_end（周日）判定，边界周不会半归属。
    """
    picked = []
    for sample in series.samples:
        week_start = date.fromisoformat(sample.week_start)
        if week_end_in_window(week_start, start_inclusive, end_exclusive):
            picked.append(sample)
    return picked


def build_trailing_weekly_model(
    series: WeeklySeries,
    index_code: str,
    multiplier: float = DEFAULT_MULTIPLIER,
    calculated_at: str | None = None,
) -> WeeklyModelRecord:
    """近 10 年模型：10 个日历年的时间跨度，样本数按实际有交易周计。

    窗口上界 = 最近完整周的 week_end 次日；下界 = 上界减 10 个日历年。
    """
    cutoff = _cutoff_week(series)
    end_exclusive = week_end_of(date.fromisoformat(cutoff)) + date.resolution
    start_inclusive, end_exclusive = trailing_window_bounds(end_exclusive)
    picked = _samples_in_window(series, start_inclusive, end_exclusive)
    fitted = _fit(
        KIND_TRAILING_WEEKLY, picked,
        start_inclusive.isoformat(), end_exclusive.isoformat(), multiplier,
    )
    return _to_record(fitted, index_code, cutoff, multiplier, calculated_at)


def build_since_inception_weekly_model(
    series: WeeklySeries,
    index_code: str,
    multiplier: float = DEFAULT_MULTIPLIER,
    calculated_at: str | None = None,
) -> WeeklyModelRecord:
    """成立以来模型：从首条有效周K（发布周）到最近完整有交易周。

    全历史回溯图与当前页"成立以来"共用该模型。
    """
    cutoff = _cutoff_week(series)
    inception = date.fromisoformat(INCEPTION_WEEK_START)
    end_exclusive = week_end_of(date.fromisoformat(cutoff)) + date.resolution
    picked = [s for s in series.samples if date.fromisoformat(s.week_start) >= inception]
    fitted = _fit(
        KIND_SINCE_INCEPTION_WEEKLY, picked,
        inception.isoformat(), end_exclusive.isoformat(), multiplier,
    )
    return _to_record(fitted, index_code, cutoff, multiplier, calculated_at)


def build_fixed_weekly_models(
    series: WeeklySeries,
    index_code: str,
    as_of: date,
    multiplier: float = DEFAULT_MULTIPLIER,
    calculated_at: str | None = None,
) -> list[WeeklyModelRecord]:
    """固定历史窗口模型：10 年训练、3 年步进、最多 3 年观察。

    窗口按名义日历区间归属；区间结束边界尚未到达时不提前发布完整窗口。
    观察期数据不参与拟合（选样只看名义训练区间）。
    """
    records: list[WeeklyModelRecord] = []
    for window in fixed_windows(as_of):
        picked = _samples_in_window(series, window.start_inclusive, window.end_exclusive)
        if not picked:
            continue
        fitted = _fit(
            KIND_FIXED_WEEKLY, picked,
            window.start_inclusive.isoformat(), window.end_exclusive.isoformat(), multiplier,
        )
        records.append(_to_record(fitted, index_code, fitted.fit_end, multiplier, calculated_at))
    return records


def fixed_window_observation_end(
    series: WeeklySeries,
    window: FixedWindow,
) -> str | None:
    """固定窗口的观察期实际截止周（周一）。

    观察期 = 名义区间结束后 3 个日历年，最多展示已有完整数据；
    样本外数据不参与拟合。窗口结束即无观察期，返回 None。
    """
    observation_end_exclusive = window.observation_end_exclusive
    candidates = [
        s for s in series.samples
        if date.fromisoformat(s.week_start) >= window.end_exclusive
        and date.fromisoformat(s.week_start) < observation_end_exclusive
    ]
    return candidates[-1].week_start if candidates else None


class WeeklyModelBuilder:
    """周线模型构建器：一次产出全部当前模型与固定窗口模型。"""

    def __init__(
        self,
        series: WeeklySeries,
        index_code: str,
        as_of: date,
        multiplier: float = DEFAULT_MULTIPLIER,
        calculated_at: str | None = None,
    ):
        self.series = series
        self.index_code = index_code
        self.as_of = as_of
        self.multiplier = multiplier
        self.calculated_at = calculated_at

    def build_all(self) -> list[WeeklyModelRecord]:
        records = [
            build_trailing_weekly_model(
                self.series, self.index_code, self.multiplier, self.calculated_at
            ),
            build_since_inception_weekly_model(
                self.series, self.index_code, self.multiplier, self.calculated_at
            ),
        ]
        records.extend(
            build_fixed_weekly_models(
                self.series, self.index_code, self.as_of, self.multiplier, self.calculated_at
            )
        )
        return records


def project_week(
    coefficients,
    multiplier: float,
    fit_start: str,
    week_start: str,
    close: float,
) -> tuple[float, float, float, float]:
    """把收盘投影到某自然周，返回 (mid, upper, lower, position_pct)。

    x 相对该模型自己的 fit_start（周一），与拟合时的自然周坐标一致。
    通道位置不裁剪到 0—100。
    """
    x = (date.fromisoformat(week_start) - date.fromisoformat(fit_start)).days / 7
    mid, upper, lower = channel_at(coefficients, x, multiplier)
    return mid, upper, lower, _position_pct(close, upper, lower)
