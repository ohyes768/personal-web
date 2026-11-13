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
    # 共管取最长（筛选口径）；mgr_experience_years 为共管最短（历史保守口径）
    mgr_experience_years_max: Optional[float] = None
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


class ManagerListItem(BaseModel):
    """经理列表行（/managers/screen）"""
    manager_id: str
    name: str
    company: Optional[str] = None
    career_years: Optional[float] = None
    current_scale_yi: Optional[float] = None
    current_fund_count: Optional[int] = None
    managed_fund_count: Optional[int] = None
    weighted_annual: Optional[float] = None      # 管理时长加权年化 %
    longest_tenure_annual: Optional[float] = None
    longest_tenure_years: Optional[float] = None
    max_drawdown: Optional[float] = None         # 负值 %
    sharpe: Optional[float] = None
    calmar: Optional[float] = None
    representative_fund: Optional[str] = None
    # ── 派生指标（11-12 调研：tenures 聚合，无额外采集）──
    tenure_win_rate: Optional[float] = None      # 任期胜率 %（tenure_return>0 占比）
    solo_ratio: Optional[float] = None           # 独管比例 %（在管基金中仅自己一位经理）
    rep_divergence: Optional[float] = None       # 代表作背离 pp（最长任期年化 − 加权年化）
    current_weighted_annual: Optional[float] = None  # 在管年化 %（仅 is_current 主动权益段）
    board_on_current: int = 0                        # 在管基金中上过夏普榜的数量（历史累计）
    current_fund_total: int = 0                      # 当前在管基金数（tenures.is_current 计数）


class TenureAffiliation(BaseModel):
    """任期基金的跨 tab 归属（徽章 + 跳转落点）"""
    tab: Optional[str] = None               # bond / stock / discovery-bond / discovery-stock
    board_weeks: int = 0                    # 上过夏普榜的周数（历史累计，complete 周）
    fund_name_market: Optional[str] = None  # funds 表正式名称（档案快照可能过时）


class ManagerTenureItem(BaseModel):
    fund_code: str
    fund_name: Optional[str] = None
    fund_type: Optional[str] = None
    size_yi: Optional[float] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    tenure_days: Optional[int] = None
    tenure_return: Optional[float] = None
    annual_return: Optional[float] = None
    is_current: bool = True
    affiliation: Optional[TenureAffiliation] = None


class ManagerDetailResponse(ManagerListItem):
    career_days: Optional[int] = None
    tenures: list[ManagerTenureItem] = []


class ManagerScreenResponse(BaseModel):
    total: int
    items: list[ManagerListItem]


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
    mgr_experience_years_max: Optional[float] = None
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
    """榜单列表项（R3：排序 (listed_weeks DESC, latest_sharpe DESC, code ASC)）

    v2（11-13 任务）：listed_weeks 改为 52 周窗口内计数；新增近12周达标
    与同类分位展示字段。
    """
    code: str
    name: str                      # 最近上榜观测的名称快照（改名不抹历史）
    listed_weeks: int              # 52 周窗口内在榜周数
    consecutive_weeks: int         # 窗口内最近一段连续在榜周数
    latest_sharpe: Optional[float] = None  # 最近上榜夏普（不是「当前夏普」）
    last_listed_week: Optional[date] = None
    on_latest_board: bool = False  # 是否在最新成功（complete）榜单内
    ret_1y: Optional[float] = None  # 近 1 年收益（FundPerformance，回退 MarketFundRank；仅展示）
    ret_3y: Optional[float] = None  # 近 3 年收益（同上）
    near_12w_qualified: Optional[int] = None  # 近12周夏普≥0.8 的周数
    near_12w_total: Optional[int] = None      # 分母（不足12周为实际周数）
    peer_pct: Optional[float] = None          # 同类排名分位（%，如 14.2）
    peer_as_of: Optional[str] = None          # 同类排名数据日期 ISO


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


# ──────────────────────────────────────────────────────────────────
# 夏普走势（GET /api/funds/sharpe-trend/{code}），任务 11-13-fund-sharpe-trend
# ⚠ 每个顶层字段都必须显式声明：response_model 序列化会静默丢弃未声明字段
#   （contracts §3a 陷阱）。后端 DTO 加字段要三处同步：models.py ↔
#   apps/fund-select/src/lib/sharpe-trend.ts ↔ 页面消费。
# ──────────────────────────────────────────────────────────────────

class SharpeTrendPointDTO(BaseModel):
    """一个周观测点：该自然周最后一个交易日的 trailing-3y 夏普。

    sharpe=None 表示该周样本不足或无定义（前端断线不补零）。
    """
    date: date
    sharpe: Optional[float] = None
    sample_days: int = 0


class SharpeTrendStatsDTO(BaseModel):
    """展示区间内稳定性统计（None 表示无定义 / 点数不足）"""
    threshold: float = 0.8
    current: Optional[float] = None
    max: Optional[float] = None
    min: Optional[float] = None
    mean: Optional[float] = None
    above_count: int = 0
    valid_count: int = 0
    above_ratio: Optional[float] = None
    consecutive_above: int = 0
    longest_below: int = 0
    trend_12w: Optional[float] = None


class SharpeTrendResponse(BaseModel):
    """单基金夏普走势响应（现算，不落库）。

    rf_basis：zero = risk_free_rate 表为空按 rf=0（生产库现状）；rate = 用库内利率。
    diagnostics：insufficient_history / no_valid_points / nav_end_date / total_points。
    """
    code: str
    name: Optional[str] = None
    range: str = "all"
    rf_basis: str = "zero"
    algorithm_version: str = "trend-v1"
    threshold: float = 0.8
    points: list[SharpeTrendPointDTO] = []
    stats: SharpeTrendStatsDTO = SharpeTrendStatsDTO()
    diagnostics: dict = {}
