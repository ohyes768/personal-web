"""夏普榜单聚合与 API 测试（implement 步骤 4：AC2–AC8、AC10）

三周 fixture（周一 2026-10-19 / 10-26 / 11-02）：
- A(000001) = [0.95, 缺席, 1.05]：累计 2 周、最近连续 1 周
- B(000002) = [0.90, 0.92, 0.94]：累计 3 周、连续 3 周
无筛选 B 排 A 前（R3）；min_latest_sharpe=1 只剩 A（implement.md 固定断言）。

当前自然周由 monkeypatch sbs._current_week 固定（不依赖运行日期）。
"""
import json
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.db.models import Base, SharpeBoardObservation, SharpeBoardWeek
from src.services import sharpe_board_service as sbs

WEEK1 = date(2026, 10, 19)
WEEK2 = date(2026, 10, 26)
WEEK3 = date(2026, 11, 2)
CURRENT = WEEK3  # 默认当前周 = 第三周 → 周历恰为三周


@pytest.fixture
def board_db():
    """in-memory SQLite + StaticPool（TestClient 线程共享同一连接）"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = Session()
    yield db
    db.close()
    engine.dispose()


@pytest.fixture
def client(board_db, monkeypatch):
    """TestClient + 依赖注入 in-memory 库；当前周固定为 WEEK3"""
    monkeypatch.setattr(sbs, "_current_week", lambda: CURRENT)
    from src.db.session import get_db
    from src.main import app

    def _override():
        yield board_db

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# UTC naive（周行 started_at 存储约定）；值本身只作占位，测试不断言具体时刻
_STARTED_UTC = datetime(2026, 10, 31, 0, 5)


def _seed_week(db, week, entries=None, *, source="stock", version="v1",
               status="complete", errors=None, diagnostics=None,
               selected_count=None):
    """直接构造周批次 + 观测行（status/errors/诊断完全可控）。

    entries: {code: (name, sharpe)}；status 非 complete 时不写观测。
    """
    if selected_count is None:
        selected_count = len(entries) if status == "complete" else 0
    try:
        profile_json = sbs.canonical_json(sbs.get_profile(source, version))
        profile_hash = sbs.canonical_hash(sbs.get_profile(source, version))
    except KeyError:
        # 未知版本（隔离测试用）：手写副本即可
        profile_json, profile_hash = "{}", "h-unknown"
    row = SharpeBoardWeek(
        source=source, profile_version=version, week_start=week,
        profile_json=profile_json, profile_hash=profile_hash,
        algorithm_version="risk-3y-v1", status=status,
        selected_count=selected_count, started_at=_STARTED_UTC,
        errors_json=json.dumps(errors, ensure_ascii=False) if errors else None,
        diagnostics_json=json.dumps(diagnostics, ensure_ascii=False) if diagnostics else None,
    )
    db.add(row)
    db.flush()
    if status == "complete" and entries:
        for code, (name, sharpe) in entries.items():
            db.add(SharpeBoardObservation(
                week_id=row.id, code=code, name=name, sharpe=sharpe,
            ))
    db.commit()
    return row


def _seed_three_weeks(db, *, source="stock", version="v1", extra_week2=None):
    """A=[0.95, 缺席, 1.05]，B=[0.90, 0.92, 0.94]；extra_week2 并入第二周"""
    w2 = {"000002": ("基金B", 0.92)}
    if extra_week2:
        w2.update(extra_week2)
    _seed_week(db, WEEK1, {"000001": ("基金A", 0.95), "000002": ("基金B", 0.90)},
               source=source, version=version)
    _seed_week(db, WEEK2, w2, source=source, version=version)
    _seed_week(db, WEEK3, {"000001": ("基金A", 1.05), "000002": ("基金B", 0.94)},
               source=source, version=version)


def _get(client, **params):
    # fixture 种子是 v1 数据；API 默认版本已切 v2（11-13 任务），
    # 这组聚合测试显式查 v1，默认版本行为由 TestApiValidation 单独验证。
    base = {"source": "stock", "profile_version": "v1"}
    base.update(params)
    return client.get("/api/funds/sharpe-board", params=base).json()


@pytest.fixture
def three_weeks(board_db):
    """标准三周榜：A=[0.95, 缺席, 1.05]，B=[0.90, 0.92, 0.94]"""
    _seed_three_weeks(board_db)
    return board_db


@pytest.fixture
def fixed_now(monkeypatch):
    """service 直调测试也固定当前周（不依赖运行日期）"""
    monkeypatch.setattr(sbs, "_current_week", lambda: CURRENT)
    return CURRENT


class TestOrderingAndConsecutive:
    """AC2：三周 fixture，B(3周) 排 A(2周) 前；A 中间断线、最近连续 1 周"""

    def test_b_ranks_before_a_no_filter(self, client, three_weeks):
        body = _get(client)
        assert body["total"] == 2
        assert [it["code"] for it in body["items"]] == ["000002", "000001"]
        by_code = {it["code"]: it for it in body["items"]}
        assert by_code["000001"]["listed_weeks"] == 2
        assert by_code["000002"]["listed_weeks"] == 3
        assert by_code["000001"]["consecutive_weeks"] == 1  # 10-26 缺席中断
        assert by_code["000002"]["consecutive_weeks"] == 3
        assert by_code["000001"]["latest_sharpe"] == 1.05
        assert by_code["000002"]["latest_sharpe"] == 0.94
        assert by_code["000001"]["last_listed_week"] == "2026-11-02"
        assert by_code["000002"]["on_latest_board"] is True
        assert body["weeks"] == ["2026-10-19", "2026-10-26", "2026-11-02"]
        assert body["latest_published_week"] == "2026-11-02"
        assert body["stale"] is False

    def test_series_broken_line_single_points(self, client, three_weeks):
        """A 中间缺席断线（不补零不连线）、单点保留；series 长度 == weeks 长度"""
        body = _get(client)
        series = {s["code"]: s for s in body["series"]}
        assert series["000001"]["values"] == [0.95, None, 1.05]
        assert series["000002"]["values"] == [0.90, 0.92, 0.94]
        assert len(body["series"]) == body["total"]  # 全部命中，不随分页

    def test_fixed_assertions_from_plan(self, client, three_weeks):
        """implement.md 步骤 4 固定断言（逐字）：下限 1 时只剩 A、保留历史低点"""
        body = _get(client, min_latest_sharpe=1)
        assert body["total"] == 1
        assert body["items"][0]["code"] == "000001"
        assert body["items"][0]["listed_weeks"] == 2
        assert body["series"][0]["values"] == [0.95, None, 1.05]

    def test_threshold_inclusive_equality(self, client, three_weeks):
        """下限含等于（R5）：B 最近 0.94、A 最近 1.05，等于下限时各自命中"""
        body = _get(client, min_latest_sharpe=0.94)
        assert "000002" in {it["code"] for it in body["items"]}  # 恰等于下限
        body2 = _get(client, min_latest_sharpe=1.05)
        assert {it["code"] for it in body2["items"]} == {"000001"}  # 恰等于下限


class TestDisplayFilters:
    """AC3/R5：min_weeks、latest_only"""

    def test_min_weeks_3_only_b(self, client, three_weeks):
        body = _get(client, min_weeks=3)
        assert body["total"] == 1
        assert [it["code"] for it in body["items"]] == ["000002"]

    def test_latest_only_drops_not_on_latest_board(self, client, board_db):
        _seed_three_weeks(board_db, extra_week2={"000003": ("基金D", 0.91)})
        body = _get(client, latest_only=True)
        assert body["total"] == 2
        assert {it["code"] for it in body["items"]} == {"000001", "000002"}
        no_filter = _get(client)
        assert no_filter["total"] == 3  # 不开 latest_only 时 D（1 周）在

    def test_latest_only_with_empty_latest_board(self, client, board_db, monkeypatch):
        """最新 complete 是空榜 → latest_only 返回零只；stale=False、榜日期真实"""
        monkeypatch.setattr(sbs, "_current_week", lambda: date(2026, 11, 9))
        _seed_three_weeks(board_db)
        _seed_week(board_db, date(2026, 11, 9), {})  # complete 空榜
        body = _get(client, latest_only=True)
        assert body["total"] == 0
        assert body["items"] == []
        assert body["latest_published_week"] == "2026-11-09"
        assert body["stale"] is False
        no_filter = _get(client)
        assert no_filter["total"] == 2  # 空榜不改全历史聚合


class TestRangeOnlyTrimsChart:
    """AC4：range 只裁图；累计周数/最近上榜值/命中集合不变；下限用范围外最新记录"""

    @pytest.fixture
    def ranged_db(self, board_db):
        """早期周 2026-06-01：C 只在该周上榜（0.9）；三周 A/B 照常"""
        _seed_week(board_db, date(2026, 6, 1), {"000003": ("基金C", 0.9)})
        _seed_three_weeks(board_db)
        return board_db

    def test_range_keeps_stats_and_hits(self, client, ranged_db):
        all_body = _get(client, range="all")
        m3_body = _get(client, range="3m")
        assert date.fromisoformat("2026-06-01") not in [
            date.fromisoformat(w) for w in m3_body["weeks"]
        ]
        assert date.fromisoformat("2026-06-01") in [
            date.fromisoformat(w) for w in all_body["weeks"]
        ]
        # 统计与命中集合不变
        assert m3_body["total"] == all_body["total"] == 3
        m3_items = {it["code"]: it for it in m3_body["items"]}
        all_items = {it["code"]: it for it in all_body["items"]}
        assert m3_items == all_items
        # values 长度各自等于 weeks 长度
        for s in m3_body["series"]:
            assert len(s["values"]) == len(m3_body["weeks"])
        for s in all_body["series"]:
            assert len(s["values"]) == len(all_body["weeks"])

    def test_no_points_in_range_all_null_series(self, client, ranged_db):
        """v2 52 周窗口：C 只在 2026-06-01 上榜（52 周窗口内，3m 范围外）。
        range=3m 只裁周历、不改统计/命中 → C 仍命中，但 3m 内无点 → 全 null。"""
        body = _get(client, range="3m", min_latest_sharpe=0.9)
        assert body["total"] == 3  # A 1.05 / B 0.94 / C 0.9 全部 ≥ 下限
        by_code = {it["code"]: it for it in body["items"]}
        assert by_code["000003"]["latest_sharpe"] == 0.9
        assert by_code["000003"]["last_listed_week"] == "2026-06-01"
        c_series = [s for s in body["series"] if s["code"] == "000003"][0]
        assert c_series["values"] == [None] * len(body["weeks"])  # 3m 内无点不造点
        # 13 个整周（current 11-02 往前 12 周），起点落在周一网格
        assert body["weeks"][0] == "2026-08-10"
        assert len(body["weeks"]) == 13
        assert all(date.fromisoformat(w).weekday() == 0 for w in body["weeks"])

    def test_range_trims_old_only_not_recent(self, client, ranged_db):
        """1y 覆盖全部观测周：图与 all 相同（回归：cutoff 不误裁）"""
        body = _get(client, range="1y")
        assert body["weeks"] == _get(client, range="all")["weeks"]

    def test_52week_window_aligns_to_monday_grid(self, client, board_db):
        """v2 回归：52 周窗口起点天然落在周一（364 = 52×7，不再有旧 365 天
        方案「raw cutoff 落周日 → series 全 null」的错位缺陷）。
        2024-11-04 的旧观测在 52 周窗口外：不进统计、不进周历、不造点。"""
        _seed_week(board_db, date(2024, 11, 4), {"000004": ("基金D旧", 0.42)})
        _seed_week(board_db, WEEK1, {"000001": ("基金A", 0.95), "000002": ("基金B", 0.90), "000004": ("基金D", 0.50)})
        _seed_week(board_db, WEEK2, {"000002": ("基金B", 0.92), "000004": ("基金D", 0.50)})
        _seed_week(board_db, WEEK3, {"000001": ("基金A", 1.05), "000002": ("基金B", 0.94), "000004": ("基金D", 0.50)})
        body = _get(client, range="1y")
        weeks = [date.fromisoformat(w) for w in body["weeks"]]
        # current=WEEK3(2026-11-02)，窗口起点 = current - 51 周 = 2025-11-10（周一）
        assert weeks[0] == date(2025, 11, 10)
        assert weeks[0].weekday() == 0
        assert (weeks[-1] - weeks[0]).days == 51 * 7  # 恰 51 个整周
        assert weeks[-1] == WEEK3  # 终点仍为当前周
        assert all(w.weekday() == 0 for w in weeks)  # 全周一网格
        d_series = [s for s in body["series"] if s["code"] == "000004"][0]
        assert d_series["values"][-3:] == [0.50, 0.50, 0.50]  # 窗口内点对位成功
        assert d_series["values"][0] is None  # 2024-11-04 旧点被窗口裁掉
        # 1y 与 all 等价（52 周整窗口）；统计只按窗口内累计
        all_body = _get(client, range="all")
        assert body["weeks"] == all_body["weeks"]
        it_1y = {it["code"]: it for it in body["items"]}["000004"]
        it_all = {it["code"]: it for it in all_body["items"]}["000004"]
        assert it_1y["listed_weeks"] == it_all["listed_weeks"] == 3  # 旧周不计


class TestStatusSemantics:
    """AC6/R6/R7：失败、停机空位、首次无历史"""

    def test_failed_current_week_shows_old_board_and_stale(self, client, board_db):
        """当周失败：旧榜日期 + stale + 错误原文透出，不冒充本周；
        failed 周无观测 → B 只 2 周、A 只 1 周"""
        _seed_week(board_db, WEEK1, {"000001": ("基金A", 0.95), "000002": ("基金B", 0.90)})
        _seed_week(board_db, WEEK2, {"000002": ("基金B", 0.92)})
        _seed_week(board_db, WEEK3, status="failed", errors=["risk:nav:000001: 东财网络超时"])
        body = _get(client)
        assert body["stale"] is True
        assert body["latest_published_week"] == "2026-10-26"  # 旧榜
        assert body["latest_attempt"]["week_start"] == "2026-11-02"
        assert body["latest_attempt"]["status"] == "failed"
        assert body["latest_attempt"]["errors"] == ["risk:nav:000001: 东财网络超时"]
        by_code = {it["code"]: it for it in body["items"]}
        assert by_code["000001"]["listed_weeks"] == 1
        assert by_code["000002"]["listed_weeks"] == 2
        assert body["series"] and {s["code"]: s["values"] for s in body["series"]}[
            "000001"] == [0.95, None, None]

    def test_gap_week_axis_with_downtime(self, client, board_db):
        """停机周在周历留空位：WEEK2 无任何周行 → weeks 仍三格 + 诊断列出无榜周"""
        _seed_week(board_db, WEEK1, {"000001": ("基金A", 0.95)})
        _seed_week(board_db, WEEK3, {"000001": ("基金A", 1.05)})
        body = _get(client)
        assert body["weeks"] == ["2026-10-19", "2026-10-26", "2026-11-02"]
        assert body["diagnostics"]["no_board_weeks"] == ["2026-10-26"]
        assert body["series"][0]["values"] == [0.95, None, 1.05]
        # 缺席/未知中断连续计数：10-26 未知 → 最近连续 1 周
        assert body["items"][0]["consecutive_weeks"] == 1

    def test_no_history_empty_state(self, client, board_db):
        """首次无数据：零榜 → total=0、weeks 空、stale、无 published"""
        body = _get(client)
        assert body["total"] == 0
        assert body["items"] == []
        assert body["weeks"] == []
        assert body["series"] == []
        assert body["latest_published_week"] is None
        assert body["latest_attempt"] is None
        assert body["stale"] is True

    def test_only_failed_attempt_no_axis(self, client, board_db):
        """只有失败尝试（无 complete）→ 无观测无轴，latest_attempt 带错误"""
        _seed_week(board_db, WEEK3, status="failed", errors=["名单没抓到"])
        body = _get(client)
        assert body["total"] == 0
        assert body["weeks"] == []
        assert body["latest_published_week"] is None
        assert body["latest_attempt"]["status"] == "failed"
        assert body["latest_attempt"]["errors"] == ["名单没抓到"]
        assert body["stale"] is True

    def test_skipped_week_visible_in_diagnostics(self, client, board_db):
        """skipped_no_new_data 周也无榜（R6：不重复抄旧值冒充在榜）"""
        _seed_week(board_db, WEEK1, {"000001": ("基金A", 0.95)})
        _seed_week(board_db, WEEK2, status="skipped_no_new_data",
                   diagnostics={"stale_codes": ["000001"]})
        _seed_week(board_db, WEEK3, {"000001": ("基金A", 1.05)})
        body = _get(client)
        assert body["diagnostics"]["no_board_weeks"] == ["2026-10-26"]
        assert body["diagnostics"]["latest_diagnostics"] == {}  # 最新是 WEEK3 complete
        assert body["items"][0]["listed_weeks"] == 2
        assert body["items"][0]["consecutive_weeks"] == 1


class TestHistoryPreservation:
    """AC8/R8：失活基金历史仍在；来源/版本隔离"""

    def test_inactive_fund_history_kept(self, client, board_db):
        """聚合不 JOIN 实时 Fund：观测里的 code 不在 funds 表也照常出榜"""
        _seed_week(board_db, WEEK1, {"999999": ("已清盘基金", 0.85)})
        body = _get(client)
        assert body["total"] == 1
        assert body["items"][0]["code"] == "999999"
        assert body["items"][0]["name"] == "已清盘基金"

    def test_source_isolation(self, client, board_db):
        """两来源独立记录，互不混算（AC7）"""
        _seed_three_weeks(board_db, source="stock")
        _seed_three_weeks(board_db, source="discovery-stock")
        stock_body = _get(client, source="stock")
        ds_body = _get(client, source="discovery-stock")
        assert stock_body["total"] == ds_body["total"] == 2
        assert stock_body["profile"]["source"] == "stock"
        assert ds_body["profile"]["source"] == "discovery-stock"
        assert ds_body["profile"]["collection_prefilters"] != {}
        assert stock_body["profile"]["collection_prefilters"] == {}

    def test_default_source_is_discovery_stock(self, client, board_db):
        """不带 source 走默认 discovery-stock（design 合同）"""
        _seed_three_weeks(board_db, source="discovery-stock")
        body = client.get("/api/funds/sharpe-board?profile_version=v1").json()
        assert body["profile"]["source"] == "discovery-stock"
        assert body["total"] == 2

    def test_version_isolation(self, board_db, fixed_now):
        """同来源不同版本互不混算（AC7）：v1 聚合不含 v2 行的数据。
        （v2 行手写 profile 副本；未知版本在 API 层 404，聚合 profile 取自常量表）"""
        _seed_three_weeks(board_db, source="stock")
        row = SharpeBoardWeek(
            source="stock", profile_version="v2", week_start=WEEK1,
            profile_json="{}", profile_hash="h2",
            algorithm_version="risk-3y-v1", status="complete",
            selected_count=1, started_at=_STARTED_UTC,
        )
        board_db.add(row)
        board_db.flush()
        board_db.add(SharpeBoardObservation(
            week_id=row.id, code="888888", name="v2基金", sharpe=0.99,
        ))
        board_db.commit()
        v1_body = sbs.aggregate_board(board_db, source="stock", profile_version="v1")
        assert v1_body["total"] == 2
        assert {it["code"] for it in v1_body["items"]} == {"000001", "000002"}
        assert "888888" not in {s["code"] for s in v1_body["series"]}
        assert v1_body["weeks"] == [WEEK1, WEEK2, WEEK3]  # service 直调返回 date 对象


class TestPaginationInvariants:
    """AC10 + contracts 分页不变量：total 切片前算、切片在排序后、series 不随分页"""

    @pytest.fixture
    def five_code_db(self, board_db):
        entries = {
            "000001": ("基金A", 1.0), "000002": ("基金B", 0.9),
            "000003": ("基金C", 0.8), "000004": ("基金D", 0.7),
            "000005": ("基金E", 0.6),
        }
        _seed_week(board_db, WEEK1, entries)
        return board_db

    def test_total_stable_across_pages(self, client, five_code_db):
        pages = [_get(client, page=p, limit=2) for p in (1, 2, 3, 4)]
        assert all(p["total"] == 5 for p in pages)
        assert [len(p["items"]) for p in pages] == [2, 2, 1, 0]  # 越界空，total 不变
        codes = [it["code"] for p in pages[:3] for it in p["items"]]
        assert codes == ["000001", "000002", "000003", "000004", "000005"]  # 无重叠无遗漏
        # 同周数按最近上榜夏普降序（R3 第二键）

    def test_series_not_paged(self, client, five_code_db):
        body = _get(client, page=1, limit=2)
        assert body["total"] == 5  # total 是筛后总数，不受 page/limit 影响
        assert len(body["items"]) == 2  # items 只当前页
        assert len(body["series"]) == 5  # series 全部命中基金
        assert {s["code"] for s in body["series"]} == {
            "000001", "000002", "000003", "000004", "000005",
        }

    def test_multi_week_ordering_key_combo(self, board_db, fixed_now):
        """排序三键联合：周数 desc → 夏普 desc → code asc"""
        _seed_week(board_db, WEEK1, {
            "000003": ("C", 0.9), "000004": ("D", 0.9),  # 同周同 sharpe → code asc
        })
        _seed_week(board_db, WEEK2, {"000003": ("C", 0.9), "000001": ("A", 0.5)})
        _seed_week(board_db, WEEK3, {"000003": ("C", 0.95), "000002": ("B", 1.2)})
        body = sbs.aggregate_board(board_db, source="stock", profile_version="v1")
        # C 3 周；其余 1 周，按最近夏普降序 B 1.2 → D 0.9 → A 0.5
        assert [it["code"] for it in body["items"]] == ["000003", "000002", "000004", "000001"]


class TestApiValidation:
    """参数合同：非法 422、未知版本 404"""

    @pytest.mark.parametrize("qs", [
        "source=bond",            # 白名单外
        "source=",                # 空
        "min_latest_sharpe=11",   # 越上界
        "min_latest_sharpe=-11",  # 越下界
        "min_weeks=0",
        "min_weeks=-1",
        "range=2m",               # 白名单外
        "page=0",
        "page=-1",
        "limit=0",
        "limit=201",
        "limit=1000",
    ])
    def test_invalid_params_422(self, client, qs):
        assert client.get(f"/api/funds/sharpe-board?{qs}").status_code == 422

    def test_unknown_version_404(self, client):
        r = client.get("/api/funds/sharpe-board?profile_version=v9")
        assert r.status_code == 404

    def test_default_params_ok(self, client, board_db):
        """全部默认参数 → 200；默认规则版本已切 v3（11-14 任务）"""
        _seed_three_weeks(board_db, source="discovery-stock", version="v3")
        r = client.get("/api/funds/sharpe-board")
        assert r.status_code == 200
        body = r.json()
        assert body["profile"]["version"] == "v3"
        assert body["profile"]["algorithm_version"] == "risk-3y-v3"
        # 显式 v1 仍可访问（版本隔离，历史不被污染）
        r1 = client.get("/api/funds/sharpe-board?profile_version=v1")
        assert r1.status_code == 200
        assert r1.json()["profile"]["version"] == "v1"

    def test_response_fields_all_present(self, client, board_db):
        """design 返回体 9 个顶层字段全部透出（Pydantic 静默砍字段陷阱）"""
        _seed_three_weeks(board_db)
        body = _get(client)
        for key in ("profile", "latest_published_week", "latest_attempt",
                    "stale", "total", "items", "weeks", "series", "diagnostics"):
            assert key in body, f"响应缺 {key} 字段（schema 未声明）"
        item = body["items"][0]
        for key in ("code", "name", "listed_weeks", "consecutive_weeks",
                    "latest_sharpe", "last_listed_week", "on_latest_board",
                    # v2 新增（DTO 显式声明，防 Pydantic 静默砍字段）
                    "near_12w_qualified", "near_12w_total", "peer_pct", "peer_as_of",
                    # v3 年度口径
                    "peer_years", "peer_qualified_years", "peer_window"):
            assert key in item
        attempt = body["latest_attempt"]
        for key in ("week_start", "status", "trigger", "started_at",
                    "finished_at", "selected_count", "errors"):
            assert key in attempt

    def test_route_registered_before_detail_route(self, client):
        """/sharpe-board 不被通用 /{code} 吞掉（注册顺序证据：响应是榜单结构）"""
        body = client.get("/api/funds/sharpe-board?profile_version=v1").json()
        assert "profile" in body  # 若被 /{code} 匹配会返回 404/基金详情结构


class TestServiceLevelAggregation:
    """service 直调（不经 HTTP）：边界周、诊断结构"""

    def test_diagnostics_payload_shape(self, board_db, fixed_now):
        _seed_week(board_db, WEEK3, status="failed",
                   diagnostics={"stale_codes": ["000001"]},
                   errors=["x"])
        body = sbs.aggregate_board(board_db, source="stock", profile_version="v1")
        assert body["diagnostics"]["no_board_weeks"] == []
        assert body["diagnostics"]["latest_diagnostics"] == {"stale_codes": ["000001"]}
        assert body["latest_attempt"]["errors"] == ["x"]

    def test_attempt_time_is_shanghai_aware(self, board_db, fixed_now):
        """UTC 存储行 → latest_attempt 时间带 +08:00（展示北京时间契约）"""
        _seed_week(board_db, WEEK3, {"000001": ("A", 0.9)})
        body = sbs.aggregate_board(board_db, source="stock", profile_version="v1")
        started = body["latest_attempt"]["started_at"]
        assert isinstance(started, datetime)
        assert started.utcoffset().total_seconds() == 8 * 3600
        # UTC 2026-10-31 00:05 → 北京 2026-10-31 08:05
        assert (started.year, started.month, started.day, started.hour) == (2026, 10, 31, 8)
