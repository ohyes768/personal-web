"""Community directory management, independent of map visibility."""
import asyncio
import sqlite3
import threading
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.services.community_directory import prepare_directory
from src.services.data_loader import DATA_DIR
from src.services.directory_collection import DirectoryJob
from src.services.residential_classifier import classify_sources
from src.services.community_admission import community_views
import json as _json

router = APIRouter(tags=['community-directory'])
_job = None
_lock = threading.Lock()


def store():
    try:
        return prepare_directory(DATA_DIR)
    except (sqlite3.Error, OSError, ValueError) as exc:
        raise HTTPException(503, '小区目录暂不可用，请检查数据目录') from exc


def job():
    global _job
    with _lock:
        if _job is None:
            _job = DirectoryJob(store())
    return _job


def _load_property_types():
    path = DATA_DIR / 'property_types.json'
    if not path.exists():
        return {}
    try:
        report = _json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return {}
    return {str(k): v for k, v in report.items() if isinstance(v, dict)} if isinstance(report, dict) else {}


def source_view(item, property_types):
    view = {k: v for k, v in item.items() if k != 'samples'}
    if item['source'] == 'tmsf' and not item.get('property_type_checked_at') and not item.get('property_type'):
        legacy = property_types.get(item['source_id'], {})
        view.update(property_type=legacy.get('property_type'), property_type_url=legacy.get('url'),
                    property_type_captured_at=legacy.get('captured_at'))
    view['residential_state'] = classify_sources([item], property_types)
    return view


async def shutdown_directory():
    if _job:
        await asyncio.to_thread(_job.shutdown)


def result(action):
    try:
        return {'success': True, 'data': action()}
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (sqlite3.Error, OSError) as exc:
        raise HTTPException(503, '目录保存失败，请重试') from exc


class CommunityInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    aliases: list[str] = Field(default_factory=list, max_length=30)
    district: str = Field('滨江', max_length=30)
    address: str = Field('', max_length=300)


class AssociationInput(BaseModel):
    community_id: str = Field(min_length=1, max_length=100)


class DiscoveryInput(BaseModel):
    sources: list[Literal['tmsf', 'amap']] = Field(default_factory=lambda: ['tmsf', 'amap'], min_length=1, max_length=2)


class AdmissionInput(BaseModel):
    revision: int = Field(ge=1)
    reason: str = Field('', max_length=300)
    property_type: Literal['住宅', '别墅', '排屋'] | None = None


class AutoSnapshotInput(BaseModel):
    snapshot_id: str = Field(min_length=64, max_length=64, pattern='^[a-f0-9]+$')


class AutoConfigInput(BaseModel):
    enabled: bool
    snapshot_id: str | None = Field(None, min_length=64, max_length=64, pattern='^[a-f0-9]+$')


def auto_review():
    from src.services.community_auto_review import AutoReview
    from src.services.community_registry import CommunityRegistry
    # Preview must never trigger legacy import/admission migration through store().
    path = (DATA_DIR / 'community_registry.sqlite3').resolve()
    if not path.exists():
        raise ValueError('请先打开小区管理并完成目录初始化')
    registry = CommunityRegistry.__new__(CommunityRegistry)
    registry.path = path
    return AutoReview(registry, DATA_DIR)


@router.get('/directory/auto-review')
def auto_status():
    return review_read(lambda: auto_review().status())


@router.post('/directory/auto-review/preview')
def auto_preview():
    return review_read(lambda: auto_review().preview())


@router.put('/directory/auto-review/config')
def auto_config(request: AutoConfigInput):
    return result(lambda: auto_review().configure(request.enabled, request.snapshot_id))


@router.post('/directory/auto-review/execute')
def auto_execute(request: AutoSnapshotInput):
    return result(lambda: auto_review().execute(request.snapshot_id))


@router.post('/directory/reviews/{candidate_id}/allow-auto-review')
def allow_candidate_auto(candidate_id: str, request: AdmissionInput):
    return result(lambda: workspace().allow_auto_review(candidate_id, revision=request.revision))


def page_data(rows, page, page_size):
    return {'items': rows[(page - 1) * page_size:page * page_size], 'total': len(rows), 'page': page}


