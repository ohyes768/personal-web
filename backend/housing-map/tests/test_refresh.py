"""采集范围与刷新结果透明化回归（11-04 批次 B）。

覆盖: 仅已收录小区采集（缺轮廓仍采）、missing 补齐去重与数量、撤销收录/换绑
跳过且不落盘、部分页失败/全部失败/正常无价/仅过期价的区分、取消不发布、
原子发布与 CSV 失败边界、GET eligible/missing、409 空补齐、互斥并发拒绝。
所有日期由注入的 today 提供, 不依赖执行当天。
"""

import asyncio
from datetime import date
import json
from pathlib import Path

import pytest

from src.services import refresh
from src.services.refresh import (
    CSV_FIELDS,
    collectible_plans,
    eligibility_counts,
    missing_plans,
)
from src.services.tmsf_fetcher import CommunityFetchResult, PriceSnapshot

# 固定"今天": 上海时区 2026-11-15（与批次 A 保持同一基准）
TODAY = date(2026, 11, 15)

_RESET_JOB = {
    "running": False, "phase": "idle", "mode": None, "total": 0, "processed": 0,
    "okCount": 0, "errorCount": 0, "updated": 0, "noData": 0, "failed": 0,
    "skipped": 0, "retained": 0, "startedAt": None, "finishedAt": None,
    "error": None, "result": None,
}


@pytest.fixture(autouse=True)
def _reset_module_state():
    """模块级 job/取消标志复位, 避免用例间状态泄漏。"""
    yield
    refresh.job.clear()
    refresh.job.update(_RESET_JOB)
    refresh._cancel_requested = False
    refresh._task = None


# ---------------------------------------------------------------------------
# 造数 helper
# ---------------------------------------------------------------------------

def _admission(state: str) -> str:
    return json.dumps({"state": state, "decision_kind": "manual", "revision": 1},
                      ensure_ascii=False)


def _seed_community(tmp_path: Path, cid: str, sids: list[str], *, state: str = "admitted",
                    name: str = "测试花园", coords=(120.207490, 30.202261),
                    source_payload: dict | None = None) -> object:
    """最小 registry: 主档坐标 + 手工收录 + matched tmsf community 来源。

    不写任何轮廓文件——collectible_plans 不读轮廓, 缺轮廓的小区照常可采。
    coords=None 表示主档无坐标（missing_coordinates）。
    """
    from src.services.community_registry import CommunityRegistry

    payload = {
        "community_id": cid, "community_name": name, "district": "滨江",
        "address": "滨江区测试路1号", "aliases": [],
    }
    if coords is not None:
        payload.update(longitude=coords[0], latitude=coords[1])
    store = CommunityRegistry(tmp_path / "community_registry.sqlite3")
    with store.db() as db:
        db.execute("INSERT INTO communities(id, payload) VALUES (?, ?)",
                   (cid, json.dumps(payload, ensure_ascii=False)))
        db.execute("INSERT INTO community_admission VALUES (?, ?)", (cid, _admission(state)))
        for sid in sids:
            record = {"name": name, "district": "滨江", "listing_count": 5}
            record.update(source_payload or {})
            db.execute(
                "INSERT INTO sources(id, source, kind, sid, payload, cid, status)"
                " VALUES (?, 'tmsf', 'community', ?, ?, ?, 'matched')",
                (f"r-{cid}-{sid}", sid, json.dumps(record, ensure_ascii=False), cid))
    return store


def _snapshot(sid: str, price_type: str = "monthly_deal_avg_latest", *, avg_price=32000,
              latest_month="2026-11", snapshot_date="2026-11-10",
              listing_count=7, deal_count=2) -> PriceSnapshot:
    if price_type == "monthly_deal_avg_latest":
        raw_payload = {"tendency": {"latest_month": latest_month}} if latest_month else {}
    else:
        raw_payload = {}
    return PriceSnapshot(
        community_id=sid, community_name="测试花园", snapshot_date=snapshot_date,
        source="tmsf", price_type=price_type, avg_price=avg_price,
        listing_count=listing_count, deal_count=deal_count,
        sample_count=0 if price_type != "listing_avg" else (listing_count or 0),
        min_price=None, max_price=None,
        source_url=f"https://www.tmsf.com/esf/xq_{price_type}_{sid}.htm",
        raw_payload=raw_payload, crawled_at=f"{snapshot_date}T12:00:00+00:00",
    )


