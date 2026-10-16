import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.services.community_registry import CommunityRegistry, dump
from src.services.directory_policy import KEY, VERSION
from src.services.directory_workflow import inventory
from src.services.directory_position import position_one, position_detail, confirm_position, PositionJob
from src.services.directory_position_state import position_view


@pytest.fixture
def setup(tmp_path):
    store = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    c = store.create('风雅钱塘', district='滨江', address='月明路1076号')
    s = store.ingest(dict(source='tmsf', source_id='t1', name='风雅钱塘', district='滨江',
                          address='月明路1076号', property_type='住宅', listing_count=3, market_state='second_hand'))
    store.associate(s['id'], c['community_id'])
    with store.db() as db:
        db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (KEY, VERSION))
    return store, c['community_id'], tmp_path


def poi(sid='B1', address='月明路1076号', name='风雅钱塘'):
    return dict(id=sid, name=name, adname='滨江区', address=address,
                typecode='120302', type='住宅小区', location='120.20749,30.20226')


class Client:
    def __init__(self, rows=None, error=None, callback=None, by_name=None, count=None):
        self.rows = [poi()] if rows is None else rows
        self.error, self.callback = error, callback
        self.by_name, self.count = by_name or {}, count
        self.calls = 0
        self.queries = []
    def search_name(self, name, *_):
        self.calls += 1
        self.queries.append(name)
        if self.callback:
            self.callback()
        if self.error:
            raise self.error
        rows = self.by_name.get(name, self.rows)
        return rows, self.count if self.count is not None else len(rows)
    def close(self): pass


def update_master(store, cid, **values):
    with store.db() as db:
        row = db.execute('SELECT payload FROM communities WHERE id=?', (cid,)).fetchone()
        payload = json.loads(row[0]); payload.update(values)
        db.execute('UPDATE communities SET payload=? WHERE id=?', (dump(payload), cid))


def test_history_is_pending_and_query_preserves_existing_point(setup):
    store, cid, data = setup
    update_master(store, cid, longitude=120.207, latitude=30.202, coordinate_system='gcj02',
                  coordinate_evidence={'source': 'historical_amap', 'source_id': 't1'})
    before = inventory(store, data)[0]
    assert before['position']['state'] == 'pending' and before['position']['has_coordinates']
    position_one(store, data, cid, Client())
    after = inventory(store, data)[0]
    assert after['position']['state'] == 'matched'
    assert after['longitude'] == 120.207  # POI completion does not move a valid map point.
    assert after['position']['selected']['longitude'] == 120.20749
    assert after['address'] == '月明路1076号' and len(store.sources()) == 1


@pytest.mark.parametrize('rows,state', [([], 'not_found'), ([poi(), poi('B2')], 'review')])
def test_review_and_empty_results_are_persisted(setup, rows, state):
    store, cid, data = setup
    with pytest.raises(ValueError):
        position_one(store, data, cid, Client(rows))
    detail = position_detail(store, data, cid)
    assert detail['state'] == state and len(detail['candidates']) == len(rows)
    assert detail['checked_at'] and detail['revision']


def test_single_exact_candidate_with_differing_address_matches(setup):
    store, cid, data = setup
    client = Client([poi(address='江南大道100号')])  # 唯一精确候选，地址不一致不再阻断自动匹配
    assert position_one(store, data, cid, client) == 'updated'
    detail = position_detail(store, data, cid)
    assert detail['state'] == 'matched' and detail['selected']['source_id'] == 'B1'
    assert detail['selected']['address'] == '江南大道100号'
    assert store.communities()[0]['longitude'] == 120.20749


def test_manual_candidate_protected_and_stale_confirmation_rejected(setup):
    store, cid, data = setup
    with pytest.raises(ValueError): position_one(store, data, cid, Client([poi(), poi('B2')]))
    detail = position_detail(store, data, cid)
    result = confirm_position(store, data, cid, revision=detail['revision'], poi_id='B2')
    assert result['state'] == 'manual' and result['selected']['source_id'] == 'B2'
    with pytest.raises(ValueError, match='变化'):
        confirm_position(store, data, cid, revision=detail['revision'], poi_id='B1')
    client = Client(error=AssertionError('manual must not query'))
    assert position_one(store, data, cid, client, force=True) == 'skipped'
    assert client.calls == 0
    assert store.communities()[0]['coordinate_evidence']['source'] == 'manual'


def test_manual_requires_valid_region_and_reliable_server_candidate(setup):
    store, cid, data = setup
    detail = position_detail(store, data, cid)
    with pytest.raises(ValueError, match='候选'):
        confirm_position(store, data, cid, revision=detail['revision'], poi_id='forged')
    with pytest.raises(ValueError, match='坐标'):
        confirm_position(store, data, cid, revision=detail['revision'], longitude=0, latitude=0, address='地图地址')
    saved = confirm_position(store, data, cid, revision=detail['revision'], longitude=120.20749,
                             latitude=30.20226, address='月明路1076号')
    assert saved['state'] == 'manual' and not saved['selected'].get('source_id')