@router.get('/directory/communities')
def communities(q: str = Query('', max_length=200), district: str = '', deleted: bool = False,
                residential_state: Literal['', 'residential', 'pending', 'non_residential'] = '',
                admission_state: Literal['', 'admitted', 'pending', 'excluded'] = '',
                source: Literal['', 'tmsf', 'amap', 'fang', 'laipai'] = '',
                property_type: Literal['', '住宅', '别墅', '排屋'] = '',
                page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100)):
    registry = store()
    sources = registry.sources()
    property_types = _load_property_types()
    rows = []
    from src.api.routes import MERGE_DROP_IDS
    for c in community_views(registry, DATA_DIR, deleted=deleted, drop_ids=MERGE_DROP_IDS):
        if admission_state and c['admission_state'] != admission_state:
            continue
        records = [r for r in sources if r['community_id'] == c['community_id']]
        if (source and not any(r['source'] == source for r in records)) or (property_type and c['effective_property_type'] != property_type):
            continue
        text = ' '.join([c['community_name'], c.get('address') or '', *c.get('aliases', []), *[r['name'] for r in records]])
        if (not district or c.get('district') == district) and q.casefold() in text.casefold():
            state = classify_sources(records, property_types) if not deleted else 'deleted'
            if residential_state and state != residential_state:
                continue
            rows.append({**c, 'sources': [source_view(r, property_types) for r in records], 'residential_state': state})
    rows.sort(key=lambda c: c['community_name'])
    return {'success': True, 'data': page_data(rows, page, page_size)}


@router.post('/directory/communities')
def create(request: CommunityInput):
    return result(lambda: store().create(request.name, district=request.district, address=request.address, aliases=request.aliases))


@router.get('/directory/communities/{cid}')
def detail(cid: str):
    registry = store()
    from src.api.routes import MERGE_DROP_IDS
    item = next((c for c in community_views(registry, DATA_DIR, drop_ids=MERGE_DROP_IDS) +
                 community_views(registry, DATA_DIR, deleted=True, drop_ids=MERGE_DROP_IDS) if c['community_id'] == cid), None)
    if not item:
        raise HTTPException(404, '小区不存在')
    from src.services.data_loader import load_polygons
    records = [s for s in registry.sources() if s['community_id'] == cid]
    property_types = _load_property_types()
    return {'success': True, 'data': {**item, 'sources': [source_view(s, property_types) for s in records],
                                    'residential_state': 'deleted' if item['deleted'] else classify_sources(records, property_types),
                                    'events': registry.events(cid), 'has_boundary': cid in load_polygons()}}


@router.put('/directory/communities/{cid}')
def update(cid: str, request: CommunityInput):
    return result(lambda: store().update(cid, name=request.name, aliases=request.aliases, address=request.address, district=request.district))


@router.delete('/directory/communities/{cid}')
def delete(cid: str, reason: str = Query('', max_length=300)):
    return result(lambda: store().delete(cid, reason))


@router.post('/directory/communities/{cid}/restore')
def restore(cid: str):
    return result(lambda: store().restore(cid))


@router.post('/directory/communities/{cid}/merge')
def merge(cid: str, request: AssociationInput):
    return result(lambda: store().merge(cid, request.community_id))


@router.get('/directory/sources')
def sources(q: str = Query('', max_length=200), source: Literal['', 'tmsf', 'fang', 'amap', 'laipai'] = '', district: str = '',
            status: Literal['', 'pending', 'matched', 'ignored'] = '',
            residential_state: Literal['', 'residential', 'pending', 'non_residential'] = '',
            page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100)):
    rows = [r for r in store().sources() if (not source or r['source'] == source)
            and (not district or (r.get('district') or '').removesuffix('区') == district)
            and (not status or r['status'] == status) and q.casefold() in (r['name'] + r['source_id']).casefold()]
    # Raw rental samples stay in storage, not in a name table's API payload.
    property_types = _load_property_types()
    rows = [source_view(r, property_types) for r in rows]
    if residential_state:
        rows = [r for r in rows if r['residential_state'] == residential_state]
    return {'success': True, 'data': page_data(rows, page, page_size)}


@router.get('/directory/sources/{rid}')
def source_detail(rid: str):
    registry = store()
    item = next((s for s in registry.sources() if s['id'] == rid), None)
    if not item:
        raise HTTPException(404, '来源不存在')
    return {'success': True, 'data': {**source_view(item, _load_property_types()),
                                    'candidates': registry.candidates(item), 'sample_count': len(item.get('samples', [])),
                                    'possible_deleted': [c['community_name'] for c in registry.communities(True)
                                                         if c['community_name'] == item['name'] or item['name'] in c.get('aliases', [])]}}


@router.post('/directory/sources/{rid}/associate')
def associate(rid: str, request: AssociationInput):
    return result(lambda: store().associate(rid, request.community_id))


@router.post('/directory/sources/{rid}/create-community')
def create_from_source(rid: str, request: CommunityInput):
    return result(lambda: store().create_from_source(rid, name=request.name, aliases=request.aliases,
                                                   district=request.district, address=request.address))


@router.delete('/directory/sources/{rid}/associate')
def unlink(rid: str, community_id: str | None = None):
    return result(lambda: store().unlink(rid, community_id))


@router.delete('/directory/sources/{rid}')
def ignore(rid: str, reason: str = Query('', max_length=300)):
    return result(lambda: store().ignore_source(rid, reason))


