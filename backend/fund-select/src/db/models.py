"""
ORM 模型（SQLAlchemy 2.x）
"""
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Fund(Base):
    """基金基础信息"""
    __tablename__ = "funds"

    code = Column(String(6), primary_key=True)
    name = Column(String(128), nullable=False, default="")
    fund_type = Column(String(64), nullable=False, default="")
    established_date = Column(Date, nullable=True)
    age_years = Column(Float, nullable=True)
    size_yi = Column(Float, nullable=True)
    mgr_name = Column(String(256), nullable=True)
    mgr_company = Column(String(128), nullable=True)
    # 共管基金的多经理聚合：min = 从业最短（最保守），max = 从业最长（老将）。
    # mgr_days / mgr_experience_years 保留 min 语义（历史口径，夏普榜单快照已冻结）。
    # 筛选（min_mgr_exp）改用 *_max：只要有资深经理在管即视为达标，
    # 避免「22 年老将 + 3 年新人」被记成 3 年而误杀（详见 design 说明）。
    mgr_days = Column(Integer, nullable=True)
    mgr_experience_years = Column(Float, nullable=True)
    mgr_days_max = Column(Integer, nullable=True)
    mgr_experience_years_max = Column(Float, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    # tab 分类（4 个 tab）：'bond'（债基·市场）/ 'stock'（股基·市场）/ 'other'（FOF/货币型/未分类）
    # 由 SUBCLASS_TO_CATEGORY 表按 akshare 子类映射得出，避免「指数型-固收」错归股基。
    market_type = Column(String(16), nullable=True, index=True)
    # akshare fund_name_em() 的「基金类型」原值（如 股票型、债券型-中短债、指数型-固收、QDII-普通股票）。
    # 用途：UI 多选筛选项 + 二次精确缩窄。
    market_subtype = Column(String(128), nullable=True, index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))


class FundPerformance(Base):
    """业绩指标（净值收益 / 回撤）"""
    __tablename__ = "fund_performance"

    code = Column(String(6), primary_key=True)
    as_of_date = Column(Date, nullable=False)
    nav_latest = Column(Float, nullable=True)
    nav_date = Column(Date, nullable=True)
    ret_1m = Column(Float, nullable=True)
    ret_6m = Column(Float, nullable=True)
    ret_1y = Column(Float, nullable=True)
    ret_3y = Column(Float, nullable=True)
    ret_5y = Column(Float, nullable=True)
    dd_1y = Column(Float, nullable=True)
    dd_3y = Column(Float, nullable=True)  # v1 筛选关键字段
    dd_5y = Column(Float, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    __table_args__ = (Index("ix_perf_dd3y", "dd_3y"),)


class FundFees(Base):
    """费率（契约对齐预研 cache/fees_{code}.json）"""
    __tablename__ = "fund_fees"

    code = Column(String(6), primary_key=True)
    fee_buy_small = Column(Float, nullable=True)      # 申购小额档（%）
    fee_redeem_lt7d = Column(Float, nullable=True)    # 持有 <7天 赎回费（%）
    fee_redeem_7d_1y = Column(Float, nullable=True)   # 7天~1年（%）
    fee_redeem_ge1y = Column(Float, nullable=True)    # ≥1年（%）
    fee_redeem_ge7d = Column(Float, nullable=True)    # ≥7天（部分基金仅有此档）
    fee_mgmt = Column(Float, nullable=True)           # 管理费（%/年）
    fee_custody = Column(Float, nullable=True)        # 托管费（%/年）
    fee_service = Column(Float, nullable=True)        # 销售服务费（%/年，C 类）
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))


class FundHoldingsBond(Base):
    """季报债券持仓（利率债/信用债/可转债分类）"""
    __tablename__ = "fund_holdings_bond"

    code = Column(String(6), primary_key=True)
    report_date = Column(Date, primary_key=True)
    rate_bond_pct = Column(Float, nullable=True)      # 利率债占净值比（%）
    credit_bond_pct = Column(Float, nullable=True)    # 信用债（%）
    convertible_pct = Column(Float, nullable=True)    # 可转债（%）
    top5_concentration = Column(Float, nullable=True) # 前五大集中度（%）
    top5_bonds = Column(String(512), nullable=True)   # 前五大债券描述
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))


