"""Business chart definitions; adding a chart does not duplicate the assistant."""
from dataclasses import dataclass


@dataclass(frozen=True)
class SeriesDefinition:
    id: str
    label: str
    store: str
    column: str
    unit: str = "%"


@dataclass(frozen=True)
class ChartDefinition:
    id: str
    title: str
    description: str
    series: tuple[SeriesDefinition, ...]
    references: tuple[SeriesDefinition, ...] = ()
    strategy: str = "描述各曲线的变化及关系；双轴高度不可直接比较，不把相关性解释为因果。"
    version: str = "1"


CHARTS = {
    "rates.china-bonds": ChartDefinition(
        "rates.china-bonds", "中国国债：10年收益率与10Y−2Y利差",
        "10年收益率是持有十年期国债的收益率；10Y−2Y是十年期减两年期收益率。"
        "例如2%减1.5%等于0.5个百分点（50bp）。线越高，长短期收益率差距越大。"
        "债券收益率上升通常伴随已有债券价格下降；仅凭利差不能判断经济好坏。",
        (
            SeriesDefinition("cn_10y", "中国10年国债收益率", "china_bond", "中国10y"),
            SeriesDefinition("cn_10y_2y", "中国10Y−2Y利差", "china_bond", "中国10年-2年"),
        ),
        (SeriesDefinition("dr007", "DR007（参考）", "dr007", "dr007"),),
        "分解利差变化=10年收益率变化−2年收益率变化。2年收益率是同日10年收益率减利差推导，"
        "必须注明推导；结合DR007解释短期资金，但不得编造新闻或确定因果。",
    ),
}
