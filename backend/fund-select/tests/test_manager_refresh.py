"""manager_refresh 编排单测：全 mock，不联网。"""
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from src.db.models import Fund, Manager, ManagerTenure
from src.services.manager_refresh import refresh


def _mk_table_row(mid, name, company, codes, days):
    return {"manager_id": mid, "name": name, "company": company,
            "fund_codes": codes, "career_days": days,
            "best_return_pct": 10.0, "current_scale_yi": 50.0}


def _tenures(code, ftype="混合型-偏股", days=3650, ret=100.0):
    return [{
        "fund_code": code, "fund_name": f"基金{code}", "fund_type": ftype,
        "size_yi": 10.0,
        "start_date": "2020-01-01", "end_date": None if ret >= 0 else "2023-01-01",
        "tenure_days": days, "tenure_return_pct": ret,
        "is_current": ret >= 0,
    }]


@pytest.fixture
def db_with_funds(db_session):
    db_session.add_all([
        Fund(code="000011", name="股票A", market_subtype="股票型", is_active=True),
        Fund(code="000022", name="偏股B", market_subtype="混合型-偏股", is_active=True),
        Fund(code="000033", name="债券C", market_subtype="债券型-长债", is_active=True),
    ])
    db_session.commit()
    return db_session


def test_full_flow_creates_managers_and_tenures(db_with_funds):
    table = [
        _mk_table_row("m1", "张三", "华夏基金", ["000011", "000022", "000033"], 5000),
        _mk_table_row("m2", "李四", "易方达基金", ["000033"], 5000),  # 只管债基 → scope 外
    ]
    tenures = _tenures("000011") + _tenures("000022")
    with patch("src.data.manager_profile_fetcher._get_with_retry") as _:
        pass  # 占位说明：providers 全部注入，不发真实请求

    stats = refresh(
        db_with_funds, task_id="t_mgr1", fetch_nav=False,
        table_provider=lambda: table,
        tenure_provider=lambda mid: tenures,
        nav_provider=lambda code: [],
        profile_fetch_delay_s=0,
    )

    # M0：两人都建骨架
    assert stats["managers_total"] == 2
    assert db_with_funds.get(Manager, "m1") is not None
    assert db_with_funds.get(Manager, "m2") is not None
    # M1：m1 命中主动权益（000011/000022），m2 只挂债基 → 不采档案
    assert stats["tenures_total"] == 2
    m1 = db_with_funds.get(Manager, "m1")
    assert m1.fetched_at is not None
    assert m1.career_years == round(5000 / 365.25, 2)
    # m2 未采档案
    assert db_with_funds.get(Manager, "m2").fetched_at is None
    # tenures 入库且年化已算
    rows = db_with_funds.query(ManagerTenure).filter_by(manager_id="m1").all()
    assert len(rows) == 2
    assert all(r.annual_return is not None for r in rows)
    # M4 聚合
    assert m1.tenure_weighted_annual is not None
    assert m1.representative_fund == "000011"
    # RefreshRun
    from src.db.models import RefreshRun
    run = db_with_funds.get(RefreshRun, "t_mgr1")
    assert run.status in ("done", "partial")


def test_resume_skips_fetched(db_with_funds):
    """断点续采：fetched_at 非空的经理不再拉档案。"""
    db_with_funds.add(Manager(manager_id="m_done", name="已采", fetched_at=datetime.now(UTC)))
    db_with_funds.commit()

    table = [
        _mk_table_row("m_done", "已采", "华夏基金", ["000011"], 5000),
        _mk_table_row("m_new", "未采", "华夏基金", ["000011"], 3000),
    ]
    calls = []

    def tenure_provider(mid):
        calls.append(mid)
        return _tenures("000011")

    refresh(db_with_funds, fetch_nav=False, table_provider=lambda: table,
            tenure_provider=tenure_provider, nav_provider=lambda c: [],
            profile_fetch_delay_s=0)
    assert calls == ["m_new"]


def test_tenure_failure_recorded_not_fatal(db_with_funds):
    """档案采集失败：记 failed + errors，不中断、不影响其他经理。"""
    table = [
        _mk_table_row("m_bad", "会失败", "华夏基金", ["000011"], 5000),
        _mk_table_row("m_ok", "会成功", "易方达基金", ["000022"], 5000),
    ]

    def tenure_provider(mid):
        if mid == "m_bad":
            raise RuntimeError("网络超时")
        return _tenures("000022")

    stats = refresh(db_with_funds, task_id="t_mgr3", fetch_nav=False,
                    table_provider=lambda: table, tenure_provider=tenure_provider,
                    nav_provider=lambda c: [], profile_fetch_delay_s=0)

    assert stats["failed"] == 1
    assert any("m_bad" in e for e in stats["errors"])
    assert stats["tenures_total"] == 1
    from src.db.models import RefreshRun
    run = db_with_funds.get(RefreshRun, "t_mgr3")
    assert run.status == "partial"
    assert run.failed == 1


