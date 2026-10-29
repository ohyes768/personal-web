"""租金参考查询（summary / detail）与网页刷新任务路由。

契约与 apps/housing-map/src/lib/rental-types.ts 一致（前端已按此实现，勿单方面改动）：
- envelope success/data；数值缺失一律 null，不出现 NaN/Infinity。
- availability 判定优先级：unmapped（无 verified 台账映射）> source_failed
  （无发布数据且最近刷新失败）> stale（快照超 30 天，yield 停用、明细保留）>
  no_samples（口径零样本）> insufficient_samples（样本 < 3）> available。
- phase 对外映射：crawling/publishing→running；cancelling→cancelling；
  done 且全部 adopted→succeeded；done 但 carried_over/absent 非空→partial_failed；
  failed/cancelled/interrupted 原样透出；无任务（job_id 为空）→ data:null。
- 样本链接只允许已知来源的 HTTPS 精确域，其他域过滤为 null。
- 售价参考只消费 load_price_snapshots 的输出（单价/口径/日期），过期签约价
  的排除规则由该加载器负责，这里不重复实现。
"""
from __future__ import annotations

import asyncio
import datetime as dt
import math
import sqlite3
import threading
from typing import Literal
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from src.api.routes import COMMUNITY_MERGE_GROUPS
from src.services.data_loader import DATA_DIR, load_communities, load_price_snapshots
from src.services.rental_reference.refresh import (
    MappingFileError,
    NoVerifiedMappings,
    RefreshAlreadyRunning,
    RefreshNotRunning,
    RentalRefreshService,
    load_verified_mappings,
)
from src.services.rental_reference.statistics import (
    AREA_BANDS,
    MIN_GROUP_SAMPLES,
    area_band_for,
    bedrooms_of,
    estimate_yield,
    group_stats,
    is_stale,
    select_valid,
)
from src.services.rental_reference.storage import load_current
from src.services.rental_reference.providers import active_sources, same_source, source_url

router = APIRouter(tags=["rentals"])

# 数据位置与 service 单例均为模块级，测试通过 monkeypatch 覆盖
_rentals_dir = DATA_DIR / "rentals"
_mappings_path = DATA_DIR / "rental_community_mappings.json"
_service: RentalRefreshService | None = None
_matching_service = None
_task_lock = threading.RLock()
_probe_service = None
_service_lock = threading.Lock()

ALLOWED_SOURCE_HOST = "zu.fang.com"
_PRICE_BASIS = {"monthly_deal_avg_latest": "signed", "listing_avg": "listing"}
AreaBandParam = Literal["all", "lt90", "90to144", "gte144"]
BedroomsParam = Literal["all", "1", "2", "3", "4plus"]


def _get_service() -> RentalRefreshService:
    global _service
    if _service is None:
        # 双检锁：并发首次 POST/GET 只能创建一个服务实例，保住"同一时间
        # 只有一个租金采集任务"的单槽语义（否则两个实例各自开线程绕过 409）。
        with _service_lock:
            if _service is None:
                _service = RentalRefreshService(
                    rentals_dir=_rentals_dir, mappings_path=_mappings_path,
                    xingfuli_only=True, task_lock=_task_lock, busy=_probe_busy)
    return _service


async def shutdown_rental_refresh() -> None:
    """服务关闭钩子：取消活动任务并等待 worker 退出；服务从未创建则无操作。"""
    if _matching_service is not None:
        await asyncio.to_thread(_matching_service.shutdown)
    if _probe_service is not None:
        await asyncio.to_thread(_probe_service.shutdown)
    service = _service
    if service is None:
        return
    await asyncio.to_thread(service.shutdown)


def _get_probe_service():
    """Lazily built probe service; the directory owns the only source registry."""
    global _probe_service
    if _probe_service is None:
        from src.services.community_registry import existing_registry
        from src.services.rental_reference.probe import ProbeService
        registry = existing_registry(_mappings_path.parent)
        if not registry:
            raise HTTPException(503, "小区目录尚未准备好")
        with _service_lock:
            if _probe_service is None:
                _probe_service = ProbeService(
                    registry, directory=_rentals_dir,
                    task_lock=_task_lock, xingfuli_only=True,
                    busy=lambda: bool(_get_service().status().get("running")) or _matching_busy())
    return _probe_service


