"""全量刷新链路的两个回归测试（11-14 全量刷新修复）

锁住两个曾经把「全量刷新」变成废功能的 bug：

1. **L0 不回填经理字段** → 预筛 1（min_mgr_exp）读 funds.mgr_experience_years_max，
   SQL 里 `NULL >= 5` 不成立 → 整个 universe 被砍成 0（实测 16239 → 1236）。
   根因：`fetch_manager_by_fund_code` 从 576747b8 重构起就没有调用方了。

2. **L0 用无经理记录的 code 覆盖已有 mgr 值** → yaml 名单基金的 mgr 来自雪球
   basic 接口（更准），不能被 akshare 经理表的「缺记录」抹成 NULL。

另附前端 Bug 的契约说明（FULL_REFRESH_API 的 key 必须与 exportKind 对齐，
否则按钮整个不渲染）—— 前端没有单测框架，这里用一条后端契约测试提醒：
合并页的 exportKind 是 bond/stock，后端 full/refresh 端点仍挂在 discovery-* 前缀下。
"""
from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from src.db.models import Fund
from src.services.market_full_pipeline import refresh_market_full_sync
from src.services.market_universe_refresh import refresh as refresh_market_universe


def _df(rows):
    return pd.DataFrame(rows)


class TestL0WritesManagerFields:
    """L0 必须回填 mgr_* —— 这是预筛 1 能不能命中的前提。"""

    def test_l0_passes_mgr_by_code_to_universe_refresh(self, db_session, monkeypatch):
        """L0 调 refresh_market_universe_db 时必须带 mgr_by_code。"""
        captured: dict = {}

        def fake_universe_refresh(db, df, task_id=None, mgr_by_code=None):
            captured["mgr_by_code"] = mgr_by_code
            return {"task_id": task_id, "total": len(df), "inserted": 0,
                    "updated": 0, "failed": 0, "errors": []}

        monkeypatch.setattr(
            "src.services.market_full_pipeline.refresh_market_universe_db",
            fake_universe_refresh,
        )
        monkeypatch.setattr(
            "src.data.manager_fetcher.fetch_manager_by_fund_code",
            lambda use_cache=True: {"000001": [{"name": "张三", "company": "某司", "days": 3650}]},
        )
        # 只让 L0 跑：L1 之后的阶段用空 universe 短路
        monkeypatch.setattr(
            "src.services.market_full_pipeline.fetch_market_rank_bulk",
            lambda symbols=None, **kw: _df([]),
        )
        monkeypatch.setattr(
            "src.services.market_full_pipeline.refresh_market_rank_db",
            lambda db, df, task_id=None: {"task_id": task_id, "total": 0, "inserted": 0,
                                          "updated": 0, "failed": 0, "errors": []},
        )
        monkeypatch.setattr(
            "src.services.market_full_pipeline.fetch_market_size",
            lambda codes, **kw: [],
        )
        monkeypatch.setattr(
            "src.services.market_full_pipeline.refresh_market_size_db",
            lambda db, rows, task_id=None: {"task_id": task_id, "total": 0, "updated": 0,
                                            "skipped": 0, "failed": 0, "errors": []},
        )

        with patch("src.services.market_full_pipeline.SessionLocal", return_value=db_session):
            refresh_market_full_sync(
                universe_filter=["股票型"],
                preset_task_id="test-l0-mgr",
            )

        assert "mgr_by_code" in captured, \
            "L0 没传 mgr_by_code → 预筛 1 会把 universe 砍成 0（11-14 回归）"
        assert captured["mgr_by_code"] == {
            "000001": [{"name": "张三", "company": "某司", "days": 3650}]
        }

    def test_manager_fields_actually_persisted(self, db_session, monkeypatch):
        """端到端：L0 跑完后 funds.mgr_experience_years_max 有值。"""
        db_session.add(Fund(
            code="000001", name="X", market_subtype="股票型", market_type="stock",
            is_active=True, size_yi=25.0, age_years=6.0,
        ))
        db_session.commit()

        # 只跑 L0：把 L1 及之后的阶段 mock 成空操作
        monkeypatch.setattr(
            "src.data.market_universe_fetcher.fetch_market_universe",
            lambda: _df([{
                "code": "000001", "name": "X", "market_subtype": "股票型", "market_type": "stock",
            }]),
        )
        monkeypatch.setattr(
            "src.data.manager_fetcher.fetch_manager_by_fund_code",
            lambda use_cache=True: {"000001": [{"name": "张三", "company": "某司", "days": 3650}]},
        )
        monkeypatch.setattr(
            "src.services.market_full_pipeline.fetch_market_rank_bulk",
            lambda symbols=None, **kw: _df([]),
        )
        monkeypatch.setattr(
            "src.services.market_full_pipeline.refresh_market_rank_db",
            lambda db, df, task_id=None: {"task_id": task_id, "total": 0, "inserted": 0,
                                          "updated": 0, "failed": 0, "errors": []},
        )
        monkeypatch.setattr(
            "src.services.market_full_pipeline.fetch_market_size",
            lambda codes, **kw: [],
        )
        monkeypatch.setattr(
            "src.services.market_full_pipeline.refresh_market_size_db",
            lambda db, rows, task_id=None: {"task_id": task_id, "total": 0, "updated": 0,
                                            "skipped": 0, "failed": 0, "errors": []},
        )
        monkeypatch.setattr(
            "src.services.market_full_pipeline.fetch_market_nav",
            lambda codes, **kw: {},
        )
        monkeypatch.setattr(
            "src.services.market_full_pipeline.refresh_market_nav_db",
            lambda db, data, task_id=None: {"task_id": task_id, "total": 0, "inserted": 0,
                                            "updated": 0, "failed": 0, "errors": []},
        )
        monkeypatch.setattr(
            "src.services.market_full_pipeline.fetch_market_achievement",
            lambda codes, **kw: {},
        )
        monkeypatch.setattr(
            "src.services.market_full_pipeline.refresh_market_achievement",
            lambda db, codes, task_id=None: {"task_id": task_id, "total": 0, "inserted": 0,
                                            "updated": 0, "failed": 0, "errors": []},
        )
        monkeypatch.setattr(
            "src.services.market_full_pipeline.refresh_market_risk_db",
            lambda db, codes, task_id=None, **kw: {"task_id": task_id, "total": 0, "inserted": 0,
                                                    "updated": 0, "failed": 0, "errors": []},
        )

        with patch("src.services.market_full_pipeline.SessionLocal", return_value=db_session):
            refresh_market_full_sync(
                universe_filter=["股票型"],
                preset_task_id="test-l0-persist",
            )

        f = db_session.get(Fund, "000001")
        assert f.mgr_name == "张三"
        assert f.mgr_company == "某司"
        assert f.mgr_days == 3650
        assert f.mgr_experience_years == round(3650 / 365.25, 2)
        assert f.mgr_experience_years_max == round(3650 / 365.25, 2)


