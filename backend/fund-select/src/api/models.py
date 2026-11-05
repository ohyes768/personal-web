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
    market_subtype: Optional[str] = None  # akshare 精确子类（fund_type 全空，用这个做 UI 展示）
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


class SharpeBoardProfileDTO(BaseModel):
    """固定规则 profile（design：source/version/filters/prefilters/algorithm）"""
    source: str
    version: str
    filters: dict = {}
    collection_prefilters: dict = {}
    market_subtypes: Optional[list[str]] = None
    algorithm_version: str = ""


class SharpeBoardAttemptDTO(BaseModel):
    """最新一次周榜尝试（任意状态；失败时 errors 原文透出，R6/R7）

    时间展示北京时间（存储 UTC，design「新表」契约）。
    """
    week_start: date
    status: str
    trigger: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    selected_count: int = 0
    errors: list[str] = []


class SharpeBoardItemDTO(BaseModel):
    """榜单列表项（R3：排序 (listed_weeks DESC, latest_sharpe DESC, code ASC)）"""
    code: str
    name: str                      # 最近上榜观测的名称快照（改名不抹历史）
    listed_weeks: int              # 累计在榜周数（全历史）
    consecutive_weeks: int         # 最近一段连续在榜周数（缺席/未知中断）
    latest_sharpe: Optional[float] = None  # 最近上榜夏普（不是「当前夏普」）
    last_listed_week: Optional[date] = None
    on_latest_board: bool = False  # 是否在最新成功（complete）榜单内


class SharpeBoardSeriesDTO(BaseModel):
    """曲线序列（全部命中基金，不随 items 分页；values 长度 == weeks 长度）"""
    code: str
    name: str
    values: list[Optional[float]] = []  # 缺席/失败/停机周为 null，断线不补零


class SharpeBoardDiagnosticsDTO(BaseModel):
    """数据状态透明化（R6/R7：成功空榜/采集失败/样本未更新可区分）"""
    no_board_weeks: list[date] = []    # 周历内无 complete 榜的周（失败/停机/未跑）
    latest_diagnostics: dict = {}      # 最新尝试行的 diagnostics_json 原样（stale_codes 等）


class SharpeBoardResponse(BaseModel):
    """GET /api/funds/sharpe-board 响应

    ⚠ 每个顶层字段都必须在此显式声明：response_model 序列化会静默丢弃
    未声明字段（contracts §3a 陷阱）。
    """
    profile: SharpeBoardProfileDTO
    latest_published_week: Optional[date] = None  # 最新 complete 周周一（失败/停机时是旧榜日期）
    latest_attempt: Optional[SharpeBoardAttemptDTO] = None
    stale: bool = False            # 当前自然周无 complete 榜 → True，不冒充本周
    total: int = 0
    items: list[SharpeBoardItemDTO] = []
    weeks: list[date] = []         # 统一周历（周一日期），range 只裁起点
    series: list[SharpeBoardSeriesDTO] = []
    diagnostics: SharpeBoardDiagnosticsDTO = SharpeBoardDiagnosticsDTO()
