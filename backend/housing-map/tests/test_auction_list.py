import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import auction_routes
from src.services import auction_history as history


def test_list_keeps_unmatched_and_uses_current_mapping_before_paging(tmp_path, monkeypatch):
    path = tmp_path / 'records.json'
    mapping = tmp_path / 'mapping.json'
    monkeypatch.setattr(auction_routes, 'AUCTION_PATH', path)
    monkeypatch.setattr(history, 'MAPPING_PATH', mapping)
    monkeypatch.setattr(history, 'load_communities', lambda: [
        {'community_id': 'c', 'community_name': '花园', 'community_alias': ''}])
    rows = [dict(source='laipai', auction_id=str(i), asset_id='a', title='住宅',
                 address='滨江', community_name='不同名', community_id='stale',
                 status='todo', end_at=date) for i, date in enumerate([
                     'bad', '2026-10-01', '2026-09-01'])]
    path.write_text(json.dumps({'version': 1, 'records': rows}))
    app = FastAPI()
    app.include_router(auction_routes.router, prefix='/api')
    with TestClient(app) as api:
        data = api.get('/api/auctions?page_size=1').json()['data']
        assert data['overall_total'] == 3
        assert data['records'][0]['auction_id'] == '1'
        assert data['records'][0]['community_id'] is None
        assert api.get('/api/auctions?association=unmatched').json()['data']['total'] == 3
        mapping.write_text(json.dumps({'version': 1, 'mappings': [
            {'source': 'laipai', 'asset_id': 'a', 'community_id': 'c'}]}))
        data = api.get('/api/auctions?q=花园&status=todo&association=matched&page=2&page_size=1').json()['data']
        assert data['total'] == 3 and data['overall_total'] == 3
        assert data['records'][0]['auction_id'] == '2'
        assert data['records'][0]['community_display_name'] == '花园'
        assert api.get('/api/auctions?community_id=c').json()['data']['total'] == 3
        assert api.get('/api/auctions?association=bad').status_code == 422
        assert api.get('/api/auctions?q=' + 'a' * 201).status_code == 422
        mapping.write_text('bad')
        assert api.get('/api/auctions').status_code == 503
