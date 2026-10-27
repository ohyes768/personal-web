from src.services.community_registry import CommunityRegistry
from src.services.directory_collection import collect_names
import threading

import pytest


def test_retry_failed_targets_known_identities_without_discovery(tmp_path, monkeypatch):
    from src.services import directory_collection as collection, tmsf_property_type as facts, tmsf_fetcher
    import scripts.fetch_tmsf_binjiang_communities as listing
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    base = dict(source='tmsf', district='滨江', property_type='住宅', address='江南大道1号')
    for sid, extra in [('1', dict(property_type_error='timeout', listing_count_error='timeout', address_error='timeout')),
                       ('2', {}), ('3', dict(address_error='timeout')),
                       ('4', dict(property_type_error='timeout'))]:
        record = store.ingest(dict(base, source_id=sid, name=f'花园{sid}', **extra))
        if sid == '4':
            store.ignore_source(record['id'])
    store.ingest(dict(base, source_kind='project', source_id='1', name='新房1',
                      project_id='1', project_siteid='33', property_type_error='timeout',
                      listing_count_error='old', address_error='timeout', market_state='new_house'))
    store.ingest(dict(base, source='fang', source_id='5', name='其他来源', property_type_error='timeout'))
    store.ingest(dict(base, source_id='6', name='尚未采集'))
    before = {r['id']: r for r in store.sources()}
    calls = []
    def forbidden():
        raise AssertionError('retry must not discover names')
    monkeypatch.setattr(listing, 'fetch_binjiang_communities', forbidden)
    monkeypatch.setattr(tmsf_fetcher, 'TmsfClient', lambda: type('Client', (), {'close': lambda _: None})())
    monkeypatch.setattr(collection, 'pause', lambda _: None)
    def community(client, sid, names):
        calls.append(('community', sid))
        return dict(property_type='住宅', address='江南大道1号', market_state='second_hand',
                    listing_count=5, listing_count_error=None)
    def project(client, **kwargs):
        calls.append(('project', str(kwargs['propertyid'])))
        return dict(property_type='住宅', address='江南大道1号', market_state='new_house')
    monkeypatch.setattr(facts, 'fetch_community_facts', community)
    monkeypatch.setattr(facts, 'fetch_project_facts_by_id', project)
    job = collection.DirectoryJob(store)
    job.start(['tmsf'], mode='retry_failed')
    job.worker.join(timeout=5)
    assert not job.worker.is_alive()
    report = job.state
    assert set(calls) == {('community', '1'), ('community', '3'), ('project', '1')}
    assert report['phase'] == 'succeeded' and report['existing'] == 3 and report['new'] == 0
    assert report['mode'] == 'retry_failed'
    assert job.status()['retryable'] == 0
    for row in store.sources():
        if (row['source_kind'], row['source_id']) in calls and row['source'] == 'tmsf':
            assert not row.get('property_type_error') and not row.get('address_error') and not row.get('listing_count_error')
        else:
            assert row == before[row['id']]


def test_retry_failures_survive_restart_and_empty_retry_does_not_start(tmp_path, monkeypatch):
    from src.services import directory_collection as collection
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    record = store.ingest(dict(source='tmsf', source_id='1', name='失败花园', district='滨江',
                               address_error='timeout', property_type_error='timeout'))
    job = collection.DirectoryJob(store)
    assert job.status()['retryable'] == 1
    assert collection.DirectoryJob(store).status()['retryable'] == 1
    store.ignore_source(record['id'])
    with pytest.raises(ValueError, match='没有.*失败'):
        job.start(['tmsf'], mode='retry_failed')
    assert job.worker is None
    with pytest.raises(ValueError, match='模式'):
        job.start(['tmsf'], mode='invalid')


def test_retry_failure_and_cancellation_keep_effective_facts(tmp_path, monkeypatch):
    from src.services import directory_collection as collection, tmsf_fetcher, tmsf_property_type as facts
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    store.ingest(dict(source='tmsf', source_id='1', name='失败花园', district='滨江',
                      property_type='住宅', property_type_error='old', address='江南大道1号'))
    client = type('Client', (), {'close': lambda _: None, 'fetch_text': lambda *_: (_ for _ in ()).throw(ValueError('timeout'))})()
    monkeypatch.setattr(tmsf_fetcher, 'TmsfClient', lambda: client)
    monkeypatch.setattr(collection, 'pause', lambda _: None)
    monkeypatch.setattr(facts, 'fetch_community_facts', lambda *_: (_ for _ in ()).throw(ValueError('timeout')))
    report = collect_names(store, ['tmsf'], mode='retry_failed')
    assert report['phase'] == 'partial_failed'
    row = store.sources()[0]
    assert row['property_type'] == '住宅' and row['address'] == '江南大道1号' and row['property_type_error']
    cancel = threading.Event()
    def interrupted(*_):
        cancel.set()
        return dict(property_type='写字楼')
    monkeypatch.setattr(facts, 'fetch_community_facts', interrupted)
    report = collect_names(store, ['tmsf'], mode='retry_failed', cancel=cancel)
    assert report['phase'] == 'cancelled'
    assert store.sources()[0]['property_type'] == '住宅'