def test_failure_retains_match_and_per_target_error(setup):
    store, cid, data = setup
    position_one(store, data, cid, Client())
    with pytest.raises(ValueError, match='失败'):
        position_one(store, data, cid, Client(error=RuntimeError('secret URL')), force=True)
    detail = position_detail(store, data, cid)
    assert detail['state'] == 'matched' and detail['selected']['source_id'] == 'B1'
    assert 'secret' not in detail['error']
    assert store.communities()[0]['longitude'] == 120.20749


def test_error_on_first_query_and_cancel_do_not_fake_not_found(setup):
    store, cid, data = setup
    with pytest.raises(ValueError): position_one(store, data, cid, Client(error=RuntimeError()))
    detail = position_detail(store, data, cid)
    assert detail['state'] == 'error'
    with pytest.raises(InterruptedError):
        position_one(store, data, cid, Client(), cancelled=lambda: True)
    assert position_detail(store, data, cid) == detail


def test_changed_identity_invalidates_evidence_and_query_stale_publish(setup):
    store, cid, data = setup
    position_one(store, data, cid, Client())
    store.update(cid, name='风雅钱塘二期', aliases=[], address='月明路1076号', district='滨江')
    # POI matching is tied to current identity; retaining coordinates is independent.
    assert position_detail(store, data, cid)['state'] == 'pending'
    with pytest.raises(ValueError, match='变化'):
        position_one(store, data, cid, Client(callback=lambda: update_master(store, cid, note='edited')), force=True)


def test_batch_queries_history_but_skips_review_and_manual(setup):
    store, cid, data = setup
    update_master(store, cid, longitude=120.207, latitude=30.202, coordinate_system='gcj02')
    job = PositionJob(store)
    job.state = dict(running=True, phase='running', total=0, processed=0, updated=0, skipped=0,
                     review=0, not_found=0, failed=0, skipped_by_state={}, errors=[])
    client = Client()
    job._run(client=client, delay=0)
    assert client.calls == 1 and job.snapshot()['updated'] == 1
    client.calls = 0
    job._run(client=client, delay=0)
    assert client.calls == 0 and job.snapshot()['skipped_by_state'] == {'matched': 1}


def add_admitted(store, name, source_id):
    c = store.create(name, district='滨江', address='月明路1076号')
    s = store.ingest(dict(source='tmsf', source_id=source_id, name=name, district='滨江',
                          address='月明路1076号', property_type='住宅', listing_count=3, market_state='second_hand'))
    store.associate(s['id'], c['community_id'])
    return c['community_id']


def test_batch_reports_outcome_counts_and_skipped_states(setup):
    store, cid, data = setup
    add_admitted(store, '确认花园', 't2')
    add_admitted(store, '荒地苑', 't3')
    job = PositionJob(store)
    job.state = dict(running=True, phase='running', total=0, processed=0, updated=0, skipped=0,
                     review=0, not_found=0, failed=0, skipped_by_state={}, errors=[])
    client = Client(by_name={'确认花园': [poi('B1', name='确认花园'), poi('B2', name='确认花园')],
                             '荒地苑': []})
    job._run(client=client, delay=0)
    snap = job.snapshot()
    assert snap['updated'] == 1 and snap['review'] == 1 and snap['not_found'] == 1 and snap['failed'] == 0
    assert snap['phase'] == 'succeeded'  # review/not_found 是预期结果，不算失败
    assert {e['state'] for e in snap['errors']} == {'review', 'not_found'}
    client.calls = 0
    job._run(client=client, delay=0)
    snap = job.snapshot()
    assert client.calls == 0 and snap['skipped'] == 3
    assert snap['skipped_by_state'] == {'matched': 1, 'review': 1, 'not_found': 1}


def test_batch_marks_genuine_failures_and_partial_phase(setup):
    store, cid, data = setup
    job = PositionJob(store)
    job.state = dict(running=True, phase='running', total=0, processed=0, updated=0, skipped=0,
                     review=0, not_found=0, failed=0, skipped_by_state={},
                     errors=[], started_at=None, finished_at=None)
    job._run(client=Client(error=RuntimeError('boom')), delay=0)
    snap = job.snapshot()
    assert snap['failed'] == 1 and snap['phase'] == 'partial_failed' and snap['errors'][0]['state'] == 'error'