def _probe_busy() -> bool:
    return bool(_probe_service and _probe_service.busy()) or _matching_busy()


def _matching_busy():
    return bool(_matching_service and _matching_service.busy())


def _get_matching_service():
    global _matching_service
    if _matching_service is None:
        from src.services.community_registry import existing_registry
        from src.services.rental_reference.matching import SourceMatchingService
        registry = existing_registry(_mappings_path.parent)
        if not registry:
            raise HTTPException(503, '小区目录尚未准备好')
        with _service_lock:
            if _matching_service is None:
                _matching_service = SourceMatchingService(
                    registry, directory=_rentals_dir, task_lock=_task_lock,
                    busy=lambda: bool(_get_service().status().get('running')) or bool(_probe_service and _probe_service.busy()))
    return _matching_service


async def resume_source_matching():
    from src.services.community_registry import existing_registry
    if (_rentals_dir / 'source_matching_job.json').exists() and existing_registry(_mappings_path.parent):
        await asyncio.to_thread(_get_matching_service().resume)


# ---------------------------------------------------------------------------
# 组装工具（纯转换，无 IO）
# ---------------------------------------------------------------------------

def _num(value: object) -> float | None:
    """有限数值原样输出，缺失/NaN/Infinity 一律 None（契约禁止序列化 NaN）。"""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        finite = float(value)
        return finite if math.isfinite(finite) else None
    return None


def _safe_source_url(url: object) -> str | None:
    """Public rental links only; credentials and other cities are rejected."""
    if not isinstance(url, str):
        return None
    try:
        parts = urlparse(url)
    except ValueError:
        return None
    if parts.scheme != "https" or parts.username or parts.password:
        return None
    if parts.hostname == 'm.xflapp.com':
        from src.services.xingfuli_rentals import validate_url
        try:
            validate_url(url)
        except ValueError:
            return None
        return url if parts.path.startswith('/zufang/') else None
    if parts.hostname != ALLOWED_SOURCE_HOST:
        return None
    return url


def _verified_source_ids() -> dict[str, str]:
    """internal community_id -> Fang source_community_id（仅 verified）。

    台账损坏是服务端数据错误（503），与"未映射"（200 + availability）严格区分。
    """
    try:
        from src.services.rental_reference.sources import SourceStore
        SourceStore(_mappings_path)
        pairs = load_verified_mappings(_mappings_path)
    except (MappingFileError, sqlite3.Error, OSError, ValueError) as exc:
        raise HTTPException(503, "rental mapping file unavailable") from exc
    return {community_id: source_id for source_id, community_id in pairs}


def _sale_reference(price_snapshots: dict, community_id: str) -> tuple[dict | None, float | None]:
    """售价参考（单价/口径/日期）与裸单价；无有效售价返回 (None, None)。

    口径映射：monthly_deal_avg_latest→signed（近期签约），listing_avg→listing（挂牌）。
    """
    snapshot = price_snapshots.get(community_id)
    if not isinstance(snapshot, dict):
        return None, None
    basis = _PRICE_BASIS.get(snapshot.get("price_type"))
    price = _num(snapshot.get("price"))
    if basis is None or price is None or price <= 0:
        return None, None
    reference = {
        "unit_price_yuan_m2": price,
        "price_kind": basis,
        "price_date": snapshot.get("date") or None,
    }
    return reference, price


def _price_with_merge_fallback(price_snapshots: dict) -> dict:
    """合并组主条目缺价格时借用 fallback 成员（与 /communities 同规则）。"""
    merged = dict(price_snapshots)
    for group in COMMUNITY_MERGE_GROUPS:
        if group["primaryId"] not in merged and group["fallbackId"] in merged:
            merged[group["primaryId"]] = merged[group["fallbackId"]]
    return merged


def _external_phase(job: dict) -> str:
    phase = job.get("phase")
    if phase in ("crawling", "publishing"):
        return "running"
    if phase == "cancelling":
        return "cancelling"
    if phase == "done":
        result = job.get("result") or {}
        if (result.get("carried_over") or result.get("absent") or job.get('deferred_count')
                or job.get('new_sources_deferred')
                or any((job.get("association") or {}).get(k) for k in ("pending", "missing", "failed", "deferred"))):
            return "partial_failed"
        return "succeeded"
    return phase if isinstance(phase, str) else "failed"


