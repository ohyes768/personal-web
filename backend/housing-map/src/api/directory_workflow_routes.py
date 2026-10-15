"""TMSF catalog and independent collection controls, enabled by explicit migration."""
import asyncio
import threading
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.services import directory_workflow as flow
from src.services.community_review import community_matches
from src.services.directory_position import PositionJob

router = APIRouter(prefix='/directory/workflow', tags=['directory-workflow'])
_position = None
_lock = threading.Lock()


def store():
    from src.api.directory_routes import store as get_store
    return get_store()


def require_store():
    registry = store()
    if not flow.is_enabled(registry):
        raise HTTPException(409, '新版名单流程尚未完成迁移，请先备份并预演迁移')
    return registry


def result(action):
    from src.api.directory_routes import result as respond
    return respond(action)


def position_job():
    global _position
    with _lock:
        if _position is None:
            _position = PositionJob(require_store())
        return _position


async def shutdown():
    if _position:
        await asyncio.to_thread(_position.shutdown)


def filtered(rows, q, district):
    return [r for r in rows if community_matches(r, r.get('sources', []), q=q, district=district)]


@router.get('/summary')
def summary(q: str = Query('', max_length=200), district: str = ''):
    def read():
        registry = store()
        if not flow.is_enabled(registry):
            return {'active': False, 'admitted': 0, 'excluded': 0, 'auction_pending': 0}
        rows = filtered(flow.inventory(registry, registry.path.parent), q, district)
        tasks = flow.auction_tasks(registry, registry.path.parent)
        return {'active': True, 'admitted': sum(r['admission_state'] == 'admitted' for r in rows),
                'excluded': sum(r['admission_state'] != 'admitted' for r in rows), 'auction_pending': len(tasks)}
    return result(read)


@router.get('/catalog')
def catalog(state: Literal['admitted', 'excluded'] = 'admitted', q: str = Query('', max_length=200),
            district: str = '', page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100)):
    def read():
        registry = require_store()
        rows = filtered(flow.inventory(registry, registry.path.parent), q, district)
        rows = [r for r in rows if r['admission_state'] == state]
        return {'items': rows[(page - 1) * page_size:page * page_size], 'total': len(rows), 'page': page}
    return result(read)


@router.get('/catalog/{cid}')
def detail(cid: str):
    def read():
        registry = require_store()
        row = next((c for c in flow.inventory(registry, registry.path.parent) if c['community_id'] == cid), None)
        if not row:
            raise HTTPException(404, '小区不存在或已删除')
        return {**row, 'events': registry.events(cid) if not row.get('source_record_id') else []}
    return result(read)


@router.post('/catalog/{cid}/retry')
def retry(cid: str):
    def action():
        registry = require_store()
        from src.api.directory_routes import job
        if (job().state or {}).get('running'):
            raise ValueError('透明售房网正在采集，请完成后重试')
        row = next((c for c in flow.inventory(registry, registry.path.parent) if c['community_id'] == cid), None)
        if not row:
            raise ValueError('小区不存在或已删除')
        from src.services.community_enrichment import enrich_source
        results = [enrich_source(registry, registry.path.parent, s['id'], include_position=False)
                   for s in row['sources'] if s['source'] == 'tmsf']
        flow.synchronize(registry, registry.path.parent)
        return {'results': results, 'errors': [e for r in results for e in r.get('errors', [])]}
    return result(action)


@router.get('/positions')
def position_status():
    return result(lambda: position_job().snapshot())


@router.post('/positions', status_code=202)
def position_start():
    return result(lambda: position_job().start())


@router.delete('/positions')
def position_cancel():
    worker = position_job()
    if not (worker.snapshot() or {}).get('running'):
        raise HTTPException(409, '当前没有高德采集任务')
    worker.cancel.set()
    return {'success': True, 'data': {'phase': 'cancelling'}}


@router.get('/auctions')
def auctions(q: str = Query('', max_length=200), include_skipped: bool = False,
             page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100)):
    def read():
        registry = require_store()
        rows = flow.auction_tasks(registry, registry.path.parent, include_skipped=include_skipped)
        rows = [r for r in rows if q.casefold() in (r['name'] + ' ' + (r.get('address') or '')).casefold()]
        return {'items': rows[(page - 1) * page_size:page * page_size], 'total': len(rows), 'page': page}
    return result(read)


class AuctionDecision(BaseModel):
    revision: str = Field(pattern='^[a-f0-9]{64}$')
    action: Literal['bind', 'skip', 'reopen']
    community_id: str | None = Field(None, max_length=100)


@router.post('/auctions/{rid}')
def decide(rid: str, body: AuctionDecision):
    registry = require_store()
    return result(lambda: flow.decide_auction(registry, registry.path.parent, rid, **body.model_dump()))