@router.post('/directory/sources/{rid}/restore')
def restore_source(rid: str):
    return result(lambda: store().restore_source(rid))


@router.post('/directory/auto-associate')
def auto_associate():
    return result(lambda: {'matched': store().auto_associate()})


@router.get('/directory/collection')
def collection_status():
    return {'success': True, 'data': job().state}


@router.post('/directory/collection', status_code=202)
def collect(request: DiscoveryInput):
    return result(lambda: job().start(list(dict.fromkeys(request.sources))))


@router.delete('/directory/collection')
def cancel():
    if not job().state or not job().state.get('running'):
        raise HTTPException(409, '当前没有名称采集任务')
    job().cancel.set()
    return {'success': True, 'data': {'phase': 'cancelling'}}


@router.post('/directory/communities/{cid}/{action}')
def admission_decision(cid: str, action: Literal['admit', 'review', 'exclude', 'restore-admission', 'allow-auto-review'], request: AdmissionInput):
    return result(lambda: store().decide_admission(cid, action, revision=request.revision,
                                                  reason=request.reason, property_type=request.property_type))


def workspace():
    from src.services.community_review import ReviewWorkspace
    return ReviewWorkspace(store(), DATA_DIR)


def review_read(action):
    try:
        return {'success': True, 'data': action()}
    except (ValueError, sqlite3.Error, OSError) as exc:
        raise HTTPException(503, '小区审核目录暂不可用，请刷新或重试同步') from exc


class ReviewInput(AdmissionInput):
    action: Literal['admit', 'merge', 'exclude']
    name: str = Field('', max_length=100)
    target_id: str | None = Field(None, max_length=100)
    member_ids: list[str] | None = Field(None, max_length=100)


class SplitInput(BaseModel):
    revision: int = Field(ge=1)
    member_ids: list[str] = Field(min_length=1, max_length=100)


@router.get('/directory/reviews')
def reviews(q: str = Query('', max_length=200), district: str = '',
            source: Literal['', 'tmsf', 'amap', 'fang', 'laipai'] = '', state: Literal['pending', 'excluded'] = 'pending',
            page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100)):
    def read():
        rows = [r for r in workspace().reviews(state=state) if
                (not district or (r.get('district') or '').removesuffix('区') == district)
                and (not source or source in r['sources'])
                and q.casefold() in ' '.join([r['name'], r.get('address') or '', *[m['name'] for m in r['members']]]).casefold()]
        return page_data(rows, page, page_size)
    return review_read(read)


@router.get('/directory/reviews/{candidate_id}')
def review_detail(candidate_id: str):
    def read():
        work = workspace()
        item = next((r for r in work.reviews() + work.reviews(state='excluded') if r['id'] == candidate_id), None)
        if not item:
            raise HTTPException(404, '候选已处理或不存在，请刷新')
        from src.services.auction_store import read_store
        aids = {aid for m in item['members'] if m['source'] == 'laipai' for aid in m.get('auction_ids', [])}
        item['rounds'] = [{k: r.get(k) for k in ('auction_id', 'asset_id', 'title', 'round', 'status', 'source_url')}
                          for r in read_store(DATA_DIR / 'auction_records.json')['records'] if str(r['auction_id']) in aids]
        return item
    return review_read(read)


@router.get('/directory/summary')
def directory_summary():
    def read():
        work = workspace()
        data = work.summary()
        with work.store.db() as db:
            row = db.execute("SELECT value FROM meta WHERE key='collection_job'").fetchone()
            data['collection'] = _json.loads(row[0]) if row else None
        from src.services.auction_association import pending_records
        _, data['auction_needs_sync'] = pending_records(DATA_DIR / 'auction_records.json')
        return data
    return review_read(read)


@router.post('/directory/reviews/{candidate_id}/decision')
def review_decision(candidate_id: str, request: ReviewInput):
    return result(lambda: workspace().decide(candidate_id, **request.model_dump()))


@router.post('/directory/reviews/{candidate_id}/split')
def review_split(candidate_id: str, request: SplitInput):
    return result(lambda: workspace().split(candidate_id, **request.model_dump()))


@router.post('/directory/reviews/{candidate_id}/restore')
def review_restore(candidate_id: str, request: AdmissionInput):
    return result(lambda: workspace().restore(candidate_id, revision=request.revision))


@router.post('/directory/reviews/sync')
def review_sync():
    from src.services.auction_store import StoreLock
    from src.services.auction_association import sync_records
    def sync():
        try:
            with StoreLock(DATA_DIR / 'auction_records.json'):
                sync_records(DATA_DIR / 'auction_records.json')
                return workspace().summary()
        except BlockingIOError as exc:
            raise HTTPException(409, '法拍更新正在进行，请稍后同步') from exc
    return review_read(sync)
