from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import directory_routes
from src.services.community_registry import CommunityRegistry


def test_management_lifecycle(tmp_path, monkeypatch):
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    monkeypatch.setattr(directory_routes, 'store', lambda: store)
    app = FastAPI()
    app.include_router(directory_routes.router, prefix='/api')
    client = TestClient(app)
    response = client.post('/api/directory/communities', json={'name': '测试花园', 'district': '滨江'})
    cid = response.json()['data']['community_id']
    item = store.ingest(dict(source='fang', source_id='123', name='测试花园', district='滨江'))
    assert client.post(f"/api/directory/sources/{item['id']}/associate", json={'community_id': cid}).status_code == 200
    assert client.get('/api/directory/communities?q=测试').json()['data']['total'] == 1
    assert client.delete(f'/api/directory/communities/{cid}').status_code == 200
    assert client.get('/api/directory/communities').json()['data']['total'] == 0
    assert client.get('/api/directory/communities?deleted=true').json()['data']['total'] == 1
    assert client.get('/api/directory/sources?status=ignored').json()['data']['total'] == 1
    assert client.post(f'/api/directory/communities/{cid}/restore').status_code == 200
    assert client.get('/api/directory/communities?page=0').status_code == 422


def test_name_collection_has_only_three_sources():
    from pydantic import ValidationError
    import pytest
    from src.services.directory_collection import ADAPTERS

    assert directory_routes.DiscoveryInput().sources == ['tmsf', 'fang', 'laipai']
    assert set(ADAPTERS) == {'tmsf', 'fang', 'laipai'}
    with pytest.raises(ValidationError):
        directory_routes.DiscoveryInput(sources=['amap'])