def test_removed_amap_cannot_run_even_with_injected_adapter(tmp_path):
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    def forbidden(*args):
        raise AssertionError('Removed Amap adapter must never run')
    with pytest.raises(ValueError, match='高德.*停止'):
        collect_names(store, ['tmsf', 'amap'], adapters={'tmsf': forbidden, 'amap': forbidden})
    assert store.sources() == []
    from src.services.directory_collection import DirectoryJob
    job = DirectoryJob(store)
    with pytest.raises(ValueError, match='高德.*停止'):
        job.start(['amap'])
    assert job.worker is None and job.state is None


def test_collection_report_ignored_and_partial_failures(tmp_path):
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    store.create('测试花园', district='滨江', address='测试路1号', community_id='c1')
    row = dict(source='fang', source_id='f1', name='测试花园', district='滨江', address='测试路1号')
    store.ingest(row)
    store.delete('c1')
    def broken(cancel, ignored):
        raise ValueError('upstream failed')
        yield
    def good(cancel, ignored):
        yield row
        yield {**row, 'source_id': 'f2'}
    report = collect_names(store, ['fang', 'tmsf'],
                           adapters={'fang': good, 'tmsf': broken})
    assert report['ignored'] == 1 and report['new'] == 1
    assert report['phase'] == 'partial_failed'
    assert report['pending'] == 1
    assert not store.communities()


def test_fang_ignored_community_skips_details_and_closes_client(monkeypatch):
    from src.services import fang_rentals, directory_collection
    requests = []
    closed = []
    class Client:
        def __init__(self, **kwargs): pass
        def fetch(self, url):
            requests.append(url)
            return 'listing'
        def close(self): closed.append(True)
    sample = dict(source_community_id='f1', community_name='测试花园', source_listing_id='l1',
                  source_url='https://zu.fang.com/hz/chuzu/3_1_1.htm', quality_flags=[])
    monkeypatch.setattr(fang_rentals, 'FangClient', Client)
    monkeypatch.setattr(fang_rentals, 'parse_listing_page', lambda *_: ([sample], None))
    rows = list(directory_collection.fang_names(threading.Event(), lambda *args: True))
    assert len(rows) == 1 and len(requests) == 1 and closed


def test_laipai_known_ignored_auction_skips_detail(monkeypatch):
    from src.services import auction_fetcher, directory_collection
    class Client:
        def list_page(self, page):
            return {'list': [{'auction_id': '1', 'object_id': '2', 'area_code': 330108}], 'count': 1}
        def detail(self, aid):
            raise AssertionError('ignored auction must not request detail')
        def close(self): pass
    monkeypatch.setattr(auction_fetcher, 'AuctionClient', Client)
    assert len(list(directory_collection.laipai_names(threading.Event(), lambda *_: True))) == 1


def test_restart_preserves_amap_failures(tmp_path):
    from src.services.directory_collection import DirectoryJob
    from src.services.community_registry import dump
    import json

    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    report = dict(phase='partial_failed', running=False, new=3, errors=[
        {'source': 'amap', 'message': '未配置高德 Web 服务 Key'},
        {'source': 'fang', 'message': 'upstream failed'},
    ], truncated=[{'source': 'amap', 'message': '旧分页限制'}], coverage={'amap': {'complete': False, 'unique': 376}})
    with store.db() as db:
        db.execute("INSERT INTO meta VALUES ('collection_job',?)", (dump(report),))
    job = DirectoryJob(store)
    assert job.state['errors'] == report['errors']
    assert job.state['truncated'] == report['truncated']
    assert job.state['new'] == 3
    assert job.state['phase'] == 'partial_failed'
    with store.db() as db:
        saved = json.loads(db.execute("SELECT value FROM meta WHERE key='collection_job'").fetchone()[0])
    assert saved == job.state
    assert DirectoryJob(store).state == saved


def test_fang_collects_beyond_ten_pages(monkeypatch):
    from src.services import fang_rentals, directory_collection
    requests = []
    class Client:
        def __init__(self, **kwargs): pass
        def fetch(self, url):
            requests.append(url)
            return str(len(requests))
        def close(self): pass
    def parse(html, url):
        page = int(html)
        return [dict(source_community_id=str(page), community_name=f'小区{page}')], (
            f'https://zu.fang.com/hz/house-a0154/n31/i3{page + 1}/' if page < 12 else None)
    monkeypatch.setattr(fang_rentals, 'FangClient', Client)
    monkeypatch.setattr(fang_rentals, 'parse_listing_page', parse)
    monkeypatch.setattr(directory_collection, 'pause', lambda cancel: None)
    rows = list(directory_collection.fang_names(threading.Event(), lambda *_: True))
    assert len(rows) == len(requests) == 12


