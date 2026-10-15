"""Catalog filters apply to the entire result, before paging."""
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import directory_routes
from src.services.community_registry import CommunityRegistry
from src.services.directory_policy import KEY, VERSION


def test_catalog_market_and_type_filters_before_paging(tmp_path, monkeypatch):
    store = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    with store.db() as db:
        db.execute('INSERT OR REPLACE INTO meta VALUES (?, ?)', (KEY, VERSION))
    rows = [('新房住宅', '住宅', 0, 'new_house', '在售'),
            ('二手住宅', '住宅', 3, 'second_hand', None),
            ('旧售完住宅', '住宅', 0, 'new_house', '售完'),
            ('办公楼', '写字楼', 3, 'second_hand', None),
            ('其他楼', '其他', 3, 'second_hand', None),
            ('用途待补', None, 3, 'second_hand', None)]
    for i, (name, prop, count, market, sale) in enumerate(rows):
        c = store.create(name, district='滨江', address='滨江区测试路1号')
        r = store.ingest(dict(source='tmsf', source_id=str(i), name=name, district='滨江',
            address='滨江区测试路1号', property_type=prop, listing_count=count,
            market_state=market, project_sale_status=sale))
        store.associate(r['id'], c['community_id'])
    monkeypatch.setattr(directory_routes, 'store', lambda: store)
    app = FastAPI()
    app.include_router(directory_routes.router, prefix='/api')
    client = TestClient(app)
    def get(**params):
        response = client.get('/api/directory/workflow/catalog', params=params)
        assert response.status_code == 200
        return response.json()['data']
    assert get(market='new_house')['items'][0]['community_name'] == '新房住宅'
    assert get(market='second_hand')['items'][0]['community_name'] == '二手住宅'
    assert get()['total'] == 2
    excluded = get(state='excluded', page_size=1)
    assert excluded['total'] == 4 and len(excluded['items']) == 1
    assert excluded['property_types'] == ['住宅', '其他', '写字楼']
    for prop, name in [('住宅', '旧售完住宅'), ('写字楼', '办公楼'), ('其他', '其他楼'), ('__missing__', '用途待补')]:
        packet = get(state='excluded', property_type=prop, page_size=1)
        assert packet['total'] == 1 and packet['items'][0]['community_name'] == name
    assert get(state='excluded', property_type='住宅', q='不存在')['total'] == 0
    assert get(market='new_house', district='萧山')['total'] == 0
    assert client.get('/api/directory/workflow/catalog?market=bad').status_code == 422
    # Historical type facts also appear in both the table and filter choices.
    (tmp_path / 'property_types.json').write_text(json.dumps({'5': {'property_type': '商铺'}}))
    historical = get(state='excluded', property_type='商铺')
    assert historical['total'] == 1
    assert historical['items'][0]['property_types'] == ['商铺']
