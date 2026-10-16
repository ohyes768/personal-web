import threading
import pytest
from src.services.community_registry import CommunityRegistry
from src.services.rental_reference.association import decide, prepare_sources, reviews
from src.services.rental_reference.refresh import RentalRefreshService


def setup(tmp_path):
    registry = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    for cid, name in [('c1', '测试花园'), ('c2', '其他花园')]:
        registry.create(name, district='滨江', address='测试路1号', community_id=cid)
        record = registry.ingest(dict(source='tmsf', source_id=cid, name=name, district='滨江', property_type='住宅'))
        registry.associate(record['id'], cid)
    return registry


def test_no_fabricated_district_and_unknown_excluded(tmp_path):
    registry = setup(tmp_path)
    registry.create('待核实', district='滨江', community_id='c3')
    calls = []
    def discover(c):
        calls.append(c['community_id'])
        return [dict(source_community_id=c['community_id'], source_name=c['community_name'],
                     source_address='测试路1号', source_url='https://zu.fang.com/hz/house-xm123/')]
    pairs, report = prepare_sources(registry, threading.Event(), lambda _: None, discover, delay=0)
    assert pairs == [] and report['pending'] == 2 and report['excluded'] == 1
    assert calls == ['c1', 'c2']


def test_mapping_reused_and_unreliable_search_stopped(tmp_path):
    registry = setup(tmp_path)
    registry.ingest(dict(source='fang', source_id='f1', name='测试花园', district='滨江', address='测试路1号'))
    calls = []
    def broken(c):
        calls.append(c['community_id']); raise ValueError('搜索未应用关键词')
    pairs, report = prepare_sources(registry, threading.Event(), lambda _: None, broken, delay=0)
    assert pairs == [('f1', 'c1')] and calls == ['c2'] and report['failed'] == 1
    assert reviews(registry)[0]['reason'] == 'search_failed'


def test_single_candidate_auto_binds_on_high_similarity(tmp_path):
    registry = setup(tmp_path)
    # 名字不完全一致（通名差异）的唯一候选：分数达标在入库时即自动绑，且带 auto 证据
    source = registry.ingest(dict(source='fang', source_id='f1', name='测试花园小区', district='滨江', address='测试路1号'))
    assert source['status'] == 'matched' and source['community_id'] == 'c1' and source['method'] == 'auto'
    assert any('相似度' in line for line in source['evidence'])


def test_single_low_similarity_candidate_stays_pending(tmp_path):
    registry = setup(tmp_path)
    # 分期冲突：字面像但不是一家，绝不自动绑
    registry.ingest(dict(source='fang', source_id='f1', name='测试花园一期', district='滨江', address='测试路1号'))
    registry.ingest(dict(source='fang', source_id='f2', name='测试花园二期', district='滨江', address='测试路1号'))
    assert registry.auto_associate() == 0
    assert not [r for r in registry.sources() if r['source'] == 'fang' and r['status'] == 'matched']


def test_multiple_candidates_stay_pending(tmp_path):
    registry = setup(tmp_path)
    registry.create('测试花园', district='滨江', community_id='c3')  # 重名小区：候选不再唯一
    registry.ingest(dict(source='fang', source_id='f1', name='测试花园小区', district='滨江', address='测试路1号'))
    assert registry.auto_associate() == 0
    assert not [r for r in registry.sources() if r['source'] == 'fang' and r['status'] == 'matched']


def test_review_candidates_carry_sorted_similarity(tmp_path):
    registry = setup(tmp_path)
    registry.create('测试花园', district='滨江', community_id='c3')  # 重名：来源保持 pending 进人工清单
    found = [dict(source_community_id='xm1', source_name='测试花园小区', source_url='https://zu.fang.com/hz/house-xm1/'),
             dict(source_community_id='xm2', source_name='测试花园西区', source_url='https://zu.fang.com/hz/house-xm2/')]
    prepare_sources(registry, threading.Event(), lambda _: None, lambda c: found, delay=0)
    items = reviews(registry)
    entry = next(i for i in items if i['community_id'] == 'c1')
    assert entry['reason'] == 'needs_selection'
    scores = [c['similarity'] for c in entry['candidates']]
    assert scores == sorted(scores, reverse=True) and scores[0] >= 0.92


