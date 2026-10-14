import threading

import pytest

from src.services import amap_directory as amap
from src.services.community_registry import CommunityRegistry
from src.services.directory_collection import collect_names, DirectoryJob
from src.services.residential_classifier import classify_sources


def poi(sid='1', name='风雅钱塘', **extra):
    return dict(id=sid, name=name, type='商务住宅;住宅区;住宅小区', typecode='120302',
                adname='滨江区', address='月明路1076号', location='120.207490,30.202261', **extra)


class Cancel:
    def __init__(self): self.cancelled = False
    def is_set(self): return self.cancelled
    def wait(self, _): return self.cancelled


class Client:
    def __init__(self, search): self._search = search; self.closed = False
    def search(self, box, page): return self._search(box, page)
    def close(self): self.closed = True


def test_spatial_subdivision_dedup_and_complete_report():
    calls = []
    def search(box, page):
        calls.append((box, page))
        if len(calls) == 1:
            return [poi()], 481
        return [poi(), poi('2', '测试花园二期')], 2
    client = Client(search)
    rows = list(amap.discover(Cancel(), lambda *_: False, client=client))
    records = [r for r in rows if 'source_id' in r]
    assert len(records) == 2 and records[1]['name'].endswith('二期')
    assert len(calls) == 5 and client.closed
    assert rows[-1]['_coverage']['complete'] is True
    assert rows[-1]['_coverage']['duplicates'] == 7


def test_pages_are_exhausted_within_each_cell():
    client = Client(lambda box, page: ([poi(str(i)) for i in range(25)] if page == 1 else [poi('26')], 26))
    rows = list(amap.discover(Cancel(), lambda *_: False, client=client))
    assert rows[-1]['_coverage']['unique'] == 26
    assert rows[-1]['_coverage']['requests'] == 2


@pytest.mark.parametrize('filtered', [False, True])
def test_overlapping_pages_count_raw_unique_ids_before_completion(filtered):
    calls = []
    def search(box, page):
        calls.append(page)
        pages = {1: ['a', 'b'], 2: ['b', 'c'], 3: ['d']}
        rows = [poi(sid) for sid in pages[page]]
        if filtered:
            for row in rows:
                if row['id'] in {'b', 'd'}:
                    row['adname'] = '萧山区'
        return rows, 4
    client = Client(search)
    rows = list(amap.discover(Cancel(), lambda *_: False, client=client))
    assert calls == [1, 2, 3]
    assert rows[-1]['_coverage']['unique'] == (2 if filtered else 4)
    assert rows[-1]['_coverage']['complete'] is True and client.closed


def test_duplicate_ids_within_a_page_do_not_exhaust_count():
    calls = []
    def search(box, page):
        calls.append(page)
        return ([poi('a'), poi('a')] if page == 1 else [poi('b')]), 2
    rows = list(amap.discover(Cancel(), lambda *_: False, client=Client(search)))
    assert calls == [1, 2]
    assert rows[-1]['_coverage']['unique'] == 2


def test_decreasing_reported_count_does_not_hide_missing_records():
    calls = []
    def search(box, page):
        calls.append(page)
        return [poi(str(page))], (3 if page == 1 else 1)
    rows = list(amap.discover(Cancel(), lambda *_: False, client=Client(search)))
    assert calls == [1, 2, 3]
    assert rows[-1]['_coverage']['unique'] == 3


def test_saturated_terminal_cell_reads_all_accessible_pages():
    calls = []
    def search(box, page):
        calls.append(page)
        return [poi(str(i)) for i in range((page - 1) * 25, page * 25)], 200
    client = Client(search)
    rows = []
    with pytest.raises(amap.AmapIncomplete):
        rows.extend(amap.discover(Cancel(), lambda *_: False, client=client, max_depth=0))
    assert calls == list(range(1, 9))
    assert len([r for r in rows if 'source_id' in r]) == 200
    assert rows[-1]['_coverage']['incomplete_cells'] == 1
    assert rows[-1]['_coverage']['complete'] is False and client.closed