def _counts_snapshot(sid: str, *, listing_count=7, deal_count=2) -> PriceSnapshot:
    return _snapshot(sid, "counts_only", avg_price=None,
                     listing_count=listing_count, deal_count=deal_count)


def _run(plans, tmp_path: Path, *, fetcher, today=TODAY, old_rows=None,
         seed: bool = True) -> dict:
    if seed:
        for plan in plans:
            _seed_community(tmp_path, plan["community_id"], plan["sources"])
    snapshot_path = tmp_path / "price_snapshots.jsonl"
    snapshot_path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in (old_rows or [])),
        encoding="utf-8")
    backup_path = tmp_path / "price_snapshots.bak.jsonl"
    backup_path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in (old_rows or [])),
        encoding="utf-8")
    return asyncio.run(refresh.run_refresh_once(
        plans, snapshot_path, backup_path, tmp_path,
        fetcher=fetcher, sleep_seconds=0, today=today))


def _plan(cid: str, sids: list[str]) -> dict:
    return {"community_id": cid, "community_name": "测试花园", "sources": list(sids)}


def _deal_row(sid: str, *, snapshot_date="2026-10-01", latest_month="2026-09", avg_price=30000) -> dict:
    return {
        "community_id": sid, "price_type": "monthly_deal_avg_latest",
        "avg_price": avg_price, "listing_count": 7, "deal_count": 2,
        "snapshot_date": snapshot_date, "source_url": "https://www.tmsf.com/esf/xq_a.htm",
        "raw_payload": {"tendency": {"latest_month": latest_month}},
    }


# ---------------------------------------------------------------------------
# 采集资格（R5）: 仅已收录小区, all 与 missing 共用
# ---------------------------------------------------------------------------

def test_collectible_plans_only_admitted_with_matched_sources(tmp_path):
    """资格 = 有效 admitted + 覆盖内坐标 + 真实小区 + matched tmsf 来源。

    不依赖地图轮廓（本用例没有写任何轮廓文件）; pending/excluded/缺坐标/
    围栏外/道路名/新房/项目身份全部排除。
    """
    _seed_community(tmp_path, "home", ["S1"])
    _seed_community(tmp_path, "pending", ["S2"], state="pending")
    _seed_community(tmp_path, "excluded", ["S3"], state="excluded")
    _seed_community(tmp_path, "nocoord", ["S4"], coords=None)
    _seed_community(tmp_path, "outside", ["S5"], coords=(116.4, 39.9))  # 围栏外
    _seed_community(tmp_path, "road", ["S6"], name="江南大道")
    _seed_community(tmp_path, "newhouse", ["S7"],
                    source_payload={"market_state": "new_house"})
    _seed_community(tmp_path, "project", ["S8"], source_payload={"project_id": "999"})

    plans = collectible_plans(tmp_path)
    assert [plan["community_id"] for plan in plans] == ["home"]
    assert plans[0]["sources"] == ["S1"]


def test_collectible_plans_collects_every_matched_source_per_community(tmp_path):
    """合并带来的多个有效 community 来源按来源去重采集, UI/统计按主小区汇总。"""
    _seed_community(tmp_path, "home", ["S1", "S2"])
    plans = collectible_plans(tmp_path)
    assert len(plans) == 1
    assert plans[0]["sources"] == ["S1", "S2"]


def test_collectible_plans_empty_without_registry(tmp_path):
    """无台账不猜测已收录, 返回空计划（R5）。"""
    assert collectible_plans(tmp_path) == []


