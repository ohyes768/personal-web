"""
snapshot_fund 单测：fetch_holdings 开关（股票宇宙刷新跳过债券季报拉取）。

全程 mock 外部 fetcher，不联网、不读真实 yaml。
"""
from datetime import date
from unittest.mock import patch

import pandas as pd

from src.db.models import FundHoldingsBond
from src.services.refresh_service import persist_snapshot, snapshot_fund

CODE = "000123"
YEAR = "2025"


def _run_snapshot(fund_type: str, fetch_holdings: bool = True,
                  bond_tables=None, analyze_ret: dict | None = None):
    """mock 全部外部依赖跑一遍 snapshot_fund。返回 (snap, fetch_bond_hold mock)。

    bond_tables 传真值 sentinel：若守卫失效（不该拉时拉了），holdings 会混入 snap 使断言失败。
    """
    basic = {"基金名称": f"基金{CODE}", "基金类型": fund_type, "基金经理": "张三"}
    with patch("src.services.refresh_service.fetch_basic", return_value=basic), \
         patch("src.services.refresh_service.fetch_nav", return_value=pd.DataFrame()), \
         patch("src.services.refresh_service.compute_performance", return_value={}), \
         patch("src.services.refresh_service.fetch_fees", return_value={}), \
         patch("src.services.refresh_service.analyze_holdings", return_value=analyze_ret or {}), \
         patch("src.services.refresh_service.fetch_achievement", return_value=pd.DataFrame()), \
         patch("src.services.refresh_service.fetch_bond_hold", return_value=bond_tables) as mock_hold:
        snap = snapshot_fund(
            CODE,
            mgr_worktime={},
            mgr_company={},
            today=pd.Timestamp("2026-09-03"),
            holdings_year=YEAR,
            fetch_holdings=fetch_holdings,
        )
    return snap, mock_hold


class TestSnapshotFundFetchHoldings:
    def test_false_skips_bond_fetch_for_mixed_type(self):
        """fetch_holdings=False（股票宇宙刷新）：混合型也不发 zqcc 请求、不产 holdings"""
        snap, mock_hold = _run_snapshot(
            fund_type="混合型-偏股", fetch_holdings=False, bond_tables=["t"],
        )
        mock_hold.assert_not_called()
        assert "holdings" not in snap

    def test_false_persists_no_holdings_row(self, db_session):
        """跳过持仓后 persist_snapshot 不写 fund_holdings_bond（既有行 updated_at 不受影响）"""
        snap, _ = _run_snapshot(
            fund_type="混合型-偏股", fetch_holdings=False, bond_tables=["t"],
        )
        persist_snapshot(db_session, snap)
        db_session.commit()
        assert db_session.query(FundHoldingsBond).filter_by(code=CODE).count() == 0

    def test_default_still_fetches_bond_holdings(self):
        """默认 True（债基路径）行为不变：仍拉季报并产出 holdings"""
        snap, mock_hold = _run_snapshot(
            fund_type="债券型-长期纯债", bond_tables=["t"],
            analyze_ret={"rate_bond_pct": 30.0, "credit_bond_pct": 50.0},
        )
        mock_hold.assert_called_once_with(CODE, YEAR)
        assert snap["holdings"] == {
            "report_date": date(2025, 12, 31),
            "rate_bond_pct": 30.0,
            "credit_bond_pct": 50.0,
        }

    def test_default_ignores_fund_type(self):
        """类型短路已删：QDII/股票型在债基路径（默认 True）也拉——控制只看开关，不看类型"""
        for fund_type in ("QDII", "股票型-标准指数"):
            _, mock_hold = _run_snapshot(fund_type=fund_type, bond_tables=["t"])
            mock_hold.assert_called_once_with(CODE, YEAR)
