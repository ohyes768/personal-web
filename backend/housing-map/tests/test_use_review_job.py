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
    def __init__(self, rows=None, error=None, callback=None, count=None):
        self.rows = rows
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
        rows = self.rows if self.rows is not None else [poi(name=name)]
        return rows, self.count if self.count is not None else len(rows)

    def close(self):
        pass


def make(store, name, property_type='商贸'):
    c = store.create(name, district='滨江', address='月明路1076号')
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
    make(store, '钱江新城', '商贸')
    job = UseReviewJob(store)
    job._run(client=Client(), delay=0)
    state = job.snapshot()
    assert state['total'] == 2 and state['processed'] == 2
    # 已收录的住宅与高德一致；未收录的商贸与高德住宅冲突，都要处理。
    assert state['updated'] == 1 and state['conflict'] == 1
    assert state['requests'] == 2


def test_a_conflict_is_reported_as_pending_review(setup):
    store, data = setup
    cid = make(store, '钱江新城', '商贸')
    job = UseReviewJob(store)
    job._run(client=Client(), delay=0)
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
    make(store, '钱江新城', '商贸')
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
        make(store, f'小区{i}', '商贸')
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
    make(store, '钱江新城', '商贸')
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
