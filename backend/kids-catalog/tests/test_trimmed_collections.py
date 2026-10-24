from src.main import Catalog
from test_device_collections import setup, add_album, confirm, generate_selected


def album_id(catalog, title):
    with catalog.db() as con:
        return con.execute('select id from albums where title=?', (title,)).fetchone()['id']


def delete(client, pk, name):
    response = client.request('DELETE', f'/api/albums/{pk}/tracks', json={'file': name})
    assert response.status_code == 200
    return response.json()


def test_eighteen_trimmed_to_one_can_be_confirmed_and_generated(setup):
    client, app, catalog, root = setup
    title = '听，小蜗牛艾玛'
    folder = add_album(root, catalog, title, 18)
    confirm(client, title)
    pk = album_id(catalog, title)
    for number in range(1, 18):
        delete(client, pk, f'{number:03d}-曲目.mp3')
    candidates = client.get('/api/collections').json()['candidates']
    assert candidates == [{'folder': title, 'title': title, 'confirmed': False, 'track_count': 1}]
    before = generate_selected(client, [title])
    assert before['snapshot'] is None
    assert before['generation']['skipped'][0]['code'] == 'incomplete'
    confirm(client, title)
    result = generate_selected(client, [title])
    assert result['snapshot']['items'] == [{'number': 1, 'title': title, 'track_count': 1}]
    assert result['generation']['integration']['metadata_errors'] == []
    again = generate_selected(client, [title])
    assert again['generation']['integration']['tags_updated'] == 0
    assert len(list(folder.iterdir())) == 1
    delete(client, pk, '018-曲目.mp3')
    assert client.get('/api/collections').json()['candidates'] == []


def test_failed_partial_is_not_a_candidate_even_if_manually_confirmed(setup):
    client, app, catalog, root = setup
    add_album(root, catalog, '下载失败', 1)
    confirm(client, '下载失败')
    with catalog.db() as con:
        con.execute("update jobs set status='partial',downloaded_tracks=1,reason='完成 1，失败 2'")
    assert client.get('/api/collections').json()['candidates'] == []


def test_legacy_user_delete_migration_is_specific_and_does_not_confirm_files(setup):
    client, app, catalog, root = setup
    add_album(root, catalog, '旧删曲', 1)
    add_album(root, catalog, '旧失败', 1)
    with catalog.db() as con:
        con.execute('alter table jobs drop column user_trimmed')
        con.execute("update jobs set status='partial',downloaded_tracks=1,reason='用户删除曲目，剩余 1 首' where album_id=?", (album_id(catalog, '旧删曲'),))
        con.execute("update jobs set status='partial',downloaded_tracks=1,reason='完成 1，失败 2' where album_id=?", (album_id(catalog, '旧失败'),))
    Catalog(catalog.path.parent)
    Catalog(catalog.path.parent)  # migration is idempotent
    rows = client.get('/api/collections').json()['candidates']
    assert rows == [{'folder': '旧删曲', 'title': '旧删曲', 'confirmed': False, 'track_count': 1}]


def test_requeue_clears_trimmed_eligibility(setup, monkeypatch):
    client, app, catalog, root = setup
    add_album(root, catalog, '精选', 2)
    pk = album_id(catalog, '精选')
    delete(client, pk, '001-曲目.mp3')
    assert client.get('/api/collections').json()['candidates']
    with monkeypatch.context() as patch:
        patch.setattr('src.main.threading.Thread.start', lambda _: None)
        assert catalog.queue(pk)['status'] == 'queued'
    with catalog.db() as con:
        assert con.execute('select user_trimmed from jobs where album_id=?', (pk,)).fetchone()[0] == 0
    assert client.get('/api/collections').json()['candidates'] == []


def test_external_file_change_after_confirmation_is_still_rejected(setup):
    client, app, catalog, root = setup
    folder = add_album(root, catalog, '精选', 2)
    pk = album_id(catalog, '精选')
    delete(client, pk, '001-曲目.mp3')
    confirm(client, '精选')
    path = folder / '002-曲目.mp3'
    path.write_bytes(path.read_bytes() + b'external change')
    result = generate_selected(client, ['精选'])
    assert result['snapshot'] is None
    assert result['generation']['skipped']


def test_deletion_invalidates_completion_inside_catalog_write_guard(setup, monkeypatch):
    import sqlite3
    import pytest
    client, app, catalog, root = setup
    add_album(root, catalog, '精选', 2)
    confirm(client, '精选')
    pk = album_id(catalog, '精选')
    original = app.state.collections.mark_failed
    checked = []
    def observe(folder):
        with sqlite3.connect(catalog.path, timeout=0) as other:
            with pytest.raises(sqlite3.OperationalError, match='locked'):
                other.execute('begin immediate')
        checked.append(True)
        original(folder)
    monkeypatch.setattr(app.state.collections, 'mark_failed', observe)
    delete(client, pk, '001-曲目.mp3')
    assert checked == [True]


def test_confirmation_holds_catalog_guard_while_scanning(setup, monkeypatch):
    import sqlite3
    import pytest
    client, app, catalog, root = setup
    add_album(root, catalog, '精选', 1)
    original = app.state.collections.confirm
    checked = []
    def observe(folder, **kwargs):
        with sqlite3.connect(catalog.path, timeout=0) as other:
            with pytest.raises(sqlite3.OperationalError, match='locked'):
                other.execute('begin immediate')
        checked.append(True)
        return original(folder, **kwargs)
    monkeypatch.setattr(app.state.collections, 'confirm', observe)
    confirm(client, '精选')
    assert checked == [True]


def test_interrupted_legacy_migration_rolls_back_column_and_can_retry(setup, monkeypatch):
    import sqlite3
    from contextlib import contextmanager
    import pytest
    client, app, catalog, root = setup
    add_album(root, catalog, '旧删曲', 1)
    with catalog.db() as con:
        con.execute('alter table jobs drop column user_trimmed')
        con.execute("update jobs set status='partial',downloaded_tracks=1,reason='用户删除曲目，剩余 1 首'")
    original = Catalog.db
    @contextmanager
    def interrupted(self):
        with original(self) as con:
            def deny_backfill(action, table, column, *unused):
                return sqlite3.SQLITE_DENY if (action == sqlite3.SQLITE_UPDATE and table == 'jobs'
                                              and column == 'user_trimmed') else sqlite3.SQLITE_OK
            con.set_authorizer(deny_backfill)
            yield con
    with monkeypatch.context() as patch:
        patch.setattr(Catalog, 'db', interrupted)
        with pytest.raises(sqlite3.DatabaseError, match='not authorized'):
            Catalog(catalog.path.parent)
    with catalog.db() as con:
        assert 'user_trimmed' not in {r['name'] for r in con.execute('pragma table_info(jobs)')}
    Catalog(catalog.path.parent)
    with catalog.db() as con:
        assert con.execute('select user_trimmed from jobs').fetchone()[0] == 1
