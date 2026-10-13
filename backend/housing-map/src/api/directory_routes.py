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
    sources: list[Literal['tmsf', 'fang', 'laipai']] = Field(default_factory=lambda: ['tmsf', 'fang', 'laipai'], min_length=1, max_length=3)
    max_pages: int = Field(10, ge=1, le=100)


def page_data(rows, page, page_size):
    return {'items': rows[(page - 1) * page_size:page * page_size], 'total': len(rows), 'page': page}


@router.get('/directory/communities')
def communities(q: str = Query('', max_length=200), district: str = '', deleted: bool = False,
                page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100)):
    registry = store()
    sources = registry.sources()
    rows = []
    for c in registry.communities(deleted):
        records = [r for r in sources if r['community_id'] == c['community_id']]
        text = ' '.join([c['community_name'], c.get('address') or '', *c.get('aliases', []), *[r['name'] for r in records]])
        if (not district or c.get('district') == district) and q.casefold() in text.casefold():
            rows.append({**c, 'sources': [{k: v for k, v in r.items() if k != 'samples'} for r in records]})
    rows.sort(key=lambda c: c['community_name'])
    return {'success': True, 'data': page_data(rows, page, page_size)}


@router.post('/directory/communities')
def create(request: CommunityInput):
    return result(lambda: store().create(request.name, district=request.district, address=request.address, aliases=request.aliases))


@router.get('/directory/communities/{cid}')
def detail(cid: str):
    registry = store()
    item = next((c for c in registry.communities() + registry.communities(True) if c['community_id'] == cid), None)
    if not item:
        raise HTTPException(404, '小区不存在')
    from src.services.data_loader import load_polygons
    return {'success': True, 'data': {**item, 'sources': [{k: v for k, v in s.items() if k != 'samples'} for s in registry.sources() if s['community_id'] == cid],
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
            page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100)):
    rows = [r for r in store().sources() if (not source or r['source'] == source)
            and (not district or (r.get('district') or '').removesuffix('区') == district)
            and (not status or r['status'] == status) and q.casefold() in (r['name'] + r['source_id']).casefold()]
    # Raw rental samples stay in storage, not in a name table's API payload.
    rows = [{k: v for k, v in r.items() if k != 'samples'} for r in rows]
    return {'success': True, 'data': page_data(rows, page, page_size)}


@router.get('/directory/sources/{rid}')
def source_detail(rid: str):
    registry = store()
    item = next((s for s in registry.sources() if s['id'] == rid), None)
    if not item:
        raise HTTPException(404, '来源不存在')
    return {'success': True, 'data': {**{k: v for k, v in item.items() if k != 'samples'},
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
    return result(lambda: job().start(list(dict.fromkeys(request.sources)), request.max_pages))


@router.delete('/directory/collection')
def cancel():
    if not job().state or not job().state.get('running'):
        raise HTTPException(409, '当前没有名称采集任务')
    job().cancel.set()
    return {'success': True, 'data': {'phase': 'cancelling'}}
