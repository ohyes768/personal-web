"""TMSF catalog and independent collection controls, enabled by explicit migration."""
import asyncio
import threading
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.services import directory_workflow as flow
from src.services.community_review import community_matches
from src.services.directory_coverage import attach_coverage
from src.services.directory_position import PositionJob, position_detail, position_one, confirm_position, PositionOutcome
from src.services.directory_use_review import (
    UseReviewJob, UseReviewOutcome, review_one, use_review_detail,
)

router = APIRouter(prefix='/directory/workflow', tags=['directory-workflow'])
_position = None
_use_review = None
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


def use_review_job():
    global _use_review
    with _lock:
        if _use_review is None:
            _use_review = UseReviewJob(require_store())
        return _use_review


async def shutdown():
    if _position:
        await asyncio.to_thread(_position.shutdown)
    if _use_review:
        await asyncio.to_thread(_use_review.shutdown)


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
        from src.services.collection_pipeline import enabled as pipeline_enabled
        with registry.db() as db:
            pipeline = pipeline_enabled(db)
        return {'active': True, 'admitted': sum(r['admission_state'] == 'admitted' for r in rows),
                'excluded': sum(r['admission_state'] != 'admitted' for r in rows), 'auction_pending': len(tasks),
                'pipeline': pipeline, 'pending': sum(r.get('workflow_state') == 'pending' for r in rows)}
    return result(read)


# UI 分桶：done=已定位（含人工确认），review=待确认队列，todo=批量或手动可处理。
POSITION_BUCKETS = {'done': {'matched', 'manual'}, 'review': {'review'}, 'todo': {'pending', 'not_found', 'error'}}
# 复核视角：冲突/待确认/一致/无结论/从未复核。
USE_FILTERS = {
    'conflict': lambda p: p.get('result') == 'conflict',
    'uncertain': lambda p: p.get('result') == 'uncertain',
    'agree': lambda p: p.get('result') in {'agree_residential', 'agree_non_residential'},
    'pending_retry': lambda p: p.get('result') == 'pending_retry' and p.get('state') is not None and not p.get('auto_skip_reason'),
    'none': lambda p: p.get('state') is None and not p.get('auto_skip_reason'),
    'skipped': lambda p: bool(p.get('auto_skip_reason')) and p.get('result') in {None, 'pending_retry'},
}


@router.get('/catalog')
def catalog(state: Literal['admitted', 'excluded'] = 'admitted', q: str = Query('', max_length=200),
            district: str = '', position: Literal['', 'matched', 'pending', 'review', 'not_found', 'error', 'manual', 'done', 'todo'] = '',
            use: Literal['', 'conflict', 'uncertain', 'pending_retry', 'agree', 'none', 'skipped'] = '',
            workflow: Literal['', 'pending', 'admitted', 'excluded'] = '',
            market: Literal['', 'new_house', 'second_hand'] = '',
            property_type: str = Query('', max_length=100),
            auction: Literal['', 'has', 'none'] = '',
            rental: Literal['', 'data', 'pending', 'unmapped', 'source_missing', 'no_samples', 'failed'] = '',
            page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100)):
    def read():
        registry = require_store()
        rows = filtered(flow.inventory(registry, registry.path.parent), q, district)
        rows = [r for r in rows if r['admission_state'] == state]
        if workflow:
            rows = [r for r in rows if r.get('workflow_state', r['admission_state']) == workflow]
        property_types = sorted({prop for r in rows for prop in r.get('property_types', [])})
        if market:
            rows = [r for r in rows if r.get('market_state') == market]
        if property_type:
            rows = [r for r in rows if not r.get('property_types')] if property_type == '__missing__' else [r for r in rows if property_type in r.get('property_types', [])]
        if position:
            states = POSITION_BUCKETS.get(position, {position})
            rows = [r for r in rows if r.get('position', {}).get('state') in states]
        if use:
            rows = [r for r in rows if USE_FILTERS[use](r.get('use_review') or {})]
        if state == 'admitted':
            rows = attach_coverage(rows, registry, registry.path.parent)
            if auction:
                rows = [r for r in rows if bool(r['coverage']['auction']['round_count']) == (auction == 'has')]
            if rental:
                rows = [r for r in rows if r['coverage']['rental']['state'] == rental]
        return {'items': rows[(page - 1) * page_size:page * page_size], 'total': len(rows), 'page': page, 'property_types': property_types}
    return result(read)


@router.get('/catalog/{cid}')
def detail(cid: str):
    def read():
        registry = require_store()
        row = next((c for c in flow.inventory(registry, registry.path.parent) if c['community_id'] == cid), None)
        if not row:
            raise HTTPException(404, '小区不存在或已删除')
        if row['admission_state'] == 'admitted':
            row = attach_coverage([row], registry, registry.path.parent, include_records=True)[0]
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


class AdmissionDecision(BaseModel):
    revision: int = Field(ge=1)
    reason: str = Field('', max_length=300)


@router.post('/catalog/{cid}/exclude')
def exclude_catalog(cid: str, body: AdmissionDecision):
    registry = require_store()
    def action():
        row = next((c for c in flow.inventory(registry, registry.path.parent) if c['community_id'] == cid), None)
        if not row or row.get('source_record_id'):
            raise ValueError('小区不存在或已删除')
        registry.decide_admission(cid, 'exclude', revision=body.revision, reason=body.reason)
        return registry.admission(cid)
    return result(action)


