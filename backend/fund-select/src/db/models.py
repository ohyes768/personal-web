"""
ORM 模型（SQLAlchemy 2.x）
"""
from datetime import UTC, date, datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Float, Index, Integer, String
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
    mgr_days = Column(Integer, nullable=True)
    mgr_experience_years = Column(Float, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
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
    # / 'unavailable:no_field' / 'unavailable:exhausted'
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


class FundRiskMetrics(Base):
    """风险/超额指标（phase2-B，近 3 年窗口，基于累计净值 vs benchmark TRI）

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
