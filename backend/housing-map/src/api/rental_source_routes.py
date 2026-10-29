"""Rental source discovery and human confirmation, isolated from price data."""
from __future__ import annotations

import logging
import sqlite3
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.api import rental_routes
from src.services.data_loader import load_communities
from src.services.rental_reference.refresh import MappingFileError, RefreshAlreadyRunning
from src.services.rental_reference.sources import SourceStore, discover

router = APIRouter(tags=['rental-sources'])
logger = logging.getLogger(__name__)


class SearchRequest(BaseModel):
    keyword: str = Field('', max_length=80)
    source_url: str = Field('', max_length=300)


class ConfirmRequest(BaseModel):
    source_community_id: str = Field(pattern=r'^\d{1,30}$')


def store() -> SourceStore:
    try:
        return SourceStore(rental_routes._mappings_path)
    except (MappingFileError, sqlite3.Error, OSError, ValueError) as exc:
        logger.exception('Rental source initialization failed')
        raise HTTPException(503, '租金来源配置暂不可用，请检查后台数据') from exc


def community(community_id: str) -> dict:
    item = next((c for c in load_communities() if c.get('community_id') == community_id), None)
    if item is None:
        raise HTTPException(404, '小区不存在')
    return item


@router.get('/rentals/sources')
def sources():
    source_store = store()
    mappings = source_store.all_mappings()
    pending = source_store.pending_counts()
    return {'success': True, 'data': {'communities': [
        {'community_id': c['community_id'], 'community_name': c['community_name'],
         'district': c.get('district'), 'subdistrict': c.get('subdistrict'),
         'mapping': mappings.get(c['community_id']), 'candidate_count': pending.get(c['community_id'], 0)} for c in load_communities()]}}


@router.get('/communities/{community_id}/rental-source')
def source(community_id: str):
    item = community(community_id)
    return {'success': True, 'data': {**store().get(community_id), 'community': item}}


@router.post('/communities/{community_id}/rental-source/search')
def search(community_id: str, request: SearchRequest):
    item = community(community_id)
    source_store = store()
    try:
        candidates = discover(item, keyword=request.keyword, source_url=request.source_url.strip())
    except ValueError as exc:
        # Explicit URL errors are user input errors; source HTML errors are upstream failures.
        if request.source_url:
            from src.services.rental_reference.sources import source_page
            try:
                source_page(request.source_url.strip())
            except ValueError as input_error:
                raise HTTPException(422, str(input_error)) from input_error
        logger.warning('Rental discovery failed: %s', exc)
        raise HTTPException(502, '房天下页面暂时无法识别，请稍后重试或打开来源搜索后导入小区链接') from exc
    except Exception as exc:
        logger.warning('Rental discovery unavailable: %s', exc)
        raise HTTPException(502, '房天下暂时无法访问，请稍后重试或导入小区租房页链接') from exc
    source_store.save_candidates(community_id, candidates, restore=bool(request.source_url.strip()))
    return {'success': True, 'data': {**source_store.get(community_id), 'community': item,
                                      'found_count': len(candidates)}}


@router.put('/communities/{community_id}/rental-source')
def confirm(community_id: str, request: ConfirmRequest):
    community(community_id)
    source_store = store()
    try:
        rental_routes._get_service().change_sources(
            lambda: source_store.confirm(community_id, request.source_community_id))
    except RefreshAlreadyRunning as exc:
        raise HTTPException(409, '租金正在更新，请结束后修改来源关联') from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {'success': True, 'data': source_store.get(community_id)}


@router.delete('/communities/{community_id}/rental-source')
def remove(community_id: str):
    community(community_id)
    source_store = store()
    try:
        rental_routes._get_service().change_sources(lambda: source_store.remove(community_id))
    except RefreshAlreadyRunning as exc:
        raise HTTPException(409, '租金正在更新，请结束后修改来源关联') from exc
    return {'success': True, 'data': source_store.get(community_id)}


@router.delete('/communities/{community_id}/rental-source/candidates/{source_id}')
def reject(community_id: str, source_id: str):
    community(community_id)
    source_store = store()
    source_store.reject(community_id, source_id)
    return {'success': True, 'data': source_store.get(community_id)}