def _error_message(item: object) -> str:
    if not isinstance(item, dict):
        return ""
    return str(item.get("error") or item.get("message") or "")


def _external_job(job: dict) -> dict:
    """服务内部 job snapshot → 对外 RentalRefreshJob 形状。"""
    result = job.get("result")
    errors = job.get("errors") or {}
    success_count = job.get("success_count") or 0
    failed_count = job.get("failed_count") or 0
    return {
        "stage": job.get("stage"),
        "association": job.get("association"),
        "job_id": job.get("job_id"),
        "running": bool(job.get("running")),
        "phase": _external_phase(job),
        "total_communities": job.get("total_communities") or 0,
        "processed_communities": job.get("processed_communities") or 0,
        "current_community_id": job.get("current_community_id"),
        "pages_fetched": job.get("pages_fetched") or 0,
        "details_fetched": job.get("details_fetched") or 0,
        "request_count": job.get("request_count") or 0,
        "detail_cache_hits": job.get("detail_cache_hits") or 0,
        "reused_communities": job.get("reused_communities") or 0,
        "deferred_count": job.get("deferred_count") or 0,
        "cooldown_until": job.get("cooldown_until"),
        "new_sources_deferred": job.get("new_sources_deferred") or 0,
        "success_count": success_count,
        "failed_count": failed_count,
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "last_success_at": job.get("last_success_at"),
        "errors": {
            "items": [{"community_id": item.get("community_id") if isinstance(item, dict) else None,
                       "message": _error_message(item)}
                      for item in errors.get("items") or []],
            "total": errors.get("total") or 0,
        },
        "result": ({"published": bool(result.get("published")),
                    "success_count": success_count,
                    "failed_count": failed_count}
                   if isinstance(result, dict) else None),
    }


def _current_job_snapshot() -> dict | None:
    # 懒创建会加载持久化 job 文件并把未结束任务标为 interrupted，
    # 服务重启后网页 GET/summary/detail 即可恢复状态（design "网页重新打开可GET恢复"）。
    return _get_service().status()


def _last_refresh_of(job: dict | None) -> dict | None:
    """最近一次刷新任务的对外状态；从未跑过（job_id 为空/idle）为 None。"""
    if not isinstance(job, dict) or not job.get("job_id") or job.get("phase") == "idle":
        return None
    phase = job.get("phase")
    finished_at = job.get("finished_at")
    if phase in ("crawling", "publishing", "cancelling"):
        return {"status": "running", "finished_at": None, "error": None}
    if phase == "done":
        return {"status": "ok", "finished_at": finished_at, "error": None}
    if phase == "cancelled":
        return {"status": "cancelled", "finished_at": finished_at, "error": None}
    # failed / interrupted（及未知终态）按失败处理，error 取最后一条错误消息
    messages = [message for item in reversed((job.get("errors") or {}).get("items") or [])
                if (message := _error_message(item))]
    if not messages:
        messages = ["interrupted by service restart" if phase == "interrupted"
                    else "rental refresh failed"]
    return {"status": "failed", "finished_at": finished_at, "error": messages[0]}


def _availability(*, mapped: bool, entry: dict | None, stale: bool,
                  valid_count: int, last_refresh: dict | None) -> str:
    if not mapped:
        return "unmapped"
    if entry is None:
        failed = bool(last_refresh and last_refresh.get("status") == "failed")
        return "source_failed" if failed else "no_samples"
    if stale:
        return "stale"
    if valid_count == 0:
        return "no_samples"
    if valid_count < MIN_GROUP_SAMPLES:
        return "insufficient_samples"
    return "available"


def _sample_out(row: dict, *, exclude_reason: str | None = None) -> dict:
    rent = _num(row.get("monthly_rent_yuan"))
    area = _num(row.get("area_m2"))
    unit = rent / area if rent is not None and area is not None and rent > 0 and area > 0 else None
    out = {
        "source_listing_id": row.get("source_listing_id"),
        "title": row.get("title") or None,
        "bedrooms": bedrooms_of(row.get("layout") if isinstance(row.get("layout"), str) else None),
        "area_m2": area,
        "month_rent_yuan": rent,
        "unit_rent_yuan_m2_month": unit,
        "source_url": _safe_source_url(row.get("source_url")),
        "captured_at": row.get("captured_at"),
    }
    if exclude_reason is not None:
        out["exclude_reason"] = exclude_reason
    return out


