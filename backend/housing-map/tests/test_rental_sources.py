import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import rental_routes, rental_source_routes
from src.services.rental_reference.refresh import RentalRefreshService, load_verified_mappings
from src.services.rental_reference.sources import SourceStore, discover, source_page
from src.services.rental_reference.storage import RentalPublishLock


def candidate(sid='123', name='测试花园'):
    return {'source': 'fang', 'source_community_id': sid, 'source_name': name,
            'source_url': f'https://zu.fang.com/hz/house-xm{sid}/',
            'source_address': '滨江区测试路1号', 'evidence': ['请核对分期']}


def ledger(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'version': 1, 'mappings': [{**candidate(), 'community_id': 'c1', 'status': 'verified'}]}))


def test_migration_is_once_and_unlink_does_not_resurrect(tmp_path):
    path = tmp_path / 'data' / 'rental_community_mappings.json'
    ledger(path)
    store = SourceStore(path)
    assert load_verified_mappings(path) == [('123', 'c1')]
    store.remove('c1')
    SourceStore(path)
    assert load_verified_mappings(path) == []


def test_existing_volume_reads_seed_and_preserves_edits(tmp_path):
    path = tmp_path / 'data' / 'rental_community_mappings.json'
    ledger(tmp_path / 'seed-data' / path.name)
    store = SourceStore(path)
    assert store.get('c1')['mapping']['source_community_id'] == '123'
    store.save_candidates('c1', [candidate('456')]); store.confirm('c1', '456')
    assert SourceStore(path).get('c1')['mapping']['source_community_id'] == '456'


def test_candidates_need_confirmation_and_are_unique(tmp_path):
    path = tmp_path / 'mappings.json'; store = SourceStore(path)
    store.save_candidates('c1', [candidate()]); store.save_candidates('c2', [candidate()])
    assert load_verified_mappings(path) == []
    with pytest.raises(ValueError): store.confirm('c1', '999')
    store.confirm('c1', '123')
    with pytest.raises(ValueError, match='其他小区'): store.confirm('c2', '123')
    store.remove('c1'); store.confirm('c2', '123')
    assert load_verified_mappings(path) == [('123', 'c2')]


def test_rejection_survives_search_and_restart(tmp_path):
    path = tmp_path / 'mappings.json'; store = SourceStore(path)
    store.save_candidates('c1', [candidate()]); store.reject('c1', '123')
    store.save_candidates('c1', [candidate()])
    assert SourceStore(path).get('c1')['candidates'] == []
    with pytest.raises(ValueError): store.confirm('c1', '123')
    store.save_candidates('c1', [candidate()], restore=True)
    assert store.get('c1')['candidates']


@pytest.mark.parametrize('url', ['http://zu.fang.com/hz/house-xm123/',
    'https://example.com/hz/house-xm123/', 'https://zu.fang.com/bj/house-xm123/',
    'https://zu.fang.com/hz/chuzu/3_123_1.htm', 'https://zu.fang.com/hz/house-xm123/?url=evil',
    'https://user@zu.fang.com/hz/house-xm123/'])
def test_import_url_is_limited(url):
    with pytest.raises(ValueError): source_page(url)


def page(name='测试花园'):
    return f'''房天下 <span class="selestfinds" id="list_103"><a true href="/hz/house/" class="term">关键字：{name}</a></span>
    <a href='/hz/house-xm999/'>无关推荐</a>
    <dl><a href='/hz/chuzu/3_123_1.htm'>整租两房</a><a href='/hz/house-xm123/'>{name}</a>
    <p>整租|2室1厅|80㎡</p>4000元/月</dl>'''


class Client:
    def __init__(self, timeout): self.closed = False
    def fetch(self, url):
        if '/chuzu/' in url: return '房天下 出租方式 住宅 地 址 滨江区测试路1号 地图'
        return page()
    def close(self): self.closed = True


def test_discovery_uses_structured_community_and_missing_address(monkeypatch):
    monkeypatch.setattr('time.sleep', lambda _: None)
    found = discover({'community_name': '测试花园', 'district': '滨江'}, source_url='https://zu.fang.com/hz/house-xm123/', client_factory=Client)
    assert [c['source_community_id'] for c in found] == ['123']
    assert found[0]['source_address'] == '滨江区测试路1号'
    assert 'status' not in found[0]
    assert '分期' in found[0]['evidence'][-1]


def test_search_returns_candidates_when_keyword_applied(monkeypatch):
    monkeypatch.setattr('time.sleep', lambda _: None)
    found = discover({'community_name': '测试花园'}, client_factory=Client)
    assert [c['source_community_id'] for c in found] == ['123']
    assert found[0]['source_address'] == '滨江区测试路1号'