@pytest.mark.parametrize('mode', ['repeated', 'empty'])
def test_abnormal_pages_subdivide_and_recover(mode):
    root = None
    calls = []
    def search(box, page):
        nonlocal root
        root = root or box
        calls.append((box, page))
        if box == root:
            return ([poi('a')] if page == 1 or mode == 'repeated' else []), 2
        return [poi('a'), poi('b')], 2
    client = Client(search)
    rows = list(amap.discover(Cancel(), lambda *_: False, client=client))
    assert len(set(box for box, _ in calls)) == 5
    assert rows[-1]['_coverage']['unique'] == 2
    assert rows[-1]['_coverage']['complete'] is True and client.closed


@pytest.mark.parametrize('mode', ['repeated', 'empty'])
def test_unrecoverable_abnormal_cell_does_not_skip_siblings(mode):
    root = None
    stuck = None
    calls = []
    def search(box, page):
        nonlocal root, stuck
        root = root or box
        calls.append((box, page))
        if box == root:
            return [poi('root')], 200
        stuck = stuck or box
        if box == stuck:
            return ([poi('stuck')] if page == 1 or mode == 'repeated' else []), 2
        return [poi(str(box))], 1
    client = Client(search)
    rows = []
    with pytest.raises(amap.AmapIncomplete, match='1 个区域'):
        rows.extend(amap.discover(Cancel(), lambda *_: False, client=client, max_depth=1))
    assert len(set(box for box, _ in calls)) == 5
    assert len([r for r in rows if 'source_id' in r]) == 5
    assert rows[-1]['_coverage']['incomplete_cells'] == 1
    assert client.closed


@pytest.mark.parametrize('recoverable', [True, False])
def test_recovery_report_and_discovered_records_survive_restart(tmp_path, monkeypatch, recoverable):
    root = None
    stuck = None
    def search(box, page):
        nonlocal root, stuck
        root = root or box
        if box == root:
            return [poi('root')], 200
        stuck = stuck or box
        if box == stuck:
            return [poi('stuck')], 2
        return [poi(str(box))], 1
    client = Client(search)
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    discover = amap.discover
    monkeypatch.setattr(amap, 'discover', lambda cancel, ignored: discover(
        cancel, ignored, client=client, max_depth=2 if recoverable else 1))
    # At depth2 the stuck box is split into four successful boxes. At depth1
    # it remains incomplete; the other three siblings still enter the registry.
    report = collect_names(store, ['amap'], cancel=Cancel())
    assert report['phase'] == ('succeeded' if recoverable else 'partial_failed')
    assert report['coverage']['amap']['complete'] is recoverable
    assert report['coverage']['amap']['incomplete_cells'] == (0 if recoverable else 1)
    assert len(store.sources()) == (9 if recoverable else 5)
    assert bool(report['truncated']) is not recoverable
    job = DirectoryJob(store)
    job._save(report)
    assert DirectoryJob(CommunityRegistry(store.path)).state == report
    assert client.closed


def test_terminal_pagination_stops_at_global_budget():
    calls = []
    def search(box, page):
        calls.append(page)
        return [poi(str(i)) for i in range((page - 1) * 25, page * 25)], 200
    client = Client(search)
    rows = []
    with pytest.raises(amap.AmapIncomplete, match='请求预算'):
        rows.extend(amap.discover(Cancel(), lambda *_: False, client=client,
                                  max_depth=0, max_requests=2))
    assert calls == [1, 2] and client.closed
    assert rows[-1]['_coverage']['unique'] == 50
    assert rows[-1]['_coverage']['complete'] is False


def test_terminal_pagination_can_be_cancelled_between_pages():
    cancel = Cancel()
    calls = []
    def search(box, page):
        calls.append(page)
        return [poi(str(i)) for i in range((page - 1) * 25, page * 25)], 200
    client = Client(search)
    with pytest.raises(InterruptedError):
        for row in amap.discover(cancel, lambda *_: False, client=client, max_depth=0):
            if row.get('_coverage', {}).get('requests') == 2:
                cancel.cancelled = True
    assert calls == [1, 2] and client.closed


