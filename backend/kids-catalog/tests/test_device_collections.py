import shutil
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.main import create_app


FIXTURE = Path(__file__).parent / 'fixtures/tone.mp3'


class FakeMA:
    def __init__(self):
        self.tracks = []
        self.fail = False

    def library_tracks(self):
        if self.fail:
            raise RuntimeError('offline')
        return self.tracks

    def album_available(self, uri):
        return not self.fail and any(t['album']['uri'] == uri for t in self.tracks)

    def album_tracks(self, uri):
        return [t for t in self.tracks if t['album']['uri'] == uri]


def add_album(root, ma, title, count):
    folder = root / title
    folder.mkdir(parents=True)
    for n in range(1, count + 1):
        name = f'{n:03d}-曲目.mp3'
        shutil.copyfile(FIXTURE, folder / name)
        ma.tracks.append({
            'item_id': f'{title}-{n}', 'track_number': n, 'disc_number': 1,
            'album': {'uri': f'library://album/{title}', 'item_id': title},
            'provider_mappings': [{'provider_domain': 'filesystem_local',
                                   'provider_instance': 'local', 'available': True,
                                   'item_id': f'{title}/{name}'}],
        })
    return folder


@pytest.fixture
def setup(tmp_path):
    ma = FakeMA()
    root = tmp_path / 'music'
    root.mkdir()
    app = create_app(data_dir=tmp_path / 'data', music_dir=root, ma_client=ma)
    return TestClient(app), app, ma, root


def generate(client):
    response = client.post('/api/collections/generate')
    assert response.status_code == 202
    import time
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        result = client.get('/api/collections').json()
        if result['generation']['status'] != 'running':
            return result
        time.sleep(.01)
    pytest.fail('generation did not finish')


def confirm(client, folder):
    assert client.post('/api/collections/confirm', json={'folder': folder}).status_code == 200


def test_counts_sort_rebuild_and_old_revision_never_plays_new_number(setup):
    client, app, ma, root = setup
    for title, count in [('长篇', 30), ('儿歌', 8), ('故事', 15)]:
        add_album(root, ma, title, count)
        confirm(client, title)
    first = generate(client)['snapshot']
    assert [(x['number'], x['track_count']) for x in first['items']] == [(1, 8), (2, 15), (3, 30)]
    assert client.get('/api/device/v1/collections').json() == first
    target = client.get('/api/device/v1/collections/by-number/1', params={'revision': first['revision']})
    assert target.json()['ma_media_uri'] == 'library://album/儿歌'
    add_album(root, ma, '短歌', 5)
    confirm(client, '短歌')
    assert client.get('/api/device/v1/collections').json() == first
    second = generate(client)['snapshot']
    assert [x['track_count'] for x in second['items']] == [5, 8, 15, 30]
    assert client.get('/api/device/v1/collections/by-number/1', params={'revision': first['revision']}).status_code == 409
    assert client.get('/api/device/v1/collections/by-number/99', params={'revision': second['revision']}).status_code == 404
    repeated = generate(client)['snapshot']
    assert repeated['items'] == second['items']


def test_skips_unconfirmed_partial_corrupt_and_ambiguous(setup):
    client, app, ma, root = setup
    add_album(root, ma, '未确认', 1)
    add_album(root, ma, '正常', 2)
    confirm(client, '正常')
    add_album(root, ma, '下载中', 3)
    confirm(client, '下载中')
    (root / '下载中/004.mp3.part').write_bytes(b'pending')
    add_album(root, ma, '损坏', 1)
    (root / '损坏/001-曲目.mp3').write_bytes(b'not audio')
    assert client.post('/api/collections/confirm', json={'folder': '损坏'}).status_code == 422
    result = generate(client)
    assert [x['title'] for x in result['snapshot']['items']] == ['正常']
    assert {x['title'] for x in result['generation']['skipped']} == {'未确认', '下载中', '损坏'}
    public = str(result['snapshot'])
    assert 'provider_mappings' not in public and '/music/' not in public


def test_failed_generation_and_removed_target_keep_snapshot(setup):
    client, app, ma, root = setup
    add_album(root, ma, '合集', 1)
    confirm(client, '合集')
    first = generate(client)['snapshot']
    ma.fail = True
    result = generate(client)
    assert result['snapshot'] == first
    assert result['generation']['status'] == 'failed'
    assert client.get('/api/device/v1/collections/by-number/1', params={'revision': first['revision']}).status_code == 503


def test_completion_survives_candidate_refresh_and_process_restart(setup, tmp_path):
    client, app, ma, root = setup
    add_album(root, ma, '旧合集', 1)
    confirm(client, '旧合集')
    app.state.catalog.refresh([])
    assert generate(client)['snapshot']['items'][0]['title'] == '旧合集'
    restarted = TestClient(create_app(data_dir=tmp_path / 'data', music_dir=root, ma_client=ma))
    assert generate(restarted)['snapshot']['items'][0]['title'] == '旧合集'
    (root / '旧合集/001-曲目.mp3').touch()
    result = generate(restarted)
    assert result['generation']['status'] == 'failed'
    assert result['snapshot']['items'][0]['title'] == '旧合集'