def _bedrooms_lens(bedrooms: str) -> int | str | None:
    """查询参数 -> group_stats 口径；None 表示全部房型合并。"""
    if bedrooms == "all":
        return None
    if bedrooms == "4plus":
        return "4plus"
    return int(bedrooms)


def _group_out(stats: dict, *, stale: bool, sale_reference: dict | None,
               sale_price: float | None) -> dict:
    """group_stats 输出 -> 对外 RentalGroup（组样本 < 3 时 rent_reference 为 null）。"""
    rent_reference = None
    reference = stats.get("rent_reference")
    if reference:
        rent_reference = {
            "median_month_rent_yuan": _num(reference["median_monthly_rent_yuan"]),
            "median_unit_rent_yuan_m2_month": _num(reference["median_unit_rent_yuan_m2_month"]),
            "p25_unit_rent_yuan_m2_month": _num(reference["p25_unit_rent_yuan_m2_month"]),
            "p75_unit_rent_yuan_m2_month": _num(reference["p75_unit_rent_yuan_m2_month"]),
            "sample_count": stats["sample_count"],
        }
    yield_estimate = None
    if rent_reference and rent_reference["median_unit_rent_yuan_m2_month"] is not None:
        found = estimate_yield(
            rent_reference["median_unit_rent_yuan_m2_month"], sale_price,
            sale_price_basis=sale_reference["price_kind"] if sale_reference else None,
            sale_price_date=sale_reference["price_date"] if sale_reference else None,
            stale=stale,
        )
        if found:
            yield_estimate = {
                "annualized_gross_yield_pct": _num(found["annualized_gross_yield_pct"]),
                "rent_to_sale_ratio": _num(found["rent_to_sale_ratio"]),
            }
    bedrooms_value = stats["bedrooms"]
    group = {
        # 契约 bedrooms 为 number|null；'4plus' 合并口径以 4 标注并附 bedrooms_filter
        "bedrooms": 4 if bedrooms_value == "4plus" else bedrooms_value,
        "area_band": stats["area_band"],
        "sample_count": stats["sample_count"],
        "rent_reference": rent_reference,
        "sale_reference": sale_reference,
        "yield_estimate": yield_estimate,
    }
    if bedrooms_value == "4plus":
        group["bedrooms_filter"] = "4plus"
    return group


def _entry_of(current: dict | None, community_id: str) -> dict | None:
    if not isinstance(current, dict):
        return None
    entry = current.get("communities", {}).get(community_id)
    return entry if isinstance(entry, dict) else None


def _mapped_entry(current: dict | None, community_id: str, source_ids: dict) -> dict | None:
    entry = _entry_of(current, community_id)
    if community_id not in source_ids:
        return None
    from src.services.community_registry import existing_registry
    registry = existing_registry(_mappings_path.parent)
    mapping = active_sources(registry).get(community_id) if registry else None
    provider = mapping['source'] if mapping else 'fang'
    if entry and not same_source(entry, provider, source_ids[community_id]):
        entry = None
    if not entry:
        if registry:
            entry = next((e for e in (current or {}).get('communities', {}).values()
                          if same_source(e, provider, source_ids[community_id])), None)
            r = next((r for r in registry.sources() if provider == 'fang' and r['source'] == 'fang'
                      and r['source_id'] == source_ids[community_id] and r['status'] == 'matched'), None)
            if not entry and r and r.get('samples'):
                # Explicitly a regional sample, not a claim of a complete community crawl.
                entry = {'source_community_id': r['source_id'], 'samples': r['samples'],
                         'captured_at': min(s.get('captured_at') or r['updated_at'] for s in r['samples']),
                         'quality': {'regional_sample': True}}
    return entry


def _source_links(community_id, source_id):
    if not source_id:
        return []
    from src.services.community_registry import existing_registry
    registry = existing_registry(_mappings_path.parent)
    record = active_sources(registry).get(community_id) if registry else None
    link = source_url(record) if record else f'https://{ALLOWED_SOURCE_HOST}/hz/house-xm{source_id}/'
    safe = _safe_source_url(link)
    return [safe] if safe else []


