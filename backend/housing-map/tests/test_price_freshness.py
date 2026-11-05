"""价格时效政策回归（11-04-housing-price-freshness 批次 A）。

覆盖: 上海当前月 6/7 个月边界、双价独立投影、未知月份不得用采集日期顶替、
30 天陈旧提示（与成交月有效期独立计算）、来源换绑与合并来源按价格类型选最新。
所有日期由注入的 today 提供, 不依赖执行当天。
"""

import json
from datetime import date
from pathlib import Path

import pytest

from src.services.data_loader import load_price_snapshots
from src.services.price_policy import (
    MAX_DEAL_AGE_MONTHS,
    STALE_AFTER_DAYS,
    collection_stale,
    deal_month_is_current,
    month_gap_from_today,
    project_price_record,
    shanghai_today,
)
from src.services.tmsf_fetcher import build_snapshots

# 固定"今天": 上海时区 2026-11-15。所有月差/天数都相对它断言。
TODAY = date(2026, 11, 15)


# ---------------------------------------------------------------------------
# 造数 helper
# ---------------------------------------------------------------------------

def _deal_record(cid="A", avg_price=200, latest_month="2026-10", snapshot_date="2026-11-01",
                 crawled_at=None, listing_count=6, deal_count=2):
    record = {
        "community_id": cid,
        "avg_price": avg_price,
        "price_type": "monthly_deal_avg_latest",
        "snapshot_date": snapshot_date,
        "listing_count": listing_count,
        "deal_count": deal_count,
        "source_url": f"https://www.tmsf.com/esf/xq_xqtendency_{cid}.htm",
        "raw_payload": {"tendency": {"latest_month": latest_month}} if latest_month else {},
    }
    if crawled_at:
        record["crawled_at"] = crawled_at
    return record


def _listing_record(cid="A", avg_price=100, snapshot_date="2026-11-01",
                    crawled_at=None, listing_count=5, deal_count=0):
    record = {
        "community_id": cid,
        "avg_price": avg_price,
        "price_type": "listing_avg",
        "snapshot_date": snapshot_date,
        "listing_count": listing_count,
        "deal_count": deal_count,
        "source_url": f"https://www.tmsf.com/esf/xq_indexnew_{cid}.htm",
    }
    if crawled_at:
        record["crawled_at"] = crawled_at
    return record


def _write_jsonl(tmp_path, records, name="price_snapshots.jsonl") -> Path:
    path = tmp_path / name
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )
    return path


def _seed_registry(tmp_path, rows):
    """最小 registry: communities + matched tmsf 来源, 供 load_price_snapshots 关联。"""
    from src.services.community_registry import CommunityRegistry

    store = CommunityRegistry(tmp_path / "community_registry.sqlite3")
    with store.db() as db:
        for cid in {row[2] for row in rows}:
            db.execute("INSERT INTO communities(id, payload) VALUES (?, '{}')", (cid,))
        for rid, sid, cid in rows:
            db.execute(
                "INSERT INTO sources(id, source, kind, sid, payload, cid, status)"
                " VALUES (?, 'tmsf', 'community', ?, '{}', ?, 'matched')",
                (rid, sid, cid),
            )
    return store


# ---------------------------------------------------------------------------
# price_policy: 上海日期与月度有效期（A1: 6/7 个月边界, 恰好 6 有效）
# ---------------------------------------------------------------------------

def test_month_gap_exactly_six_months_stays_current():
    assert month_gap_from_today("2026-05", today=TODAY) == 6
    assert deal_month_is_current("2026-05", today=TODAY) is True


def test_month_gap_seven_months_is_expired():
    assert month_gap_from_today("2026-04", today=TODAY) == 7
    assert deal_month_is_current("2026-04", today=TODAY) is False


def test_same_month_and_future_month_bounds():
    assert deal_month_is_current("2026-11", today=TODAY) is True
    # 未来月份是异常数据, 不视为有效当前价
    assert deal_month_is_current("2026-12", today=TODAY) is False


