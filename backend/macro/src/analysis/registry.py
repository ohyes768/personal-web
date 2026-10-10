"""Business chart definitions; adding a chart does not duplicate the assistant."""
from dataclasses import dataclass


@dataclass(frozen=True)
class SeriesDefinition:
    id: str
    label: str
    store: str
    column: str
    unit: str = "%"
    is_rate: bool = True
    relative_change: bool = False


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

# Fixed daily panels share the same raw evidence and session pipeline.
DAILY_SERIES = {
    s.id: s for s in (
        *CHARTS["rates.china-bonds"].series,
        SeriesDefinition("dr007", "DR007", "dr007", "dr007"),
        SeriesDefinition("sofr", "SOFR", "ted_spread", "SOFR"),
        SeriesDefinition("us_3m", "美债3个月收益率", "us_treasuries", "美债3m"),
        SeriesDefinition("us_2y", "美债2年收益率", "us_treasuries", "美债2y"),
        SeriesDefinition("us_10y", "美债10年收益率", "us_treasuries", "美债10y"),
        SeriesDefinition("ted_spread", "SOFR−美债3个月利差", "ted_spread", "TED利差"),
        SeriesDefinition("dxy", "美元指数", "exchange_rates", "美元指数", "点", relative_change=True),
        SeriesDefinition("usd_cny", "USD/CNY", "exchange_rates", "美元人民币", "人民币/美元", relative_change=True),
        SeriesDefinition("usd_jpy", "USD/JPY", "exchange_rates", "美元日元", "日元/美元", relative_change=True),
        SeriesDefinition("usd_eur", "USD/EUR", "exchange_rates", "美元欧元", "欧元/美元", relative_change=True),
        SeriesDefinition("vix", "VIX", "vix", "Close_VIX", "点"),
        SeriesDefinition("hibor", "HIBOR隔夜", "hibor", "HIBOR_Overnight"),
        SeriesDefinition("tga", "TGA余额", "tga", "Close_TGA", "百万美元"),
        SeriesDefinition("volume", "两市成交额", "volume", "total_amount_yi", "亿元"),
        SeriesDefinition("margin", "融资余额", "margin", "margin_balance_yi", "亿元"),
        SeriesDefinition("turnover", "换手率", "turnover", "turnover_rate", is_rate=False),
        SeriesDefinition("north_deal", "北向成交额", "fund_flow", "北向成交额", "亿元"),
        SeriesDefinition("south_net", "南向净流入", "fund_flow", "南向净流入", "亿元"),
        SeriesDefinition("gold", "黄金", "commodities", "黄金", "元/克", relative_change=True),
        SeriesDefinition("silver", "白银", "commodities", "白银", "元/克", relative_change=True),
        SeriesDefinition("oil", "原油", "commodities", "原油", "美元/桶", relative_change=True),
        SeriesDefinition("copper", "铜", "commodities", "铜", "美元/吨", relative_change=True),
        SeriesDefinition("hk_hsi", "恒生指数", "indices", "HKHSI", "点", relative_change=True),
        SeriesDefinition("sh_000001", "上证指数", "indices", "SH000001", "点", relative_change=True),
        SeriesDefinition("spx", "标普500", "indices", "SPX", "点", relative_change=True),
        SeriesDefinition("ixic", "纳斯达克", "indices", "IXIC", "点", relative_change=True),
        SeriesDefinition("dji", "道琼斯", "indices", "DJI", "点", relative_change=True),
    )
}

