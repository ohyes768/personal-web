from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import directory_routes
from src.services.community_registry import CommunityRegistry


def test_review_api_counts_filter_pagination_decision_and_recovery(tmp_path, monkeypatch):
    store = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    monkeypatch.setattr(directory_routes, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(directory_routes, 'store', lambda: store)
    app = FastAPI(); app.include_router(directory_routes.router, prefix='/api')
    client = TestClient(app)
    store.ingest(dict(source='amap', source_id='1', name='新花园', district='滨江', address='滨江区测试路'))
    data = client.get('/api/directory/reviews?source=amap').json()['data']
    assert data['total'] == 1
    row = data['items'][0]
    assert client.get('/api/directory/reviews?source=laipai').json()['data']['total'] == 0
    assert client.get('/api/directory/reviews?page=2&page_size=1').json()['data']['items'] == []
    decision = dict(action='admit', revision=row['revision'], name='新花园', property_type='住宅')
    response = client.post(f"/api/directory/reviews/{row['id']}/decision", json=decision)
    assert response.status_code == 200
    assert client.post(f"/api/directory/reviews/{row['id']}/decision", json=decision).status_code == 409
    assert client.get('/api/directory/summary').json()['data']['residential'] == 1
    assert client.get('/api/directory/summary').json()['data']['pending'] == 0
    cid = response.json()['data']['community_id']
    client.post(f'/api/directory/communities/{cid}/review', json={'revision': 2, 'reason': '待核对'})
    row = client.get('/api/directory/reviews').json()['data']['items'][0]
    assert row['existing_cid'] == cid
    assert client.post(f"/api/directory/reviews/{row['id']}/decision", json={'action': 'exclude', 'revision': row['revision'], 'reason': '确认非住宅'}).status_code == 200
    row = client.get('/api/directory/reviews?state=excluded').json()['data']['items'][0]
    assert client.post(f"/api/directory/reviews/{row['id']}/restore", json={'revision': row['revision']}).status_code == 200
    assert client.get('/api/directory/reviews').json()['data']['items'][0]['auto_review_locked']
    assert client.get('/api/directory/reviews?page=0').status_code == 422
    assert client.get('/api/directory/reviews/not-there').status_code == 404