def test_unparseable_deal_month_is_not_current():
    for bad in (None, "", "abc", "2026-13", "2026"):
        assert deal_month_is_current(bad, today=TODAY) is False
    assert month_gap_from_today("abc", today=TODAY) is None


def test_deal_expires_naturally_as_today_advances():
    # 同一条 2026-05 成交价: 当前月 11 月有效, 推进到 12 月自然过期（A1）
    assert deal_month_is_current("2026-05", today=TODAY) is True
    assert deal_month_is_current("2026-05", today=date(2026, 12, 1)) is False


def test_shanghai_today_prefers_injected_date():
    assert shanghai_today(TODAY) == TODAY


# ---------------------------------------------------------------------------
# price_policy: 30 天陈旧提示（R1: 与 6 个月有效期分别计算）
# ---------------------------------------------------------------------------

def test_stale_collection_after_thirty_days():
    assert STALE_AFTER_DAYS == 30
    assert collection_stale("2026-10-15", today=TODAY) is True   # 恰好 31 天
    assert collection_stale("2026-10-16", today=TODAY) is False  # 恰好 30 天不算超期


def test_stale_collection_accepts_iso_timestamp_and_rejects_unknown():
    assert collection_stale("2026-10-01T03:00:00+00:00", today=TODAY) is True
    assert collection_stale(None, today=TODAY) is False
    assert collection_stale("垃圾", today=TODAY) is False


def test_stale_flag_is_independent_of_month_validity():
    # 月差 1 个月（有效）但 40 天未采集: 仍是当前价, 同时带陈旧提示
    month, captured = "2026-10", "2026-10-06"
    assert deal_month_is_current(month, today=TODAY) is True
    assert collection_stale(captured, today=TODAY) is True


# ---------------------------------------------------------------------------
# price_policy: 单条记录投影
# ---------------------------------------------------------------------------

def test_deal_record_projects_month_and_capture():
    entry = project_price_record(_deal_record(), today=TODAY)
    assert entry["current"] is True
    assert entry["expired"] is False
    assert entry["price"] == 200
    assert entry["month"] == "2026-10"
    assert entry["captured_at"] == "2026-11-01"
    assert entry["source_url"].endswith("xq_xqtendency_A.htm")
    assert entry["stale"] is False


def test_listing_record_has_no_deal_month():
    # 挂牌价没有成交月份概念, 不得用采集日期顶替月份（R1）
    entry = project_price_record(_listing_record(), today=TODAY)
    assert entry["current"] is True
    assert entry["month"] is None
    assert entry["captured_at"] == "2026-11-01"


def test_listing_without_active_listings_projects_none():
    assert project_price_record(_listing_record(listing_count=0), today=TODAY) is None
    assert project_price_record(_listing_record(listing_count=None), today=TODAY) is None


def test_deal_without_month_projects_none():
    # 未知月份不得用采集日期代替（R1）: 不产出当前价也不产出历史价
    assert project_price_record(_deal_record(latest_month=None), today=TODAY) is None
    assert project_price_record(_deal_record(latest_month="bad"), today=TODAY) is None


def test_expired_deal_projects_as_history():
    entry = project_price_record(_deal_record(latest_month="2026-04"), today=TODAY)
    assert entry["current"] is False
    assert entry["expired"] is True
    assert entry["price"] == 200
    assert entry["month"] == "2026-04"


# ---------------------------------------------------------------------------
# data_loader.load_price_snapshots: 双价投影与兼容字段
# ---------------------------------------------------------------------------

def test_dual_prices_returned_independently(tmp_path):
    path = _write_jsonl(tmp_path, [_deal_record(), _listing_record()])
    entry = load_price_snapshots(path, today=TODAY)["A"]

    # 兼容字段: 有效签约优先
    assert entry["price"] == 200
    assert entry["price_type"] == "monthly_deal_avg_latest"
    assert entry["date"] == "2026-11-01"
    # 双价独立返回（R2）, 各自带月份/采集日/来源/陈旧标记
    assert entry["deal"]["price"] == 200
    assert entry["deal"]["month"] == "2026-10"
    assert entry["listing"]["price"] == 100
    assert entry["listing"]["month"] is None
    assert entry["deal"]["source_url"] != entry["listing"]["source_url"]
    assert entry["history_deal"] is None


