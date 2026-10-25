import json

import pytest

from src.services.community_registry import CommunityRegistry, dump
from src.services.directory_policy import KEY, VERSION
from src.services.directory_use_review import UseReviewJob, review_one
from src.services.use_review_policy import use_review_view


def poi(sid='B1', name='风雅钱塘', typecode='120302'):
    return dict(id=sid, name=name, adname='滨江区', address='月明路1076号',
                typecode=typecode, type='住宅小区', location='120.20749,30.20226')


class Client:
    def __init__(self, rows=None, error=None, callback=None, count=None, typecode='120302'):
        self.rows = rows
        self.typecode = typecode
        self.error, self.callback = error, callback
        self.count = count
        self.calls = 0
        self.queries = []

    def search_name(self, name, district, types='120300|120203'):
        self.calls += 1
        self.queries.append(name)
        if self.callback:
            self.callback()
        if self.error:
            raise self.error
        rows = self.rows if self.rows is not None else [poi(name=name, typecode=self.typecode)]
        return rows, self.count if self.count is not None else len(rows)

    def close(self):
        pass


def make(store, name, property_type='公寓'):
    c = store.create(name, district='滨江', address='月明路1076号',
                     longitude=120.20749, latitude=30.20226, coordinate_system='gcj02',
                     coordinate_evidence={'source': 'amap', 'source_id': name})
    s = store.ingest(dict(source='tmsf', source_id=name, name=name, district='滨江',
                          address='月明路1076号', property_type=property_type, listing_count=3,
                          market_state='second_hand'))
    store.associate(s['id'], c['community_id'])
    return c['community_id']


@pytest.fixture
def setup(tmp_path):
    store = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    with store.db() as db:
        db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (KEY, VERSION))
    return store, tmp_path


def test_the_job_reviews_admitted_and_excluded_targets(setup):
    store, data = setup
    make(store, '风雅钱塘', '住宅')
    make(store, '钱江新城', '公寓')
    job = UseReviewJob(store)
    job._run(client=Client(typecode='120101'), delay=0)
    state = job.snapshot()
    assert state['total'] == 2 and state['processed'] == 2
    # 已定位住宅与高德非住宅冲突；公寓仍需核对用途。
    assert state['updated'] == 1 and state['conflict'] == 1
    assert state['requests'] == 2


def test_a_conflict_is_reported_as_pending_review(setup):
    store, data = setup
    cid = make(store, '钱江新城', '住宅')
    job = UseReviewJob(store)
    job._run(client=Client(rows=[poi(name='钱江新城', typecode='120101')]), delay=0)
    state = job.snapshot()
    assert state['conflict'] == 1 and state['updated'] == 0
    from src.services.directory_policy import eligibility
    from src.services.directory_workflow import inventory
    row = next(r for r in inventory(store, data) if r['community_id'] == cid)
    assert row['qualification'] == 'use_conflict'
    assert row['admission_state'] == 'excluded' and row['facts_state'] == 'incomplete'


def test_targets_with_existing_evidence_are_skipped(setup):
    store, data = setup
    cid = make(store, '风雅钱塘', '住宅')
    review_one(store, data, cid, Client())
    job = UseReviewJob(store)
    job._run(client=Client(), delay=0)
    state = job.snapshot()
    assert state['skipped'] == 1 and state['updated'] == 0 and state['requests'] == 0


def test_not_found_and_errors_are_counted_by_outcome(setup):
    store, data = setup
    make(store, '钱江新城', '公寓')
    job = UseReviewJob(store)
    job._run(client=Client(rows=[]), delay=0)
    assert job.snapshot()['not_found'] == 1
    job = UseReviewJob(store)
    job._run(client=Client(error=RuntimeError('boom')), delay=0)
    state = job.snapshot()
    assert state['error'] == 1 and state['phase'] == 'partial_failed'


def test_the_budget_stops_the_round_and_reports_it(setup):
    store, data = setup
    for i in range(3):
        make(store, f'小区{i}', '公寓')
    job = UseReviewJob(store)
    job._run(client=Client(), delay=0, budget=2)
    state = job.snapshot()
    assert state['requests'] == 2 and state['processed'] == 2
    assert state['phase'] == 'partial_failed'
    assert any('预算' in e['message'] for e in state['errors'])


def test_an_empty_run_needs_no_key_and_makes_no_request(setup, monkeypatch):
    store, data = setup

    def boom():
        raise AssertionError('空跑不应构造高德客户端')

    monkeypatch.setattr('src.services.directory_use_review.AmapClient', boom)
    job = UseReviewJob(store)
    job._run(delay=0)
    state = job.snapshot()
    assert state['total'] == 0 and state['requests'] == 0 and state['phase'] == 'succeeded'