_FIXED_PANELS = (
    ("rates.short-rates", "短端利率：DR007、SOFR与美债3M", ("dr007", "sofr", "us_3m"),
     "DR007反映中国银行间7天资金价格；SOFR是美国隔夜担保融资利率；美债3M是三个月国债收益率。单位均为%，但市场、期限与口径不同。",
     "分别描述中国和美国短端资金价格，不把跨市场利差直接解释为套利机会。"),
    ("rates.ted", "SOFR与美债3M利差", ("ted_spread",),
     "这里的TED标签实际表示SOFR减美债3个月收益率，单位为百分点；不是传统LIBOR减国库券的TED利差。",
     "严格说明这是SOFR−美债3M口径，不能套用传统TED信用风险阈值。"),
    ("treasury-exchange.yields", "中美债券收益率", ("us_3m", "us_2y", "us_10y", "cn_10y"),
     "收益率以%表示。美国不同期限可观察收益率曲线；中国10年收益率属于另一货币市场，不能只凭收益率高低判断投资价值。",
     "比较收益率变化用bp；跨期限和跨币种比较说明口径差异，日期不一致时不要直接相减。"),
    ("treasury-exchange.fx", "美元指数与汇率", ("dxy", "usd_cny", "usd_jpy", "usd_eur"),
     "图中显示各曲线相对各自首个有效展示值的变化。分析使用原始指数与汇率，区间涨幅以各自首个原始观测为基期，缩放后可能与图的基期不同。USD/CNY上升表示一美元兑换更多人民币。",
     "原始汇率不能按绝对值横向比较。区间涨幅引用change_percent及其起止日期，不称为图上纵轴值；USD/EUR是欧元/美元，不能反向解释。"),
    ("liquidity.vix", "VIX波动率指数", ("vix",),
     "VIX反映期权市场对标普500未来约30天波动的预期，以指数点表示；它不是股票涨跌幅，也不直接预测涨跌方向。",
     "描述波动预期的变化，不把VIX当成确定方向或买卖信号。"),
    ("liquidity.hibor", "香港隔夜拆息", ("hibor",),
     "HIBOR隔夜是香港银行间隔夜资金利率，单位为%；节假日与短期资金需求可能影响波动。",
     "描述香港短期资金价格，不能仅凭单日尖峰断言政策或资金危机。"),
    ("liquidity.tga", "美国财政部账户余额", ("tga",),
     "TGA是美国财政部在美联储的账户余额。原始证据为百万美元，图中为千亿美元：原始值乘0.00001。余额变化不等于市场资金流入流出的一比一变化。",
     "引用时明确单位；百万美元除100000得到图示千亿美元。财政收支与其他流动性因素未提供时不推断确定市场影响。"),
    ("market-sentiment", "A股成交、融资与换手率", ("volume", "margin", "turnover"),
     "成交额是每日交易金额，融资余额是尚未偿还的融资存量，均为亿元；换手率为%。双轴高度不可直接比较，融资余额不是当日净流入。",
     "分别描述交易活跃程度和融资存量；换手率变化用百分点，不能称利率bp；存量变化不等于全部市场资金净流入。"),
    ("fund-flow", "沪深港通：北向成交与南向净流入", ("north_deal", "south_net"),
     "北向成交额包含买卖交易，不能当作北向净买入；南向净流入有正负方向。二者单位均为亿元，但含义与市场不同。",
     "不得把北向成交额称为净流入；南向负值表示净流出，过零时不要计算百分比涨幅。"),
    ("commodities.precious", "黄金与白银", ("gold", "silver"),
     "黄金、白银报价单位为元/克，双轴尺度各自独立。报价变化反映价格，不等于持有收益，数据源和交易日也可能不同。",
     "用各自价格变化或区间涨幅比较，不能从双轴高度判断相对贵贱或编造供需事件。"),
    ("commodities.industrial", "原油与铜", ("oil", "copper"),
     "原油为美元/桶，铜为美元/吨；不同单位和双轴尺度不能直接比较价格高低。",
     "分别描述价格及共同日期变化；供需、汇率、宏观解释只能是可能性，不编造新闻。"),
    ("stock-indices.cn-hk", "恒生与上证指数", ("hk_hsi", "sh_000001"),
     "两指数均以点表示，但基期、成分及市场不同；绝对点数不能比较投资价值，港股与A股交易日可能不同。",
     "用各自区间涨幅描述表现，比较时注明起止日，跨市场日期不一致时使用共同日期；不将指数变化等同所有个股收益。"),
    ("stock-indices.us-growth", "标普500与纳斯达克", ("spx", "ixic"),
     "标普500与纳斯达克成分和权重不同，单位均为点；双轴高度及绝对点数不能直接比较表现。",
     "比较各自区间涨幅，不从指数走势确定行业原因；美国交易日期不代表与亚洲同一时刻。"),
    ("stock-indices.dow", "道琼斯指数", ("dji",),
     "道琼斯为价格加权股票指数，单位为点，不能代表所有美国股票的表现。",
     "描述指数点位变化和区间涨幅，不从曲线单独判断确定经济原因或未来方向。"),
)

for chart_id, title, ids, description, strategy in _FIXED_PANELS:
    CHARTS[chart_id] = ChartDefinition(
        chart_id, title, description, tuple(DAILY_SERIES[key] for key in ids),
        strategy=strategy,
    )
