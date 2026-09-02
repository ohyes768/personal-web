"""
pytest 夹具：in-memory SQLite + 预置数据
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.db.models import Base, Fund, FundFees, FundHoldingsBond, FundPerformance


@pytest.fixture
def db_session():
    # StaticPool：in-memory SQLite 单连接共享（TestClient 的线程要用同一连接才能看到表）
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _mk_fund(code: str, **kw) -> Fund:
    """测试基金工厂：默认值可被 kw 覆盖"""
    defaults = dict(
        code=code,
        name=f"基金{code}",
        fund_type="债券型-长期纯债",
        age_years=5.0,
        size_yi=10.0,
        mgr_name="张三",
        mgr_company="某基金公司",
        mgr_days=3650,
        mgr_experience_years=10.0,
        is_active=True,
    )
    defaults.update(kw)
    return Fund(**defaults)


@pytest.fixture
def seeded_db(db_session, monkeypatch):
    """3 只代表性基金：
    A: 全字段，优等生
    B: 高回撤、年轻、小规模、资浅经理
    C: is_active=False（清盘），不应出现在筛选结果
    D: 无业绩记录（LEFT JOIN 应保留）
    """
    from pathlib import Path

    from src.utils.config import get_funds_config_path, get_stock_funds_config_path

    def _load(config_path=None):
        path = Path(config_path) if config_path is not None else get_funds_config_path()
        if path.resolve() == get_stock_funds_config_path().resolve() or path.name == "funds_stock.yaml":
            return []
        return ["000001", "000002", "000003", "000004"]

    monkeypatch.setattr("src.data.fund_universe.load_fund_codes", _load)
    db_session.add_all([
        _mk_fund("000001", name="基金A"),
        _mk_fund("000002", name="基金B", age_years=1.0, size_yi=0.5,
                 mgr_days=365, mgr_experience_years=1.0),
        _mk_fund("000003", name="基金C", is_active=False),
        _mk_fund("000004", name="基金D"),
    ])
    db_session.add_all([
        FundPerformance(code="000001", as_of_date=__import__("datetime").date(2026, 9, 1),
                        dd_3y=-3.0, ret_1y=2.0, ret_3y=8.0, ret_5y=20.0),
        FundPerformance(code="000002", as_of_date=__import__("datetime").date(2026, 9, 1),
                        dd_3y=-8.0, ret_1y=-1.0, ret_3y=-5.0, ret_5y=None),
        FundPerformance(code="000003", as_of_date=__import__("datetime").date(2026, 9, 1),
                        dd_3y=-1.0, ret_1y=1.0, ret_3y=3.0, ret_5y=5.0),
    ])
    db_session.add_all([
        FundFees(code="000001", fee_mgmt=0.3, fee_custody=0.1),
        FundFees(code="000002", fee_mgmt=0.5, fee_custody=0.15, fee_service=0.4),
        FundFees(code="000003", fee_mgmt=0.2, fee_custody=0.05),
    ])
    db_session.add_all([
        FundHoldingsBond(code="000001", report_date=__import__("datetime").date(2025, 12, 31),
                         rate_bond_pct=30.0, credit_bond_pct=50.0, convertible_pct=0.0),
        FundHoldingsBond(code="000002", report_date=__import__("datetime").date(2025, 12, 31),
                         rate_bond_pct=10.0, credit_bond_pct=20.0, convertible_pct=5.0),
    ])
    db_session.commit()
    return db_session
