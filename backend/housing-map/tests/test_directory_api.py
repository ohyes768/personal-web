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


def test_name_collection_uses_only_tmsf_and_rejects_amap():
    from pydantic import ValidationError
    import pytest
    from src.services.directory_collection import ADAPTERS

    assert directory_routes.DiscoveryInput().sources == ['tmsf']
    assert set(ADAPTERS) == {'tmsf', 'fang', 'laipai'}
    with pytest.raises(ValidationError):
        directory_routes.DiscoveryInput(sources=['fang'])
    with pytest.raises(ValidationError):
        directory_routes.DiscoveryInput(sources=['amap'])


def test_collection_http_rejects_removed_source_without_starting_job(monkeypatch):
    calls = []
    class Job:
        def start(self, sources):
            calls.append(sources)
            return {'running': True}
    monkeypatch.setattr(directory_routes, 'job', lambda: Job())
    app = FastAPI(); app.include_router(directory_routes.router, prefix='/api')
    client = TestClient(app)
    assert client.post('/api/directory/collection', json={'sources': ['amap']}).status_code == 422
    assert client.post('/api/directory/collection', json={'sources': ['tmsf', 'amap']}).status_code == 422
    assert calls == []
    assert client.post('/api/directory/collection', json={}).status_code == 202
    assert calls == [['tmsf']]


def test_community_filter_by_residential_state(tmp_path, monkeypatch):
    import json as _json
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api import directory_routes
    from src.services.community_registry import CommunityRegistry

    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)
    property_types = {"t1": {"property_type": "住宅"}, "t2": {"property_type": "写字楼"}, "t3": {"property_type": "其他"}}
    (data / "property_types.json").write_text(_json.dumps(property_types, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(directory_routes, "DATA_DIR", data)
    monkeypatch.setattr(directory_routes, "store", lambda: CommunityRegistry(data / "registry.sqlite3"))

    store = CommunityRegistry(data / "registry.sqlite3")
    for cid, name in [("1", "住宅A"), ("2", "写字楼B"), ("3", "待核实C")]:
        store.create(name, district="滨江", community_id=cid)
        source = store.ingest(dict(source='tmsf', source_id='t' + cid, name=name, district='滨江'))
        store.associate(source['id'], cid)

    app = FastAPI()
    app.include_router(directory_routes.router, prefix="/api")
    client = TestClient(app)

    all_resp = client.get("/api/directory/communities")
    assert all_resp.status_code == 200
    assert all_resp.json()["data"]["total"] == 3

    res_resp = client.get("/api/directory/communities?residential_state=residential")
    assert res_resp.status_code == 200
    items = res_resp.json()["data"]["items"]
    assert {c["community_id"] for c in items} == {"1"}
    assert items[0]["residential_state"] == "residential"

    bad_resp = client.get("/api/directory/communities?residential_state=unknown")
    assert bad_resp.status_code == 422


def test_collected_types_filter_sources_and_follow_current_association(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(directory_routes, 'DATA_DIR', tmp_path)
    # A stale summary must not determine the state of a local community.
    (tmp_path / 'residential_classification.json').write_text(json.dumps({'entries': [
        {'community_id': 'local-a', 'state': 'non_residential'}]}))
    registry = CommunityRegistry(tmp_path / 'registry.sqlite3')
    monkeypatch.setattr(directory_routes, 'store', lambda: registry)
    registry.create('花园A', district='滨江', community_id='local-a')
    registry.create('花园B', district='滨江', community_id='local-b')
    item = registry.ingest(dict(source='tmsf', source_id='11', name='花园A', district='滨江',
                                property_type='住宅', property_type_checked_at='2026-10-13'))
    registry.associate(item['id'], 'local-a')
    app = FastAPI()
    app.include_router(directory_routes.router, prefix='/api')
    client = TestClient(app)
    def residential_ids():
        return {c['community_id'] for c in client.get('/api/directory/communities?residential_state=residential').json()['data']['items']}
    assert residential_ids() == {'local-a'}
    assert client.get('/api/directory/sources?residential_state=residential').json()['data']['total'] == 1
    registry.associate(item['id'], 'local-b')
    assert residential_ids() == {'local-b'}
    registry.ingest(dict(source='tmsf', source_id='11', name='花园A', property_type_error='获取失败'))
    assert residential_ids() == {'local-b'}  # Failed attempts preserve the last effective fact.
    assert client.get('/api/directory/sources?residential_state=residential').json()['data']['items'][0]['property_type'] == '住宅'
    registry.ingest(dict(source='tmsf', source_id='11', name='花园A', property_type='住宅', property_type_error=None))
    fang = registry.ingest(dict(source='fang', source_id='f1', name='花园B', samples=[
        {'source_listing_id': 'l1', 'property_type': '写字楼'}]))
    registry.associate(fang['id'], 'local-b')
    assert not residential_ids()  # Source conflict remains pending.
    registry.unlink(fang['id'])
    assert residential_ids() == {'local-b'}
    registry.unlink(item['id'])
    assert not residential_ids()


def test_amap_source_classification_and_binding(tmp_path, monkeypatch):
    from src.services.amap_directory import normalize_poi
    registry = CommunityRegistry(tmp_path / 'registry.sqlite3')
    monkeypatch.setattr(directory_routes, 'store', lambda: registry)
    monkeypatch.setattr(directory_routes, '_load_property_types', lambda: {})
    app = FastAPI(); app.include_router(directory_routes.router, prefix='/api')
    client = TestClient(app)
    row = registry.ingest(normalize_poi(dict(id='B1', name='花园西区', typecode='120302',
        type='商务住宅;住宅区;住宅小区', adname='滨江区', address='测试路1号', location='120.207490,30.202261')))
    assert client.get('/api/directory/sources?source=amap&residential_state=pending').json()['data']['total'] == 1
    detail = client.get('/api/directory/sources/' + row['id']).json()['data']
    assert detail['residential_hint'] and detail['residential_state'] == 'pending'
    response = client.post('/api/directory/sources/' + row['id'] + '/create-community',
                           json={'name': '花园西区', 'district': '滨江', 'address': '测试路1号'})
    cid = response.json()['data']['community_id']
    assert response.json()['data']['longitude'] == 120.207490
    registry.ingest(dict(source='tmsf', source_id='t1', name='花园西区', district='滨江',
                         address='测试路1号', property_type='住宅'))
    assert client.get('/api/directory/communities?residential_state=residential').json()['data']['total'] == 1
    assert client.delete('/api/directory/communities/' + cid).status_code == 200
    assert client.get('/api/directory/sources?source=amap&status=ignored').json()['data']['total'] == 1