def test_skip_restart_reopen_bind_without_deleting(tmp_path):
    registry = setup(tmp_path)
    source = registry.ingest(dict(source='fang', source_id='f1', name='测试花园'))
    decide(registry, 'c1', 'skip')
    registry = CommunityRegistry(registry.path)
    assert reviews(registry)[0]['reason'] == 'skipped'
    assert len(registry.communities()) == 2
    assert next(s for s in registry.sources() if s['id']==source['id'])['status'] == 'pending'
    calls = []
    prepare_sources(registry, threading.Event(), lambda _: None, lambda c: calls.append(c['community_id']) or [], delay=0)
    assert 'c1' not in calls
    decide(registry, 'c1', 'reopen'); decide(registry, 'c1', 'bind', source['id'])
    assert not any(i['community_id']=='c1' for i in reviews(registry))
    with pytest.raises(ValueError, match='已绑定'): decide(registry, 'c1', 'skip')


def test_new_candidates_reopen_skip_and_rejected_stays_rejected(tmp_path):
    registry = setup(tmp_path)
    first = registry.ingest(dict(source='fang', source_id='f1', name='测试花园'))
    decide(registry, 'c1', 'skip')
    second = registry.ingest(dict(source='fang', source_id='f2', name='测试花园'))
    assert reviews(registry)[0]['reason'] == 'needs_selection'
    registry.unlink(first['id'], 'c1')
    assert {c['id'] for c in reviews(registry)[0]['candidates']} == {second['id']}
    with pytest.raises(ValueError, match='候选'): decide(registry, 'c1', 'bind', first['id'])


def test_zero_mappings_finishes_with_review(tmp_path, monkeypatch):
    registry = setup(tmp_path)
    from src.services.rental_reference import sources
    monkeypatch.setattr(sources, 'discover', lambda *a, **k: [])
    service = RentalRefreshService(tmp_path/'rentals', tmp_path/'rental_community_mappings.json', delay=0)
    service.start(); service._thread.join(5)
    job = service.status()
    assert not job['running'] and job['phase']=='done'
    assert job['association']['missing']==2 and job['result']['published'] is False
    assert len(reviews(registry))==2


def test_ignored_candidate_cannot_bind(tmp_path):
    registry = setup(tmp_path)
    source = registry.ingest(dict(source='fang', source_id='f1', name='测试花园'))
    registry.ignore_source(source['id'])
    with pytest.raises(ValueError): decide(registry, 'c1', 'bind', source['id'])


def test_unique_complete_evidence_auto_associates(tmp_path):
    registry = setup(tmp_path)
    # Exact addresses and externally evidenced district, not inferred district.
    registry.update('c1', name='测试花园', aliases=[], address='杭州市滨江区测试路1号')
    def discover(c):
        return [dict(source_community_id='100', source_name='测试花园',
                     source_address='杭州市滨江区测试路1号', source_url='https://zu.fang.com/hz/house-xm100/')] if c['community_id']=='c1' else []
    pairs, report = prepare_sources(registry, threading.Event(), lambda _: None, discover, delay=0)
    assert pairs == [('100', 'c1')] and report['matched']==1


def test_budget_cancellation_and_empty_search_distinct(tmp_path):
    registry = setup(tmp_path)
    pairs, report = prepare_sources(registry, threading.Event(), lambda _: None, lambda _: [], delay=0, budget=1)
    assert not pairs and report['missing']==1 and report['failed']==0 and report['deferred']==1
    task = next(r for r in reviews(registry) if r['reason']=='search_deferred')
    assert task['searched_at'] is None and '额度已用完' in task['message']
    calls = []
    prepare_sources(registry, threading.Event(), lambda _: None,
                    lambda c: calls.append(c['community_id']) or [], delay=0, budget=1)
    assert calls == [task['community_id']]
    cancel = threading.Event(); cancel.set()
    from src.services.fang_rentals import RentalCrawlCancelled
    with pytest.raises(RentalCrawlCancelled):
        prepare_sources(registry, cancel, lambda _: None, lambda _: [], delay=0)


