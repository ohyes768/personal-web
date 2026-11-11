"""经理口径指标计算（任务 11-10-fund-manager-evaluation）。

口径版本 mgr-3y-v1：变更必须升版本号（对齐 sharpe_board 的 ALGORITHM_VERSION 惯例）。

锚点（实测，写进测试防回归）：
- 富国天惠 161005 全历史复权收益 ≈1500%（不是累计净值的 462%）
- 张坤 30189744：最长任期年化 ≈10.5%，管理时长加权年化 ≈5.2%
"""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np

# 经理口径业绩的基金段判定：排除制（债基/货币/FOF/固收+ 不算股票经理业绩）。
# 不用精确白名单：QDII-混合（如易方达优质精选 110011，张坤任期最长的基金）
# 实际是偏股 QDII，白名单会把它漏掉，加权年化从 ≈5.2% 掉到 ≈0.3%。
_EXCLUDED_TYPE_PREFIXES = ("债券型", "货币型", "固定收益", "中短债")
_EXCLUDED_TYPE_KEYWORDS = ("货币", "FOF", "固收")


def is_active_equity(fund_type: str | None) -> bool:
    """基金类型是否计入经理的权益业绩段。"""
    if not fund_type:
        return False
    if fund_type.startswith(_EXCLUDED_TYPE_PREFIXES):
        return False
    return not any(k in fund_type for k in _EXCLUDED_TYPE_KEYWORDS)


# 兼容旧引用（设计文档里的概念名）；判定一律走 is_active_equity()
ACTIVE_EQUITY_SUBTYPES = {"股票型", "混合型-偏股"}

ALGORITHM_VERSION = "mgr-3y-v1"

RISK_FREE_ANNUAL_PCT = 2.0  # 夏普无风险利率（与 risk_service 口径一致）
TRADING_DAYS = 252


# 年化最低任期：不足 90 天（一个季度）的段年化无统计意义。
# 实测：1 天任期回报 4.16% → 年化 2.9 亿%（方一航 019113，新发基金建仓期）。
MIN_ANNUALIZE_DAYS = 90


def annualize(tenure_return_pct: float | None, tenure_days: int | None) -> float | None:
    """累计任职回报 → 年化。days=0、days<90 或 return<=-100 返回 None。"""
    if not tenure_return_pct or not tenure_days or tenure_days <= 0:
        return None
    if tenure_days < MIN_ANNUALIZE_DAYS:
        return None
    if tenure_return_pct <= -100:
        return None
    return ((1 + tenure_return_pct / 100) ** (365.0 / tenure_days) - 1) * 100


def weighted_annual(tenures: Sequence[dict[str, Any]]) -> float | None:
    """管理时长加权年化（只统计主动权益段）。

    为什么必须加权：只看最长任期单只 = 让经理自选代表作。
    实测张坤最长任期 10.53% / 全段加权 6.78%。

    Args:
        tenures: fetch_manager_tenures 返回的 dict 列表（可含 annual_return）
    """
    total_days = 0.0
    acc = 0.0
    for t in tenures:
        if not is_active_equity(t.get("fund_type")):
            continue
        ann = t.get("annual_return")
        days = t.get("tenure_days")
        if ann is None or not days or days <= 0:
            continue
        acc += ann * days
        total_days += days
    if total_days <= 0:
        return None
    return acc / total_days


def pick_representative(tenures: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    """代表基金：主动权益优先 → 任期最长 → 在管优先。

    注意优先级：任期最长必须在在管之前。若反过来，新建仓的短在管段
    会压过真正的长任期段（实测刘小明：36 天在管段被选为代表，
    最长任期显示 0.1 年，而其 22% 加权年化来自已离任的长段）。
    另外优先选年化可用的段（≥90 天），风险指标窗口才有意义。
    """
    eq = [t for t in tenures if is_active_equity(t.get("fund_type"))]
    pool = eq or list(tenures)
    if not pool:
        return None
    return max(pool, key=lambda t: (
        t.get("annual_return") is not None,
        t.get("tenure_days") or 0,
        bool(t.get("is_current")),
    ))


def slice_series(series: Sequence[tuple[str, float]],
                 start: str | None = None, end: str | None = None,
                 start_days_ago: int | None = None) -> list[tuple[str, float]]:
    """按任职窗口切复权序列。

    关键：基金净值序列是基金全历史，经理任期只是其中一段。不切窗口会把
    前任经理的收益/回撤算到现任头上（实测 110011 全历史 472% vs
    张坤 2012-09 接任后 ≈309%）。窗口终点取 min(end, 序列尾)，起点取
    第一个 >= start 的点。
    """
    out = series
    if start:
        out = [p for p in out if p[0] >= start]
    if end:
        out = [p for p in out if p[0] <= end]
    return list(out)


def compute_risk(series: Sequence[tuple[str, float]]) -> dict[str, float | None] | None:
    """基于复权净值序列算风险指标。

    Args:
        series: [(date_str, adjusted_nav), ...]，首点 nav 应为 1.0

    Returns:
        {"total_return_pct", "cagr_pct", "max_drawdown_pct", "annual_vol_pct",
         "sharpe", "calmar", "sample_days"}；样本 <30 点返回 None。
    """
    if series is None or len(series) < 30:
        return None
    nav = np.array([s[1] for s in series], dtype=float)
    days = _span_days(series)
    if days <= 0:
        return None
    yrs = days / 365.0
    total = nav[-1] / nav[0] - 1
    cagr = ((1 + total) ** (1 / yrs) - 1) * 100

    peak = np.maximum.accumulate(nav)
    mdd = float(((nav - peak) / peak).min() * 100)

    rets = np.diff(nav) / nav[:-1]
    vol = float(rets.std(ddof=1) * np.sqrt(TRADING_DAYS) * 100)

    sharpe = (cagr - RISK_FREE_ANNUAL_PCT) / vol if vol > 0 else None
    calmar = cagr / abs(mdd) if mdd < 0 else None
    return {
        "total_return_pct": total * 100,
        "cagr_pct": cagr,
        "max_drawdown_pct": mdd,
        "annual_vol_pct": vol,
        "sharpe": sharpe,
        "calmar": calmar,
        "sample_days": days,
    }


def _span_days(series: Sequence[tuple[str, float]]) -> int:
    from datetime import date
    d0 = date.fromisoformat(series[0][0])
    d1 = date.fromisoformat(series[-1][0])
    return (d1 - d0).days
