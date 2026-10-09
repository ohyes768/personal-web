"""独立法拍查询及手动刷新路由。"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from src.services import auction_refresh
from src.services.auction_store import AUCTION_PATH, read_store

router = APIRouter(tags=["auctions"])


@router.get("/auctions")
def list_auctions(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                  status: str | None = None, community_id: str | None = None):
    try:
        store = read_store(AUCTION_PATH)
    except (ValueError, OSError) as exc:
        raise HTTPException(503, "auction store unavailable") from exc
    rows = [r for r in store["records"] if (status is None or r["status"] == status)
            and (community_id is None or r.get("community_id") == community_id)]
    rows.sort(key=lambda r: (r.get("end_at") or "", r["auction_id"]), reverse=True)
    start = (page - 1) * page_size
    return {"success": True, "data": {"records": rows[start:start + page_size], "total": len(rows),
            "page": page, "page_size": page_size, "last_run": store.get("last_run"),
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
