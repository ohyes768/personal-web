"""模型种类、模型 ID 与区域分类。

模型种类（首版只支持沪深300）：
    historical_fixed_120m  固定 120 月窗口（36 月步进），新完整窗口出现后增加，不覆盖旧窗口
    trailing_120m          最近 120 个完整自然月，新完整月到来后生成新版本
    since_inception        2005-04 至最近完整月，新完整月到来后生成新版本

全历史回溯图与当前页"成立以来"模型在同一数据版本/截止月份时复用同一模型。
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

from src.core.regression import ALGORITHM_VERSION, Coefficients

KIND_FIXED = "historical_fixed_120m"
KIND_TRAILING = "trailing_120m"
KIND_SINCE_INCEPTION = "since_inception"
CURRENT_MODEL_KINDS = (KIND_TRAILING, KIND_SINCE_INCEPTION)

INCEPTION_MONTH = "2005-04"


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


def data_hash(closes: list[float]) -> str:
    """训练用月收盘序列的哈希（同月内价格变化不改变完整月序列 → 哈希稳定）。"""
    payload = json.dumps([round(c, 6) for c in closes], separators=(",", ":"))
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
