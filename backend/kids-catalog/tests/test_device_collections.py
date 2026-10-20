import shutil
import threading
import urllib.request
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.main import create_app


FIXTURE = Path(__file__).parent / 'fixtures/tone.mp3'


def add_album(root, catalog, title, count, *, monthly=True):
    folder = root / title
    folder.mkdir(parents=True)
    for number in range(1, count + 1):
        shutil.copyfile(FIXTURE, folder / f'{number:03d}-曲目.mp3')
    if monthly:
        # Completion evidence is controlled separately by each test.
        with catalog.db() as con:
            con.execute("insert into albums(platform,album_id,title,url,age_evidence,age_confidence,last_seen) "
                        "values('蜻蜓FM',?,?, '', '', '', 'current')", (title, title))
            album_id = con.execute('select last_insert_rowid()').fetchone()[0]
            con.execute("insert into jobs(album_id,status,created_at,updated_at) values(?,'done','now','now')",
                        (album_id,))
    return folder


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / 'music'
    root.mkdir()
    app = create_app(data_dir=tmp_path / 'data', music_dir=root)
    return TestClient(app), app, app.state.catalog, root


def wait_for_generation(client):
    import time
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        result = client.get('/api/collections').json()
        if result['generation']['status'] != 'running':
            return result
        time.sleep(.01)
    pytest.fail('generation did not finish')


def generate(client):
    assert client.post('/api/collections/generate').status_code == 202
    return wait_for_generation(client)


def confirm(client, folder):
    assert client.post('/api/collections/confirm', json={'folder': folder}).status_code == 200


def test_counts_sort_rebuild_and_old_revision_never_plays_new_number(setup):
    client, app, catalog, root = setup
    for title, count in [('长篇', 30), ('儿歌', 8), ('故事', 15)]:
        add_album(root, catalog, title, count)
        confirm(client, title)
    first = generate(client)['snapshot']
    assert [(x['number'], x['track_count']) for x in first['items']] == [(1, 8), (2, 15), (3, 30)]
    assert client.get('/api/device/v1/collections').json() == first
    target = client.get('/api/device/v1/collections/by-number/1', params={'revision': first['revision']})
    assert target.json() == {'revision': first['revision'], 'number': 1, 'title': '儿歌', 'track_count': 8}
    add_album(root, catalog, '短歌', 5)
    confirm(client, '短歌')
    assert client.get('/api/device/v1/collections').json() == first
    second = generate(client)['snapshot']
    assert [x['track_count'] for x in second['items']] == [5, 8, 15, 30]
    assert client.get('/api/device/v1/collections/by-number/1', params={'revision': first['revision']}).status_code == 409
    assert client.get('/api/device/v1/collections/by-number/99', params={'revision': second['revision']}).status_code == 404
    repeated = generate(client)['snapshot']
    assert repeated['items'] == second['items']


def test_skips_unconfirmed_partial_and_corrupt_audio(setup):
    client, app, catalog, root = setup
    add_album(root, catalog, '未确认', 1)
    add_album(root, catalog, '正常', 2)
    confirm(client, '正常')
    add_album(root, catalog, '下载中', 3)
    confirm(client, '下载中')
    (root / '下载中/004.mp3.part').write_bytes(b'pending')
    add_album(root, catalog, '损坏', 1)
    (root / '损坏/001-曲目.mp3').write_bytes(b'not audio')
    assert client.post('/api/collections/confirm', json={'folder': '损坏'}).status_code == 422
    result = generate(client)
    assert [x['title'] for x in result['snapshot']['items']] == ['正常']
    assert {x['title'] for x in result['generation']['skipped']} == {'未确认', '下载中', '损坏'}
    public = str(result['snapshot'])
    assert 'provider_mappings' not in public and '/music/' not in public


def test_unavailable_nas_keeps_previous_snapshot_and_name_lookup(setup):
    client, app, catalog, root = setup
    folder = add_album(root, catalog, '合集', 1)
    confirm(client, '合集')
    first = generate(client)['snapshot']
    (folder / '001-曲目.mp3').unlink()
    folder.rmdir()
    result = generate(client)
    assert result['snapshot'] == first
    assert result['generation']['status'] == 'failed'
    response = client.get('/api/device/v1/collections/by-number/1', params={'revision': first['revision']})
    assert response.status_code == 200
    assert response.json()['title'] == '合集'