def test_listing_backfills_compatible_price_without_deal(tmp_path):
    path = _write_jsonl(tmp_path, [_listing_record()])
    entry = load_price_snapshots(path, today=TODAY)["A"]

    assert entry["price"] == 100
    assert entry["price_type"] == "listing_avg"
    assert entry["deal"] is None
    assert entry["listing"]["price"] == 100


def test_expired_deal_with_listing_switches_compatible_price_to_listing(tmp_path):
    # 2026-04 成交已过期（月差 7）: 只进 history_deal, 兼容价回落到挂牌（A1/R2）
    path = _write_jsonl(tmp_path, [
        _deal_record(latest_month="2026-04"),
        _listing_record(),
    ])
    entry = load_price_snapshots(path, today=TODAY)["A"]

    assert entry["deal"] is None
    assert entry["history_deal"]["price"] == 200
    assert entry["history_deal"]["month"] == "2026-04"
    assert entry["price"] == 100
    assert entry["price_type"] == "listing_avg"


def test_expired_deal_without_listing_keeps_history_and_counts(tmp_path):
    # 无有效当前价: 兼容价置空, 但历史与套数照常返回（R1: 允许"暂无近期价格"）
    path = _write_jsonl(tmp_path, [_deal_record(latest_month="2026-04")])
    entry = load_price_snapshots(path, today=TODAY)["A"]

    assert entry["price"] is None
    assert entry["price_type"] is None
    assert entry["date"] is None
    assert entry["history_deal"]["price"] == 200
    assert entry["counts"]["deal_count"] == 2
    assert entry["counts"]["listing_count"] == 6


def test_unknown_month_deal_yields_no_current_price_but_counts(tmp_path):
    # 未知月份: 不进当前价也不进历史, 套数独立保留
    path = _write_jsonl(tmp_path, [_deal_record(latest_month=None)])
    entry = load_price_snapshots(path, today=TODAY)["A"]

    assert entry["deal"] is None
    assert entry["history_deal"] is None
    assert entry["price"] is None
    assert entry["counts"]["deal_count"] == 2


def test_stale_price_is_kept_with_original_capture_date(tmp_path):
    # 31 天未成功更新: 价格与原采集日期保留, stale=True（R1）; 月差 1 仍有效
    path = _write_jsonl(tmp_path, [
        _deal_record(latest_month="2026-10", snapshot_date="2026-10-15"),
    ])
    entry = load_price_snapshots(path, today=TODAY)["A"]

    assert entry["price"] == 200
    assert entry["deal"]["stale"] is True
    assert entry["deal"]["captured_at"] == "2026-10-15"
    assert entry["date"] == "2026-10-15"


def test_counts_only_record_updates_counts_but_not_prices(tmp_path):
    # counts_only 快照（抓到首页但无任何价格）: 只贡献套数槽, 不冒充价格（R3）
    path = _write_jsonl(tmp_path, [{
        "community_id": "A", "avg_price": None, "price_type": "counts_only",
        "listing_count": 7, "deal_count": 2, "snapshot_date": "2026-11-10",
        "source_url": "https://www.tmsf.com/esf/xq_indexnew_A.htm",
    }])
    entry = load_price_snapshots(path, today=TODAY)["A"]

    assert entry["price"] is None
    assert entry["deal"] is None
    assert entry["listing"] is None
    assert entry["counts"] == {"listing_count": 7, "deal_count": 2, "captured_at": "2026-11-10"}


