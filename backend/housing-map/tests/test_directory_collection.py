from src.services.community_registry import CommunityRegistry
from src.services.directory_collection import collect_names
import threading


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


def test_restart_removes_persisted_amap_messages_only(tmp_path):
    from src.services.directory_collection import DirectoryJob
    from src.services.community_registry import dump
    import json

    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    report = dict(phase='partial_failed', running=False, new=3, errors=[
        {'source': 'amap', 'message': '未配置高德 Web 服务 Key'},
        {'source': 'fang', 'message': 'upstream failed'},
    ], truncated=[{'source': 'amap', 'message': '旧分页限制'}])
    with store.db() as db:
        db.execute("INSERT INTO meta VALUES ('collection_job',?)", (dump(report),))
    job = DirectoryJob(store)
    assert job.state['errors'] == [report['errors'][1]]
    assert job.state['truncated'] == []
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
