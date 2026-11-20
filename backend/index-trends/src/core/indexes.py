"""指数注册表：本服务支持观察的指数清单。

一个指数 = 代码 + 腾讯行情 symbol + 名称 + 起始边界。算法层（通道拟合、
周线模型、交易日历）不感知指数差异，只按传进来的 index_code 落库与计算。

新增指数只需在 INDEXES 追加一条：不新增表、不改存储结构、不改接口形状。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IndexDef:
    """一个可观察指数的全部静态属性。"""

    code: str
    """指数代码（字符串，全链路主键）。"""

    symbol: str
    """腾讯 fqkline 的 symbol（如 sh000300 / sz399673）。"""

    name: str
    """展示名称。"""

    inception_month: str
    """价格指数起点月（YYYY-MM），月线归档用。"""

    inception_week: str
    """起点所在自然周的周一（YYYY-MM-DD）。成立以来模型从这里起算。"""

    earliest_weekly: str
    """周K 必须覆盖到此日或更早；晚于它视为供应商数据不完整。"""

    has_trend: bool = True
    """是否提供走势通道。False = 只做估值分位（不采行情、不出通道图）。"""


INDEXES: tuple[IndexDef, ...] = (
    IndexDef(
        code="000300",
        symbol="sh000300",
        name="沪深300",
        inception_month="2005-04",
        inception_week="2005-04-04",
        earliest_weekly="2005-04-30",
    ),
    IndexDef(
        code="399673",
        symbol="sz399673",
        name="创业板50",
        inception_month="2014-06",
        inception_week="2014-06-16",
        # 指数 2014-06-18 发布；留一个月容差，避免供应商首周口径差异把刷新打死
        earliest_weekly="2014-07-15",
        # 只做 PB/PE 分位：不采行情、不出通道图（用户明确不需要通道）
        has_trend=False,
    ),
)

BY_CODE: dict[str, IndexDef] = {item.code: item for item in INDEXES}

DEFAULT_INDEX_CODE = INDEXES[0].code


def get_index(code: str) -> IndexDef | None:
    """按代码取指数；未知代码返回 None（由调用方决定 404 还是默认）。"""
    return BY_CODE.get(code)


def index_codes() -> tuple[str, ...]:
    return tuple(item.code for item in INDEXES)


def trend_index_codes() -> tuple[str, ...]:
    """只列出有走势通道的指数（行情刷新只该遍历这些）。"""
    return tuple(item.code for item in INDEXES if item.has_trend)
