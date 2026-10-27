import asyncio
import json
import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import directory_routes, routes
from src.services import data_loader
from src.services.community_directory import prepare_directory


@pytest.mark.parametrize('use_source_district', [False, True])
def test_verified_position_address_survives_map_loading(tmp_path, monkeypatch, use_source_district):
    from src.services.community_admission import community_views
    (tmp_path / 'binjiang_communities.json').write_text(json.dumps([
        dict(community_id='100', community_name='国信嘉园', district='滨江', address='之江三号路以西')]))
    (tmp_path / 'property_types.json').write_text(json.dumps({'100': {'property_type': '住宅'}}))
    (tmp_path / 'binjiang_coordinates.json').write_text(json.dumps({'100': dict(
        longitude=120.161695, latitude=30.189725, formatted_address='杭州市滨江区国信嘉园')}))
    store = prepare_directory(tmp_path)
    with store.db() as db:
        row = db.execute("SELECT payload FROM communities WHERE id='100'").fetchone()
        payload = json.loads(row['payload'])
        payload.update(longitude=120.161695, latitude=30.189725)
        if not use_source_district:
            payload['geographic_address'] = '杭州市滨江区国信嘉园'
        db.execute("UPDATE communities SET payload=? WHERE id='100'", (json.dumps(payload),))
    if use_source_district:
        store.ingest(dict(source='tmsf', source_id='100', name='国信嘉园', district='滨江',
                          address='之江三号路以西', address_district='滨江', property_type='住宅'))
    monkeypatch.setattr(data_loader, 'DATA_DIR', tmp_path)
    assert community_views(store, tmp_path)[0]['map_status'] == 'displayed'
    coordinates = data_loader.load_coordinates()
    assert '滨江区' in coordinates['100']['formatted_address']
    body = asyncio.run(routes.get_communities())
    assert [c['community_id'] for c in body['data']] == ['100']
    assert body['stats'] == {'admitted': 1, 'displayed': 0, 'hidden': {'missing_boundary': 1}}


def test_admission_api_and_map_share_state_but_keep_collection_identity(tmp_path, monkeypatch):
    (tmp_path / 'binjiang_communities.json').write_text(json.dumps([
        dict(community_id='100', community_name='江汉路小区', district='滨江', address='杭州市滨江区江汉路')]), encoding='utf-8')
    (tmp_path / 'property_types.json').write_text(json.dumps({'100': {'property_type': '住宅'}}))
    (tmp_path / 'binjiang_coordinates.json').write_text(json.dumps({'100': dict(
        longitude=120.207490, latitude=30.202261, formatted_address='杭州市滨江区江汉路')}))
    store = prepare_directory(tmp_path)
    monkeypatch.setattr(directory_routes, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(directory_routes, 'store', lambda: store)
    monkeypatch.setattr(data_loader, 'DATA_DIR', tmp_path)
    app = FastAPI()
    app.include_router(directory_routes.router, prefix='/api')
    client = TestClient(app)
    item = client.get('/api/directory/communities/100').json()['data']
    assert item['map_status'] == 'displayed'
    assert item['admission']['revision'] == 1
    assert {c['community_id'] for c in asyncio.run(routes.get_communities())['data']} == {'100'}
    response = client.post('/api/directory/communities/100/review', json={'revision': 1, 'reason': '疑似道路'})
    assert response.status_code == 200
    assert client.post('/api/directory/communities/100/admit', json={'revision': 1, 'property_type': '住宅'}).status_code == 409
    assert client.post('/api/directory/communities/100/admit', json={'revision': 2, 'property_type': '公寓'}).status_code == 422
    assert client.get('/api/directory/communities?admission_state=pending').json()['data']['total'] == 1
    assert asyncio.run(routes.get_communities())['data'] == []
    assert data_loader.load_communities()[0]['tmsf_id'] == '100'
    from src.services.refresh import select_refresh_targets
    assert select_refresh_targets(data_loader.load_communities()) == ['100']
    assert store.sources()[0]['status'] == 'matched'
    assert client.post('/api/directory/communities/100/exclude', json={'revision': 2}).status_code == 409
    assert client.post('/api/directory/communities/100/exclude', json={'revision': 2, 'reason': '确认非住宅'}).status_code == 200
    assert client.post('/api/directory/communities/100/restore-admission', json={'revision': 3}).json()['data']['auto_review_locked']
    assert client.post('/api/directory/communities/100/allow-auto-review', json={'revision': 4}).json()['data']['state'] == 'pending'
    assert client.post('/api/directory/communities/100/admit', json={'revision': 5, 'property_type': '排屋'}).status_code == 200
    assert asyncio.run(routes.get_communities())['data'][0]['property_type'] == '排屋'


def test_missing_or_invalid_coordinates_are_explained(tmp_path):
    from src.services.community_admission import community_views
    from src.services.community_registry import CommunityRegistry
    store = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    store.create('测试花园', community_id='local-one', district='滨江', address='滨江区测试路1号')
    store.decide_admission('local-one', 'admit', revision=1, property_type='住宅')
    assert community_views(store, tmp_path)[0]['map_status'] == 'missing_coordinates'
    from src.services.refresh import select_refresh_targets
    assert select_refresh_targets(store.communities(), {'local-one': dict(longitude=120.207490, latitude=30.202261)}) == []
    invalid = dict(longitude=float('nan'), latitude=30, formatted_address='滨江区')
    assert community_views(store, tmp_path, coordinates={'local-one': invalid})[0]['map_status'] == 'check_coordinates'
