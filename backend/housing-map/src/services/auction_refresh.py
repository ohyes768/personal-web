"""脚本与手动后台任务共享的法拍采集流程。"""
import asyncio
import threading
import time
from contextlib import nullcontext

from src.services.auction_fetcher import AuctionClient, normalize_auction, now_iso
from src.services.auction_store import AUCTION_PATH, StoreLock, write_store
from src.services.data_loader import load_communities


def collect_auctions(path=AUCTION_PATH, *, client=None, communities=None, max_pages=100,
                     limit=0, dry_run=False, delay=1.2, cancelled=lambda: False, progress=lambda _: None,
                     reserved_lock=None):
    if not 1 <= max_pages <= 500 or not 0 <= limit <= 10000:
        raise ValueError("invalid collection limits")
    owned = client is None
    rows, seen, scanned = [], set(), 0
    complete = False

    def check():
        if cancelled():
            raise InterruptedError("auction collection cancelled")

    with nullcontext() if reserved_lock else StoreLock(path):
        check()
        client = client or AuctionClient()
        communities = load_communities() if communities is None else communities
        try:
            for page in range(1, max_pages + 1):
                check()
                data = client.list_page(page)
                items, count = data["list"], data["count"]
                if not items and scanned < count:
                    raise RuntimeError("auction page unexpectedly empty")
                ids = []
                for item in items:
                    if not isinstance(item, dict) or not str(item.get("auction_id", "")).isdigit():
                        raise RuntimeError("invalid auction list item")
                    ids.append(str(item["auction_id"]))
                if items and all(aid in seen for aid in ids):
                    raise RuntimeError("repeated auction page")
                for item, aid in zip(items, ids):
                    check()
                    if aid in seen:
                        continue
                    seen.add(aid)
                    if str(item.get("area_code")) != "330108":
                        continue
                    if delay:
                        time.sleep(delay)
                    check()
                    detail = client.detail(aid)
                    if str(detail.get("auction_id")) != aid:
                        raise RuntimeError("auction detail identity mismatch")
                    row = normalize_auction(detail, communities)
                    if row:
                        rows.append(row)
                    progress({"page": page, "processed": len(seen), "matched": len(rows)})
                    if limit and len(rows) >= limit:
                        break
                scanned += len(items)
                progress({"page": page, "processed": len(seen), "matched": len(rows)})
                if limit and len(rows) >= limit:
                    break
                if scanned >= count:
                    complete = True
                    break
                if delay:
                    time.sleep(delay)
            check()
            result = {"complete": complete, "pages": page, "processed": len(seen),
                      "matched": len(rows), "saved": 0 if dry_run else len(rows), "errors": 0,
                      "finished_at": now_iso(), "dry_run": dry_run}
            if not dry_run:
                write_store(path, rows, result)
            return result
        finally:
            if owned:
                client.close()


job = {"running": False, "phase": "idle", "processed": 0, "matched": 0,
       "started_at": None, "finished_at": None, "error": None, "result": None}
_cancel = threading.Event()
_task = None


async def start_refresh(max_pages=100, limit=0):
    global _task
    if job["running"]:
        return False
    reservation = StoreLock(AUCTION_PATH)
    try:
        reservation.__enter__()
    except BlockingIOError:
        return False
    _cancel.clear()
    job.update(running=True, phase="fetching", processed=0, matched=0, started_at=now_iso(),
               finished_at=None, error=None, result=None)
    loop = asyncio.get_running_loop()

    def progress(values):
        loop.call_soon_threadsafe(job.update, values)

    async def run():
        worker = asyncio.create_task(asyncio.to_thread(collect_auctions, AUCTION_PATH,
                            max_pages=max_pages, limit=limit, cancelled=_cancel.is_set,
                            progress=progress, reserved_lock=reservation))
        try:
            job["result"] = await asyncio.shield(worker)
            job["phase"] = "done"
        except asyncio.CancelledError:
            # to_thread keeps running after task cancellation: retain the file lock until it exits.
            _cancel.set()
            try:
                await worker
            except Exception:
                pass
            job["phase"] = "cancelled"
            raise
        except InterruptedError:
            job["phase"] = "cancelled"
        except Exception as exc:
            job.update(phase="error", error=f"{type(exc).__name__}: {exc}")
        finally:
            reservation.__exit__()
            job.update(running=False, finished_at=now_iso())
    _task = asyncio.create_task(run())
    return True


def cancel_refresh():
    if not job["running"]:
        return False
    _cancel.set()
    job["phase"] = "cancelling"
    return True


async def shutdown_refresh():
    if job["running"] and _task:
        cancel_refresh()
        await _task