def test_exact_path_match_rejects_wrong_album_and_incomplete_tracks(setup):
    client, app, ma, root = setup
    add_album(root, ma, '正确', 2)
    confirm(client, '正确')
    ma.tracks.pop()
    result = generate(client)
    assert result['snapshot'] is None
    assert result['generation']['skipped'][0]['reason']
    assert client.get('/api/device/v1/collections').status_code == 404
    assert client.post('/api/collections/confirm', json={'folder': '../outside'}).status_code == 422


def test_parallel_generation_rejected_and_old_snapshot_stays_readable(setup):
    client, app, ma, root = setup
    add_album(root, ma, '合集', 1)
    confirm(client, '合集')
    first = generate(client)['snapshot']
    entered, release = threading.Event(), threading.Event()
    original = ma.library_tracks

    def slow():
        entered.set()
        assert release.wait(5)
        return original()

    ma.library_tracks = slow
    try:
        assert client.post('/api/collections/generate').status_code == 202
        assert entered.wait(2)
        assert client.post('/api/collections/generate').status_code == 409
        assert client.get('/api/device/v1/collections').json() == first
    finally:
        release.set()


def test_album_with_extra_remote_track_is_not_published(setup):
    client, app, ma, root = setup
    add_album(root, ma, '合集', 1)
    confirm(client, '合集')
    ma.tracks.append({'item_id': 'remote-extra', 'track_number': 2,
                      'album': {'uri': 'library://album/合集'},
                      'provider_mappings': [{'provider_domain': 'spotify', 'item_id': 'remote'}]})
    result = generate(client)
    assert result['snapshot'] is None
    assert result['generation']['status'] == 'failed'


def test_capacity_failure_keeps_previous_and_ties_are_stable(setup, monkeypatch):
    from src import device_collections
    client, app, ma, root = setup
    add_album(root, ma, '甲', 1)
    confirm(client, '甲')
    first = generate(client)['snapshot']
    add_album(root, ma, '乙', 1)
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
    client, app, ma, root = setup
    add_album(root, ma, '下载中', 1)
    app.state.collections.mark_downloading('下载中')
    assert client.post('/api/collections/confirm', json={'folder': '下载中'}).status_code == 422


def test_generation_rechecks_files_before_publication(setup):
    client, app, ma, root = setup
    add_album(root, ma, '合集', 1)
    confirm(client, '合集')
    first = generate(client)['snapshot']
    original = ma.album_tracks

    def changed(uri):
        (root / '合集/001-曲目.mp3').touch()
        return original(uri)

    ma.album_tracks = changed
    result = generate(client)
    assert result['snapshot'] == first
    assert result['generation']['status'] == 'failed'


def test_downloaded_jobs_are_migrated_before_candidate_refresh(setup, tmp_path):
    client, app, ma, root = setup
    add_album(root, ma, '历史下载', 2)
    with app.state.catalog.db() as con:
        con.execute("insert into albums(platform,album_id,title,url,age_evidence,age_confidence,last_seen) "
                    "values('蜻蜓FM','1','历史下载','','','','old')")
        con.execute("insert into jobs(album_id,status,created_at,updated_at,total_tracks,downloaded_tracks) "
                    "values(1,'done','old','old',2,2)")
    restarted = create_app(data_dir=tmp_path / 'data', music_dir=root, ma_client=ma)
    restarted.state.catalog.refresh([])
    assert generate(TestClient(restarted))['snapshot']['items'][0]['track_count'] == 2


def test_expired_generation_lease_can_be_retried(setup):
    client, app, ma, root = setup
    add_album(root, ma, '合集', 1)
    confirm(client, '合集')
    with app.state.collections.db() as con:
        con.execute("update generation set status='running',started=0,token='dead-worker' where id=1")
    assert client.get('/api/collections').json()['generation']['status'] == 'failed'
    assert generate(client)['generation']['status'] == 'done'


@pytest.mark.parametrize('wrong_order', [False, True])
def test_actual_playback_expansion_must_preserve_file_order(setup, wrong_order):
    client, app, ma, root = setup
    add_album(root, ma, '合集', 2)
    confirm(client, '合集')
    original = ma.album_tracks

    def expansion(uri):
        tracks = original(uri)
        if wrong_order:
            return list(reversed(tracks))
        return [{**track, 'track_number': 3 - track['track_number']} for track in tracks]

    ma.album_tracks = expansion
    result = generate(client)
    assert result['snapshot'] is None
    assert result['generation']['status'] == 'failed'
