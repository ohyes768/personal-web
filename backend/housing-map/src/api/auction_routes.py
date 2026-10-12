"""独立法拍查询及手动刷新路由。"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Literal

from src.services import auction_refresh
from src.services import auction_history
from src.services.auction_store import AUCTION_PATH, read_store

router = APIRouter(tags=["auctions"])


@router.get('/auctions/community-summary')
def community_summary():
    try:
        return {'success': True, 'data': auction_history.get_summary()}
    except (ValueError, OSError) as exc:
        raise HTTPException(503, 'auction history unavailable') from exc


@router.get('/communities/{community_id}/auction-history')
def community_history(community_id: str, period: Literal['12m', '24m', 'all'] = '12m',
                      area_band: Literal['all', 'lt90', '90to144', 'gte144'] = 'all',
                      page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    try:
        data = auction_history.get_history(community_id, period=period, area_band=area_band,
                                           page=page, page_size=page_size)
        return {'success': True, 'data': data}
    except KeyError as exc:
        raise HTTPException(404, 'community not found') from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(503, 'auction history unavailable') from exc


@router.get("/auctions")
def list_auctions(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                  status: str | None = None, community_id: str | None = None,
                  q: str = Query('', max_length=200),
                  association: Literal['all', 'matched', 'unmatched'] = 'all'):
    try:
        store = read_store(AUCTION_PATH)
        communities = auction_history.load_communities()
        mappings = auction_history.load_mappings(auction_history.MAPPING_PATH, communities)
        rows = auction_history.associate_records(store['records'], communities, mappings, keep_unmatched=True)
    except (ValueError, OSError) as exc:
        raise HTTPException(503, "auction store unavailable") from exc
    names = {str(c['community_id']): c['community_name'] for c in communities}
    overall_total = len(rows)
    keyword = q.strip().casefold()
    for row in rows:
        row['community_display_name'] = names.get(row['community_id'])
        row['association_status'] = 'matched' if row['community_id'] else 'unmatched'
    rows = [r for r in rows if (status is None or r['status'] == status)
            and (community_id is None or r['community_id'] == community_id)
            and (association == 'all' or r['association_status'] == association)
            and (not keyword or any(keyword in str(r.get(k) or '').casefold()
                 for k in ('title', 'address', 'community_name', 'community_display_name')))]
    rows.sort(key=lambda r: ((auction_history.parse_date(r.get('end_at')).timestamp()
                             if auction_history.parse_date(r.get('end_at')) else float('-inf')),
                            r['source'], r['auction_id']), reverse=True)
    start = (page - 1) * page_size
    return {"success": True, "data": {"records": rows[start:start + page_size], "total": len(rows),
            "overall_total": overall_total, "page": page, "page_size": page_size, "last_run": store.get("last_run"),
            "available": AUCTION_PATH.exists(), "source": "laipai"}}


@router.get("/auctions/refresh")
async def refresh_status():
    return {"success": True, "data": dict(auction_refresh.job)}


@router.post("/auctions/refresh")
async def start_refresh(max_pages: int = Query(100, ge=1, le=500), limit: int = Query(0, ge=0, le=10000)):
    if not await auction_refresh.start_refresh(max_pages, limit):
        return JSONResponse({"success": False, "error": "auction collection already running"}, status_code=409)
    return JSONResponse({"success": True, "data": dict(auction_refresh.job)}, status_code=202)


@router.delete("/auctions/refresh")
async def cancel_refresh():
    if not auction_refresh.cancel_refresh():
        return JSONResponse({"success": False, "error": "no running auction collection"}, status_code=409)
    return {"success": True, "data": dict(auction_refresh.job)}