def _excluded_rows(valid_audit: dict) -> list[dict]:
    """排除明细 = 过滤排除（带理由）+ 疑似重复（可追踪、默认不计样本数）。"""
    rows = list(valid_audit["excluded"])
    rows.extend({"source_listing_id": item["sample"].get("source_listing_id"),
                 "exclusion_reason": "suspected_duplicate", "sample": item["sample"]}
                for item in valid_audit["suspect_duplicates"])
    return rows


# ---------------------------------------------------------------------------
# 查询路由
# ---------------------------------------------------------------------------

@router.get("/rentals/summary")
def rentals_summary(area_band: AreaBandParam = "all",
                    bedrooms: BedroomsParam = "all"):
    """看板租金摘要：每个内部小区一条，统一口径（area_band x bedrooms）。"""
    source_ids = _verified_source_ids()
    current = load_current(_rentals_dir)
    communities = load_communities()
    prices = _price_with_merge_fallback(load_price_snapshots())
    last_refresh = _last_refresh_of(_current_job_snapshot())
    now = dt.datetime.now(dt.UTC)
    lens_band = None if area_band == "all" else area_band
    lens_bedrooms = _bedrooms_lens(bedrooms)

    entries = []
    for community in communities:
        community_id = community.get("community_id")
        if not isinstance(community_id, str) or not community_id:
            continue
        entry = _mapped_entry(current, community_id, source_ids)
        stale = is_stale(entry.get("captured_at"), now=now) if entry else False
        valid_count = 0
        unit_rent = None
        if entry:
            valid, _audit = select_valid(entry.get("samples") or [])
            stats = group_stats(valid, bedrooms=lens_bedrooms, band=lens_band)
            valid_count = stats["sample_count"]
            reference = stats["rent_reference"]
            if reference:
                unit_rent = _num(reference["median_unit_rent_yuan_m2_month"])
        availability = _availability(mapped=community_id in source_ids, entry=entry,
                                     stale=stale, valid_count=valid_count,
                                     last_refresh=last_refresh)
        sale_reference, sale_price = _sale_reference(prices, community_id)
        estimate = None
        if entry and unit_rent is not None:
            estimate = estimate_yield(
                unit_rent, sale_price,
                sale_price_basis=sale_reference["price_kind"] if sale_reference else None,
                sale_price_date=sale_reference["price_date"] if sale_reference else None,
                stale=stale,
            )
        entries.append({
            "community_id": community_id,
            "availability": availability,
            "last_refresh": last_refresh,
            "sample_count": valid_count,
            "captured_at": entry.get("captured_at") if entry else None,
            "unit_rent_yuan_m2_month": unit_rent,
            "annualized_gross_yield_pct":
                _num(estimate["annualized_gross_yield_pct"]) if estimate else None,
        })

    return {"success": True, "data": {"area_band": area_band, "bedrooms": bedrooms,
                                      "summaries": entries}}