def test_price_record_without_counts_does_not_reset_old_counts_capture(tmp_path):
    # 缺套数的新价格记录（如 index 页失败只抓到走势）不得把旧套数标成本轮采集（R3）
    path = _write_jsonl(tmp_path, [
        _deal_record(snapshot_date="2026-11-01", listing_count=None, deal_count=None),
        _listing_record(snapshot_date="2026-10-01", listing_count=6, deal_count=2),
    ])
    entry = load_price_snapshots(path, today=TODAY)["A"]

    # 套数槽保留旧记录的采集时间; 价格槽用新记录
    assert entry["deal"]["price"] == 200
    assert entry["counts"]["listing_count"] == 6
    assert entry["counts"]["captured_at"] == "2026-10-01"


def test_counts_carry_independent_capture_time_and_honest_zero(tmp_path):
    # 最新的挂牌记录 listing_count=0: 无挂牌价条目, 但套数如实计 0 并附采集时间（R3）
    path = _write_jsonl(tmp_path, [
        _listing_record(snapshot_date="2026-10-01"),
        _listing_record(avg_price=90, snapshot_date="2026-11-01", listing_count=0),
    ])
    entry = load_price_snapshots(path, today=TODAY)["A"]

    assert entry["listing"]["price"] == 100  # 挂牌价槽取"产出条目"的最新记录
    assert entry["counts"]["listing_count"] == 0
    assert entry["counts"]["captured_at"] == "2026-11-01"


def test_per_type_latest_wins_regardless_of_file_order(tmp_path):
    # 合并来源按价格类型分别选最新记录, 不按文件顺序覆盖（design: 双价投影）
    path = _write_jsonl(tmp_path, [
        _deal_record(avg_price=210, snapshot_date="2026-11-02"),   # 新 deal 在前
        _listing_record(avg_price=110, snapshot_date="2026-11-02"),
        _deal_record(avg_price=190, snapshot_date="2026-10-20"),   # 旧 deal 在后
        _listing_record(avg_price=90, snapshot_date="2026-10-20"),
    ])
    entry = load_price_snapshots(path, today=TODAY)["A"]

    assert entry["deal"]["price"] == 210
    assert entry["deal"]["month"] == "2026-10"
    assert entry["listing"]["price"] == 110
    assert entry["price"] == 210


def test_merge_sources_select_latest_per_price_type(tmp_path):
    # 来源换绑/多来源: deal 取 S1（更新）, listing 取 S2, 互不整体覆盖
    _seed_registry(tmp_path, [("r1", "S1", "home"), ("r2", "S2", "home")])
    path = _write_jsonl(tmp_path, [
        _deal_record(cid="S1", avg_price=210, snapshot_date="2026-11-02"),
        _deal_record(cid="S2", avg_price=180, snapshot_date="2026-10-20"),
        _listing_record(cid="S2", avg_price=95, snapshot_date="2026-11-01"),
        _listing_record(cid="S1", avg_price=85, snapshot_date="2026-10-01"),
    ])
    entry = load_price_snapshots(path, today=TODAY)["home"]

    assert entry["deal"]["price"] == 210
    assert entry["listing"]["price"] == 95
    assert entry["price"] == 210
    # 未在 registry 中的来源不出现
    assert "S9" not in load_price_snapshots(path, today=TODAY)


def test_refresh_status_is_normalized_from_sidecar(tmp_path):
    # price_refresh_status.json 归一化（批次 B 定稿形状）: 条目必须带 outcome 字段,
    # 无文件/坏条目归一为缺失, 不编造未知字段
    path = _write_jsonl(tmp_path, [_deal_record()])
    (tmp_path / "price_refresh_status.json").write_text(json.dumps({
        "A": {
            "community_id": "A", "outcome": "failed", "partial": False,
            "retained": True, "retained_reason": "fetch_failed",
            "retained_price_date": "2026-10-01", "price_updated": False,
            "counts_updated": False, "mode": "all",
            "run_id": "2026-11-03T01:00:00.000Z", "updated_at": "2026-11-03T01:05:00.000Z",
        },
        "bad": {"last_attempt_at": "2026-11-03T01:00:00+00:00"},  # 无 outcome: 忽略
    }, ensure_ascii=False), encoding="utf-8")
    entries = load_price_snapshots(path, today=TODAY)

    assert entries["A"]["refresh"]["outcome"] == "failed"
    assert entries["A"]["refresh"]["retained_reason"] == "fetch_failed"

    entry_no_file = load_price_snapshots(_write_jsonl(tmp_path, [_deal_record(cid="B")], name="other.jsonl"),
                                         today=TODAY)
    assert entry_no_file["B"]["refresh"] is None


