"""Wait for MA's actual local sync, then verify exact provider file membership."""
import time
from pathlib import PurePosixPath

from src.music_assistant import MAError, relative_ma_path


def synchronize(client, expected, *, timeout=300, progress=None, cancelled=None):
    deadline = time.monotonic() + timeout

    def check():
        if cancelled and cancelled():
            raise MAError('生成任务已过期，请重新生成')
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise MAError('MA 同步或曲库核对超时，请稍后重新生成')
        return min(30, remaining)

    def rpc(command, **args):
        return client.call(command, request_timeout=check(), **args)

    def notify(status, message):
        if progress:
            progress({'status': status, 'message': message})

    providers = rpc('providers', provider_type='music')
    if not isinstance(providers, list):
        raise MAError('MA 本地文件来源响应异常')
    roots = {}
    for provider in providers:
        if provider.get('domain') != 'filesystem_local' or not provider.get('available', False):
            continue
        instance = provider.get('instance_id')
        if not isinstance(instance, str):
            continue
        config = rpc('config/providers/get', instance_id=instance)
        value = config.get('values', {}).get('path') if isinstance(config, dict) else None
        path = value.get('value') if isinstance(value, dict) else value
        if isinstance(path, str) and PurePosixPath(path).is_absolute() and (
                PurePosixPath(client.root).is_relative_to(PurePosixPath(path))):
            roots[instance] = path
    if not roots:
        raise MAError('MA 没有可用且挂载路径匹配的本地文件来源')
    notify('syncing', '设备歌单已生成，正在同步 MA 本地曲库')
    tasks = rpc('music/sync', providers=sorted(roots), media_types=['track', 'album'])
    if not isinstance(tasks, list) or not tasks:
        raise MAError('MA 未启动同步任务，请检查本地来源同步设置')
    ids = [t.get('id') for t in tasks if isinstance(t, dict)]
    if len(ids) != len(tasks) or any(not isinstance(i, str) or not i for i in ids):
        raise MAError('MA 同步任务响应异常')
    pending = set(ids)
    while pending:
        for task_id in list(pending):
            task = rpc('tasks/get', task_id=task_id)
            if not isinstance(task, dict) or task.get('id') != task_id:
                raise MAError('MA 同步任务响应异常')
            status = task.get('status')
            if status == 'success':
                pending.remove(task_id)
            elif status not in ('pending', 'running'):
                raise MAError('MA 同步未成功完成，请检查 MA 后重试')
        if pending:
            time.sleep(min(2, check()))
    notify('verifying', 'MA 扫描完成，正在核对所选专辑的曲目')
    check()
    tracks = client.library_tracks(deadline=deadline)

    def paths(track):
        found = set()
        for mapping in track.get('provider_mappings', []):
            instance = mapping.get('provider_instance')
            if instance not in roots or not mapping.get('available', True):
                continue
            rel = relative_ma_path(mapping.get('item_id', ''), roots[instance])
            if rel:
                normalized = relative_ma_path(str(PurePosixPath(roots[instance]) / rel), client.root)
                if normalized:
                    found.add(normalized)
        return found

    indexed = {}
    for track in tracks:
        for path in paths(track):
            indexed.setdefault(path, []).append(track)
    for folder, collection in expected.items():
        check()
        required = {folder + '/' + name for name in collection['files']}
        album_uris = set()
        for path in required:
            matches = indexed.get(path, [])
            good = [t.get('album') or {} for t in matches if t.get('is_playable', True)]
            good = [a for a in good if a.get('name') == collection['title'] and a.get('uri')]
            if len(good) != 1:
                raise MAError('MA 尚未将所选文件归入目标专辑，请稍后重新生成')
            album_uris.add(good[0]['uri'])
        if len(album_uris) != 1:
            raise MAError('MA 专辑分组不一致，请检查合集标签')
        album_tracks = client.album_tracks(next(iter(album_uris)), deadline=deadline)
        actual = set().union(*(paths(t) for t in album_tracks)) if album_tracks else set()
        if (actual != required or len(album_tracks) != len(required)
                or any(len(paths(t) & required) != 1 for t in album_tracks)):
            raise MAError('MA 专辑曲目与当前合集不一致，请稍后重新生成')
    check()
    return {'status': 'ready', 'message': 'MA 已就绪：所选专辑和曲目已核对'}