@router.get("/communities/{community_id}/rentals")
def community_rentals(
    community_id: str,
    area_band: AreaBandParam = "all",
    bedrooms: BedroomsParam = "all",
    view: Literal["valid", "excluded"] = "valid",
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
):
    """小区租金与收益详情：分组汇总 + 明细分页 + 排除理由。

    未知小区 ID 与"已核验映射缺失"严格区分：前者 404，后者 200 + unmapped。
    """
    known_ids = {c.get("community_id") for c in load_communities()}
    if community_id not in known_ids:
        raise HTTPException(404, "community not found")
    source_ids = _verified_source_ids()
    current = load_current(_rentals_dir)
    prices = _price_with_merge_fallback(load_price_snapshots())
    last_refresh = _last_refresh_of(_current_job_snapshot())
    now = dt.datetime.now(dt.UTC)

    entry = _mapped_entry(current, community_id, source_ids)
    stale = is_stale(entry.get("captured_at"), now=now) if entry else False
    valid: list[dict] = []
    excluded: list[dict] = []
    if entry:
        valid, audit = select_valid(entry.get("samples") or [])
        excluded = _excluded_rows(audit)

    lens_band = None if area_band == "all" else area_band
    lens_bedrooms = _bedrooms_lens(bedrooms)

    sale_reference, sale_price = _sale_reference(prices, community_id)
    # 口径（band x bedrooms）统一走一次 group_stats：sample_count / availability /
    # valid 明细与分组输出同源，保证详情与看板数字一致
    scoped = group_stats(valid, bedrooms=lens_bedrooms, band=lens_band)
    sample_count = scoped["sample_count"]

    bands = AREA_BANDS if lens_band is None else [lens_band]
    groups: list[dict] = []
    for band in bands:
        merged = group_stats(valid, bedrooms=None, band=band)
        band_rows = merged["candidates"]
        bedroom_values = sorted({count for row in band_rows
                                 if (count := bedrooms_of(row.get("layout"))) is not None})
        if lens_bedrooms is None:
            band_groups = [group_stats(valid, bedrooms=count, band=band)
                           for count in bedroom_values]
            if band_rows:
                band_groups.append(merged)
        else:
            band_groups = [group_stats(valid, bedrooms=lens_bedrooms, band=band)]
        groups.extend(_group_out(stats, stale=stale, sale_reference=sale_reference,
                                 sale_price=sale_price)
                      for stats in band_groups)

    if view == "excluded":
        rows = [_sample_out(item["sample"], exclude_reason=item["exclusion_reason"])
                for item in excluded]
        total = len(excluded)
    else:
        rows = [_sample_out(row) for row in scoped["candidates"]]
        total = sample_count

    distribution: dict[str, int] = {}
    for row in valid:
        count = bedrooms_of(row.get("layout") if isinstance(row.get("layout"), str) else None)
        key = "null" if count is None else str(count)
        distribution[key] = distribution.get(key, 0) + 1

    source_id = (entry or {}).get("source_community_id") or source_ids.get(community_id)
    availability = _availability(mapped=community_id in source_ids, entry=entry,
                                 stale=stale, valid_count=sample_count,
                                 last_refresh=last_refresh)
    start = (page - 1) * page_size
    return {"success": True, "data": {
        "availability": availability,
        "last_refresh": last_refresh,
        "sample_count": sample_count,
        "excluded_count": len(excluded),
        "captured_at": entry.get("captured_at") if entry else None,
        "regional_sample": bool(entry and entry.get('quality', {}).get('regional_sample')),
        "groups": groups,
        "bedrooms_distribution": distribution,
        "samples": rows[start:start + page_size],
        "page": page,
        "page_size": page_size,
        "total": total,
        "source_links": _source_links(community_id, source_id),
    }}


# ---------------------------------------------------------------------------
# 刷新任务路由
# ---------------------------------------------------------------------------

@router.get("/rentals/refresh")
async def rental_refresh_status():
    job = _current_job_snapshot()
    data = _external_job(job) if isinstance(job, dict) and job.get("job_id") else None
    return {"success": True, "data": data}


@router.post("/rentals/refresh")
async def start_rental_refresh():
    """启动租金刷新（范围由已核验台账决定，无任意 URL 参数）。"""
    try:
        await asyncio.to_thread(_verified_source_ids)
        if _probe_busy():
            return JSONResponse({"success": False, "error": "租金来源探查进行中，请结束后再更新"},
                                status_code=409)
        snapshot = await asyncio.to_thread(_get_service().start)
    except RefreshAlreadyRunning:
        return JSONResponse({"success": False, "error": "rental refresh job already running"},
                            status_code=409)
    except NoVerifiedMappings:
        return JSONResponse({"success": False, "error": "还没有幸福里租金来源，请先运行“匹配租金来源”"},
                            status_code=422)
    except MappingFileError:
        return JSONResponse({"success": False, "error": "rental mapping file unavailable"},
                            status_code=503)
    return JSONResponse({"success": True, "data": _external_job(snapshot)}, status_code=202)


@router.delete("/rentals/refresh")
async def cancel_rental_refresh():
    try:
        snapshot = await asyncio.to_thread(_get_service().cancel)
    except RefreshNotRunning:
        return JSONResponse({"success": False, "error": "no active rental refresh job"},
                            status_code=409)
    return {"success": True, "data": _external_job(snapshot)}