@pytest.mark.parametrize('mode', ['repeated', 'empty'])
def test_budget_after_abnormal_page_keeps_current_coverage_counters(mode):
    calls = []
    def search(box, page):
        calls.append(page)
        return ([poi('a')] if page == 1 or mode == 'repeated' else []), 2
    client = Client(search)
    rows = []
    with pytest.raises(amap.AmapIncomplete, match='请求预算'):
        rows.extend(amap.discover(Cancel(), lambda *_: False, client=client, max_requests=2))
    assert calls == [1, 2] and client.closed
    assert rows[-1]['_coverage']['requests'] == 2
    assert rows[-1]['_coverage']['cells'] == 1
    assert rows[-1]['_coverage']['complete'] is False


@pytest.mark.parametrize('saturated', [True, False])
def test_budget_after_terminal_cell_keeps_incomplete_count(saturated):
    root = None
    def search(box, page):
        nonlocal root
        root = root or box
        if box == root:
            return [poi('root')], 200
        if saturated:
            return [poi(str(i)) for i in range((page - 1) * 25, page * 25)], 200
        return [poi(str(page))], 9
    rows = []
    with pytest.raises(amap.AmapIncomplete, match='请求预算'):
        rows.extend(amap.discover(Cancel(), lambda *_: False, client=Client(search),
                                  max_depth=1, max_requests=9))
    assert rows[-1]['_coverage']['requests'] == 9
    assert rows[-1]['_coverage']['incomplete_cells'] == 1


def test_eight_short_pages_subdivide_and_discover_missing_records():
    root = None
    calls = []
    def search(box, page):
        nonlocal root
        root = root or box
        calls.append((box, page))
        if box == root:
            return [poi(str(page))], 9
        return [poi('1'), poi('missing', '补充花园')], 2
    client = Client(search)
    rows = list(amap.discover(Cancel(), lambda *_: False, client=client))
    records = [r for r in rows if 'source_id' in r]
    assert len(records) == 9 and records[-1]['source_id'] == 'missing'
    assert [page for box, page in calls if box == root] == list(range(1, 9))
    children = [box for box, page in calls if box != root]
    assert len(set(children)) == 4
    assert all(box[2] - box[0] < root[2] - root[0] for box in children)
    assert rows[-1]['_coverage']['complete'] is True and client.closed
    assert rows[-1]['_coverage']['requests'] == 12


def test_page_limit_at_max_depth_keeps_scanning_sibling_regions():
    root = None
    stuck = None
    calls = []
    def search(box, page):
        nonlocal root, stuck
        root = root or box
        calls.append((box, page))
        if box == root:
            return [poi('root')], 200
        stuck = stuck or box
        if box == stuck:
            return [poi(f'stuck-{page}')], 9
        return [poi(str(box))], 1
    client = Client(search)
    rows = []
    with pytest.raises(amap.AmapIncomplete, match='1 个区域'):
        rows.extend(amap.discover(Cancel(), lambda *_: False, client=client, max_depth=1))
    # The unresolved first child must not hide the other three children.
    assert len({box for box, page in calls}) == 5
    assert len([r for r in rows if 'source_id' in r]) == 12
    assert rows[-1]['_coverage']['incomplete_cells'] == 1
    assert rows[-1]['_coverage']['complete'] is False and client.closed


def test_subdivision_after_page_limit_still_respects_request_budget():
    client = Client(lambda box, page: ([poi(str(page))], 9))
    rows = []
    with pytest.raises(amap.AmapIncomplete, match='请求预算'):
        rows.extend(amap.discover(Cancel(), lambda *_: False, client=client, max_requests=8))
    assert rows[-1]['_coverage']['requests'] == 8 and client.closed