def test_snapshot_and_completion_survive_refresh_but_next_generation_is_current_only(setup, tmp_path):
    client, app, catalog, root = setup
    add_album(root, catalog, '旧合集', 1)
    confirm(client, '旧合集')
    first = generate(client)['snapshot']
    app.state.catalog.refresh([])
    assert client.get('/api/device/v1/collections').json() == first
    assert generate(client)['snapshot'] == first
    restarted = TestClient(create_app(data_dir=tmp_path / 'data', music_dir=root))
    assert generate(restarted)['snapshot'] == first
    catalog = restarted.app.state.catalog
    add_album(root, catalog, '新合集', 2)
    confirm(restarted, '新合集')
    assert [i['title'] for i in generate(restarted)['snapshot']['items']] == ['新合集']
    with restarted.app.state.collections.db() as con:
        assert con.execute("select status from completions where folder='旧合集'").fetchone()[0] == 'complete'


def test_counting_audio_does_not_require_filename_track_numbers(setup):
    client, app, catalog, root = setup
    folder = add_album(root, catalog, '儿歌', 2)
    (folder / '001-曲目.mp3').rename(folder / '摇篮曲.mp3')
    (folder / '002-曲目.mp3').rename(folder / '²-晚安.mp3')
    confirm(client, '儿歌')
    result = generate(client)
    assert result['generation']['status'] == 'done'
    assert result['snapshot']['items'] == [{'number': 1, 'title': '儿歌', 'track_count': 2}]
    assert client.post('/api/collections/confirm', json={'folder': '../outside'}).status_code == 422


def test_parallel_generation_rejected_and_old_snapshot_stays_readable(setup):
    client, app, catalog, root = setup
    add_album(root, catalog, '合集', 1)
    confirm(client, '合集')
    first = generate(client)['snapshot']
    entered, release = threading.Event(), threading.Event()
    original = app.state.collections.scan

    def slow(folder):
        entered.set()
        assert release.wait(5)
        return original(folder)

    app.state.collections.scan = slow
    try:
        assert client.post('/api/collections/generate').status_code == 202
        assert entered.wait(2)
        assert client.post('/api/collections/generate').status_code == 409
        assert client.get('/api/device/v1/collections').json() == first
    finally:
        release.set()
        wait_for_generation(client)


def test_capacity_failure_keeps_previous_and_ties_are_stable(setup, monkeypatch):
    from src import device_collections
    client, app, catalog, root = setup
    add_album(root, catalog, '甲', 1)
    confirm(client, '甲')
    first = generate(client)['snapshot']
    add_album(root, catalog, '乙', 1)
    confirm(client, '乙')
    monkeypatch.setattr(device_collections, 'MAX_ITEMS', 1)
    result = generate(client)
    assert result['snapshot'] == first
    assert result['generation']['status'] == 'failed'
    monkeypatch.setattr(device_collections, 'MAX_ITEMS', 500)
    second = generate(client)['snapshot']
    repeated = generate(client)['snapshot']
    assert repeated['items'] == second['items']
    monkeypatch.setattr(device_collections, 'MAX_BYTES', 10)
    result = generate(client)
    assert result['snapshot'] == repeated
    assert result['generation']['status'] == 'failed'


def test_manual_confirmation_cannot_override_running_download(setup):
    client, app, catalog, root = setup
    add_album(root, catalog, '下载中', 1)
    app.state.collections.mark_downloading('下载中')
    assert client.post('/api/collections/confirm', json={'folder': '下载中'}).status_code == 422


def test_generation_rechecks_files_before_publication(setup):
    client, app, catalog, root = setup
    add_album(root, catalog, '合集', 1)
    confirm(client, '合集')
    first = generate(client)['snapshot']
    original = app.state.collections.scan
    mutated = False

    def changed(folder):
        nonlocal mutated
        manifest = original(folder)
        if not mutated:
            (root / '合集/001-曲目.mp3').touch()
            mutated = True
        return manifest

    app.state.collections.scan = changed
    result = generate(client)
    assert result['snapshot'] == first
    assert result['generation']['status'] == 'failed'


