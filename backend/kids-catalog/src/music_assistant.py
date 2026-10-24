"""MA JSON-RPC adapter; never return upstream errors or credentials."""
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import PurePosixPath
from urllib.parse import unquote, urlparse


class MAError(RuntimeError):
    pass


class MusicAssistant:
    def __init__(self):
        self.url = os.getenv('KIDS_MA_URL', '').rstrip('/')
        self.token = os.getenv('KIDS_MA_TOKEN', '')
        self.root = os.getenv('KIDS_MA_MUSIC_ROOT', '/music').rstrip('/')

    @property
    def configured(self):
        return bool(self.url and self.token)

    def sync_collections(self, expected, **kwargs):
        from src.ma_sync import synchronize
        return synchronize(self, expected, **kwargs)

    def call(self, command, *, request_timeout=30, **args):
        if not self.url or not self.token:
            raise MAError('请配置 MA 连接地址和 API token')
        request = urllib.request.Request(
            self.url + '/api',
            data=json.dumps({'message_id': 'kids-catalog', 'command': command, 'args': args}).encode(),
            headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {self.token}'},
        )
        try:
            with urllib.request.urlopen(request, timeout=max(.01, min(30, request_timeout))) as response:
                data = json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise MAError('MA 认证失败，请检查 API token') from None
            raise MAError('MA 查询失败，请检查连接及服务状态') from None
        except (OSError, ValueError):
            raise MAError('MA 连接失败或返回格式异常') from None
        if isinstance(data, dict) and ('error' in data or 'error_code' in data):
            raise MAError('MA 拒绝查询，请检查权限和 API 版本')
        return data.get('result', data) if isinstance(data, dict) else data

    def library_tracks(self, *, deadline=None):
        tracks = []
        for offset in range(0, 100000, 500):
            remaining = deadline - time.monotonic() if deadline is not None else 30
            if remaining <= 0:
                raise MAError('MA 曲库核对超时，请重新生成')
            page = self.call('music/tracks/library_items', limit=500, offset=offset, request_timeout=remaining)
            if not isinstance(page, list):
                raise MAError('MA 曲库响应格式异常')
            tracks.extend(page)
            if len(page) < 500:
                return tracks
        raise MAError('MA 曲库超过扫描上限')

    def album_available(self, uri):
        try:
            item = self.call('music/item_by_uri', uri=uri)
            return isinstance(item, dict) and item.get('available', True) and item.get('uri') == uri
        except MAError:
            return False

    def album_tracks(self, uri, *, deadline=None):
        remaining = deadline - time.monotonic() if deadline is not None else 30
        if remaining <= 0:
            raise MAError('MA 曲库核对超时，请重新生成')
        tracks = self.call('music/albums/album_tracks', item_id=uri.rsplit('/', 1)[-1],
                           provider_instance_id_or_domain='library', in_library_only=False, request_timeout=remaining)
        if not isinstance(tracks, list):
            raise MAError('MA 专辑曲目响应格式异常')
        return tracks


def relative_ma_path(value, root='/music'):
    """Provider item ids are relative paths or paths in MA's music namespace."""
    value = unquote(str(value)).replace('\\', '/')
    if value.startswith('file://'):
        value = urlparse(value).path
    path = PurePosixPath(value)
    if path.is_absolute():
        try:
            path = path.relative_to(PurePosixPath(root))
        except ValueError:
            return None
    if '..' in path.parts or not path.parts:
        return None
    return path.as_posix()