def test_risk_metrics_populated(db_with_funds):
    """M3：nav_provider 注入合成复权序列 → managers 风险字段非空。"""
    from datetime import date, timedelta
    d0 = date(2020, 1, 1)
    nav = [( (d0 + timedelta(days=i)).isoformat(), 1.0 + i * 0.001) for i in range(400)]
    table = [_mk_table_row("m1", "张三", "华夏基金", ["000011"], 5000)]
    refresh(db_with_funds, fetch_nav=True, table_provider=lambda: table,
            tenure_provider=lambda mid: _tenures("000011"),
            nav_provider=lambda code: nav, profile_fetch_delay_s=0)

    m1 = db_with_funds.get(Manager, "m1")
    assert m1.representative_fund == "000011"
    assert m1.max_drawdown is not None
    assert m1.sharpe is not None
    assert m1.longest_tenure_years == round(3650 / 365.25, 2)


def test_manager_re_fetch_replaces_tenures(db_with_funds):
    """重采幂等：同一经理二次采集，tenures 全量替换不重复。"""
    table = [_mk_table_row("m1", "张三", "华夏基金", ["000011"], 5000)]
    kw = dict(fetch_nav=False, table_provider=lambda: table,
              tenure_provider=lambda mid: _tenures("000011"),
              nav_provider=lambda c: [], profile_fetch_delay_s=0)
    refresh(db_with_funds, **kw)
    # 强制视为待采
    db_with_funds.get(Manager, "m1").fetched_at = None
    db_with_funds.commit()
    refresh(db_with_funds, **kw)

    rows = db_with_funds.query(ManagerTenure).filter_by(manager_id="m1").all()
    assert len(rows) == 1  # 不是 2 条


def test_force_refetches_even_when_fetched(db_with_funds):
    """force=True：已采过的经理也重采（档案变更靠这个更新，不是一次性采集）。"""
    db_with_funds.add(Manager(manager_id="m_done", name="已采", fetched_at=datetime.now(UTC)))
    db_with_funds.commit()

    table = [_mk_table_row("m_done", "已采", "华夏基金", ["000011"], 5000)]
    calls = []

    def tenure_provider(mid):
        calls.append(mid)
        return _tenures("000011")

    refresh(db_with_funds, fetch_nav=False, force=True, table_provider=lambda: table,
            tenure_provider=tenure_provider, nav_provider=lambda c: [],
            profile_fetch_delay_s=0)
    assert calls == ["m_done"]


def test_force_false_default_keeps_resume_semantics(db_with_funds):
    """不传 force 就是断点续采（向后兼容）：已采的不再拉。"""
    db_with_funds.add(Manager(manager_id="m_done", name="已采", fetched_at=datetime.now(UTC)))
    db_with_funds.commit()

    table = [_mk_table_row("m_done", "已采", "华夏基金", ["000011"], 5000)]
    calls = []
    refresh(db_with_funds, fetch_nav=False, table_provider=lambda: table,
            tenure_provider=lambda mid: (calls.append(mid), _tenures("000011"))[1],
            nav_provider=lambda c: [], profile_fetch_delay_s=0)
    assert calls == []


def test_progress_total_reports_pending_count(db_with_funds):
    """进度分母 = 本轮待采人数，刷新页面的进度条靠它。"""
    from src.db.models import RefreshRun

    table = [
        _mk_table_row("m1", "张三", "华夏基金", ["000011"], 5000),
        _mk_table_row("m2", "李四", "易方达基金", ["000022"], 5000),
    ]
    refresh(db_with_funds, task_id="t_prog", fetch_nav=False, force=True,
            table_provider=lambda: table,
            tenure_provider=lambda mid: _tenures("000011"),
            nav_provider=lambda c: [], profile_fetch_delay_s=0)

    run = db_with_funds.get(RefreshRun, "t_prog")
    assert run.total == 2
    assert run.completed == 2
    assert run.finished_at is not None


def test_errors_persisted_as_json_array(db_with_funds):
    """RefreshRun.errors 契约是 JSON 数组字符串（/refresh/status 要 json.loads 解析）。"""
    import json

    from src.db.models import RefreshRun

    table = [_mk_table_row("m_bad", "会失败", "华夏基金", ["000011"], 5000)]

    def tenure_provider(mid):
        raise RuntimeError("网络超时")

    refresh(db_with_funds, task_id="t_err", fetch_nav=False,
            table_provider=lambda: table, tenure_provider=tenure_provider,
            nav_provider=lambda c: [], profile_fetch_delay_s=0)

    run = db_with_funds.get(RefreshRun, "t_err")
    parsed = json.loads(run.errors)
    assert isinstance(parsed, list)
    assert any("m_bad" in e for e in parsed)