class TestL0DoesNotClobberExistingManagerData:
    """akshare 经理表缺记录时，不能把已有 mgr 值抹成 NULL。"""

    def test_existing_mgr_preserved_when_no_manager_record(self, db_session):
        """已有 mgr（来自雪球 basic 接口）的基金，在 akshare 缺记录时应保持原值。"""
        db_session.add(Fund(
            code="000001", name="X", market_subtype="股票型", market_type="stock",
            is_active=True, mgr_name="老王", mgr_company="老公司",
            mgr_days=5000, mgr_experience_years=13.69, mgr_experience_years_max=13.69,
        ))
        db_session.commit()

        df = _df([{
            "code": "000001", "name": "X", "market_subtype": "股票型", "market_type": "stock",
        }])
        # mgr_by_code 里没有 000001（akshare 缺记录）
        refresh_market_universe(db_session, df, mgr_by_code={})

        f = db_session.get(Fund, "000001")
        assert f.mgr_name == "老王", "akshare 缺记录不能把已有 mgr_name 清空"
        assert f.mgr_company == "老公司"
        assert f.mgr_days == 5000
        assert f.mgr_experience_years_max == 13.69

    def test_existing_mgr_updated_when_manager_record_present(self, db_session):
        """akshare 有记录时正常更新（覆盖旧值）。"""
        db_session.add(Fund(
            code="000001", name="X", market_subtype="股票型", market_type="stock",
            is_active=True, mgr_name="老王", mgr_days=5000,
            mgr_experience_years_max=13.69,
        ))
        db_session.commit()

        df = _df([{
            "code": "000001", "name": "X", "market_subtype": "股票型", "market_type": "stock",
        }])
        refresh_market_universe(
            db_session, df,
            mgr_by_code={"000001": [{"name": "新人", "company": "新公司", "days": 500}]},
        )

        f = db_session.get(Fund, "000001")
        assert f.mgr_name == "新人"
        assert f.mgr_days == 500
        assert f.mgr_experience_years_max == round(500 / 365.25, 2)


class TestFullRefreshEndpointContract:
    """前端「全量刷新」按钮依赖后端端点仍然挂在 discovery-* 前缀下。

    11-14 修复：合并页的 exportKind 变成 bond/stock，但后端端点没搬家——
    前端 FULL_REFRESH_API 的 key 改成 bond/stock，URL 仍指 discovery-*。
    这条测试锁住「端点在、路径没变」，避免有人搬路由时静默改 URL。
    """

    def test_full_refresh_endpoints_exist(self):
        """端点挂在 discovery-* 前缀下（合并页的 exportKind 变了，URL 没变）。"""
        from src.api.routes import router_discovery_bond, router_discovery_stock
        stock = {r.path for r in router_discovery_stock.routes}
        bond = {r.path for r in router_discovery_bond.routes}
        assert "/discovery-stock/full/refresh" in stock
        assert "/discovery-stock/full/refresh/status" in stock
        assert "/discovery-bond/full/refresh" in bond
        assert "/discovery-bond/full/refresh/status" in bond
        # 主路由（/api/funds）下**不该**再有 full/refresh（否则前端会打错端点）
        from src.api.routes import router
        assert not any("full/refresh" in r.path for r in router.routes)

    def test_full_refresh_accepts_three_prefilter_params(self):
        """弹框只传 3 个预筛参数（min_ret_3y / min_size_yi / min_mgr_exp）。"""
        from src.api.routes import (
            discovery_bond_full_refresh,
            discovery_stock_full_refresh,
        )
        import inspect
        for fn in (discovery_bond_full_refresh, discovery_stock_full_refresh):
            params = list(inspect.signature(fn).parameters.keys())
            assert "min_ret_3y" in params
            assert "min_size_yi" in params
            assert "min_mgr_exp" in params
            # 不该有 max_nav_stale_days（后端常量固定 14 天）
            assert "max_nav_stale_days" not in params
