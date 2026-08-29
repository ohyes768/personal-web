"""数据模型定义"""
from __future__ import annotations

from pydantic import BaseModel
from datetime import date
from typing import Optional, Dict, List


class TreasuryData(BaseModel):
    """国债数据"""

    date: date
    value: Optional[float] = None


class USTreasuries(BaseModel):
    """美国国债数据"""

    m3: TreasuryData
    y2: TreasuryData
    y10: TreasuryData


class EUTreasuries(BaseModel):
    """欧洲国债数据（德国）"""

    m3: TreasuryData
    y2: TreasuryData
    y10: TreasuryData


class JPTreasuries(BaseModel):
    """日本国债数据"""

    m3: Optional[TreasuryData] = None
    y2: Optional[TreasuryData] = None
    y10: TreasuryData


class USTreasuriesUpdateData(BaseModel):
    """美债更新响应数据"""

    us_treasuries: USTreasuries


class EUTreasuriesUpdateData(BaseModel):
    """欧债更新响应数据"""

    eu_treasuries: EUTreasuries


class JPTreasuriesUpdateData(BaseModel):
    """日债更新响应数据"""

    jp_treasuries: JPTreasuries


class MacroData(BaseModel):
    """宏观经济数据"""

    us_treasuries: USTreasuries
    eu_treasuries: EUTreasuries
    jp_treasuries: JPTreasuries


class ExchangeRateData(BaseModel):
    """汇率数据"""

    date: date
    value: Optional[float] = None


class ExchangeRates(BaseModel):
    """汇率数据"""

    dollar_index: ExchangeRateData
    usd_cny: ExchangeRateData
    usd_jpy: ExchangeRateData
    usd_eur: ExchangeRateData


class ExchangeRatesUpdateData(BaseModel):
    """汇率更新响应数据"""

    exchange_rates: ExchangeRates


class VIXData(BaseModel):
    """VIX恐慌指数数据"""

    date: date
    value: Optional[float] = None


class VIXUpdateData(BaseModel):
    """VIX更新响应数据"""

    vix: VIXData


class TGAData(BaseModel):
    """TGA 账户余额数据（单位：百万美元）"""

    date: date
    value: Optional[float] = None


class TGAUpdateData(BaseModel):
    """TGA 更新响应数据"""

    tga: TGAData


class HIBORData(BaseModel):
    """HIBOR 隔夜拆息数据（单位：%）"""

    date: date
    value: Optional[float] = None


class HIBORUpdateData(BaseModel):
    """HIBOR 更新响应数据"""

    hibor: HIBORData


class DR007Data(BaseModel):
    """DR007（中国货币网7天质押式回购加权利率，单位：%）"""

    date: date
    value: Optional[float] = None


class DR007UpdateData(BaseModel):
    """DR007 更新响应数据"""

    dr007: DR007Data


class VolumeData(BaseModel):
    """两市合计成交额（单位：亿元）"""

    date: date
    value: Optional[float] = None


class VolumeUpdateData(BaseModel):
    """两市成交额 更新响应数据"""

    volume: VolumeData


class TurnoverData(BaseModel):
    """两市加权换手率（单位：%）"""

    date: date
    value: Optional[float] = None


class TurnoverUpdateData(BaseModel):
    """换手率 更新响应数据"""

    turnover: TurnoverData


class MarginData(BaseModel):
    """融资余额（单位：亿元）"""

    date: date
    value: Optional[float] = None


class MarginUpdateData(BaseModel):
    """融资余额 更新响应数据"""

    margin: MarginData


class VolumeTurnoverHistoryData(BaseModel):
    """两市成交额/换手率历史回补结果"""

    volume_rows: int = 0        # 成交额写入行数
    turnover_rows: int = 0      # 换手率写入行数
    start: str                  # 实际起始日期
    end: str                    # 实际结束日期


class VolumeTurnoverHistoryUpdateData(BaseModel):
    """两市成交额/换手率 历史回补响应数据"""

    history: VolumeTurnoverHistoryData


class FundFlowData(BaseModel):
    """资金流向数据"""

    date: date
    net_flow: Optional[float] = None  # 净流入（亿元）
    buy: Optional[float] = None       # 买入额（亿元）
    sell: Optional[float] = None      # 卖出额（亿元）


class FundFlow(BaseModel):
    """资金流向"""

    north: FundFlowData  # 北向资金（港股通→A股）
    south: FundFlowData  # 南向资金（A股→港股通）


