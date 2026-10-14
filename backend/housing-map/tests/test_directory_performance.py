from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import directory_routes
from src.services.community_registry import CommunityRegistry
from src.services.community_review import ReviewWorkspace


def test_summary_refreshes_once_without_matching_suggestions(tmp_path, monkeypatch):
    store = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    store.ingest(dict(source='amap', source_id='1', name='待审核花园', district='滨江', address='滨江区测试路'))
    work = ReviewWorkspace(store, tmp_path)
    original = work.refresh; calls = []
    def refresh():
        calls.append(1); return original()
    def forbidden(*args, **kwargs):
        raise AssertionError('Counting must not build suggestions')
    monkeypatch.setattr(work, 'refresh', refresh)
    monkeypatch.setattr(store, 'candidates', forbidden)
    assert work.summary()['pending'] == 1
    assert len(calls) == 1


def test_paged_review_matches_only_returned_members_and_filtered_counts_agree(tmp_path, monkeypatch):
    store = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    for i in range(3):
        store.ingest(dict(source='amap', source_id=str(i), name=f'候选花园{i}', district='滨江', address=f'滨江区测试路{i}号'))
    cid = store.create('住宅花园', aliases=['居民别名'], district='滨江', address='滨江区住宅路')['community_id']
    store.decide_admission(cid, 'admit', revision=1, property_type='住宅')
    monkeypatch.setattr(directory_routes, 'store', lambda: store)
    monkeypatch.setattr(directory_routes, 'DATA_DIR', tmp_path)
    app = FastAPI(); app.include_router(directory_routes.router, prefix='/api')
    client = TestClient(app); calls = []
    original = store.candidates
    def candidates(record, **kwargs):
        calls.append(record['id']); return original(record, **kwargs)
    monkeypatch.setattr(store, 'candidates', candidates)
    rows = client.get('/api/directory/reviews?page_size=1').json()['data']
    assert rows['total'] == 3 and len(calls) == 1
    calls.clear()
    summary = client.get('/api/directory/summary?q=候选花园1&district=滨江&source=amap').json()['data']
    assert summary['pending'] == 3 and summary['residential'] == 1
    assert summary['filtered'] == {'residential': 0, 'pending': 1, 'excluded': 0}
    assert calls == []
    summary = client.get('/api/directory/summary?q=居民别名&property_type=住宅').json()['data']
    assert summary['filtered'] == {'residential': 1, 'pending': 0, 'excluded': 0}
