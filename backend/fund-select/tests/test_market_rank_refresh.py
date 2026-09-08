"""
market_fund_rank upsert refresh 单测（in-memory SQLite）
"""
from datetime import date
from unittest.mock import patch
import json

import pandas as pd

from src.db.models import Fund, MarketFundRank, RefreshRun
from src.services.market_rank_refresh import refresh as refresh_market_rank


def _df(rows: list[tuple]) -> pd.DataFrame:
    """构造 fetcher 返回 DataFrame：code / name / nav_date / nav_latest / ret_* / ft_code"""
    cols = ["code", "name", "nav_date", "nav_latest",
            "ret_1w", "ret_1m", "ret_3m", "ret_6m",
            "ret_1y", "ret_2y", "ret_3y", "ret_ytd", "ret_all", "ft_code"]
    return pd.DataFrame(rows, columns=cols)


def _row(code, **kw):
    defaults = {
        "code": code, "name": f"基金{code}",
        "nav_date": date(2026, 9, 7), "nav_latest": 1.5,
        "ret_1w": 0.5, "ret_1m": 1.0, "ret_3m": 3.0, "ret_6m": 6.0,
        "ret_1y": 12.0, "ret_2y": 25.0, "ret_3y": 40.0,
        "ret_ytd": 8.0, "ret_all": 60.0, "ft_code": "gp",
    }
    defaults.update(kw)
    return defaults


class TestRefreshMarketRank:
    def test_insert_new_codes(self, db_session):
        df = _df([_row("000001"), _row("000002")])
        result = refresh_market_rank(db_session, df, task_id=None)
        assert result["total"] == 2
        assert result["inserted"] == 2
        assert result["failed"] == 0

        rows = {r.code: r for r in db_session.query(MarketFundRank).all()}
        assert rows["000001"].ret_3y == 40.0
        assert rows["000001"].ft_code == "gp"
        assert rows["000001"].nav_date == date(2026, 9, 7)

    def test_update_existing_overwrites(self, db_session):
        # 预设已有
        db_session.add(MarketFundRank(
            code="000001", nav_latest=0.5, ret_3y=10.0, ft_code="gp",
        ))
        db_session.commit()

        df = _df([_row("000001", ret_3y=99.0)])
        result = refresh_market_rank(db_session, df, task_id=None)
        assert result["updated"] == 1
        assert result["inserted"] == 0

        r = db_session.get(MarketFundRank, "000001")
        assert r.ret_3y == 99.0  # 覆盖

    def test_refresh_run_progress(self, db_session):
        run = RefreshRun(task_id="test-task-001", status="running", total=0)
        db_session.add(run)
        db_session.commit()

        df = _df([_row("000001")])
        result = refresh_market_rank(db_session, df, task_id="test-task-001")

        run = db_session.get(RefreshRun, "test-task-001")
        assert run.total == 1
        assert run.completed == 1
        assert run.status == "done"
        assert run.finished_at is not None
        assert result["task_id"] == "test-task-001"

    def test_empty_dataframe(self, db_session):
        result = refresh_market_rank(db_session, _df([]))
        assert result["total"] == 0
        assert result["inserted"] == 0

    def test_does_not_touch_fund_performance(self, db_session):
        """关键回归：refresh market_fund_rank 不能污染 fund_performance"""
        from src.db.models import FundPerformance
        # 预设 fund_performance
        db_session.add(FundPerformance(code="000001", as_of_date=date(2026, 9, 1),
                                          ret_3y=99.0))
        db_session.commit()

        df = _df([_row("000001", ret_3y=10.0)])
        refresh_market_rank(db_session, df, task_id=None)

        # fund_performance 应该保持不变
        fp = db_session.query(FundPerformance).filter_by(code="000001").first()
        assert fp.ret_3y == 99.0  # 未变

        # market_fund_rank 应该写入新值
        mr = db_session.get(MarketFundRank, "000001")
        assert mr.ret_3y == 10.0  # 新值