def test_missing_plans_requires_both_current_prices_missing():
    """补齐目标 = 两种当前可用价格都没有; 缺一种、超30天未更新但仍有价都不算缺。"""
    plans = [_plan("a", ["A"]), _plan("b", ["B"]), _plan("c", ["C"]), _plan("d", ["D"])]
    prices = {
        "a": {"deal": {"price": 1}, "listing": {"price": 2}},   # 双价齐全
        "b": {"deal": None, "listing": {"price": 2}},            # 只缺一种不算缺价
        # c 完全缺价
        "d": {"deal": {"price": 1, "stale": True}, "listing": None},  # 陈旧但仍有价
    }
    assert [plan["community_id"] for plan in missing_plans(plans, prices)] == ["c"]


def test_eligibility_counts_reports_eligible_and_missing(monkeypatch):
    monkeypatch.setattr(refresh, "collectible_plans",
                        lambda *a, **k: [_plan("a", ["A"]), _plan("c", ["C"])])
    monkeypatch.setattr(refresh, "load_price_snapshots",
                        lambda *a, **k: {"a": {"deal": {"price": 1}, "listing": None}})
    assert eligibility_counts() == {"eligible": 2, "missing": 1}


# ---------------------------------------------------------------------------
# 每轮结果透明化（R3）
# ---------------------------------------------------------------------------

