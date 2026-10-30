"""Human re-review stays pending until explicitly resolved; no forced admission."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.services.community_registry import CommunityRegistry
from src.services.directory_workflow import inventory, admitted
from tests.test_collection_pipeline import store, source, master, positioned, RULE


def create(store, **changes):
    c = positioned(master(), '120201' if changes.get('property_type') == '写字楼' else '120302')
    store.create(c['community_name'], community_id='c', district=c['district'],
                 address=c['address'], collection_pipeline_version=RULE, amap_position=c['amap_position'])
    values = source()
    values.update(changes)
    r = store.ingest(values)
    store.associate(r['id'], 'c')
    return r


def client(store, monkeypatch):
    from src.api import directory_workflow_routes as routes
    monkeypatch.setattr(routes, 'store', lambda: store)
    app = FastAPI()
    app.include_router(routes.router, prefix='/api')
    return TestClient(app)


@pytest.mark.parametrize('initial', ['admitted', 'manual_excluded', 'non_residential', 'listing_low'])
def test_reopen_persists_pending_then_completes_without_bypassing_gates(store, tmp_path, monkeypatch, initial):
    r = create(store, **({'property_type': '写字楼'} if initial == 'non_residential' else
                         {'listing_count': 1} if initial == 'listing_low' else {}))
    if initial == 'manual_excluded':
        store.decide_admission('c', 'exclude', revision=1, reason='人工确认不收录')
    api = client(store, monkeypatch)
    before_sources = store.sources()
    revision = store.admission('c')['revision']
    response = api.post('/api/directory/workflow/catalog/c/reopen-review', json={'revision': revision})
    assert response.status_code == 200, response.text
    decision = response.json()['data']
    assert decision['review_requested'] and decision['auto_review_locked']
    assert not admitted(store, tmp_path)
    row = inventory(CommunityRegistry(store.path), tmp_path)[0]
    assert row['workflow_state'] == 'pending' and row['qualification'] == 'manual_review'
    summary = api.get('/api/directory/workflow/summary').json()['data']
    assert summary['pending'] == 1 and summary['admitted'] == 0
    assert api.get('/api/directory/workflow/catalog?state=excluded&workflow=pending').json()['data']['total'] == 1
    assert api.get('/api/directory/workflow/catalog?state=excluded&workflow=excluded').json()['data']['total'] == 0
    assert api.post('/api/directory/workflow/catalog/c/reopen-review', json={'revision': revision}).status_code == 409
    assert store.sources() == before_sources
    response = api.post('/api/directory/workflow/catalog/c/complete-review', json={'revision': decision['revision']})
    assert response.status_code == 200, response.text
    row = inventory(store, tmp_path)[0]
    assert row['workflow_state'] == ('admitted' if initial in {'admitted', 'manual_excluded'} else 'excluded')
    if initial == 'non_residential':
        assert row['qualification'] == 'non_residential'
    elif initial == 'listing_low':
        assert row['qualification'] == 'listing_low'
    assert store.sources() == before_sources
    assert store.sources()[0]['id'] == r['id']


def test_reopened_review_can_be_resolved_by_use_confirmation_or_exclusion(store, tmp_path):
    create(store)
    store.decide_admission('c', 'reopen-review', revision=1)
    store.confirm_use('c', revision=2, decision='residential', property_type='住宅')
    assert inventory(store, tmp_path)[0]['workflow_state'] == 'admitted'
    store.decide_admission('c', 'reopen-review', revision=3)
    store.decide_admission('c', 'exclude', revision=4, reason='人工确认不收录')
    assert inventory(store, tmp_path)[0]['workflow_state'] == 'excluded'
    with pytest.raises(ValueError, match='人工排除'):
        store.confirm_use('c', revision=5, decision='residential', property_type='住宅')


def test_complete_review_requires_explicit_reopening_and_active_identity(store, monkeypatch):
    create(store)
    api = client(store, monkeypatch)
    assert api.post('/api/directory/workflow/catalog/c/complete-review', json={'revision': 1}).status_code == 409
    assert api.post('/api/directory/workflow/catalog/source-unknown/reopen-review', json={'revision': 1}).status_code == 409
    store.delete('c')
    assert api.post('/api/directory/workflow/catalog/c/reopen-review', json={'revision': 1}).status_code == 409