class FundFlowCumulativeData(BaseModel):
    """资金流向累计数据"""

    date: date
    cum_7d: Optional[float] = None  # 7日累计净流入（亿元）
    cum_30d: Optional[float] = None  # 30日累计净流入（亿元）


class FundFlowWithCumulative(BaseModel):
    """资金流向（包含累计数据）"""

    north: FundFlowData  # 北向资金（港股通→A股）
    south: FundFlowData  # 南向资金（A股→港股通）
    north_cumulative: FundFlowCumulativeData  # 北向资金累计数据
    south_cumulative: FundFlowCumulativeData  # 南向资金累计数据


class FundFlowUpdateData(BaseModel):
    """资金流向更新响应数据"""

    fund_flow: FundFlow


class FundFlowCumulativeResponse(BaseModel):
    """资金流向累计数据响应"""

    north_cumulative: FundFlowCumulativeData  # 北向资金累计数据
    south_cumulative: FundFlowCumulativeData  # 南向资金累计数据


class FundFlowHistoryItem(BaseModel):
    """资金流向历史数据项"""

    date: str
    north_net: Optional[float] = None    # 北向净流入
    north_buy: Optional[float] = None    # 北向买入
    north_sell: Optional[float] = None   # 北向卖出
    south_net: Optional[float] = None    # 南向净流入
    south_buy: Optional[float] = None    # 南向买入
    south_sell: Optional[float] = None   # 南向卖出


class FundFlowHistoryResponse(BaseModel):
    """资金流向历史数据响应"""

    data: List[FundFlowHistoryItem]


class MacroDataWithRates(BaseModel):
    """宏观经济数据（包含汇率）"""

    us_treasuries: USTreasuries
    eu_treasuries: EUTreasuries
    jp_treasuries: JPTreasuries
    exchange_rates: ExchangeRates


class MacroDataWithRatesAndVIX(BaseModel):
    """宏观经济数据（包含汇率和VIX）"""

    us_treasuries: USTreasuries
    eu_treasuries: EUTreasuries
    jp_treasuries: JPTreasuries
    exchange_rates: ExchangeRates
    vix: VIXData


class UpdateResponse(BaseModel):
    """更新响应"""

    success: bool
    message: str
    data: Optional[
        USTreasuriesUpdateData
        | EUTreasuriesUpdateData
        | JPTreasuriesUpdateData
        | MacroData
        | ExchangeRatesUpdateData
        | MacroDataWithRates
        | VIXUpdateData
        | TGAUpdateData
        | HIBORUpdateData
        | MacroDataWithRatesAndVIX
        | FundFlowUpdateData
        | ChinaBondUpdateData
        | TedSpreadUpdateData
        | CommoditiesUpdateData
        | IndicesUpdateData
        | DR007UpdateData
        | VolumeUpdateData
        | TurnoverUpdateData
        | MarginUpdateData
        | VolumeTurnoverHistoryUpdateData
    ] = None
    updated_at: Optional[str] = None
    error_code: Optional[str] = None


class DataResponse(BaseModel):
    """数据查询响应"""

    success: bool
    message: str
    data: Optional[Dict] = None
    error_code: Optional[str] = None


class HealthResponse(BaseModel):
    """健康检查响应"""

    status: str
    service: str
    version: str
    last_update: Optional[str] = None


class ChinaBondData(BaseModel):
    """中国国债数据"""

    date: date
    value: Optional[float] = None  # 10年期国债收益率（%）


class ChinaBondUpdateData(BaseModel):
    """中国国债更新响应数据"""

    china_bond_10y: ChinaBondData


class TedSpreadData(BaseModel):
    """TED利差数据"""

    date: date
    sofr: Optional[float] = None    # SOFR 利率（%）
    us_3m: Optional[float] = None   # 美国3个月国债收益率（%）
    ted_spread: Optional[float] = None  # TED利差 = SOFR - DGS3MO（%）


class TedSpreadUpdateData(BaseModel):
    """TED利差更新响应数据"""

    ted_spread: TedSpreadData


class CommoditiesData(BaseModel):
    """商品数据（黄金/白银/原油/铜，统一走阿里云 alirmcom2）"""

    date: date
    gold: Optional[float] = None     # 黄金（元/克，SGEAU9999）
    silver: Optional[float] = None   # 白银（元/克，SGEAG9999）
    oil: Optional[float] = None      # 原油（美元/桶，UKOIL）
    copper: Optional[float] = None   # 铜（美元/吨，USHG）