def test_legacy_snapshot_without_new_fields_still_loads(tmp_path):
    # 旧快照兼容: 只有兼容字段的历史记录照常加载, 新字段缺失归一为 None（R4）
    legacy = {
        "community_id": "A", "avg_price": 300, "price_type": "listing_avg",
        "listing_count": 7, "deal_count": 0, "snapshot_date": "2026-09-01",
    }
    path = _write_jsonl(tmp_path, [legacy])
    entry = load_price_snapshots(path, today=TODAY)["A"]

    assert entry["price"] == 300
    assert entry["listing"]["price"] == 300
    assert entry["deal"] is None
    assert entry["history_deal"] is None
    assert entry["refresh"] is None


def test_newhouse_records_never_enter_projection(tmp_path):
    # 新房隔离: new_house 快照与 /newhouse/ URL 不进二手价投影
    path = _write_jsonl(tmp_path, [
        {**_deal_record(cid="N2", latest_month="2026-10"), "market_state": "new_house"},
        {**_listing_record(cid="N3"), "source_url": "https://www.tmsf.com/newhouse/xxx.htm"},
    ])
    assert load_price_snapshots(path, today=TODAY) == {}


# ---------------------------------------------------------------------------
# 采集器: 走势点数不再是成交样本数（R4: trend_point_count）; counts-only 快照（R3）
# ---------------------------------------------------------------------------

INDEX_HTML = """
<span class="big">测试花园</span>
在售房源：<font style="color:red">7</font> 套
挂牌均价<span> </span>32000元/㎡
"""

INDEX_COUNTS_ONLY_HTML = """
<span class="big">测试花园</span>
近30日签约 <font>2</font> 套
"""

INDEX_UNPARSEABLE_HTML = "<html><body>验证盾拦截页</body></html>"

TENDENCY_HTML = (
    "var tendency2 = '[{\"ticks\":[\"2026-08\",\"2026-09\",\"2026-10\"],"
    "\"line\":[31000,31500,32000]}]';"
)

EMPTY_TENDENCY_HTML = "<html><body>暂无走势</body></html>"


def test_builder_records_trend_point_count_not_as_sample_count():
    snapshots = build_snapshots("100", INDEX_HTML, TENDENCY_HTML)
    by_type = {s.price_type: s for s in snapshots}

    deal = by_type["monthly_deal_avg_latest"]
    assert deal.avg_price == 32000
    assert deal.raw_payload["tendency"]["latest_month"] == "2026-10"
    # 走势图长度记入 trend_point_count, 不再冒充成交样本数（R4）
    assert deal.trend_point_count == 3
    assert deal.sample_count == 0
    # 固定置信度不作为测量值暴露
    assert deal.confidence_score is None

    listing = by_type["listing_avg"]
    assert listing.trend_point_count is None
    assert listing.sample_count == 7  # 挂牌套数是真实样本数
    assert listing.confidence_score is None


def test_builder_emits_counts_only_snapshot_without_any_price():
    # 抓到首页且解析出套数但没有任何价格: 生成 counts_only 快照（R3）
    snapshots = build_snapshots("100", INDEX_COUNTS_ONLY_HTML, EMPTY_TENDENCY_HTML)

    assert [s.price_type for s in snapshots] == ["counts_only"]
    counts = snapshots[0]
    assert counts.avg_price is None
    assert counts.deal_count == 2
    assert counts.trend_point_count is None
    assert counts.confidence_score is None


