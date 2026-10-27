import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.services.community_registry import CommunityRegistry
from src.services.directory_policy import KEY, VERSION


def poi(sid='B1', name='风雅钱塘', typecode='120302'):
    return dict(id=sid, name=name, adname='滨江区', address='月明路1076号',
                typecode=typecode, type='住宅小区', location='120.20749,30.20226')


class Client:
    def __init__(self, rows=None):
        self.rows = rows

    def search_name(self, name, district, types='120300|120203'):
        rows = self.rows if self.rows is not None else [poi(name=name)]
        return rows, len(rows)

    def close(self):
        pass


@pytest.fixture
def setup(tmp_path, monkeypatch):
    from src.api import directory_routes, directory_workflow_routes as routes
    store = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    c = store.create('风雅钱塘', district='滨江', address='月明路1076号')
    s = store.ingest(dict(source='tmsf', source_id='t1', name='风雅钱塘', district='滨江',
                          address='月明路1076号', property_type='商贸', listing_count=3,
                          market_state='second_hand'))
    store.associate(s['id'], c['community_id'])
    with store.db() as db:
        db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (KEY, VERSION))
    monkeypatch.setattr(directory_routes, 'store', lambda: store)
    monkeypatch.setattr(routes, '_position', None)
    monkeypatch.setattr(routes, '_use_review', None)
    monkeypatch.setattr('src.services.directory_use_review.AmapClient', lambda: Client())
    app = FastAPI(); app.include_router(routes.router, prefix='/api')
    client = TestClient(app)
    return client, store, c['community_id']


BASE = '/api/directory/workflow'
EVIDENCE = [{'source': 'kerui', 'url': 'https://www.cihud.com/x/1', 'note': '住宅'}]


def test_a_single_review_returns_the_projection(setup):
    client, store, cid = setup
    before = client.get(f'{BASE}/catalog/{cid}/use-review').json()['data']
    assert '非住宅' in before['auto_skip_reason']
    response = client.post(f'{BASE}/catalog/{cid}/use-review')
    assert response.status_code == 200, response.text
    data = response.json()['data']
    assert data['state'] == 'checked' and data['category'] == 'residential'
    assert data['result'] == 'conflict'
    assert data['evidence']['poi_id'] == 'B1'
    assert data['human'] is None and data['re_review'] is False
    assert data['errors'] == []


def test_skipped_filter_separates_automatic_skips_from_unresolved_work(setup):
    client, store, cid = setup
    result = client.get(f'{BASE}/catalog?state=excluded&use=skipped').json()['data']
    assert result['total'] == 1 and result['items'][0]['community_id'] == cid
    assert client.get(f'{BASE}/catalog?state=excluded&use=none').json()['data']['total'] == 0
    client.post(f'{BASE}/catalog/{cid}/use-review')
    # A manually discovered conflict stays in the conflict queue even if auto queries skip it.
    assert client.get(f'{BASE}/catalog?state=excluded&use=skipped').json()['data']['total'] == 0
    assert client.get(f'{BASE}/catalog?state=excluded&use=conflict').json()['data']['total'] == 1


def test_a_review_that_finds_nothing_reports_the_error(setup, monkeypatch):
    client, store, cid = setup
    monkeypatch.setattr('src.services.directory_use_review.AmapClient', lambda: Client(rows=[]))
    response = client.post(f'{BASE}/catalog/{cid}/use-review')
    assert response.status_code == 200
    data = response.json()['data']
    assert data['state'] == 'not_found' and data['errors']


def test_confirm_writes_the_decision_and_reports_it_in_the_row(setup):
    client, store, cid = setup
    response = client.post(f'{BASE}/catalog/{cid}/use-review/confirm', json={
        'revision': 1, 'decision': 'residential', 'property_type': '住宅',
        'use_evidence': EVIDENCE, 'reason': '克而瑞为住宅'})
    assert response.status_code == 200, response.text
    assert response.json()['data']['use_decision'] == 'residential'
    row = client.get(f'{BASE}/catalog?state=admitted').json()['data']
    assert row['total'] == 1
    detail = client.get(f'{BASE}/catalog/{cid}').json()['data']
    assert detail['use_review']['human']['decision'] == 'residential'
    assert detail['use_review']['re_review'] is False