def test_flat_name_strips_dots_suffixes_and_parens():
    from src.services.directory_position import _flat_name
    assert _flat_name('中海·钱塘山水') == _flat_name('中海钱塘山水') == '中海钱塘山水'
    assert _flat_name('积家') == _flat_name('积家小区')
    assert _flat_name('中天官河锦庭（排屋）') == '中天官河锦庭'
    assert _flat_name('金成滨玺云著邸') == '金成滨玺云著'
    assert _flat_name('绿城·晓风印月') == '绿城晓风印月'


def test_dot_and_suffix_names_still_match_candidates(setup):
    store, cid, data = setup
    client = Client([poi('B1', name='风雅·钱塘')])
    assert position_one(store, data, cid, client) == 'updated'
    assert position_detail(store, data, cid)['selected']['name'] == '风雅·钱塘'


def test_api_filters_before_pagination_and_snapshot_write_rules(setup, monkeypatch):
    from src.api import directory_routes, directory_workflow_routes as routes
    store, cid, data = setup
    monkeypatch.setattr(directory_routes, 'store', lambda: store)
    monkeypatch.setattr(routes, '_position', None)
    monkeypatch.setattr('src.services.directory_position.AmapClient', lambda: Client())
    app = FastAPI(); app.include_router(routes.router, prefix='/api')
    client = TestClient(app); base = '/api/directory/workflow'
    assert client.get(base + '/catalog?position=pending&page_size=1').json()['data']['total'] == 1
    response = client.post(base + f'/catalog/{cid}/position/query')
    assert response.status_code == 200, response.text
    assert response.json()['data']['state'] == 'matched'
    assert client.get(base + '/catalog?position=pending&page_size=1').json()['data']['total'] == 0
    assert client.get(base + '/catalog?position=matched&page_size=1').json()['data']['total'] == 1
    assert client.get(base + '/catalog?position=bogus').status_code == 422
    detail = client.get(base + f'/catalog/{cid}/position').json()['data']
    update_master(store, cid, note='stale')
    assert client.post(base + f'/catalog/{cid}/position/confirm', json={'revision': detail['revision'], 'poi_id': 'B1'}).status_code == 409
    # An older successful check must not turn a new stale write into HTTP 200.
    monkeypatch.setattr('src.services.directory_position.AmapClient',
                        lambda: Client(callback=lambda: update_master(store, cid, note='changed during query')))
    assert client.post(base + f'/catalog/{cid}/position/query').status_code == 409
    routes.position_job().state = {'running': True}
    assert client.post(base + f'/catalog/{cid}/position/query').status_code == 409


def test_deleted_or_excluded_target_cannot_be_queried_or_confirmed(setup):
    store, cid, data = setup
    detail = position_detail(store, data, cid)
    store.delete(cid)
    with pytest.raises(ValueError): position_one(store, data, cid, Client())
    with pytest.raises(ValueError): confirm_position(store, data, cid, revision=detail['revision'], poi_id='B1')


def test_legacy_manual_source_point_is_protected(setup):
    store, cid, data = setup
    source = store.sources()[0]
    store.ingest({**source, 'longitude': 120.207, 'latitude': 30.202, 'coordinate_system': 'gcj02',
                  'coordinate_evidence': {'source': 'manual'}})
    client = Client()
    assert position_detail(store, data, cid)['state'] == 'manual'
    assert position_one(store, data, cid, client, force=True) == 'skipped' and client.calls == 0


def test_manual_edit_overrides_previous_automatic_status(setup):
    store, cid, data = setup
    position_one(store, data, cid, Client())
    update_master(store, cid, longitude=120.208, coordinate_origin='manual')
    detail = position_detail(store, data, cid)
    assert detail['state'] == 'manual' and detail['selected']['longitude'] == 120.208
    assert not detail['candidates']


def test_addressless_candidate_auto_matches_but_confirm_requires_address(setup):
    store, cid, data = setup
    client = Client([poi(address='')])  # 唯一候选不再因地址为空进 review，自动 matched
    assert position_one(store, data, cid, client) == 'updated'
    detail = position_detail(store, data, cid)
    assert detail['state'] == 'matched' and detail['selected']['source_id'] == 'B1'
    with pytest.raises(ValueError, match='地图地址'):
        confirm_position(store, data, cid, revision=detail['revision'], poi_id='B1')  # 人工确认仍拒绝无地址候选
    assert position_detail(store, data, cid)['state'] == 'matched'


def with_alias(store, cid):
    store.update(cid, name='风雅钱塘', aliases=['茂御居'], address='月明路1076号', district='滨江')