def test_builder_emits_nothing_when_index_page_unparseable():
    # 首页连套数都解析不出: 不产出记录, 由刷新层按解析失败处理（R3）
    assert build_snapshots("100", INDEX_UNPARSEABLE_HTML, EMPTY_TENDENCY_HTML) == []


def test_builder_does_not_emit_counts_only_when_prices_exist():
    # 有价格快照时不额外生成 counts_only（套数随价格快照携带）
    snapshots = build_snapshots("100", INDEX_HTML, TENDENCY_HTML)
    assert {s.price_type for s in snapshots} == {"monthly_deal_avg_latest", "listing_avg"}


# ---------------------------------------------------------------------------
# API 投影: routes._assemble_community 透出新字段且新房隔离（R2/A3）
# ---------------------------------------------------------------------------

def _full_price_entry():
    return {
        "price": 200, "price_type": "monthly_deal_avg_latest", "date": "2026-11-01",
        "deal": {"price": 200, "month": "2026-10", "captured_at": "2026-11-01",
                 "source_url": "u1", "stale": False},
        "listing": {"price": 100, "month": None, "captured_at": "2026-10-01",
                    "source_url": "u2", "stale": True},
        "history_deal": None,
        "counts": {"listing_count": 6, "deal_count": 2, "captured_at": "2026-11-01"},
        "refresh": {"status": "failed"},
    }


def test_assemble_community_projects_price_details():
    from src.api.routes import _assemble_community

    record = _assemble_community(
        {"community_id": "A", "community_name": "花园"},
        coordinates={}, pois_block={"pois": {}}, price_data=_full_price_entry(),
        subway_stations=[], community_ages={}, community_attrs={},
    )
    price = record["price"]
    assert price["deal"]["month"] == "2026-10"
    assert price["listing"]["stale"] is True
    assert price["counts"] == {"listing_count": 6, "deal_count": 2, "captured_at": "2026-11-01"}
    assert price["refresh"] == {"status": "failed"}
    assert price["deal_avg_price"] == 200
    assert price["listing_avg_price"] is None


def test_new_house_price_block_stays_isolated():
    from src.api.routes import _assemble_community

    record = _assemble_community(
        {"community_id": "A", "community_name": "花园", "market_state": "new_house"},
        coordinates={}, pois_block={"pois": {}}, price_data=_full_price_entry(),
        subway_stations=[], community_ages={}, community_attrs={},
    )
    price = record["price"]
    # 新房不得泄漏二手价格与新字段（R2/A3）
    assert price["deal_avg_price"] is None
    assert price["listing_avg_price"] is None
    assert price["deal"] is None
    assert price["listing"] is None
    assert price["history_deal"] is None
    assert price["counts"] is None


# ---------------------------------------------------------------------------
# 租售比消费方: 日期优先用价格所属月份, 不用采集日期顶替（R1）
# ---------------------------------------------------------------------------

def test_sale_reference_prefers_price_month_over_capture_date():
    from src.api.rental_routes import _sale_reference

    prices = {"A": _full_price_entry()}
    reference, price = _sale_reference(prices, "A")

    assert price == 200
    assert reference["price_kind"] == "signed"
    assert reference["price_date"] == "2026-10"  # deal.month, 不是采集日 2026-11-01


def test_sale_reference_falls_back_to_capture_date_without_month():
    from src.api.rental_routes import _sale_reference

    prices = {"B": {
        "price": 100, "price_type": "listing_avg", "date": "2026-09-20",
        "deal": None,
        "listing": {"price": 100, "month": None, "captured_at": "2026-09-20",
                    "source_url": "u", "stale": False},
        "history_deal": None, "counts": None, "refresh": None,
    }}
    reference, price = _sale_reference(prices, "B")

    assert price == 100
    assert reference["price_kind"] == "listing"
    assert reference["price_date"] == "2026-09-20"