def test_cancel_before_subdivided_cell_prevents_more_requests():
    cancel = Cancel()
    calls = []
    def search(box, page):
        calls.append(page)
        return [poi(str(page))], 9
    client = Client(search)
    with pytest.raises(InterruptedError):
        for row in amap.discover(cancel, lambda *_: False, client=client):
            if row.get('_coverage', {}).get('requests') == 8:
                cancel.cancelled = True
    assert calls == list(range(1, 9)) and client.closed


@pytest.mark.parametrize('mode', ['empty', 'repeated', 'budget', 'depth'])
def test_incomplete_queries_raise_and_preserve_already_yielded_records(mode):
    if mode == 'empty':
        search = lambda box, page: ([poi()] if page == 1 else [], 26)
    else:
        search = lambda box, page: ([poi()], 481 if mode in {'budget', 'depth'} else 26)
    client = Client(search)
    seen = []
    with pytest.raises(amap.AmapIncomplete):
        for row in amap.discover(Cancel(), lambda *_: False, client=client,
                                 max_requests=1 if mode == 'budget' else 256,
                                 max_depth=0 if mode == 'depth' else 8):
            seen.append(row)
    assert any('source_id' in r for r in seen) and client.closed


def test_filters_district_bounds_and_subordinate_pois():
    for field, value in [('adname', '萧山区'), ('location', '116.4,39.9'),
                         ('typecode', '120201'), ('name', '风雅钱塘北门'), ('name', '风雅钱塘12号楼')]:
        row = poi(); row[field] = value
        assert amap.normalize_poi(row) is None
    assert amap.normalize_poi(poi(name='测试花园西区'))['name'] == '测试花园西区'
    row = poi(); row['location'] = 'NaN,30.2'
    with pytest.raises(ValueError): amap.normalize_poi(row)


def test_cancel_closes_client():
    cancel = Cancel()
    def search(box, page):
        cancel.cancelled = True
        return [poi()], 1
    client = Client(search)
    with pytest.raises(InterruptedError): list(amap.discover(cancel, lambda *_: False, client=client))
    assert client.closed


def test_ignored_identity_is_not_revived_and_coverage_is_not_a_source(tmp_path):
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    original = store.ingest(amap.normalize_poi(poi()))
    store.ignore_source(original['id'])
    def adapter(cancel, ignored):
        yield amap.normalize_poi(poi(name='风雅钱塘改名'))
        yield {'_coverage': {'complete': True, 'unique': 1}}
    report = collect_names(store, ['amap'], adapters={'amap': adapter})
    assert report['ignored'] == 1 and report['new'] == 0
    assert report['coverage']['amap']['complete']
    assert store.sources()[0]['name'] == '风雅钱塘'
    job = DirectoryJob(store); job._save(report)
    assert DirectoryJob(store).state['coverage'] == report['coverage']


def test_map_hint_never_overrides_property_use():
    hint = amap.normalize_poi(poi())
    assert classify_sources([hint]) == 'pending'
    assert classify_sources([hint, {'source': 'tmsf', 'source_id': 't', 'property_type': '住宅'}]) == 'residential'
    assert classify_sources([hint, {'source': 'tmsf', 'source_id': 't', 'property_type': '写字楼'}]) == 'non_residential'
    assert classify_sources([hint, {'source': 'tmsf', 'source_id': 't', 'property_type': '公寓'}]) == 'pending'


def test_transport_error_cannot_leak_key(monkeypatch):
    monkeypatch.setenv('AMAP_WEB_SERVICE_KEY', 'private-key')
    client = amap.AmapClient()
    def failed(*args, **kwargs): raise RuntimeError('https://example?key=private-key')
    monkeypatch.setattr(client.session, 'get', failed)
    try:
        with pytest.raises(ValueError, match='高德请求失败') as exc:
            client.search((120.1, 30.1, 120.2, 30.2), 1)
        assert 'private-key' not in str(exc.value)
    finally: client.close()
