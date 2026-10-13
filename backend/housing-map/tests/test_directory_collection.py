from src.services.community_registry import CommunityRegistry
from src.services.directory_collection import collect_names
import threading


def test_collection_report_ignored_and_partial_failures(tmp_path):
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    store.create('测试花园', district='滨江', address='测试路1号', community_id='c1')
    row = dict(source='fang', source_id='f1', name='测试花园', district='滨江', address='测试路1号')
    store.ingest(row)
    store.delete('c1')
    def broken(cancel, limit, ignored):
        raise ValueError('upstream failed')
        yield
    def good(cancel, limit, ignored):
        yield row
        yield {**row, 'source_id': 'f2'}
    report = collect_names(store, ['fang', 'tmsf'], max_pages=1,
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
    rows = list(directory_collection.fang_names(threading.Event(), 1, lambda *args: True))
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
    assert len(list(directory_collection.laipai_names(threading.Event(), 1, lambda *_: True))) == 1