def test_laipai_collects_beyond_ten_pages(monkeypatch):
    from src.services import auction_fetcher, directory_collection
    requests = []
    class Client:
        def list_page(self, page):
            requests.append(page)
            return {'list': [{'auction_id': str(page), 'object_id': str(page),
                              'area_code': 330108}], 'count': 12}
        def close(self): pass
    monkeypatch.setattr(auction_fetcher, 'AuctionClient', Client)
    monkeypatch.setattr(directory_collection, 'pause', lambda cancel: None)
    rows = list(directory_collection.laipai_names(threading.Event(), lambda *_: True))
    assert len(rows) == 12 and requests == list(range(1, 13))


def test_laipai_repeated_page_reports_incomplete(monkeypatch):
    import pytest
    from src.services import auction_fetcher, directory_collection
    class Client:
        def list_page(self, page):
            return {'list': [{'auction_id': '1', 'object_id': '1', 'area_code': 330108}], 'count': 12}
        def close(self): pass
    monkeypatch.setattr(auction_fetcher, 'AuctionClient', Client)
    monkeypatch.setattr(directory_collection, 'pause', lambda cancel: None)
    with pytest.raises(directory_collection.DiscoveryTruncated, match='分页重复'):
        list(directory_collection.laipai_names(threading.Event(), lambda *_: True))


def test_fang_detail_failures_are_reported_without_losing_candidates(tmp_path, monkeypatch):
    from src.services import fang_rentals, directory_collection
    closed = []
    class Client:
        def __init__(self, **kwargs): pass
        def fetch(self, url):
            if '/chuzu/' in url:
                raise ValueError('challenge URL with private query')
            return 'listing'
        def close(self): closed.append(True)
    samples = [dict(source_community_id='f1', community_name='测试花园',
                    source_listing_id=f'l{i}', source_url=f'https://zu.fang.com/hz/chuzu/3_{i}_1.htm',
                    quality_flags=[]) for i in range(2)]
    monkeypatch.setattr(fang_rentals, 'FangClient', Client)
    monkeypatch.setattr(fang_rentals, 'parse_listing_page', lambda *_: (samples, None))
    monkeypatch.setattr(directory_collection, 'pause', lambda _: None)
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    report = collect_names(store, ['fang'])
    assert report['phase'] == 'partial_failed' and report['running'] is False
    assert report['new'] == report['pending'] == 1
    assert len(report['errors']) == 2
    assert {e['listing_id'] for e in report['errors']} == {'l0', 'l1'}
    assert all(e['stage'] == 'detail' and e['source_id'] == 'f1' for e in report['errors'])
    assert 'private query' not in str(report)
    item = store.sources()[0]
    assert len(item['samples']) == 2 and item['status'] == 'pending'
    assert all('detail_fetch_failed' in s['quality_flags'] for s in item['samples'])
    assert '_collection_errors' not in item
    assert all('_collection_error' not in s for s in item['samples'])
    assert closed


def test_directory_job_initialization_failure_finishes_and_can_restart(tmp_path, monkeypatch):
    import sqlite3
    from src.services import directory_collection
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    job = directory_collection.DirectoryJob(store)
    original = store.sources
    def broken():
        raise sqlite3.OperationalError('unavailable')
    monkeypatch.setattr(store, 'sources', broken)
    job.start(['tmsf'])
    job.worker.join(timeout=5)
    assert not job.worker.is_alive()
    assert job.state['phase'] == 'failed' and job.state['running'] is False
    assert job.state['finished_at'] and job.state['errors'][0]['stage'] == 'task'
    assert directory_collection.DirectoryJob(store).state == job.state
    monkeypatch.setattr(store, 'sources', original)
    monkeypatch.setitem(directory_collection.ADAPTERS, 'tmsf', lambda *_: iter([]))
    job.start(['tmsf'])
    job.worker.join(timeout=5)
    assert job.state['phase'] == 'succeeded' and job.state['running'] is False


def test_directory_job_save_failure_finishes_in_memory(tmp_path, monkeypatch, caplog):
    import sqlite3
    from src.services import directory_collection
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    job = directory_collection.DirectoryJob(store)
    def broken():
        raise sqlite3.OperationalError('unavailable')
    monkeypatch.setattr(store, 'sources', broken)
    monkeypatch.setattr(store, 'db', broken)
    report = collect_names(store, ['tmsf'], progress=job._save)
    assert report['phase'] == 'failed' and report['running'] is False
    assert job.state['phase'] == 'failed' and job.state['running'] is False
    assert any(e['stage'] == 'save' for e in job.state['errors'])
    assert 'Could not persist community collection report' in caplog.text