def test_cancelling_stops_the_run_and_writes_nothing(setup):
    store, data = setup
    make(store, '钱江新城', '公寓')
    job = UseReviewJob(store)
    job.cancel.set()
    job._run(client=Client(), delay=0)
    assert job.snapshot()['phase'] == 'cancelled'
    from src.services.directory_use_review import stored_review
    assert stored_review(store, store.communities()[0]['community_id'])['state'] is None


def test_an_interrupted_run_resumes_on_the_next_start(setup):
    store, data = setup
    make(store, '钱江新城', '商贸')
    job = UseReviewJob(store)
    job.state = dict(running=True, phase='running', processed=0, total=1, updated=0, conflict=0,
                      not_found=0, uncertain=0, error=0, skipped=0, requests=0, errors=[],
                      started_at='2026-10-23T00:00:00+00:00', finished_at=None)
    job._save()
    resumed = UseReviewJob(store)
    assert resumed.snapshot()['phase'] == 'interrupted'
    assert resumed.snapshot()['running'] is False


def test_the_job_never_overwrites_a_human_decision(setup):
    store, data = setup
    cid = make(store, '钱江新城', '商贸')
    store.confirm_use(cid, revision=1, decision='residential', property_type='住宅',
                       use_evidence=[{'source': 'kerui', 'url': 'https://x/1', 'note': ''}])
    before = store.admission(cid)
    job = UseReviewJob(store)
    job._run(client=Client(), delay=0)
    assert store.admission(cid) == before


def update_master(store, cid, **values):
    with store.db() as db:
        payload = json.loads(db.execute('SELECT payload FROM communities WHERE id=?', (cid,)).fetchone()[0])
        payload.update(values)
        db.execute('UPDATE communities SET payload=? WHERE id=?', (dump(payload), cid))


@pytest.mark.parametrize('case', ['non_residential', 'other', 'outside', 'manual', 'position_pending'])
def test_skipped_only_run_needs_no_client_or_new_evidence(setup, monkeypatch, case):
    from src.services.directory_workflow import inventory
    from src.services.directory_use_review import use_review_detail
    store, data = setup
    prop = {'non_residential': '写字楼', 'other': '其他', 'outside': '公寓',
            'manual': '公寓', 'position_pending': '住宅'}[case]
    cid = make(store, case, prop)
    if case == 'outside':
        update_master(store, cid, address='浙江省杭州市拱墅区艾润堂')
    if case == 'manual':
        store.confirm_use(cid, revision=1, decision='non_residential', reason='人工核实',
                          use_evidence=[{'source': 'other', 'url': 'https://example.com/evidence'}])
    if case == 'position_pending':
        update_master(store, cid, coordinate_evidence={})
    before = inventory(store, data)[0]
    assert before['use_review']['auto_skip_reason']
    assert use_review_detail(store, data, cid)['auto_skip_reason'] == before['use_review']['auto_skip_reason']

    def boom():
        raise AssertionError('跳过项目不应构造高德客户端')

    monkeypatch.setattr('src.services.directory_use_review.AmapClient', boom)
    job = UseReviewJob(store)
    job._run(delay=0)
    state = job.snapshot()
    assert state['total'] == 0 and state['requests'] == 0 and state['phase'] == 'succeeded'
    after = inventory(store, data)[0]
    assert after['qualification'] == before['qualification']
    assert after['use_review']['state'] is None
    if case == 'outside':
        assert '区域异常' in after['use_review']['auto_skip_reason']


def test_mixed_catalog_only_queries_unclear_and_positioned_residential(setup):
    store, data = setup
    for name, prop in [('IX-WORK', '其他'), ('办公中心', '写字楼'), ('待核实公寓', '公寓'),
                       ('用途缺失', None), ('已定位住宅', '住宅')]:
        make(store, name, prop)
    client = Client()
    job = UseReviewJob(store)
    job._run(client=client, delay=0)
    assert set(client.queries) == {'待核实公寓', '用途缺失', '已定位住宅'}
    assert job.snapshot()['total'] == 3


def test_batch_rechecks_scope_before_request_but_manual_query_is_allowed(setup):
    store, data = setup
    cid = make(store, 'IX-WORK', '其他')
    client = Client()
    assert review_one(store, data, cid, client, automatic=True) == 'skipped'
    assert client.calls == 0
    assert review_one(store, data, cid, client) == 'updated'
    assert client.calls == 1
