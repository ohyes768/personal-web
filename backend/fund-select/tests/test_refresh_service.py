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
                  fetch_ranking: bool = False,
                  bond_tables=None, analyze_ret: dict | None = None):
    """mock 全部外部依赖跑一遍 snapshot_fund。返回 (snap, mocks dict)。

    fetch_ranking 控制是否调 fetch_achievement（stock 路径传 True，债基路径默认 False）。
    """
    basic = {"基金名称": f"基金{CODE}", "基金类型": fund_type, "基金经理": "张三"}
    with patch("src.services.refresh_service.fetch_basic", return_value=basic), \
         patch("src.services.refresh_service.fetch_nav", return_value=pd.DataFrame()), \
         patch("src.services.refresh_service.compute_performance", return_value={}), \
         patch("src.services.refresh_service.fetch_fees", return_value={}), \
         patch("src.services.refresh_service.analyze_holdings", return_value=analyze_ret or {}), \
         patch("src.services.refresh_service.fetch_achievement", return_value=pd.DataFrame()) as mock_ach, \
         patch("src.services.refresh_service.fetch_bond_hold", return_value=bond_tables) as mock_hold:
        snap = snapshot_fund(
            CODE,
            mgr_worktime={},
            mgr_company={},
            today=pd.Timestamp("2026-09-03"),
            holdings_year=YEAR,
            fetch_holdings=fetch_holdings,
            fetch_ranking=fetch_ranking,
        )
    return snap, {"fetch_bond_hold": mock_hold, "fetch_achievement": mock_ach}


class TestSnapshotFundFetchHoldings:
    def test_false_skips_bond_fetch_for_mixed_type(self):
        """fetch_holdings=False（股票宇宙刷新）：混合型也不发 zqcc 请求、不产 holdings"""
        snap, mocks = _run_snapshot(
            fund_type="混合型-偏股", fetch_holdings=False, bond_tables=["t"],
        )
        mocks["fetch_bond_hold"].assert_not_called()
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
        snap, mocks = _run_snapshot(
            fund_type="债券型-长期纯债", bond_tables=["t"],
            analyze_ret={"rate_bond_pct": 30.0, "credit_bond_pct": 50.0},
        )
        mocks["fetch_bond_hold"].assert_called_once_with(CODE, YEAR)
        assert snap["holdings"] == {
            "report_date": date(2025, 12, 31),
            "rate_bond_pct": 30.0,
            "credit_bond_pct": 50.0,
        }

    def test_default_ignores_fund_type(self):
        """类型短路已删：QDII/股票型在债基路径（默认 True）也拉——控制只看开关，不看类型"""
        for fund_type in ("QDII", "股票型-标准指数"):
            _, mocks = _run_snapshot(fund_type=fund_type, bond_tables=["t"])
            mocks["fetch_bond_hold"].assert_called_once_with(CODE, YEAR)


class TestSnapshotFundFetchRanking:
    """fetch_ranking 参数控制雪球业绩排名抓取（stock 路径开启，债基路径默认关闭）。

    修复点：原 fund_type 白名单遗漏「混合型」，改为参数化后所有 funds_stock.yaml
    名单基金（股票型 / QDII / 混合型）都抓。
    """

    def test_stock_path_fetches_ranking_for_mixed_flexible(self):
        """fetch_ranking=True（stock 路径）：混合型-灵活配置也调 fetch_achievement（修复点）"""
        _, mocks = _run_snapshot(
            fund_type="混合型-灵活配置", fetch_ranking=True,
        )
        mocks["fetch_achievement"].assert_called_once_with(CODE)

    def test_stock_path_fetches_ranking_for_mixed_partial_equity(self):
        """fetch_ranking=True（stock 路径）：混合型-偏股也调 fetch_achievement（修复点）"""
        _, mocks = _run_snapshot(
            fund_type="混合型-偏股", fetch_ranking=True,
        )
        mocks["fetch_achievement"].assert_called_once_with(CODE)

    def test_stock_path_fetches_ranking_for_stock_type(self):
        """fetch_ranking=True（stock 路径）：股票型仍调 fetch_achievement（回归保护）"""
        _, mocks = _run_snapshot(
            fund_type="股票型-标准指数", fetch_ranking=True,
        )
        mocks["fetch_achievement"].assert_called_once_with(CODE)

    def test_stock_path_fetches_ranking_for_qdii(self):
        """fetch_ranking=True（stock 路径）：QDII 仍调 fetch_achievement（回归保护）"""
        _, mocks = _run_snapshot(
            fund_type="QDII", fetch_ranking=True,
        )
        mocks["fetch_achievement"].assert_called_once_with(CODE)

    def test_bond_path_skips_ranking_even_for_stock_typed_funds(self):
        """fetch_ranking=False（债基路径）：即便 fund_type=股票型 也不调 fetch_achievement

        防止债基 refresh 误把股票型基金（如未来 yaml 误归类）写 ranking。
        """
        _, mocks = _run_snapshot(
            fund_type="股票型-标准指数", fetch_ranking=False,
        )
        mocks["fetch_achievement"].assert_not_called()