class RefreshRun(Base):
    """刷新批次进度"""
    __tablename__ = "refresh_runs"

    task_id = Column(String(36), primary_key=True)
    status = Column(String(16), nullable=False, default="running")  # running/done/error
    total = Column(Integer, nullable=False, default=0)
    completed = Column(Integer, nullable=False, default=0)
    failed = Column(Integer, nullable=False, default=0)
    errors = Column(String(2048), nullable=True)  # JSON 数组字符串
    started_at = Column(DateTime, default=lambda: datetime.now(UTC))
    finished_at = Column(DateTime, nullable=True)


class FundAchievementRank(Base):
    """业绩排名（雪球 achievement_xq）

    每只基金多条记录，复合主键 (code, period_kind, period)。
    第一阶段仅用于决策"同类排名"展示；决策 7 不展示"周期最大回撒"列，
    但 achievement_xq 一次性返回，全量入表便于未来拓展。
    """
    __tablename__ = "fund_achievement_rank"

    code = Column(String(6), primary_key=True)
    period_kind = Column(String(32), primary_key=True)         # 年度业绩 / 季度业绩 / 周业绩
    period = Column(String(32), primary_key=True)               # 1y / 3y / 5y / 2025 / 成立以来
    ret = Column(Float, nullable=True)                          # 本产品区间收益（%）
    max_dd = Column(Float, nullable=True)                       # 本产品最大回撒（%，决定 7 不展示但保留列）
    peer_rank = Column(String(32), nullable=True)               # '1694/5606'
    as_of_date = Column(Date, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC),
                        onupdate=lambda: datetime.now(UTC))


class FundBenchmark(Base):
    """业绩比较基准 TRI 序列（参考日=1000 加权日收益复利累加）

    每只基金 × 交易日一行，复合主键 (code, date)。
    tri=NULL 表示无可用基准（如 968157 互认基金无「业绩比较基准」字段）。
    """
    __tablename__ = "fund_benchmark"

    code = Column(String(6), primary_key=True)
    date = Column(Date, primary_key=True)
    tri = Column(Float, nullable=True)
    source = Column(String(64), nullable=False, default="fetched")
    # 'fetched' / 'partial:fallback:sh000906' / 'fallback_chain:sh000906'
    # / 'unavailable:no_field' / 'unavailable:exhausted' / 'skipped:qdii'
    # / 'unavailable:unknown_majority'
    # （QDII/互认基金跳过合成，tri=NULL，基准相关指标显示 -；
    #   unknown_majority = 非停更收录指数缺失且 ≥50% 权重成分未收录，宁缺毋错不顶替）
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC),
                        onupdate=lambda: datetime.now(UTC))


class RiskFreeRate(Base):
    """无风险利率日频（主源中国国债 2Y，年化小数）"""
    __tablename__ = "risk_free_rate"

    date = Column(Date, primary_key=True)
    rate = Column(Float, nullable=False)
    source = Column(String(32), nullable=False, default="bond_zh_us_rate_2y")
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC),
                        onupdate=lambda: datetime.now(UTC))


class MarketFundRank(Base):
    """市场 tab 业绩（东方财富 rankhandler 批量接口）

    与 fund_performance 独立：
      - 老 yaml refresh 走 fund_performance（含 dd_3y + sharpe + ir + alpha + ...）
      - 市场 tab 走 market_fund_rank（9 个时间段涨幅：ret_1w/1m/3m/6m/1y/2y/3y/ytd/all）
    """
    __tablename__ = "market_fund_rank"

    code = Column(String(6), primary_key=True)
    nav_date = Column(Date, nullable=True)
    nav_latest = Column(Float, nullable=True)
    ret_1w = Column(Float, nullable=True)
    ret_1m = Column(Float, nullable=True)
    ret_3m = Column(Float, nullable=True)
    ret_6m = Column(Float, nullable=True)
    ret_1y = Column(Float, nullable=True)
    ret_2y = Column(Float, nullable=True)
    ret_3y = Column(Float, nullable=True)
    ret_ytd = Column(Float, nullable=True)
    ret_all = Column(Float, nullable=True)
    ft_code = Column(String(8), nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))


