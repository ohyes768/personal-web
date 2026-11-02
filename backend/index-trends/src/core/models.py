"""模型种类、模型 ID 与区域分类。

模型种类（首版只支持沪深300）：
    historical_fixed_120m  固定 120 月窗口（36 月步进），新完整窗口出现后增加，不覆盖旧窗口
    trailing_120m          最近 120 个完整自然月，新完整月到来后生成新版本
    since_inception        2005-04 至最近完整月，新完整月到来后生成新版本

全历史回溯图与当前页"成立以来"模型在同一数据版本/截止月份时复用同一模型。

周线种类（与月线完全隔离，独立算法版本 lrc-ltb-week-v1）：
    historical_fixed_10y_weekly  固定 10 年训练窗口（3 年步进）
    trailing_10y_weekly          最近 10 个日历年（按实际有交易周计样本）
    since_inception_weekly       2005-04 至最近完整有交易周

周线字段一律用 week_* 语义：fit_start/fit_end 是周一（YYYY-MM-DD），
fit_last_trade_date 是该周实际最后交易日，data_cutoff_week 是最近完整周的周一。
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

from src.core.regression import ALGORITHM_VERSION, WEEK_ALGORITHM_VERSION, Coefficients

KIND_FIXED = "historical_fixed_120m"
KIND_TRAILING = "trailing_120m"
KIND_SINCE_INCEPTION = "since_inception"
CURRENT_MODEL_KINDS = (KIND_TRAILING, KIND_SINCE_INCEPTION)

INCEPTION_MONTH = "2005-04"

KIND_FIXED_WEEKLY = "historical_fixed_10y_weekly"
KIND_TRAILING_WEEKLY = "trailing_10y_weekly"
KIND_SINCE_INCEPTION_WEEKLY = "since_inception_weekly"
CURRENT_WEEKLY_MODEL_KINDS = (KIND_TRAILING_WEEKLY, KIND_SINCE_INCEPTION_WEEKLY)

TIMEFRAME_WEEK = "week"

# 月线 kind → 周线 kind 的迁移映射（report_settings 用）
LEGACY_KIND_TO_WEEKLY = {
    KIND_TRAILING: KIND_TRAILING_WEEKLY,
    KIND_SINCE_INCEPTION: KIND_SINCE_INCEPTION_WEEKLY,
    KIND_FIXED: KIND_FIXED_WEEKLY,
}


@dataclass(frozen=True)
class ModelRecord:
    model_id: str
    index_code: str
    kind: str
    fit_start: str
    fit_end: str
    months: int
    algorithm_version: str
    data_cutoff_month: str
    data_hash: str
    multiplier: float
    coefficients: Coefficients
    calculated_at: str


@dataclass(frozen=True)
class WeeklyModelRecord:
    """周线模型记录。

    与月线 ModelRecord 字段语义不同（周数不是"月数"），单独成类避免
    把 months 列改装成周数。
    """

    model_id: str
    index_code: str
    kind: str
    timeframe: str
    sample_count: int
    fit_start: str          # 训练起始周（周一）
    fit_end: str            # 训练结束周（周一）
    fit_last_trade_date: str  # 训练结束周的实际最后交易日
    calendar_window_start: str  # 日历窗口下界（含）
    calendar_window_end: str    # 日历窗口上界（不含）
    data_cutoff_week: str   # 最近完整周的周一
    algorithm_version: str
    data_hash: str
    multiplier: float
    coefficients: Coefficients
    calculated_at: str

    @property
    def stable_id(self) -> str:
        """固定窗口的页面稳定标识（用名义窗口起点命名，数据更新不变）。"""
        return f"fixed-{self.calendar_window_start[:7]}"


def data_hash(closes: list[float]) -> str:
    """训练用月收盘序列的哈希（同月内价格变化不改变完整月序列 → 哈希稳定）。"""
    payload = json.dumps([round(c, 6) for c in closes], separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def weekly_data_hash(weeks: list[str], closes: list[float]) -> str:
    """训练用周序列哈希：必须含周坐标与收盘，不能只散列收盘。

    只散列收盘会让"同一批收盘配不同周坐标"（例如整周休市挪位）得到相同哈希，
    从而复用错误的模型版本。
    """
    payload = json.dumps(
        [[w, round(c, 6)] for w, c in zip(weeks, closes)], separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def build_model_id(
    index_code: str,
    kind: str,
    fit_start: str,
    fit_end: str,
    hash_value: str,
    algorithm_version: str = ALGORITHM_VERSION,
) -> str:
    """模型 ID 至少包含指数、种类、训练起止、算法版本和数据哈希。"""
    return f"{index_code}|{kind}|{fit_start}|{fit_end}|{algorithm_version}|{hash_value}"


def build_weekly_model_id(
    index_code: str,
    kind: str,
    fit_start: str,
    fit_end: str,
    hash_value: str,
    algorithm_version: str = WEEK_ALGORITHM_VERSION,
) -> str:
    """周线模型 ID：含指数、week 周期、种类、训练起止、算法版本与坐标+价格哈希。"""
    return (
        f"{index_code}|{TIMEFRAME_WEEK}|{kind}|{fit_start}|{fit_end}"
        f"|{algorithm_version}|{hash_value}"
    )


# ---- 区域与位置 ----
# 区域阈值 25/75 是可读性分层，不是买卖阈值。
REGION_BELOW = "below_channel"   # 通道下方 p<0
REGION_LOWER = "lower"           # 低位 0<=p<25
REGION_MIDDLE = "middle"         # 中部 25<=p<75
REGION_UPPER = "upper"           # 高位 75<=p<=100
REGION_ABOVE = "above_channel"   # 通道上方 p>100

REGION_LABELS_ZH = {
    REGION_BELOW: "通道下方",
    REGION_LOWER: "低位",
    REGION_MIDDLE: "中部",
    REGION_UPPER: "高位",
    REGION_ABOVE: "通道上方",
}


class InvalidChannelError(ValueError):
    """轨道宽度无效（deviation 非正或非有限），模型无效，不能继续分类。"""


def position_pct(close: float, upper: float, lower: float) -> float:
    """(close-lower)/(upper-lower)*100，不裁剪到 0—100。"""
    if not all(math.isfinite(v) for v in (close, upper, lower)):
        raise InvalidChannelError("轨道值非有限")
    width = upper - lower
    if width <= 0:
        raise InvalidChannelError(f"轨道宽度无效: {width}")
    return (close - lower) / width * 100


def classify_region(pct: float) -> str:
    if pct < 0:
        return REGION_BELOW
    if pct < 25:
        return REGION_LOWER
    if pct < 75:
        return REGION_MIDDLE
    if pct <= 100:
        return REGION_UPPER
    return REGION_ABOVE
