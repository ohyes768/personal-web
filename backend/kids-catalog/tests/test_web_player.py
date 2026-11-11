"""浏览器播放数据源接口：GET /api/collections/{folder}/tracks。"""
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.main import create_app
from tests.test_device_collections import FIXTURE


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / 'music'
    root.mkdir()
    app = create_app(data_dir=tmp_path / 'data', music_dir=root)
    return TestClient(app), app.state.catalog, root


def make_album(root, catalog, title, count):
    """已下载合集：目录 + N 首编号曲目 + done 台账（与设备候选口径一致）。"""
    folder = root / title
    folder.mkdir(parents=True)
    for number in range(1, count + 1):
        shutil.copyfile(FIXTURE, folder / f'{number:03d}-曲目{number}.mp3')
    with catalog.db() as con:
        con.execute("insert into albums(platform,album_id,title,url,age_evidence,age_confidence,last_seen) "
                    "values('蜻蜓FM',?,?, '', '', '', 'current')", (title, title))
        album_id = con.execute('select last_insert_rowid()').fetchone()[0]
        con.execute("insert into jobs(album_id,status,created_at,updated_at) values(?,'done','now','now')",
                    (album_id,))
    return folder


def test_tracks_sorted_with_titles(setup):
    client, catalog, root = setup
    make_album(root, catalog, '儿歌', 3)
    body = client.get('/api/collections/%E5%84%BF%E6%AD%8C/tracks').json()
    assert [row['file'] for row in body['tracks']] == ['001-曲目1.mp3', '002-曲目2.mp3', '003-曲目3.mp3']
    assert [row['title'] for row in body['tracks']] == ['曲目1', '曲目2', '曲目3']


def test_tracks_filter_non_audio_and_keep_order(setup):
    client, catalog, root = setup
    folder = make_album(root, catalog, '故事', 2)
    (folder / '封面.txt').write_text('x', encoding='utf-8')
    (folder / 'notes.m4a').write_bytes(b'\x00')
    body = client.get('/api/collections/故事/tracks').json()
    assert [row['file'] for row in body['tracks']] == ['001-曲目1.mp3', '002-曲目2.mp3', 'notes.m4a']


def test_tracks_unknown_folder_404(setup):
    client, catalog, root = setup
    make_album(root, catalog, '儿歌', 1)
    response = client.get('/api/collections/不存在/tracks')
    assert response.status_code == 404
    assert response.json()['detail']['code'] == 'unknown_folder'


@pytest.mark.parametrize('folder', ['../outside', 'a/b', '.'])
def test_tracks_rejects_traversal(setup, folder):
    client, catalog, root = setup
    assert client.get(f'/api/collections/{folder}/tracks').status_code == 404


def test_collections_expose_published_folders(setup):
    """已发布合集带播放目录：上月发布、本月不在候选里的合集也能播。"""
    client, catalog, root = setup
    snapshot = {'schema_version': 1, 'revision': 'rev-1', 'generated_at': '2026-11-07T00:00:00',
                'items': [{'number': 1, 'title': '儿歌', 'track_count': 3}]}
    with client.app.state.collections.db() as con:
        con.execute('insert or replace into publication values(1,?,?)', (json.dumps(snapshot), '{}'))
    body = client.get('/api/collections').json()
    assert body['published'] == [{'number': 1, 'title': '儿歌', 'folder': '儿歌'}]
    # 目录名就是播放入口，tracks 接口能直接用它取到曲目
    tracks = client.get('/api/collections/%E5%84%BF%E6%AD%8C/tracks')
    assert tracks.status_code == 404  # 目录还没建好时给出可读错误，不白屏
    assert tracks.json()['detail']['code'] == 'unknown_folder'
