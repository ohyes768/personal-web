"""Catalog reuse must never hide changed facts or leak caller mutations."""
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from src.services import directory_workflow as flow
from src.services.community_registry import CommunityRegistry, dump
from src.services.directory_policy import KEY, VERSION


def directory(tmp_path):
    store = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    c = store.create('测试花园', district='滨江', address='测试路8号')
    source = store.ingest(dict(source='tmsf', source_id='1', name='测试花园', district='滨江',
                               address='测试路8号', property_type='住宅', listing_count=5))
    store.associate(source['id'], c['community_id'])
    with store.db() as db:
        db.execute('INSERT INTO meta VALUES (?,?)', (KEY, VERSION))
    return store, c, source


def count_builds(monkeypatch):
    calls = []
    original = flow.community_views

    def build(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(flow, 'community_views', build)
    return calls


def test_inventory_reuses_version_across_store_instances_and_isolates_mutations(tmp_path, monkeypatch):
    store, _, _ = directory(tmp_path)
    calls = count_builds(monkeypatch)
    first = flow.inventory(store, tmp_path)
    expected = json.loads(json.dumps(first))
    first[0]['sources'][0]['name'] = '污染'
    first[0]['admission']['state'] = '污染'
    assert flow.inventory(CommunityRegistry(store.path), tmp_path) == expected
    assert len(calls) == 1


@pytest.mark.parametrize('table', ['communities', 'sources', 'community_admission', 'meta'])
@pytest.mark.parametrize('wal', [False, True])
def test_inventory_invalidates_external_commits(tmp_path, monkeypatch, table, wal):
    store, c, source = directory(tmp_path)
    calls = count_builds(monkeypatch)
    # Keep a WAL connection open to test commits not checkpointed into the main file.
    with sqlite3.connect(store.path) as writer:
        if wal:
            writer.execute('PRAGMA journal_mode=WAL')
        before = flow.inventory(store, tmp_path)
        if table == 'communities':
            value = {**c, 'community_name': '新名字花园'}
            writer.execute('UPDATE communities SET payload=? WHERE id=?', (dump(value), c['community_id']))
        elif table == 'sources':
            value = {**source, 'property_type': '商铺'}
            writer.execute('UPDATE sources SET payload=? WHERE id=?', (dump(value), source['id']))
        elif table == 'community_admission':
            value = dict(state='excluded', decision_kind='manual', revision=2, auto_review_locked=True, reason='人工排除')
            writer.execute('UPDATE community_admission SET payload=? WHERE cid=?', (dump(value), c['community_id']))
        else:
            writer.execute('UPDATE meta SET value=? WHERE key=?', ('disabled', KEY))
        writer.commit()
        after = flow.inventory(store, tmp_path)
        assert len(calls) == 2
        if table != 'meta':
            assert after != before
        assert flow.inventory(store, tmp_path) == after
        assert len(calls) == 2


@pytest.mark.parametrize('filename', ['property_types.json', 'binjiang_coordinates.json'])
def test_inventory_invalidates_files_and_atomic_replacement(tmp_path, monkeypatch, filename):
    store, _, _ = directory(tmp_path)
    calls = count_builds(monkeypatch)
    flow.inventory(store, tmp_path)
    path = tmp_path / filename
    path.write_text('{}', encoding='utf-8')
    flow.inventory(store, tmp_path)
    replacement = tmp_path / 'replacement.json'
    replacement.write_text('{}', encoding='utf-8')
    replacement.replace(path)
    flow.inventory(store, tmp_path)
    path.unlink()
    flow.inventory(store, tmp_path)
    assert len(calls) == 4


def test_auction_tasks_reuses_version_and_tracks_auction_file(tmp_path, monkeypatch):
    store, _, _ = directory(tmp_path)
    calls = count_builds(monkeypatch)
    assert flow.auction_tasks(store, tmp_path) == []
    assert flow.auction_tasks(store, tmp_path) == []
    assert len(calls) == 1
    (tmp_path / 'auction_records.json').write_text('{"version":1,"records":[]}', encoding='utf-8')
    assert flow.auction_tasks(store, tmp_path) == []
    assert len(calls) == 2


def test_concurrent_inventory_builds_once(tmp_path, monkeypatch):
    store, _, _ = directory(tmp_path)
    calls = count_builds(monkeypatch)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: flow.inventory(store, tmp_path), range(4)))
    assert all(row == results[0] for row in results)
    assert len(calls) == 1


def test_changes_during_build_and_failures_are_not_cached(tmp_path, monkeypatch):
    store, _, _ = directory(tmp_path)
    original = flow.community_views
    calls = []

    def build(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise ValueError('broken facts')
        result = original(*args, **kwargs)
        if len(calls) == 2:
            (tmp_path / 'property_types.json').write_text('{}', encoding='utf-8')
        return result

    monkeypatch.setattr(flow, 'community_views', build)
    with pytest.raises(ValueError, match='broken facts'):
        flow.inventory(store, tmp_path)
    flow.inventory(store, tmp_path)
    flow.inventory(store, tmp_path)
    flow.inventory(store, tmp_path)
    assert len(calls) == 3


def test_cache_is_bounded_and_does_not_store_failed_rebuilds(tmp_path):
    from src.services.directory_projection_cache import ProjectionCache
    cache = ProjectionCache(capacity=2)
    paths = [tmp_path / str(index) for index in range(3)]
    calls = []

    def build():
        calls.append(1)
        return {'items': [len(calls)]}

    for path in paths:
        cache.read([path], build)
    cache.read([paths[1]], build)  # retained
    assert len(calls) == 3
    cache.read([paths[0]], build)  # evicted
    assert len(calls) == 4


def test_source_lookup_work_is_linear_and_keeps_membership(tmp_path, monkeypatch):
    from src.services.community_admission import community_views
    store, c, source = directory(tmp_path)
    for i in range(12):
        other = store.create(f'花园{i}', district='滨江', address='测试路8号')
        row = store.ingest(dict(source='tmsf', source_id=str(i + 2), name=f'花园{i}', district='滨江'))
        store.associate(row['id'], other['community_id'])
    lookups = []
    original = store._source

    class Source(dict):
        def __getitem__(self, key):
            if key == 'community_id':
                lookups.append(1)
            return super().__getitem__(key)

    monkeypatch.setattr(store, '_source', lambda row: Source(original(row)))
    views = community_views(store, tmp_path)
    assert len(views) == 13
    assert len(lookups) <= 26
    lookups.clear()
    rows = flow.inventory(store, tmp_path)
    assert len(rows) == 13
    assert len(lookups) <= 52
    assert next(row for row in rows if row['community_id'] == c['community_id'])['sources'][0]['id'] == source['id']