@router.post('/catalog/{cid}/resume')
def resume_catalog(cid: str, body: AdmissionDecision):
    registry = require_store()
    def action():
        current = registry.admission(cid)
        if current.get('decision_kind') != 'manual' or not (current.get('state') == 'excluded' or current.get('auto_review_locked')):
            raise ValueError('只有人工排除的小区可以恢复自动分类')
        registry.decide_admission(cid, 'restore-admission', revision=body.revision)
        registry.decide_admission(cid, 'allow-auto-review', revision=body.revision + 1)
        return registry.admission(cid)
    return result(action)


@router.get('/positions')
def position_status():
    return result(lambda: position_job().snapshot())


class PositionStart(BaseModel):
    mode: Literal['all', 'retry_failed'] = 'all'


@router.post('/positions', status_code=202)
def position_start(body: PositionStart | None = None):
    return result(lambda: position_job().start(mode=body.mode if body else 'all'))


@router.delete('/positions')
def position_cancel():
    worker = position_job()
    if not (worker.snapshot() or {}).get('running'):
        raise HTTPException(409, '当前没有高德采集任务')
    worker.cancel.set()
    return {'success': True, 'data': {'phase': 'cancelling'}}


class PositionDecision(BaseModel):
    revision: str = Field(pattern='^[a-f0-9]{64}$')
    poi_id: str | None = Field(None, min_length=1, max_length=100)
    coordinates_verified: bool = Field(False, strict=True)
    longitude: float | None = Field(None, ge=-180, le=180, allow_inf_nan=False)
    latitude: float | None = Field(None, ge=-90, le=90, allow_inf_nan=False)
    address: str | None = Field(None, max_length=300)


def position_write(action):
    def run():
        worker = position_job()
        with worker.lock:
            if (worker.snapshot() or {}).get('running'):
                raise ValueError('高德批量补全正在进行，请完成后再操作单个小区')
            return action()
    return result(run)


@router.get('/catalog/{cid}/position')
def read_position(cid: str):
    registry = require_store()
    return result(lambda: position_detail(registry, registry.path.parent, cid))


@router.post('/catalog/{cid}/position/query')
def query_position(cid: str):
    registry = require_store()
    def run():
        errors = []
        try:
            position_one(registry, registry.path.parent, cid, force=True)
        except PositionOutcome as exc:
            errors.append(str(exc))
        return {**position_detail(registry, registry.path.parent, cid), 'errors': errors}
    return position_write(run)


@router.post('/catalog/{cid}/position/confirm')
def choose_position(cid: str, body: PositionDecision):
    registry = require_store()
    return position_write(lambda: confirm_position(registry, registry.path.parent, cid, **body.model_dump()))


@router.get('/use-reviews')
def use_review_status():
    return result(lambda: use_review_job().snapshot())


@router.post('/use-reviews', status_code=202)
def use_review_start():
    return result(lambda: use_review_job().start())


@router.delete('/use-reviews')
def use_review_cancel():
    worker = use_review_job()
    if not (worker.snapshot() or {}).get('running'):
        raise HTTPException(409, '当前没有用途复核任务')
    worker.cancel.set()
    return {'success': True, 'data': {'phase': 'cancelling'}}


class UseEvidence(BaseModel):
    source: str = Field(min_length=1, max_length=30)
    url: str = Field(min_length=1, max_length=500)
    note: str = Field('', max_length=300)


class UseConfirm(BaseModel):
    revision: int = Field(ge=1)
    decision: Literal['residential', 'non_residential']
    property_type: Literal['住宅', '别墅', '排屋'] | None = None
    use_evidence: list[UseEvidence] = Field(min_length=1, max_length=10)
    reason: str = Field('', max_length=300)


def use_review_write(action):
    def run():
        worker = use_review_job()
        with worker.lock:
            if (worker.snapshot() or {}).get('running'):
                raise ValueError('高德用途复核正在进行，请完成后再操作单个小区')
            return action()
    return result(run)


@router.get('/catalog/{cid}/use-review')
def read_use_review(cid: str):
    registry = require_store()
    return result(lambda: use_review_detail(registry, registry.path.parent, cid))


@router.post('/catalog/{cid}/use-review')
def query_use_review(cid: str):
    registry = require_store()

    def run():
        errors = []
        try:
            review_one(registry, registry.path.parent, cid, force=True)
        except UseReviewOutcome as exc:
            errors.append(str(exc))
        return {**use_review_detail(registry, registry.path.parent, cid), 'errors': errors}
    return use_review_write(run)


@router.post('/catalog/{cid}/use-review/confirm')
def confirm_use_review(cid: str, body: UseConfirm):
    registry = require_store()

    def run():
        if body.decision == 'residential' and not body.property_type:
            raise HTTPException(422, '确认住宅必须选择住宅、别墅或排屋类型')
        if body.decision == 'non_residential' and not body.reason.strip():
            raise HTTPException(422, '确认非住宅必须填写理由')
        registry.confirm_use(cid, revision=body.revision, decision=body.decision,
                             property_type=body.property_type,
                             use_evidence=[item.model_dump() for item in body.use_evidence],
                             reason=body.reason)
        return registry.admission(cid)
    return use_review_write(run)


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