def test_refresh_round_updates_prices_and_persists_status(tmp_path):
    fetch_calls = []

    def fetcher(sid, *, timeout):
        fetch_calls.append(sid)
        return CommunityFetchResult(snapshots=[_snapshot(sid)], errors=[])

    result = _run([_plan("home", ["S1"])], tmp_path, fetcher=fetcher)

    assert fetch_calls == ["S1"]
    assert result["outcome"] == "succeeded"
    assert result["published"] is True
    assert result["updated"] == 1
    assert result["noData"] == result["failed"] == result["skipped"] == 0
    assert result["retained"] == 0
    rows = [json.loads(line) for line in
            (tmp_path / "price_snapshots.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows and rows[0]["community_id"] == "S1"
    status = refresh.load_refresh_status(tmp_path)
    assert status["home"]["outcome"] == "updated"
    assert status["home"]["price_updated"] is True
    assert status["home"]["counts_updated"] is True
    assert status["home"]["price_captured_at"] == "2026-11-10T12:00:00+00:00"


def test_refresh_round_counts_only_is_not_a_price_update(tmp_path):
    """抓到首页但只有套数: counts 更新不冒充价格更新; 旧价保留并带原日期（R3）。"""
    old = [_deal_row("S1", snapshot_date="2026-10-01")]

    def fetcher(sid, *, timeout):
        return CommunityFetchResult(snapshots=[_counts_snapshot(sid)], errors=[])

    result = _run([_plan("home", ["S1"])], tmp_path, fetcher=fetcher, old_rows=old)

    assert result["outcome"] == "no_data"
    assert result["published"] is True  # counts 快照照常落盘
    assert result["retained"] == 1
    assert result["outcomes"]["home"]["price_updated"] is False
    assert result["outcomes"]["home"]["counts_updated"] is True
    assert result["outcomes"]["home"]["retained_price_date"] == "2026-10-01"
    assert result["outcomes"]["home"]["retained_reason"] == "no_price_data"
    rows = [json.loads(line) for line in
            (tmp_path / "price_snapshots.jsonl").read_text(encoding="utf-8").splitlines()]
    kinds = sorted(row["price_type"] for row in rows)
    assert kinds == ["counts_only", "monthly_deal_avg_latest"]


def test_refresh_round_expired_deal_only_is_no_data_not_update(tmp_path):
    """仅抓到过期签约价不计有效价格更新; 过期价保留为历史参考（R1/R3）。"""
    def fetcher(sid, *, timeout):
        return CommunityFetchResult(
            snapshots=[_snapshot(sid, latest_month="2026-04")], errors=[])

    result = _run([_plan("home", ["S1"])], tmp_path, fetcher=fetcher)

    assert result["outcome"] == "no_data"
    assert result["outcomes"]["home"]["sources"]["S1"]["reason"] == "expired_only"
    assert result["outcomes"]["home"]["price_updated"] is False
    rows = [json.loads(line) for line in
            (tmp_path / "price_snapshots.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[0]["raw_payload"]["tendency"]["latest_month"] == "2026-04"


def test_refresh_round_partial_page_failure_marks_partial(tmp_path):
    """部分页失败但有有效价格: updated + partial, errors 原样保留不吞（R3）。"""
    def fetcher(sid, *, timeout):
        return CommunityFetchResult(
            snapshots=[_snapshot(sid)], errors=["index: RuntimeError: blocked"])

    result = _run([_plan("home", ["S1"])], tmp_path, fetcher=fetcher)

    # 轮级: 有页面失败 → 部分成功; 小区级: updated + partial, errors 不吞
    assert result["outcome"] == "partial"
    assert result["updated"] == 1
    assert result["outcomes"]["home"]["outcome"] == "updated"
    assert result["outcomes"]["home"]["partial"] is True
    assert result["outcomes"]["home"]["sources"]["S1"]["errors"] == ["index: RuntimeError: blocked"]


def test_refresh_round_fetch_failure_keeps_old_snapshot(tmp_path):
    """全部页面抓取失败: failed + 旧主快照原样保留 + 旧价保留原因（R3/R4）。"""
    _seed_community(tmp_path, "home", ["S1"])
    snapshot_path = tmp_path / "price_snapshots.jsonl"
    snapshot_path.write_text(json.dumps(_deal_row("S1")) + "\n", encoding="utf-8")
    backup_path = tmp_path / "price_snapshots.bak.jsonl"
    backup_path.write_text(json.dumps(_deal_row("S1")) + "\n", encoding="utf-8")

    def fetcher(sid, *, timeout):
        return CommunityFetchResult(snapshots=[], errors=["tendency: RuntimeError: blocked"])

    result = asyncio.run(refresh.run_refresh_once(
        [_plan("home", ["S1"])], snapshot_path, backup_path, tmp_path,
        fetcher=fetcher, sleep_seconds=0, today=TODAY))

    assert result["outcome"] == "failed"
    assert result["published"] is False
    assert result["failed"] == 1
    assert result["retained"] == 1
    assert result["outcomes"]["home"]["retained_reason"] == "fetch_failed"
    assert result["outcomes"]["home"]["counts_updated"] is False
    assert snapshot_path.read_text(encoding="utf-8") == json.dumps(_deal_row("S1")) + "\n"
    status = refresh.load_refresh_status(tmp_path)
    assert status["home"]["outcome"] == "failed"


def test_refresh_round_parse_failure_distinguished(tmp_path):
    """页面抓到但完全解析不出（无快照无错误）= 解析失败, 与网络失败区分（R3）。"""
    def fetcher(sid, *, timeout):
        return CommunityFetchResult(snapshots=[], errors=[])

    result = _run([_plan("home", ["S1"])], tmp_path, fetcher=fetcher)

    assert result["outcome"] == "failed"
    assert result["outcomes"]["home"]["sources"]["S1"]["reason"] == "parse_failed"


def test_refresh_round_mixed_sources_summarized_per_community(tmp_path):
    """双来源小区: 一来源更新一来源失败 → 小区 updated + partial。"""
    calls = []

    def fetcher(sid, *, timeout):
        calls.append(sid)
        if sid == "S2":
            return CommunityFetchResult(snapshots=[], errors=["tendency: RuntimeError: x"])
        return CommunityFetchResult(snapshots=[_snapshot(sid)], errors=[])

    result = _run([_plan("home", ["S1", "S2"])], tmp_path, fetcher=fetcher)

    assert calls == ["S1", "S2"]
    assert result["outcome"] == "partial"
    assert result["updated"] == 1
    assert result["failed"] == 0  # failed 按主小区计: updated 吸收失败来源
    assert result["outcomes"]["home"]["partial"] is True


def test_refresh_progress_counts_communities_not_sources(tmp_path):
    """进度按主小区计: 双来源小区 processed 不按请求数超 total（R5: 计数与目标一致）。"""
    calls = []

    def fetcher(sid, *, timeout):
        calls.append(sid)
        return CommunityFetchResult(snapshots=[_snapshot(sid)], errors=[])

    result = _run([_plan("home", ["S1", "S2"]), _plan("home2", ["S3"])], tmp_path, fetcher=fetcher)

    assert calls == ["S1", "S2", "S3"]
    # total = 小区数 2（start_refresh 设置）; processed 同单位, 不因三次请求超总数
    assert refresh.job["processed"] == 2
    assert result["updated"] == 2


# ---------------------------------------------------------------------------
# 撤销收录 / 换绑跳过（R5）
# ---------------------------------------------------------------------------

def test_refresh_round_skips_source_revoked_before_request(tmp_path):
    """请求前重查: 资格已丢失的来源跳过, 进度计已处理, 不发请求。"""
    _seed_community(tmp_path, "home", ["S1"])
    store = _seed_community(tmp_path, "other", [])
    with store.db() as db:
        db.execute("UPDATE community_admission SET payload=? WHERE cid='home'",
                   (_admission("excluded"),))
    calls = []

    def fetcher(sid, *, timeout):
        calls.append(sid)
        return CommunityFetchResult(snapshots=[_snapshot(sid)], errors=[])

    result = _run([_plan("home", ["S1"])], tmp_path, fetcher=fetcher, seed=False)

    assert calls == []  # 未发请求
    assert result["outcome"] == "skipped"
    assert result["skipped"] == 1
    assert refresh.job["processed"] == 1  # 跳过也计已处理（total 由 start_refresh 设置）
    assert result["published"] is False
    assert refresh.load_refresh_status(tmp_path)["home"]["outcome"] == "skipped"


def test_refresh_round_drops_result_when_revoked_mid_round(tmp_path):
    """返回后重查: 任务期间撤销收录 → 本轮结果不落盘（R5）。"""
    _seed_community(tmp_path, "home", ["S1"])
    store = _seed_community(tmp_path, "other", [])

    def fetcher(sid, *, timeout):
        with store.db() as db:
            db.execute("UPDATE community_admission SET payload=? WHERE cid='home'",
                       (_admission("excluded"),))
        return CommunityFetchResult(snapshots=[_snapshot(sid)], errors=[])

    result = _run([_plan("home", ["S1"])], tmp_path, fetcher=fetcher, seed=False)

    assert result["outcome"] == "skipped"
    assert result["published"] is False
    rows = [json.loads(line) for line in
            (tmp_path / "price_snapshots.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows == []  # 抓到的结果被丢弃
    assert refresh.job["processed"] == 1


def test_refresh_round_skips_rebound_source(tmp_path):
    """任务期间来源换绑到其他小区 → 本小区跳过且结果不落盘。"""
    _seed_community(tmp_path, "home", ["S1"])
    store = _seed_community(tmp_path, "other", [])

    def fetcher(sid, *, timeout):
        with store.db() as db:
            db.execute("UPDATE sources SET cid='other' WHERE sid='S1'")
        return CommunityFetchResult(snapshots=[_snapshot(sid)], errors=[])

    result = _run([_plan("home", ["S1"])], tmp_path, fetcher=fetcher, seed=False)

    assert result["outcome"] == "skipped"
    assert result["published"] is False


# ---------------------------------------------------------------------------
# 取消与发布安全（R4）
# ---------------------------------------------------------------------------

def test_refresh_round_cancel_does_not_publish_or_persist(tmp_path):
    """任务取消: 不发布快照、不写状态, 仅向上传播取消（design: 仅记录取消尝试）。"""
    _seed_community(tmp_path, "home", ["S1"])
    _seed_community(tmp_path, "home2", ["S2"])
    snapshot_path = tmp_path / "price_snapshots.jsonl"
    snapshot_path.write_text(json.dumps(_deal_row("S9")) + "\n", encoding="utf-8")
    backup_path = tmp_path / "price_snapshots.bak.jsonl"
    backup_path.write_text(json.dumps(_deal_row("S9")) + "\n", encoding="utf-8")

    def fetcher(sid, *, timeout):
        if sid == "S2":
            refresh._cancel_requested = True
        return CommunityFetchResult(snapshots=[_snapshot(sid)], errors=[])

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(refresh.run_refresh_once(
            [_plan("home", ["S1"]), _plan("home2", ["S2"])],
            snapshot_path, backup_path, tmp_path,
            fetcher=fetcher, sleep_seconds=0, today=TODAY))
    # 第一小区已抓到的结果也不落盘; 主快照原样保留; 状态未写
    assert snapshot_path.read_text(encoding="utf-8") == json.dumps(_deal_row("S9")) + "\n"
    assert refresh.load_refresh_status(tmp_path) == {}


def test_atomic_write_failure_keeps_old_snapshot_and_cleans_tmp(tmp_path, monkeypatch):
    """临时文件写/替换失败: 旧主快照完好, 无 .tmp 残留（R4）。"""
    path = tmp_path / "price_snapshots.jsonl"
    path.write_text('{"old": true}\n', encoding="utf-8")

    def boom(src, dst):
        raise OSError("replace failed")

    monkeypatch.setattr(refresh.os, "replace", boom)
    with pytest.raises(OSError):
        refresh.write_jsonl(path, [{"new": True}])
    monkeypatch.undo()

    assert path.read_text(encoding="utf-8") == '{"old": true}\n'
    assert not (tmp_path / "price_snapshots.jsonl.tmp").exists()


def test_csv_failure_reports_warning_but_snapshot_published(tmp_path, monkeypatch):
    """CSV 失败: 只报警告并明确主快照已发布, 不得误称主快照未变（R4）。"""
    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(refresh, "rewrite_csv", boom)
    result = _run([_plan("home", ["S1"])], tmp_path,
                  fetcher=lambda sid, *, timeout: CommunityFetchResult(
                      snapshots=[_snapshot(sid)], errors=[]))

    assert result["published"] is True
    assert result["warnings"] and "主快照已发布" in result["warnings"][0]
    assert '"community_id": "S1"' in (tmp_path / "price_snapshots.jsonl").read_text(encoding="utf-8")


def test_rewrite_csv_uses_new_contract_columns(tmp_path):
    """CSV 契约列: 移除 sample_count/confidence_score, 携带 trend_point_count（R4）。"""
    assert "sample_count" not in CSV_FIELDS
    assert "confidence_score" not in CSV_FIELDS
    assert "trend_point_count" in CSV_FIELDS

    refresh.rewrite_csv(tmp_path, [_deal_row("S1")])
    header = (tmp_path / "price_snapshots.csv").read_text(encoding="utf-8-sig").splitlines()[0]
    assert header.split(",") == CSV_FIELDS


def test_refresh_status_merges_across_rounds(tmp_path):
    """状态文件跨轮合并: 新轮只更新本轮小区, 其他小区条目保留。"""
    refresh.save_refresh_status(tmp_path, {
        "a": {"community_id": "a", "outcome": "updated", "price_updated": True},
    })
    refresh.save_refresh_status(tmp_path, {
        "b": {"community_id": "b", "outcome": "failed", "retained": True},
    })
    status = refresh.load_refresh_status(tmp_path)
    assert status["a"]["outcome"] == "updated"
    assert status["b"]["outcome"] == "failed"


# ---------------------------------------------------------------------------
# 启动入口（R5）: mode / 409 / 互斥
# ---------------------------------------------------------------------------

def test_start_refresh_rejects_concurrent_runs():
    refresh.job["running"] = True
    ok, status, body = asyncio.run(refresh.start_refresh(0))
    assert ok is False
    assert status == 409


def test_start_refresh_rejects_unknown_mode():
    ok, status, _ = asyncio.run(refresh.start_refresh(0, mode="everything"))
    assert ok is False
    assert status == 422


def test_start_refresh_all_mode_409_when_no_collectible(monkeypatch):
    monkeypatch.setattr(refresh, "collectible_plans", lambda *a, **k: [])
    ok, status, body = asyncio.run(refresh.start_refresh(0))
    assert ok is False
    assert status == 409
    assert body["success"] is False


def test_start_refresh_missing_mode_409_when_no_missing(monkeypatch):
    """补齐目标为空: 409 且不产生任务（A8: N=0 不启动空任务）。"""
    plans = [_plan("a", ["A"])]
    monkeypatch.setattr(refresh, "collectible_plans", lambda *a, **k: plans)
    monkeypatch.setattr(refresh, "load_price_snapshots",
                        lambda *a, **k: {"a": {"deal": {"price": 1}, "listing": None}})
    ok, status, body = asyncio.run(refresh.start_refresh(0, mode="missing"))
    assert ok is False
    assert status == 409
    assert refresh.job["running"] is False


def test_start_refresh_missing_mode_recalculates_and_runs(monkeypatch, tmp_path):
    """启动时重算补齐目标; 运行共用同一互斥; 终态带 mode 与统计。"""
    _seed_community(tmp_path, "b", ["B"])
    plans = [_plan("a", ["A"]), _plan("b", ["B"])]
    monkeypatch.setattr(refresh, "collectible_plans", lambda *a, **k: plans)
    monkeypatch.setattr(refresh, "load_price_snapshots",
                        lambda *a, **k: {"a": {"deal": {"price": 1}, "listing": None}})

    async def scenario():
        ok, status, body = await refresh.start_refresh(0, mode="missing")
        assert ok is True
        assert status == 200
        assert body["data"]["mode"] == "missing"
        assert body["data"]["total"] == 1  # 只有 b 缺价
        assert refresh.job["running"] is True
        # 运行中再启动: 互斥 409
        ok2, status2, _ = await refresh.start_refresh(0, mode="all")
        assert ok2 is False and status2 == 409
        await refresh._task

    calls = []

    def fetcher(sid, *, timeout):
        calls.append(sid)
        return CommunityFetchResult(snapshots=[_snapshot(sid)], errors=[])

    monkeypatch.setattr(refresh, "fetch_community_snapshots", fetcher)
    import src.services.data_loader as data_loader
    monkeypatch.setattr(data_loader, "DATA_DIR", tmp_path)
    monkeypatch.setattr(refresh, "DATA_DIR", tmp_path)
    asyncio.run(scenario())

    assert calls == ["B"]
    assert refresh.job["phase"] == "done"
    assert refresh.job["mode"] == "missing"
    assert refresh.job["updated"] == 1
    assert refresh.job["result"]["outcome"] == "succeeded"
    assert refresh.load_refresh_status(tmp_path)["b"]["outcome"] == "updated"


def test_get_refresh_status_exposes_job_with_counts(monkeypatch):
    """GET /api/refresh: job 字段 + eligible/missing 数量（批次 C 依赖）。"""
    from src.api import routes

    monkeypatch.setattr(refresh, "eligibility_counts",
                        lambda *a, **k: {"eligible": 3, "missing": 1})
    body = asyncio.run(routes.get_refresh_status())
    assert body["success"] is True
    assert body["data"]["eligible"] == 3
    assert body["data"]["missing"] == 1
    for key in ("running", "phase", "mode", "total", "processed", "okCount", "errorCount",
                "updated", "noData", "failed", "skipped", "retained",
                "startedAt", "finishedAt", "error", "result"):
        assert key in body["data"]
