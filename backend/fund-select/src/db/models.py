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