@pytest.mark.parametrize('alias_rows,state', [
    ([poi()], 'matched'),
    ([poi(address='江南大道100号')], 'matched'),
    ([poi('B1'), poi('B2')], 'review'),
])
def test_alias_retry_after_empty_primary_name(setup, alias_rows, state):
    store, cid, data = setup
    with_alias(store, cid)
    client = Client(rows=[], by_name={'茂御居': alias_rows})
    if state == 'matched':
        assert position_one(store, data, cid, client) == 'updated'
    else:
        with pytest.raises(ValueError):
            position_one(store, data, cid, client)
    detail = position_detail(store, data, cid)
    assert detail['state'] == state and len(detail['candidates']) == len(alias_rows)
    assert client.queries == ['风雅钱塘', '茂御居']


def test_alias_retry_exhausted_stays_not_found(setup):
    store, cid, data = setup
    with_alias(store, cid)
    client = Client(rows=[])
    with pytest.raises(ValueError, match='未找到名称、区域及分类可靠的高德地点'):
        position_one(store, data, cid, client)
    detail = position_detail(store, data, cid)
    assert detail['state'] == 'not_found' and not detail['candidates']
    assert client.queries == ['风雅钱塘', '茂御居']


def test_single_containment_candidate_matches_and_stops_retry(setup):
    store, cid, data = setup
    with_alias(store, cid)
    client = Client([poi(name='风雅钱塘御涛轩', address='江南大道100号')])  # 唯一宽松候选（名字包含、地址不同）也自动 matched
    assert position_one(store, data, cid, client) == 'updated'
    detail = position_detail(store, data, cid)
    assert detail['state'] == 'matched' and detail['selected']['source_id'] == 'B1'
    assert client.queries == ['风雅钱塘']  # 主名已有候选（宽松也算命中），不发起别名重查


def test_exact_and_containment_candidates_merge_into_review(setup):
    store, cid, data = setup
    rows = [poi('B1'), poi('B2', name='风雅钱塘公馆')]
    with pytest.raises(ValueError):
        position_one(store, data, cid, Client(rows))
    detail = position_detail(store, data, cid)
    assert detail['state'] == 'review'
    assert [c['source_id'] for c in detail['candidates']] == ['B1', 'B2']


def test_short_names_do_not_participate_in_containment(setup):
    store, cid, data = setup
    store.update(cid, name='风雅钱塘', aliases=['西湖'], address='月明路1076号', district='滨江')
    client = Client([poi(name='西湖大院')])  # 「西湖」归一化长度 < 3，包含匹配不生效
    with pytest.raises(ValueError, match='未找到名称、区域及分类可靠的高德地点'):
        position_one(store, data, cid, client)
    assert position_detail(store, data, cid)['state'] == 'not_found'
    assert client.queries == ['风雅钱塘', '西湖']


def test_alias_identical_to_primary_is_not_requeried(setup):
    store, cid, data = setup
    store.update(cid, name='风雅钱塘', aliases=['风雅钱塘', '风雅 钱塘'], address='月明路1076号', district='滨江')
    client = Client(rows=[])
    with pytest.raises(ValueError):
        position_one(store, data, cid, client)
    assert client.queries == ['风雅钱塘'] and client.calls == 1
    assert position_detail(store, data, cid)['state'] == 'not_found'


def test_alias_retry_is_capped_at_three_queries(setup):
    store, cid, data = setup
    store.update(cid, name='风雅钱塘', aliases=['别名一号楼', '别名二号楼', '别名三号楼', '别名四号楼'],
                 address='月明路1076号', district='滨江')
    client = Client(rows=[])
    with pytest.raises(ValueError):
        position_one(store, data, cid, client)
    assert client.queries == ['风雅钱塘', '别名一号楼', '别名二号楼', '别名三号楼']
    assert client.calls == 4


def test_primary_exact_candidates_skip_alias_retry(setup):
    store, cid, data = setup
    with_alias(store, cid)
    client = Client([poi(), poi('B2')])  # 主名已有精确候选 → review，不重查别名
    with pytest.raises(ValueError):
        position_one(store, data, cid, client)
    assert client.calls == 1 and position_detail(store, data, cid)['state'] == 'review'
    client = Client()  # force 重查：主名唯一精确候选 → matched，同样不重查
    assert position_one(store, data, cid, client, force=True) == 'updated' and client.calls == 1


@pytest.mark.parametrize('rows', [[], [poi()]])
def test_truncated_result_stays_review_without_retry(setup, rows):
    store, cid, data = setup
    with_alias(store, cid)
    client = Client(rows=rows, count=26)  # 疑似截断：即使唯一候选也维持 review 文案，不发起别名重查
    with pytest.raises(ValueError, match='未找到唯一可靠位置'):
        position_one(store, data, cid, client)
    detail = position_detail(store, data, cid)
    assert detail['state'] == 'review' and len(detail['candidates']) == len(rows)
    assert client.calls == 1