def test_downloaded_jobs_are_migrated_before_candidate_refresh(setup, tmp_path):
    client, app, catalog, root = setup
    add_album(root, catalog, '历史下载', 2)
    with app.state.catalog.db() as con:
        con.execute("update jobs set total_tracks=2,downloaded_tracks=2")
    restarted = create_app(data_dir=tmp_path / 'data', music_dir=root)
    first = generate(TestClient(restarted))['snapshot']
    assert first['items'][0]['track_count'] == 2
    restarted.state.catalog.refresh([])
    assert generate(TestClient(restarted))['snapshot'] == first
    with restarted.state.collections.db() as con:
        assert con.execute("select status from completions where folder='历史下载'").fetchone()[0] == 'complete'


def test_expired_generation_lease_can_be_retried(setup):
    client, app, catalog, root = setup
    add_album(root, catalog, '合集', 1)
    confirm(client, '合集')
    with app.state.collections.db() as con:
        con.execute("update generation set status='running',started=0,token='dead-worker' where id=1")
    assert client.get('/api/collections').json()['generation']['status'] == 'failed'
    assert generate(client)['generation']['status'] == 'done'


def test_generate_only_downloaded_current_kids_albums_not_all_nas_folders(setup):
    client, app, catalog, root = setup
    add_album(root, catalog, '本月儿歌', 2)
    add_album(root, catalog, 'NAS历史专辑', 1)
    add_album(root, catalog, '本月未下载', 1)
    confirm(client, '本月儿歌')
    confirm(client, 'NAS历史专辑')
    (root / 'cache').mkdir()
    (root / 'cache' / 'temporary.mp3').write_bytes(b'not audio')
    app.state.catalog.refresh([
        {'platform': '蜻蜓FM', 'album_id': '1', 'title': '本月|儿歌', 'url': '', 'age_evidence': '', 'age_confidence': ''},
        {'platform': '蜻蜓FM', 'album_id': '2', 'title': '本月未下载', 'url': '', 'age_evidence': '', 'age_confidence': ''},
    ])
    with app.state.catalog.db() as con:
        album_id = con.execute("select id from albums where album_id='1'").fetchone()[0]
        con.execute("insert into jobs(album_id,status,created_at,updated_at,total_tracks,downloaded_tracks) "
                    "values(?,'done','now','now',2,2)", (album_id,))
    result = generate(client)
    assert [(item['title'], item['track_count']) for item in result['snapshot']['items']] == [('本月|儿歌', 2)]
    assert result['generation']['skipped'] == []


def test_no_current_downloads_never_falls_back_to_all_nas(setup):
    client, app, catalog, root = setup
    add_album(root, catalog, '历史专辑', 1)
    confirm(client, '历史专辑')
    app.state.catalog.refresh([])
    result = generate(client)
    assert result['snapshot'] is None
    assert result['generation']['status'] == 'failed'
    assert result['generation']['skipped'] == []


def test_monthly_source_change_during_generation_keeps_old_snapshot(setup):
    client, app, catalog, root = setup
    add_album(root, catalog, '本月合集', 1)
    confirm(client, '本月合集')
    first = generate(client)['snapshot']
    original = app.state.collections.scan

    def refresh_during_scan(folder):
        manifest = original(folder)
        app.state.catalog.refresh([])
        return manifest

    app.state.collections.scan = refresh_during_scan
    result = generate(client)
    assert result['generation']['status'] == 'failed'
    assert '本月合集列表发生变化' in result['generation']['error']
    assert result['snapshot'] == first


def test_refresh_after_final_source_check_waits_until_publication(setup, monkeypatch):
    client, app, catalog, root = setup
    add_album(root, catalog, '本月合集', 1)
    confirm(client, '本月合集')
    original_db = app.state.collections.db
    attempted, finished = threading.Event(), threading.Event()
    workers = []

    def refresh():
        attempted.set()
        app.state.catalog.refresh([])
        finished.set()

    class Connection:
        def __init__(self, con):
            self.con = con

        def execute(self, sql, *args):
            if sql.startswith('insert into publication'):
                worker = threading.Thread(target=refresh)
                workers.append(worker)
                worker.start()
                assert attempted.wait(2)
                assert not finished.wait(.15), 'refresh raced past final source check'
            return self.con.execute(sql, *args)

    @contextmanager
    def observed_db():
        with original_db() as con:
            yield Connection(con)

    monkeypatch.setattr(app.state.collections, 'db', observed_db)
    try:
        result = generate(client)
        assert result['generation']['status'] == 'done'
        assert result['snapshot']['items'][0]['title'] == '本月合集'
    finally:
        for worker in workers:
            worker.join(3)
    assert finished.is_set()