def test_search_rejects_ignored_keyword_and_closes_client(caplog):
    class Ignored(Client):
        instance = None
        def __init__(self, timeout): super().__init__(timeout); Ignored.instance = self
        def fetch(self, url):
            # Site ignored the search term: no selected-condition echo, city-wide page.
            return ('<title>杭州租房</title>'
                    + page().replace('class="term">关键字：测试花园<', '')
                    + '<p>private-body-marker</p>')
    with pytest.raises(ValueError, match='未应用关键词'):
        discover({'community_name': '测试花园'}, client_factory=Ignored)
    assert Ignored.instance.closed
    assert 'stage=keyword_validation' in caplog.text
    assert 'actual_keyword=None' in caplog.text
    assert "title='杭州租房'" in caplog.text
    assert 'error_type=ValueError' in caplog.text
    assert 'private-body-marker' not in caplog.text
    assert any(r.exc_info for r in caplog.records)


def test_search_zero_results_yields_no_citywide_recommendations(caplog):
    class NoMatch(Client):
        def fetch(self, url):
            return page() + '很抱歉，没有找到相符的房源，您可能对以下房源感兴趣。'
    with caplog.at_level('INFO'):
        assert discover({'community_name': '测试花园'}, client_factory=NoMatch) == []
    assert 'Rental discovery no-match' in caplog.text


def test_discovery_request_failure_logs_stage_and_closes(caplog):
    class Broken(Client):
        instance = None
        def __init__(self, timeout):
            super().__init__(timeout)
            Broken.instance = self
        def fetch(self, url):
            raise TimeoutError('upstream timeout')
    with pytest.raises(TimeoutError):
        discover({'community_id': 'c1', 'community_name': '测试花园'}, client_factory=Broken)
    assert Broken.instance.closed
    assert 'community_id=c1' in caplog.text
    assert 'stage=fetch' in caplog.text
    assert 'error_type=TimeoutError' in caplog.text


def test_source_edits_block_active_worker_and_cli(tmp_path, monkeypatch):
    service = RentalRefreshService(tmp_path / 'rentals', tmp_path / 'mapping.json')
    from src.services.rental_reference.refresh import RefreshAlreadyRunning
    monkeypatch.setattr(service, '_has_active_thread', lambda: True)
    with pytest.raises(RefreshAlreadyRunning): service.change_sources(lambda: None)
    monkeypatch.setattr(service, '_has_active_thread', lambda: False)
    with RentalPublishLock(tmp_path / 'rentals' / 'rental_publish'):
        with pytest.raises(RefreshAlreadyRunning): service.change_sources(lambda: None)


def test_snapshot_not_used_after_unlink_or_rebind():
    current = {'communities': {'c1': {'source_community_id': '123', 'samples': [1]}}}
    assert rental_routes._mapped_entry(current, 'c1', {}) is None
    assert rental_routes._mapped_entry(current, 'c1', {'c1': '456'}) is None
    assert rental_routes._mapped_entry(current, 'c1', {'c1': '123'})['samples'] == [1]


@pytest.fixture
def api(tmp_path, monkeypatch):
    path = tmp_path / 'data' / 'rental_community_mappings.json'
    monkeypatch.setattr(rental_routes, '_mappings_path', path)
    monkeypatch.setattr(rental_routes, '_rentals_dir', tmp_path / 'rentals')
    monkeypatch.setattr(rental_routes, '_service', None)
    monkeypatch.setattr(rental_source_routes, 'load_communities', lambda: [{'community_id': 'c1', 'community_name': '测试花园'}])
    app = FastAPI(); app.include_router(rental_source_routes.router, prefix='/api')
    with TestClient(app) as client: yield client


def test_api_fang_discovery_and_confirmation_are_retired(api):
    path = '/api/communities/c1/rental-source'
    assert api.get(path).json()['data']['mapping'] is None
    assert api.put(path, json={'source_community_id': '123'}).status_code == 410
    assert api.post(path + '/search', json={}).status_code == 410
    assert api.delete(path).json()['data']['mapping'] is None
    assert api.get('/api/communities/unknown/rental-source').status_code == 404


def test_api_cannot_import_fang_links(api):
    path = '/api/communities/c1/rental-source/search'
    response = api.post(path, json={'source_url': 'https://zu.fang.com/hz/house-xm123/'})
    assert response.status_code == 410
    assert '幸福里' in response.json()['detail']


def test_empty_community_page_still_provides_review_candidate():
    class Empty(Client):
        def fetch(self, url):
            return '房天下 暂无房源 <a href="/hz/house-xm123/">测试花园租房</a>'
    found = discover({'community_name': '测试花园'}, source_url='https://zu.fang.com/hz/house-xm123/', client_factory=Empty)
    assert found[0]['source_name'] == '测试花园'
    assert found[0]['source_address'] is None
