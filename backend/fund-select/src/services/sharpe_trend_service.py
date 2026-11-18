"""
夏普走势：单基金周频滚动 3 年夏普（现算，不落库）

口径决定（见任务 research/data-basis.md 实测）：
- **纯净值口径**：夏普只用 R_p（东财日增长率/100）与 R_f，**不 join fund_benchmark**。
  risk_service.compute_risk_metrics 在有基准时会 inner join，而生产库 fund_benchmark
  最早只到 2023-11-08，会把历史 3 年窗口截断成 1 年（000628 在 2024-09-30
  窗口：join 版 2.42/n=219，纯净值版 0.68/n=729）。走势页若沿用 join 会画出
  虚假断崖，恰好与「稳定性」判断相反。
- 公式与 risk_service 一致：mean(excess)/std(excess, ddof=1) × √252；
  std=0 或 NaN → 无定义（该周不出点）。
- R_f 年化小数 / 252 折日频，reindex 到窗口 ffill 缺省 0。生产库
  risk_free_rate 当前为空表 → rf_basis="zero"，如实标注不静默。

性能（实测）：净值拉取 0.12s + 603 个周点计算 0.17s ≈ 0.3s/请求，
无需预计算落库；仅加进程内 1 小时 TTL 缓存避免区间切换重复打网络。

本模块是纯读：不写任何表、不进调度、不影响周榜发布。
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from src.data.nav_fetcher import fetch_nav
from src.db.models import Fund, RiskFreeRate
from src.services.risk_service import MIN_SAMPLE_DAYS, TRADING_DAYS, WINDOW_YEARS
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.sharpe_trend")

ALGORITHM_VERSION = "trend-v1"
DEFAULT_THRESHOLD = 0.8
WINDOW_DAYS = 365 * WINDOW_YEARS

_NAV_TTL_SECONDS = 3600
_nav_cache: dict[str, tuple[float, pd.DataFrame]] = {}


class NavFetchError(Exception):
    """净值外部请求失败（与「确实无历史」分开，API 映射 502 可重试）"""


class FundNotFoundError(Exception):
    """基金不存在 / 无任何净值历史（API 映射 404）"""


@dataclass(frozen=True)
class TrendPoint:
    """一个周观测点：该自然周最后一个交易日的 trailing-3y 夏普"""
    date: date
    sharpe: float | None
    sample_days: int


@dataclass(frozen=True)
class TrendStats:
    """展示区间内的稳定性统计（全部基于有效点；None 表示无定义）"""
    threshold: float = DEFAULT_THRESHOLD
    current: float | None = None
    max: float | None = None
    min: float | None = None
    mean: float | None = None
    above_count: int = 0
    valid_count: int = 0
    above_ratio: float | None = None
    consecutive_above: int = 0
    longest_below: int = 0
    trend_12w: float | None = None


@dataclass
class TrendResult:
    """build_trend 的返回值（API 层按此构造 DTO）"""
    code: str
    name: str | None
    range: str
    rf_basis: str
    algorithm_version: str
    threshold: float
    points: list[TrendPoint] = field(default_factory=list)
    stats: TrendStats = field(default_factory=TrendStats)
    diagnostics: dict = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────
# 纯函数（无 IO，可单测）
# ──────────────────────────────────────────────────────────────────

def nav_to_returns(nav: pd.DataFrame) -> pd.Series:
    """单位净值「日增长率」(%) → 复权日收益小数序列，索引为净值日期（升序）。

    与 risk_service._risk_returns 同源口径：分红日已除息调整，勿用累计净值
    pct_change。这里不切时间窗（滚动算法自己按每周末回看 3 年）。
    """
    if nav is None or nav.empty:
        return pd.Series(dtype=float)
    s = nav.set_index("净值日期")["日增长率"].astype(float).div(100).dropna()
    return s.sort_index()


def _sharpe_from_excess(excess: np.ndarray) -> float | None:
    """mean/std(ddof=1) × √252；std=0/NaN → None（与 risk_service 一致）"""
    if len(excess) < 2:
        return None
    std = float(excess.std(ddof=1))
    if std == 0 or math.isnan(std):
        return None
    v = float(excess.mean()) / std * math.sqrt(TRADING_DAYS)
    return None if math.isnan(v) else v


def rolling_sharpe_series(
    r_p: pd.Series,
    r_f: pd.Series | None = None,
    *,
    window_days: int = WINDOW_DAYS,
    min_sample_days: int = MIN_SAMPLE_DAYS,
    trading_days: int = TRADING_DAYS,
) -> list[TrendPoint]:
    """周频滚动 trailing-3y 夏普（**不 join 基准**，见模块 docstring）。

    - 每个自然周最后一个交易日出一个点；回看 window_days（默认 3 年）。
    - 样本 < min_sample_days → sharpe=None（保留点，供上层裁前导空点）。
    - r_f 为年化小数日频序列（按日期索引），内部 /252 折日频后 ffill 对齐；
      None 或空 → 按 rf=0 处理。
    """
    if r_p is None or len(r_p) == 0:
        return []
    r_p = r_p.sort_index()
    idx = r_p.index
    values = r_p.to_numpy(dtype=float)

    # rf 一次性对齐到全序列，避免每周重复 reindex
    rf_daily: pd.Series | None = None
    if r_f is not None and len(r_f) > 0:
        rf_daily = (r_f / trading_days).reindex(idx).ffill().fillna(0.0)

    # 每个自然周最后一个交易日
    ends = r_p.groupby(idx.to_period("W")).apply(lambda g: g.index.max()).tolist()

    out: list[TrendPoint] = []
    for end in ends:
        start_ts = end - pd.Timedelta(days=window_days)
        mask = (idx >= start_ts) & (idx <= end)
        w = values[mask]
        n = int(len(w))
        if n < min_sample_days:
            out.append(TrendPoint(date=end.date(), sharpe=None, sample_days=n))
            continue
        if rf_daily is not None:
            excess = w - rf_daily[mask].to_numpy(dtype=float)
        else:
            excess = w
        out.append(TrendPoint(
            date=end.date(),
            sharpe=_sharpe_from_excess(excess),
            sample_days=n,
        ))
    return out


def _slope(values: list[float]) -> float | None:
    """最小二乘斜率（每周变化量）；<2 点或 x 无方差 → None"""
    n = len(values)
    if n < 2:
        return None
    xs = np.arange(n, dtype=float)
    ys = np.asarray(values, dtype=float)
    xm, ym = float(xs.mean()), float(ys.mean())
    denom = float(((xs - xm) ** 2).sum())
    if denom == 0:
        return None
    return float(((xs - xm) * (ys - ym)).sum() / denom)


def compute_trend_stats(
    points: list[TrendPoint], threshold: float = DEFAULT_THRESHOLD,
) -> TrendStats:
    """展示区间内稳定性统计。

    - 有效点 = sharpe 非 None 的点；None（样本不足/无定义）不计入统计，
      但会**打断**连续达标 / 连续低于的计数（缺口不是「达标」或「低于」的证据）。
    - consecutive_above：从最后一个点往回数，连续 sharpe ≥ threshold 的点数。
    - longest_below：最长连续 sharpe < threshold 的点数。
    - trend_12w：最近 12 个有效点的最小二乘斜率（每周变化量）；不足 12 → None。
    """
    valid = [p.sharpe for p in points if p.sharpe is not None]
    if not valid:
        return TrendStats(threshold=threshold)

    above_count = sum(1 for v in valid if v >= threshold)

    consecutive_above = 0
    for p in reversed(points):
        if p.sharpe is not None and p.sharpe >= threshold:
            consecutive_above += 1
        else:
            break

    longest_below = 0
    run = 0
    for p in points:
        if p.sharpe is not None and p.sharpe < threshold:
            run += 1
            longest_below = max(longest_below, run)
        else:
            run = 0

    return TrendStats(
        threshold=threshold,
        current=valid[-1],
        max=max(valid),
        min=min(valid),
        mean=float(np.mean(valid)),
        above_count=above_count,
        valid_count=len(valid),
        above_ratio=above_count / len(valid),
        consecutive_above=consecutive_above,
        longest_below=longest_below,
        trend_12w=_slope(valid[-12:]) if len(valid) >= 12 else None,
    )


def trim_leading_gaps(points: list[TrendPoint]) -> list[TrendPoint]:
    """裁掉首个有效点之前的空点（「历史不足」段），保留中间真实缺口。"""
    first = next((i for i, p in enumerate(points) if p.sharpe is not None), None)
    return points[first:] if first is not None else []


def filter_range(points: list[TrendPoint], range_key: str, today: date) -> list[TrendPoint]:
    """range 只裁返回的点集，不改每个点的 3 年滚动窗口。"""
    days = {"all": None, "3y": 365 * 3, "1y": 365}.get(range_key)
    if days is None:
        return points
    cutoff = today - timedelta(days=days)
    return [p for p in points if p.date >= cutoff]


# ──────────────────────────────────────────────────────────────────
# 编排（IO：缓存净值 + 读库 rf/name）
# ──────────────────────────────────────────────────────────────────

def clear_nav_cache() -> None:
    """清空进程内净值缓存（测试用；重启自然失效）。"""
    _nav_cache.clear()


def _load_nav(code: str) -> pd.DataFrame:
    """底层外部请求（独立函数便于测试 monkeypatch）。"""
    return fetch_nav(code)


def _cached_nav(code: str) -> pd.DataFrame:
    """进程内 TTL 缓存：区间切换/重复查看不重复打网络。

    只缓存非空结果；失败不缓存（下次可重试）。无锁 —— GIL 下 dict 读写安全，
    并发重复拉取最坏是多一次请求，无害。
    """
    now = time.monotonic()
    hit = _nav_cache.get(code)
    if hit is not None and now - hit[0] < _NAV_TTL_SECONDS:
        return hit[1]
    df = _load_nav(code)
    if df is not None and not df.empty:
        _nav_cache[code] = (now, df)
    return df


def _load_rf(db: Session) -> tuple[pd.Series | None, str]:
    """读 risk_free_rate（年化小数日频序列）。

    生产库该表当前为空（fetcher 未入调度）→ (None, "zero")，如实标注。
    """
    rows = db.query(RiskFreeRate).order_by(RiskFreeRate.date).all()
    if not rows:
        return None, "zero"
    return pd.Series(
        [float(r.rate) for r in rows],
        index=pd.DatetimeIndex([r.date for r in rows]),
    ), "rate"


def build_trend(
    db: Session,
    code: str,
    range_key: str = "all",
    *,
    threshold: float = DEFAULT_THRESHOLD,
    today: date | None = None,
) -> TrendResult:
    """单基金夏普走势：读 name/rf → 缓存拉净值 → 滚动计算 → 裁 range → 统计。

    Raises:
        NavFetchError: 净值外部请求失败（API → 502）
        FundNotFoundError: 无任何净值历史（API → 404）
    """
    today = today or date.today()
    fund = db.get(Fund, code)
    # 代码不在基金表 → 直接判不存在（404），不浪费一次网络请求。
    # akshare 对未知代码抛的是「Unknown JavaScript error during parse」解析异常，
    # 若走到净值拉取会被误判成 502 源故障（语义错误）。
    # 注意：Fund 表本身有净值但已清盘的基金仍会走下面的净值拉取，属正常。
    if fund is None:
        raise FundNotFoundError(code)
    name = fund.name

    r_f, rf_basis = _load_rf(db)

    try:
        nav = _cached_nav(code)
    except Exception as e:  # noqa: BLE001
        logger.warning("[trend] %s 净值拉取失败: %s", code, str(e)[:120])
        raise NavFetchError(str(e)[:200]) from e

    if nav is None or nav.empty:
        raise FundNotFoundError(code)

    r_p = nav_to_returns(nav)
    diagnostics: dict = {"nav_end_date": str(r_p.index.max().date()) if len(r_p) else None}

    if len(r_p) < MIN_SAMPLE_DAYS:
        diagnostics["insufficient_history"] = True
        diagnostics["total_return_days"] = len(r_p)
        return TrendResult(
            code=code, name=name, range=range_key, rf_basis=rf_basis,
            algorithm_version=ALGORITHM_VERSION, threshold=threshold,
            points=[], stats=TrendStats(threshold=threshold),
            diagnostics=diagnostics,
        )

    raw = rolling_sharpe_series(r_p, r_f)
    points = trim_leading_gaps(raw)
    if not points:
        diagnostics["no_valid_points"] = True
        return TrendResult(
            code=code, name=name, range=range_key, rf_basis=rf_basis,
            algorithm_version=ALGORITHM_VERSION, threshold=threshold,
            points=[], stats=TrendStats(threshold=threshold),
            diagnostics=diagnostics,
        )

    points = filter_range(points, range_key, today)
    diagnostics["total_points"] = len(points)
    return TrendResult(
        code=code, name=name, range=range_key, rf_basis=rf_basis,
        algorithm_version=ALGORITHM_VERSION, threshold=threshold,
        points=points,
        stats=compute_trend_stats(points, threshold),
        diagnostics=diagnostics,
    )