def test_directory_and_number_lookup_work_without_ma_configuration(tmp_path, monkeypatch):
    for key in ('KIDS_MA_URL', 'KIDS_MA_TOKEN', 'KIDS_MA_MUSIC_ROOT'):
        monkeypatch.delenv(key, raising=False)

    original_urlopen = urllib.request.urlopen

    def no_network(*args, **kwargs):
        # The module-level app has its own unrelated monthly collector thread.
        if threading.current_thread().name == 'monthly-refresh':
            return original_urlopen(*args, **kwargs)
        raise AssertionError('Directory generation and name lookup must never contact MA')

    monkeypatch.setattr('urllib.request.urlopen', no_network)
    root = tmp_path / 'music'
    folder = root / '本月儿歌'
    folder.mkdir(parents=True)
    shutil.copyfile(FIXTURE, folder / '001-儿歌.mp3')
    app = create_app(data_dir=tmp_path / 'data', music_dir=root)
    app.state.catalog.refresh([{'platform': '蜻蜓FM', 'album_id': '1', 'title': '本月儿歌',
                               'url': '', 'age_evidence': '', 'age_confidence': ''}])
    with app.state.catalog.db() as con:
        con.execute("insert into jobs(album_id,status,created_at,updated_at,total_tracks,downloaded_tracks) "
                    "values(1,'done','now','now',1,1)")
    client = TestClient(app)
    result = generate(client)
    assert result['generation']['status'] == 'done'
    snapshot = result['snapshot']
    response = client.get('/api/device/v1/collections/by-number/1', params={'revision': snapshot['revision']})
    assert response.status_code == 200
    assert response.json() == {'revision': snapshot['revision'], 'number': 1,
                               'title': '本月儿歌', 'track_count': 1}


@pytest.mark.parametrize('count', [501, 1106, 3000])
def test_long_collections_are_counted_from_nas_without_ma_limit(setup, count):
    client, app, catalog, root = setup
    add_album(root, catalog, '长合集', count)
    confirm(client, '长合集')
    result = generate(client)
    assert result['generation']['status'] == 'done'
    assert result['snapshot']['items'] == [{'number': 1, 'title': '长合集', 'track_count': count}]


def test_old_ma_targets_do_not_affect_name_lookup_or_new_publications(setup):
    client, app, catalog, root = setup
    add_album(root, catalog, '儿歌', 1)
    confirm(client, '儿歌')
    first = generate(client)['snapshot']
    with app.state.collections.db() as con:
        con.execute("update publication set targets='obsolete-invalid-ma-json' where id=1")
    response = client.get('/api/device/v1/collections/by-number/1', params={'revision': first['revision']})
    assert response.status_code == 200
    assert response.json() == {'revision': first['revision'], 'number': 1, 'title': '儿歌', 'track_count': 1}
    assert generate(client)['generation']['status'] == 'done'
    with app.state.collections.db() as con:
        assert con.execute('select targets from publication where id=1').fetchone()[0] == '{}'


def test_status_and_directory_are_read_from_one_database_snapshot(setup, monkeypatch):
    import json
    import time
    client, app, catalog, root = setup
    store = app.state.collections
    original_db = store.db
    ready, committed = threading.Event(), threading.Event()
    workers = []
    snapshot = {'schema_version': 1, 'revision': 'test-revision', 'generated_at': 'now',
                'items': [{'number': 1, 'title': '儿歌', 'track_count': 1}]}
    with original_db() as con:
        con.execute("update generation set status='running',started=? where id=1", (time.time(),))

    def publish():
        with original_db() as con:
            con.execute('insert into publication values(1,?,?)', (json.dumps(snapshot), '{}'))
            con.execute("update generation set status='done' where id=1")
            ready.set()
        committed.set()

    class Connection:
        def __init__(self, con):
            self.con = con

        def execute(self, sql, *args):
            if sql.startswith('select status,error,skipped,started'):
                worker = threading.Thread(target=publish)
                workers.append(worker)
                worker.start()
                assert ready.wait(2)
                committed.wait(.15)
            return self.con.execute(sql, *args)

    @contextmanager
    def observed_db():
        with original_db() as con:
            yield Connection(con)

    monkeypatch.setattr(store, 'db', observed_db)
    result = store.read()
    for worker in workers:
        worker.join(3)
    assert committed.is_set()
    assert result['generation']['status'] != 'done' or result['snapshot'] == snapshot