class CommoditiesUpdateData(BaseModel):
    """商品更新响应数据"""

    commodities: CommoditiesData


class IndicesData(BaseModel):
    """5 个全球股指 K 线数据（恒生/上证/标普500/纳指/道指，统一走阿里云 alirmcom2 comkm）"""

    date: date
    HKHSI: Optional[float] = None       # 恒生指数
    SH000001: Optional[float] = None    # 上证指数
    SPX: Optional[float] = None         # 标普500
    IXIC: Optional[float] = None        # 纳斯达克综合
    DJI: Optional[float] = None         # 道琼斯


class IndicesUpdateData(BaseModel):
    """股指更新响应数据"""

    indices: IndicesData


# === 宏观信号数据模型(对齐前端 MacroSignalSnapshot shape) ===

class MacroIndicator(BaseModel):
    """单个指标(三时间都是指标级)

    - data_date:       数据时间(指标数值所属/发布日期)
    - analyzed_at:     分析时间(skill 生成该值的时间,ISO timestamp)
    - next_release_at: 下个周期预期发布日期(自报优先,后端规则兜底)
    - frequency:       发布频率 'daily'/'monthly'(日频前端不渲染「下次」段)
    - updated_at:      兼容别名 = data_date,前端迁移完成后删除
    """
    key: str
    value: Optional[float] = None
    updated_at: Optional[str] = None       # 'YYYY-MM-DD',兼容别名 = data_date
    data_date: Optional[str] = None        # 'YYYY-MM-DD',数据时间
    analyzed_at: Optional[str] = None      # ISO timestamp,分析时间
    next_release_at: Optional[str] = None  # 'YYYY-MM-DD',下个周期预期发布日
    next_release_note: Optional[str] = None  # 预期口径说明,如「CPI/PPI 每月9日发布」
    frequency: Optional[str] = None        # 'daily' | 'monthly',自报优先、规则表兜底;null=未知
    month_avg: Optional[float] = None      # 日频指标的月均值(skill 计算,透传;与 value 同采样月)


class MacroSignalGroup(BaseModel):
    """一个分组(6 大主题之一)"""
    conclusion: Optional[str] = None
    total_score: Optional[float] = None  # 维度总分(0-100,skill 评分框架输出)
    indicators: List[MacroIndicator] = []


class MacroSignalSnapshot(BaseModel):
    """一个月快照 = 6 个分组"""
    month: str  # 'YYYY-MM'
    groups: Dict[str, MacroSignalGroup]  # 6 个 dimension key
    generated_at: Optional[str] = None  # 所有指标 analyzed_at 的最大值(全页最新分析时间)


class MacroSignalResponse(BaseModel):
    """GET /api/macro/signal 响应"""
    success: bool = True
    data: MacroSignalSnapshot


class MacroMonthsResponse(BaseModel):
    """GET /api/macro/months 响应"""
    months: List[str] = []  # 降序


# === 日频快照数据模型(信号首页 · 日频模式) ===

class DailyIndicator(BaseModel):
    """日频快照单个指标

    - value/prev_value: 所选日期(或回退)的值与其前一个有值日的值(前端算日变化)
    - data_date: 实际数据日期;≠ 所选 date 即发生了回退(如 15:00 后当日未入库)
    """
    key: str                          # 与前端 INDICATOR_LABELS key 对齐
    value: Optional[float] = None
    prev_value: Optional[float] = None
    data_date: Optional[str] = None   # 'YYYY-MM-DD'


class DailyGroup(BaseModel):
    """日频快照一个分组(3 大维度之一;无 skill 评分,故无 conclusion/total_score)"""
    indicators: List[DailyIndicator] = []


class DailySnapshotData(BaseModel):
    """GET /api/macro/daily-snapshot 数据体"""
    date: str                     # 实际生效日期 'YYYY-MM-DD'(date 参数或 15:00 规则推导)
    dates: List[str] = []         # 可选日期列表(降序,A股交易日近 60 个 ∪ 今日)
    groups: Dict[str, DailyGroup]  # 3 个 dimension key


class DailySnapshotResponse(BaseModel):
    """GET /api/macro/daily-snapshot 响应"""
    success: bool = True
    data: DailySnapshotData