def test_search_pause_logs_trigger_and_deferred_count(tmp_path, caplog):
    registry = setup(tmp_path)
    calls = []
    def broken(c):
        calls.append(c['community_id'])
        raise ValueError('搜索未应用关键词')
    with caplog.at_level('INFO'):
        _, report = prepare_sources(registry, threading.Event(), lambda _: None, broken, delay=0)
    assert calls == ['c1'] and report['failed'] == 1 and report['deferred'] == 1
    tasks = {r['community_id']: r for r in reviews(registry)}
    assert tasks['c1']['reason'] == 'search_failed'
    assert tasks['c2']['reason'] == 'search_deferred' and tasks['c2']['searched_at'] is None
    assert '尚未查询' in tasks['c2']['message']
    assert report['checked'] == sum(report[k] for k in ('matched','pending','skipped','missing','failed','deferred'))
    assert 'Rental source search paused community_id=c1' in caplog.text
    assert '搜索未应用关键词' in caplog.text
    assert 'requests=1 deferred=1' in caplog.text
    assert sum(bool(r.exc_info) for r in caplog.records) == 1


def test_deferred_only_job_is_partial_not_succeeded():
    from src.api.rental_routes import _external_phase
    assert _external_phase({'phase':'done', 'association':{'deferred':2}}) == 'partial_failed'
    assert _external_phase({'phase':'done', 'association':{'deferred':0}}) == 'succeeded'


def test_found_candidate_with_different_name_remains_selectable(tmp_path):
    registry = setup(tmp_path)
    def discover(c):
        return [dict(source_community_id='101', source_name='花园一期', source_address='',
                     source_url='https://zu.fang.com/hz/house-xm101/')] if c['community_id']=='c1' else []
    prepare_sources(registry, threading.Event(), lambda _: None, discover, delay=0)
    task = next(r for r in reviews(registry) if r['community_id']=='c1')
    assert len(task['candidates']) == 1
    decide(registry, 'c1', 'bind', task['candidates'][0]['id'])


def test_review_api_single_choice_and_locked_decisions(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api import rental_source_routes, rental_routes
    registry = setup(tmp_path)
    source = registry.ingest(dict(source='fang', source_id='101', name='测试花园'))
    decide(registry, 'c1', 'skip')
    service = RentalRefreshService(tmp_path/'rentals', tmp_path/'rental_community_mappings.json', delay=0)
    monkeypatch.setattr(rental_routes, '_mappings_path', tmp_path/'rental_community_mappings.json')
    monkeypatch.setattr(rental_routes, '_get_service', lambda: service)
    app = FastAPI(); app.include_router(rental_source_routes.router)
    client = TestClient(app)
    assert client.get('/rentals/association-tasks').json()['data']['items'][0]['reason']=='skipped'
    assert client.post('/rentals/association-tasks/c1', json={'action':'bind','candidate_id':[source['id']]}).status_code==422
    assert client.post('/rentals/association-tasks/c1', json={'action':'reopen'}).status_code==200
    assert client.post('/rentals/association-tasks/c1', json={'action':'bind','candidate_id':source['id']}).status_code==200
    assert client.get('/rentals/association-tasks').json()['data']['items']==[]


def test_empty_search_cache_does_not_extend_itself(tmp_path):
    registry = setup(tmp_path)
    calls = []
    discover = lambda c: calls.append(c['community_id']) or []
    prepare_sources(registry, threading.Event(), lambda _: None, discover, delay=0)
    first = reviews(registry)[0]['searched_at']
    prepare_sources(registry, threading.Event(), lambda _: None, discover, delay=0)
    assert len(calls)==2 and reviews(registry)[0]['searched_at']==first
    decide(registry, 'c1', 'reopen')
    prepare_sources(registry, threading.Event(), lambda _: None, discover, delay=0)
    assert len(calls)==3


def test_deleted_during_crawl_never_publishes(tmp_path, monkeypatch):
    registry = setup(tmp_path)
    registry.ingest(dict(source='fang', source_id='100', name='测试花园', district='滨江', address='测试路1号'))
    from src.services.rental_reference import sources
    monkeypatch.setattr(sources, 'discover', lambda *a, **k: [])
    class Client:
        def __init__(self, **kwargs): pass
        def fetch(self, url):
            registry.delete('c1')
            return '<title>杭州租房 - 房天下</title><p>暂无房源</p>'
        def close(self): pass
    service = RentalRefreshService(tmp_path/'rentals', tmp_path/'rental_community_mappings.json', fetch_factory=Client, delay=0)
    service.start(); service._thread.join(5)
    assert not service.status()['result']['published']
    from src.services.rental_reference.storage import load_current
    assert load_current(tmp_path/'rentals') is None
