import io
import json
import urllib.error

import pytest

from src.music_assistant import MAError, MusicAssistant, relative_ma_path


def test_rpc_auth_pagination_and_actual_album_expansion(monkeypatch):
    monkeypatch.setenv('KIDS_MA_URL', 'http://ma.test:8095/')
    monkeypatch.setenv('KIDS_MA_TOKEN', 'local-test-token')
    requests = []

    def respond(request, timeout):
        payload = json.loads(request.data)
        requests.append((payload, request.get_header('Authorization')))
        if payload['command'] == 'music/tracks/library_items':
            data = [{'item_id': str(n)} for n in range(500)] if payload['args']['offset'] == 0 else []
        elif payload['command'] == 'music/albums/album_tracks':
            data = [{'item_id': '1'}]
        else:
            data = {'uri': payload['args']['uri'], 'available': True}
        return io.BytesIO(json.dumps(data).encode())

    monkeypatch.setattr('urllib.request.urlopen', respond)
    ma = MusicAssistant()
    assert len(ma.library_tracks()) == 500
    assert requests[1][0]['args']['offset'] == 500
    assert all(auth == 'Bearer local-test-token' for _, auth in requests)
    assert ma.album_tracks('library://album/12') == [{'item_id': '1'}]
    assert requests[-1][0]['args'] == {'item_id': '12', 'provider_instance_id_or_domain': 'library', 'in_library_only': False}
    assert ma.album_available('library://album/12')


def test_auth_errors_never_expose_upstream_content(monkeypatch):
    monkeypatch.setenv('KIDS_MA_URL', 'http://ma.test:8095')
    monkeypatch.setenv('KIDS_MA_TOKEN', 'secret-test-token')

    def fail(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 401, 'secret-test-token', {}, None)

    monkeypatch.setattr('urllib.request.urlopen', fail)
    with pytest.raises(MAError, match='认证失败') as error:
        MusicAssistant().library_tracks()
    assert 'secret-test-token' not in str(error.value)
    assert MusicAssistant().album_available('library://album/1') is False


@pytest.mark.parametrize('value,root,expected', [
    ('合集/001-儿歌.mp3', '/music', '合集/001-儿歌.mp3'),
    ('/mnt/audio/合集/001.mp3', '/mnt/audio', '合集/001.mp3'),
    ('file:///music/%E5%90%88%E9%9B%86/001.mp3', '/music', '合集/001.mp3'),
    ('/other/合集/001.mp3', '/music', None),
    ('../outside.mp3', '/music', None),
])
def test_ma_path_namespace(value, root, expected):
    assert relative_ma_path(value, root) == expected