class FundRiskMetrics(Base):
    """风险/超额指标（phase2-B，近 3 年窗口，基于日增长率复权收益 vs benchmark TRI）

    benchmark 不可用（tri=NULL）或样本不足时各指标为 NULL。
    """
    __tablename__ = "fund_risk_metrics"

    code = Column(String(6), primary_key=True)
    sharpe = Column(Float, nullable=True)
    ir = Column(Float, nullable=True)
    alpha = Column(Float, nullable=True)          # T-M 截距年化
    gamma = Column(Float, nullable=True)          # T-M 二次项（日频原值）
    alpha_ir = Column(Float, nullable=True)
    excess_3y = Column(Float, nullable=True)      # 3 年累计超额（小数）
    sample_days = Column(Integer, nullable=True)  # 实际样本交易日数（诊断）
    as_of_date = Column(Date, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC),
                        onupdate=lambda: datetime.now(UTC))


class SharpeBoardWeek(Base):
    """夏普榜单周批次（每周一行；source+profile_version+week_start 联合唯一）

    周榜状态机：complete（已发布，冻结不可重写）/ failed / skipped_no_new_data
    （可同周重试）。running 不落表，复用 scheduler 内存状态。
    时间列保存 UTC 挂钟（naive），展示层转北京时间。
    profile_json 是完整规则副本（canonical JSON），规则变更换 profile_version 不改旧行。
    """
    __tablename__ = "sharpe_board_weeks"
    __table_args__ = (
        UniqueConstraint("source", "profile_version", "week_start",
                         name="uq_sharpe_board_weeks_source_version_week"),
        Index("ix_sharpe_board_weeks_source_week", "source", "week_start"),
    )

    id = Column(Integer, primary_key=True)               # 自增
    source = Column(String(32), nullable=False)          # 'stock' | 'discovery-stock'
    profile_version = Column(String(16), nullable=False)  # 'v1'
    week_start = Column(Date, nullable=False)            # 任务开始所在北京时间自然周的周一
    profile_json = Column(Text, nullable=False)          # 完整规则副本（canonical JSON）
    profile_hash = Column(String(64), nullable=False)    # canonical JSON sha256
    algorithm_version = Column(String(16), nullable=False)  # 夏普算法口径版本
    status = Column(String(32), nullable=False)          # complete|failed|skipped_no_new_data
    run_id = Column(String(64), nullable=True)           # 关联 RefreshRun.task_id
    trigger = Column(String(32), nullable=True)          # scheduled|manual
    started_at = Column(DateTime, nullable=False)        # 本轮采集开始时刻（UTC）
    finished_at = Column(DateTime, nullable=True)        # 本轮采集结束时刻（UTC）
    published_at = Column(DateTime, nullable=True)       # 发布时刻（UTC，仅 complete）
    selected_count = Column(Integer, nullable=False, default=0)
    errors_json = Column(Text, nullable=True)            # JSON 数组：本轮采集错误
    diagnostics_json = Column(Text, nullable=True)       # JSON 对象：诊断（样本未更新等）
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC),
                        onupdate=lambda: datetime.now(UTC))


class SharpeBoardObservation(Base):
    """夏普榜单周观测（一只基金一周一行；week_id+code 联合唯一）

    不引用实时 Fund 表（无外键到 funds）：基金清盘/改名/失活不抹掉历史；
    name 是入选时名称快照。sharpe 只存有限数（NULL/NaN/Infinity 不写观测）。
    """
    __tablename__ = "sharpe_board_observations"
    __table_args__ = (
        UniqueConstraint("week_id", "code", name="uq_sharpe_board_obs_week_code"),
        Index("ix_sharpe_board_obs_code", "code"),
    )

    id = Column(Integer, primary_key=True)  # 自增
    week_id = Column(Integer, ForeignKey("sharpe_board_weeks.id"), nullable=False, index=True)
    code = Column(String(6), nullable=False)
    name = Column(String(128), nullable=False)  # 入选时名称快照
    sharpe = Column(Float, nullable=False)      # 近三年夏普（有限数）
    metric_calculated_at = Column(DateTime, nullable=True)  # 指标计算时刻（UTC，未知留空）
    returns_end_date = Column(Date, nullable=True)          # 实际收益样本截止日（未知留空）
    sample_days = Column(Integer, nullable=True)
    evidence_json = Column(Text, nullable=True)  # 筛选字段 + 来源刷新 ID（JSON）
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC),
                        onupdate=lambda: datetime.now(UTC))