def test_confirm_accepts_a_request_without_evidence(setup):
    client, store, cid = setup
    omitted = client.post(f'{BASE}/catalog/{cid}/use-review/confirm', json={
        'revision': 1, 'decision': 'residential', 'property_type': '住宅', 'reason': ''})
    assert omitted.status_code == 200, omitted.text
    assert omitted.json()['data']['use_evidence'] == []
    empty_url = client.post(f'{BASE}/catalog/{cid}/use-review/confirm', json={
        'revision': 2, 'decision': 'residential', 'property_type': '别墅',
        'use_evidence': [{'source': 'kerui', 'url': '', 'note': ''}], 'reason': ''})
    assert empty_url.status_code == 200, empty_url.text
    assert empty_url.json()['data']['use_evidence'][0]['url'] == ''


def test_confirm_still_requires_a_residential_type_and_a_non_residential_reason(setup):
    client, store, cid = setup
    assert client.post(f'{BASE}/catalog/{cid}/use-review/confirm', json={
        'revision': 1, 'decision': 'non_residential',
        'use_evidence': EVIDENCE, 'reason': ''}).status_code == 422
    assert client.post(f'{BASE}/catalog/{cid}/use-review/confirm', json={
        'revision': 1, 'decision': 'residential',
        'use_evidence': EVIDENCE, 'reason': ''}).status_code == 422
    assert client.post(f'{BASE}/catalog/{cid}/use-review/confirm', json={
        'revision': 1, 'decision': '住宅', 'property_type': '住宅',
        'use_evidence': EVIDENCE, 'reason': ''}).status_code == 422


def test_confirm_rejects_a_stale_revision_and_a_deleted_target(setup):
    client, store, cid = setup
    client.post(f'{BASE}/catalog/{cid}/use-review/confirm', json={
        'revision': 1, 'decision': 'residential', 'property_type': '住宅',
        'use_evidence': EVIDENCE, 'reason': '克而瑞为住宅'})
    assert client.post(f'{BASE}/catalog/{cid}/use-review/confirm', json={
        'revision': 1, 'decision': 'non_residential',
        'use_evidence': EVIDENCE, 'reason': '改判'}).status_code == 409
    store.delete(cid)
    assert client.post(f'{BASE}/catalog/{cid}/use-review/confirm', json={
        'revision': 2, 'decision': 'residential', 'property_type': '住宅',
        'use_evidence': EVIDENCE, 'reason': ''}).status_code == 409


def test_the_use_filter_applies_before_pagination(setup):
    client, store, cid = setup
    client.post(f'{BASE}/catalog/{cid}/use-review')
    conflict = client.get(f'{BASE}/catalog?state=excluded&use=conflict').json()['data']
    assert conflict['total'] == 1
    assert client.get(f'{BASE}/catalog?state=excluded&use=agree').json()['data']['total'] == 0
    assert client.get(f'{BASE}/catalog?state=excluded&use=none').json()['data']['total'] == 0
    assert client.get(f'{BASE}/catalog?state=excluded&use=pending_retry').json()['data']['total'] == 0
    assert client.get(f'{BASE}/catalog?state=excluded&use=bogus').status_code == 422


def test_the_batch_job_is_persistent_and_cancellable(setup, monkeypatch):
    client, store, cid = setup
    from src.api import directory_workflow_routes as routes
    assert client.get(f'{BASE}/use-reviews').json()['data'] is None
    # Test the lifecycle endpoints without a worker racing the cancellation request.
    monkeypatch.setattr(routes.use_review_job(), '_run', lambda: None)
    started = client.post(f'{BASE}/use-reviews')
    assert started.status_code == 202, started.text
    routes.use_review_job().state = dict(routes.use_review_job()._initial_state(), total=1)
    assert client.delete(f'{BASE}/use-reviews').status_code == 200


def test_a_running_batch_refuses_single_writes(setup):
    client, store, cid = setup
    from src.api import directory_workflow_routes as routes
    routes.use_review_job().state = dict(routes.use_review_job()._initial_state(), total=1)
    assert client.post(f'{BASE}/catalog/{cid}/use-review').status_code == 409
    assert client.post(f'{BASE}/catalog/{cid}/use-review/confirm', json={
        'revision': 1, 'decision': 'residential', 'property_type': '住宅',
        'use_evidence': EVIDENCE, 'reason': ''}).status_code == 409


def test_the_endpoints_are_closed_before_the_migration(setup):
    client, store, cid = setup
    with store.db() as db:
        db.execute('DELETE FROM meta WHERE key=?', (KEY,))
    assert client.post(f'{BASE}/catalog/{cid}/use-review').status_code == 409
    assert client.get(f'{BASE}/use-reviews').status_code == 409