class ReviewDecision(BaseModel):
    action: Literal['bind', 'skip', 'reopen']
    candidate_id: str | None = Field(None, max_length=100)


def review_registry():
    from src.services.community_registry import existing_registry
    registry = existing_registry(rental_routes._mappings_path.parent)
    if not registry:
        raise HTTPException(503, '小区目录尚未准备好')
    return registry


@router.get('/rentals/association-tasks')
def association_tasks():
    from src.services.rental_reference.association import reviews
    try:
        return {'success': True, 'data': {'items': reviews(review_registry())}}
    except (OSError, sqlite3.Error, ValueError) as exc:
        raise HTTPException(503, '租金待处理清单暂不可用') from exc


@router.post('/rentals/association-tasks/{cid}')
def association_decision(cid: str, request: ReviewDecision):
    from src.services.rental_reference.association import decide
    try:
        rental_routes._get_service().change_sources(
            lambda: decide(review_registry(), cid, request.action, request.candidate_id))
    except RefreshAlreadyRunning as exc:
        raise HTTPException(409, '租金正在更新，请结束后处理') from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(503, '处理结果保存失败，请重试') from exc
    return {'success': True, 'data': {'saved': True}}


class ProbeSelectRequest(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=100)
    revision: int | None = Field(None, ge=0)


def _probe():
    try:
        return rental_routes._get_probe_service()
    except HTTPException:
        raise
    except (OSError, sqlite3.Error) as exc:
        logger.exception('Rental probe service unavailable')
        raise HTTPException(503, '租金来源探查暂不可用，请稍后重试') from exc


@router.get('/communities/{community_id}/rental-source/probe')
def probe_status(community_id: str):
    """Read-only probe state; never starts a network request on its own."""
    community(community_id)
    try:
        return {'success': True, 'data': _probe().status(community_id)}
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(503, '探查状态读取失败，请重试') from exc


@router.post('/communities/{community_id}/rental-source/probe')
def probe_start(community_id: str):
    """Look for the community's homepage; repeated clicks reuse the running job."""
    community(community_id)
    from src.services.rental_reference.probe import ProbeAlreadyRunning, ProbeInvalid
    try:
        return {'success': True, 'data': _probe().start(community_id)}
    except ProbeAlreadyRunning as exc:
        raise HTTPException(409, str(exc)) from exc
    except ProbeInvalid as exc:
        raise HTTPException(422, str(exc)) from exc
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(503, '探查启动失败，请重试') from exc


@router.post('/communities/{community_id}/rental-source/probe/select')
def probe_select(community_id: str, request: ProbeSelectRequest):
    """Confirm a homepage; the system then finds the rental entry inside it."""
    community(community_id)
    from src.services.rental_reference.probe import ProbeAlreadyRunning, ProbeConflict, ProbeInvalid
    try:
        return {'success': True, 'data': _probe().select(community_id, request.candidate_id, request.revision)}
    except ProbeConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ProbeAlreadyRunning as exc:
        raise HTTPException(409, str(exc)) from exc
    except ProbeInvalid as exc:
        raise HTTPException(422, str(exc)) from exc
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(503, '主页选择保存失败，请重试') from exc


@router.post('/communities/{community_id}/rental-source/probe/retry')
def probe_retry(community_id: str):
    """Retry the failed stage of the probe."""
    community(community_id)
    from src.services.rental_reference.probe import ProbeAlreadyRunning, ProbeInvalid
    try:
        return {'success': True, 'data': _probe().retry(community_id)}
    except ProbeAlreadyRunning as exc:
        raise HTTPException(409, str(exc)) from exc
    except ProbeInvalid as exc:
        raise HTTPException(422, str(exc)) from exc
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(503, '探查重试失败，请稍后重试') from exc


@router.post('/communities/{community_id}/rental-source/probe/cancel')
def probe_cancel(community_id: str):
    """Stop the running probe; a chosen homepage is kept."""
    community(community_id)
    from src.services.rental_reference.probe import ProbeNotRunning
    try:
        return {'success': True, 'data': _probe().cancel(community_id)}
    except ProbeNotRunning as exc:
        raise HTTPException(409, str(exc)) from exc
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(503, '探查取消失败，请重试') from exc
