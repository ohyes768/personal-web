"""
Pydantic DTO
"""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class FeeDTO(BaseModel):
    fee_buy_small: Optional[float] = None
    fee_redeem_lt7d: Optional[float] = None
    fee_redeem_7d_1y: Optional[float] = None
    fee_redeem_ge1y: Optional[float] = None
    fee_redeem_ge7d: Optional[float] = None
    fee_mgmt: Optional[float] = None
    fee_custody: Optional[float] = None
    fee_service: Optional[float] = None


class RankPercentileDTO(BaseModel):
    """同类排名百分位（_parse_peer_rank 输出）"""
    pct: Optional[float] = None
    total: Optional[int] = None
    rank: Optional[int] = None


class FundListItem(BaseModel):
    """筛选列表项（主表一行）"""
    code: str
    name: str
    fund_type: str
    size_yi: Optional[float] = None
    age_years: Optional[float] = None
    dd_3y: Optional[float] = None
    ret_1m: Optional[float] = None
    ret_1y: Optional[float] = None
    ret_3y: Optional[float] = None
    ret_5y: Optional[float] = None
    sharpe: Optional[float] = None      # phase2-B 风险指标（近 3 年）
    ir: Optional[float] = None
    alpha: Optional[float] = None       # T-M 截距年化
    gamma: Optional[float] = None       # T-M 二次项
    alpha_ir: Optional[float] = None
    excess_3y: Optional[float] = None   # 3 年累计超额（小数）
    mgr_name: Optional[str] = None
    mgr_company: Optional[str] = None
    mgr_experience_years: Optional[float] = None
    rate_bond_pct: Optional[float] = None
    fee_mgmt: Optional[float] = None
    fee_custody: Optional[float] = None
    fee_service: Optional[float] = None
    fee_annual: Optional[float] = None  # 管理费+托管费(+销售服务费)
    updated_at: Optional[datetime] = None
    # L1 业绩（MarketFundRank 派生；全量刷新后才有）
    mr_nav_latest: Optional[float] = None
    mr_nav_date: Optional[date] = None
    mr_ret_1w: Optional[float] = None
    mr_ret_1m: Optional[float] = None
    mr_ret_3m: Optional[float] = None
    mr_ret_6m: Optional[float] = None
    mr_ret_1y: Optional[float] = None
    mr_ret_2y: Optional[float] = None
    mr_ret_3y: Optional[float] = None
    mr_ret_ytd: Optional[float] = None
    mr_ret_all: Optional[float] = None
    # L5 同类排名（雪球 achievement_xq；股票 tab 有，债基 tab 永远 null）
    rank_ytd: Optional[RankPercentileDTO] = None
    rank_1y:  Optional[RankPercentileDTO] = None
    rank_3y:  Optional[RankPercentileDTO] = None
    rank_5y:  Optional[RankPercentileDTO] = None


class ScreenResponse(BaseModel):
    total: int
    items: list[FundListItem]


class HoldingsDTO(BaseModel):
    report_date: Optional[date] = None
    rate_bond_pct: Optional[float] = None
    credit_bond_pct: Optional[float] = None
    convertible_pct: Optional[float] = None
    top5_concentration: Optional[float] = None
    top5_bonds: Optional[str] = None


class FundDetailResponse(BaseModel):
    code: str
    name: str
    fund_type: str
    established_date: Optional[date] = None
    age_years: Optional[float] = None
    size_yi: Optional[float] = None
    mgr_name: Optional[str] = None
    mgr_company: Optional[str] = None
    mgr_days: Optional[int] = None
    mgr_experience_years: Optional[float] = None
    is_active: bool = True
    # 业绩全量
    ret_1m: Optional[float] = None
    ret_6m: Optional[float] = None
    ret_1y: Optional[float] = None
    ret_3y: Optional[float] = None
    ret_5y: Optional[float] = None
    dd_1y: Optional[float] = None
    dd_3y: Optional[float] = None
    dd_5y: Optional[float] = None
    nav_latest: Optional[float] = None
    nav_date: Optional[date] = None
    # 风险/超额指标（phase2-B；FundRiskMetrics 行缺失时全为 None，前端 RiskMetricsGrid 显示「无数据」）
    sharpe: Optional[float] = None
    ir: Optional[float] = None
    alpha: Optional[float] = None
    gamma: Optional[float] = None
    alpha_ir: Optional[float] = None
    excess_3y: Optional[float] = None
    fees: FeeDTO = FeeDTO()
    holdings: Optional[HoldingsDTO] = None
    achievement_ranks: list["AchievementRankDTO"] = []


class AchievementRankDTO(BaseModel):
    period_kind: str
    period: str
    ret: Optional[float] = None
    peer_rank: Optional[str] = None


class RefreshResponse(BaseModel):
    task_id: str
    status: str = "started"


class RefreshStatusResponse(BaseModel):
    task_id: str
    status: str
    total: int = 0
    completed: int = 0
    failed: int = 0
    errors: list[str] = []


class StatsResponse(BaseModel):
    total: int
    with_performance: int
    with_fees: int
    with_holdings: int
    last_refresh_at: Optional[datetime] = None
