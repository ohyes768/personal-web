"""A single durable device directory, independent of disposable candidate rows."""
import hashlib
import json
import logging
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from src.audio_tags import open_audio, safe_child
from src.collection_metadata import MetadataError, prepare_collection, recover_manifest
from src.music_assistant import MAError, MusicAssistant

logger = logging.getLogger(__name__)
MAX_ITEMS = 500
MAX_BYTES = 128 * 1024
LEASE_SECONDS = 15 * 60


class CollectionError(ValueError):
    pass


class GenerationChanged(RuntimeError):
    pass


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def file_order(row):
    """Retain old numbered manifests while accepting ordinary audio filenames."""
    prefix, separator, _ = row[0].partition('-')
    return (0, int(prefix), row[0]) if separator and prefix.isdecimal() else (1, 0, row[0])


class DeviceCollections:
    def __init__(self, data_dir, music_dir, candidate_source):
        self.path = Path(data_dir) / 'device_collections.sqlite3'
        self.root = Path(music_dir)
        self.candidate_source = candidate_source
        self.ma = MusicAssistant()
        with self.db() as con:
            con.executescript('''
                create table if not exists completions (
                    folder text primary key, manifest text, status text not null);
                -- targets is retained for compatibility with existing databases;
                -- new publications store an empty object and never read MA targets.
                create table if not exists publication (
                    id integer primary key check(id=1), snapshot text not null, targets text not null);
                create table if not exists generation (
                    id integer primary key check(id=1), token text, started real,
                    status text not null, error text, skipped text not null default '[]');
                insert or ignore into generation(id,status) values(1,'idle');
            ''')
            columns = {r[1] for r in con.execute('pragma table_info(generation)')}
            if 'integration' not in columns:
                con.execute("alter table generation add column integration text not null default '{}'")

    @contextmanager
    def db(self):
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    def scan(self, folder):
        if not folder or Path(folder).name != folder or '/' in folder or '\\' in folder:
            raise CollectionError('合集必须是音频根目录下的直接子目录')
        directory = safe_child(self.root, folder)
        if not directory.is_dir():
            raise CollectionError('合集目录不存在')
        files = []
        for path in sorted(directory.iterdir()):
            if path.name.endswith(('.part', '.tmp')):
                raise CollectionError('存在未完成的临时下载')
            if path.is_symlink() or path.is_junction():
                raise CollectionError('合集包含链接，已跳过')
            if path.is_dir():
                raise CollectionError('合集包含子目录，需整理后再生成')
            if path.suffix.lower() not in ('.mp3', '.m4a'):
                continue
            try:
                before = path.stat()
                audio = open_audio(path)
                if audio.info.length <= 0 or before.st_size <= 0:
                    raise ValueError('empty')
                after = path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError('changed')
            except Exception as exc:
                # Parser exceptions vary by codec; never leak local paths to clients.
                raise CollectionError('音频损坏、不可读取或正在变化') from exc
            files.append([path.name, after.st_size, after.st_mtime_ns])
        if not files:
            raise CollectionError('没有有效音频文件')
        return sorted(files, key=file_order)

    def record_legacy(self, folder, expected):
        try:
            directory = safe_child(self.root, folder)
            files = [[p.name, p.stat().st_size, p.stat().st_mtime_ns]
                     for p in directory.iterdir() if p.suffix.lower() in ('.mp3', '.m4a')]
            if len(files) != expected:
                return
            files.sort(key=file_order)
            with self.db() as con:
                con.execute("insert or ignore into completions values(?,?,'complete')", (folder, encoded(files)))
        except (OSError, ValueError):
            return

    def mark_downloading(self, folder):
        with self.db() as con:
            con.execute("insert into completions values(?,null,'downloading') on conflict(folder) "
                        "do update set status='downloading',manifest=null", (folder,))

    def mark_failed(self, folder):
        with self.db() as con:
            con.execute("update completions set status='incomplete' where folder=?", (folder,))

    def confirm(self, folder, expected=None, only_missing=False):
        manifest = self.scan(folder)
        if expected is not None and len(manifest) != expected:
            raise CollectionError('实际文件数量与下载完成记录不一致')
        with self.db() as con:
            if only_missing:
                con.execute("insert or ignore into completions values(?,?,'complete')", (folder, encoded(manifest)))
            else:
                # Never let manual confirmation override a running download.
                con.execute('begin immediate')
                row = con.execute('select status from completions where folder=?', (folder,)).fetchone()
                if row and row['status'] == 'downloading' and expected is None:
                    raise CollectionError('合集仍在下载，请等待完成')
                con.execute("insert into completions values(?,?,'complete') on conflict(folder) "
                            "do update set manifest=excluded.manifest,status='complete'", (folder, encoded(manifest)))
        return len(manifest)

    def read(self):
        with self.db() as con:
            con.execute('begin')
            row = con.execute('select snapshot from publication where id=1').fetchone()
            job = dict(con.execute('select status,error,skipped,started,integration from generation where id=1').fetchone())
        job['skipped'] = json.loads(job['skipped'])
        job['integration'] = json.loads(job['integration'])
        if job['status'] == 'running' and time.time() - job['started'] > LEASE_SECONDS:
            job.update(status='failed', error='上次生成已中断或超时，可以重新生成')
        return {'snapshot': json.loads(row['snapshot']) if row else None, 'generation': job}

    def completion_status(self):
        """完成台账：{folder: (status, manifest 记录的曲目数)}，manifest 未写时曲目数为 None。"""
        with self.db() as con:
            return {row['folder']: (row['status'],
                    len(json.loads(row['manifest'])) if row['manifest'] else None)
                    for row in con.execute('select folder,status,manifest from completions')}

    def start(self, prepare=None, selected_folders=None):
        token = uuid.uuid4().hex
        with self.db() as con:
            con.execute('begin immediate')
            row = con.execute('select * from generation where id=1').fetchone()
            if row['status'] == 'running' and time.time() - row['started'] < LEASE_SECONDS:
                return False
            con.execute("update generation set token=?,started=?,status='running',error=null,skipped='[]',integration='{}' where id=1",
                        (token, time.time()))
        threading.Thread(target=self._generate, args=(token, prepare, selected_folders),
                         daemon=True, name='device-directory').start()
        return True

    def is_current(self, token):
        with self.db() as con:
            row = con.execute('select token,status from generation where id=1').fetchone()
        return row['token'] == token and row['status'] == 'running'

    def update_integration(self, token, state):
        with self.db() as con:
            return bool(con.execute("update generation set integration=? where token=? and status='running'",
                                    (encoded(state), token)).rowcount)

    def _prepare_metadata(self, token, source, observed, state):
        folder = source['folder']
        audit_dir = self.path.parent / 'collection-tag-audit'
        # Catalog first: block queue/delete/refresh for this collection while
        # acknowledging only our own writes. Network I/O never happens here.
        with self.candidate_source() as candidates:
            if source not in candidates:
                raise GenerationChanged('生成期间本月合集列表发生变化，请重新生成')
            with self.db() as con:
                con.execute('begin immediate')
                job = con.execute('select token,status from generation where id=1').fetchone()
                row = con.execute('select * from completions where folder=?', (folder,)).fetchone()
                if job['token'] != token or job['status'] != 'running':
                    raise CollectionError('生成任务已过期')
                if not row or row['status'] != 'complete':
                    raise CollectionError('生成期间下载状态发生变化，请重新生成')
                old = json.loads(row['manifest'])
                try:
                    known = recover_manifest(self.root, folder, old, observed, audit_dir)
                except MetadataError as exc:
                    raise CollectionError(str(exc)) from None
                if known != old:
                    con.execute('update completions set manifest=? where folder=?', (encoded(known), folder))
            last = [list(r) for r in known]
            active = [None]

            @contextmanager
            def guard():
                with self.db() as con:
                    con.execute('begin immediate')
                    job = con.execute('select token,status from generation where id=1').fetchone()
                    row = con.execute('select * from completions where folder=?', (folder,)).fetchone()
                    if job['token'] != token or job['status'] != 'running':
                        raise CollectionError('生成任务已过期')
                    if not row or row['status'] != 'complete' or row['manifest'] != encoded(last):
                        raise CollectionError('生成期间下载状态发生变化，请重新生成')
                    active[0] = con
                    try:
                        yield
                    finally:
                        active[0] = None

            def checkpoint(updated):
                active[0].execute('update completions set manifest=? where folder=?', (encoded(updated), folder))
                last[:] = updated
                state['tags_updated'] += 1
                active[0].execute('update generation set integration=? where token=?', (encoded(state), token))

            try:
                prepared, _ = prepare_collection(self.root, folder, source['title'], last,
                                                  audit_dir, checkpoint, guard=guard)
                last[:] = prepared
            except MetadataError as exc:
                state['metadata_errors'].append({'title': source['title'], 'message': str(exc)})
            if self.scan(folder) != last:
                raise CollectionError('生成期间音频发生变化，请重新生成')
        return last

    def _sync_ma(self, token, sources, selected, manifests, state):
        state['phase'] = 'syncing'
        if state['metadata_errors']:
            state['ma'] = {'status': 'failed', 'message': '部分合集标签未就绪，请查看音频信息提示后重新生成'}
        elif not self.ma.configured:
            state['ma'] = {'status': 'not_configured', 'message': '设备歌单已生成；请配置 MA 地址和 API token 后重新生成'}
        else:
            def progress(value):
                state['ma'] = value
                if not self.update_integration(token, state):
                    raise MAError('生成任务已过期')
            try:
                expected = {source['folder']: {'title': source['title'],
                            'files': [r[0] for r in manifests[source['folder']]]}
                            for source in sources if source['folder'] in manifests}
                state['ma'] = self.ma.sync_collections(expected, progress=progress,
                                                       cancelled=lambda: not self.is_current(token))
                # A library scan must not bless a collection deleted or queued
                # for download while MA was doing its own background work.
                with self.candidate_source() as current:
                    current_sources = current if selected is None else [x for x in current if x['folder'] in selected]
                    if current_sources != sources:
                        raise MAError('生成后合集或下载状态发生变化，请重新生成')
                    with self.db() as con:
                        con.execute('begin immediate')
                        for folder, manifest in manifests.items():
                            row = con.execute('select * from completions where folder=?', (folder,)).fetchone()
                            if not row or row['status'] != 'complete' or row['manifest'] != encoded(manifest):
                                raise MAError('生成后文件或下载状态发生变化，请重新生成')
                            if self.scan(folder) != manifest:
                                raise MAError('生成后音频发生变化，请重新生成')
                        state['phase'] = 'finished'
                        con.execute("update generation set status='done',integration=? where token=? and status='running'",
                                    (encoded(state), token))
                        return
            except MAError as exc:
                state['ma'] = {'status': 'failed', 'message': str(exc)}
            except Exception:
                logger.warning('MA integration failed without exposing upstream content')
                state['ma'] = {'status': 'failed', 'message': 'MA 同步或文件核对失败，请稍后重新生成'}
        state['phase'] = 'finished'
        with self.db() as con:
            con.execute("update generation set status='done',integration=? where token=? and status='running'",
                        (encoded(state), token))

    def _generate(self, token, prepare, selected_folders=None):
        skipped = []
        state = {'phase': 'tagging', 'tags_updated': 0, 'metadata_errors': [], 'ma': {'status': 'pending'}}
        if not self.update_integration(token, state):
            return
        # None = 全部候选；给定时只保留选中的合集，未选者不进歌单也不进 skipped。
        selected = set(selected_folders) if selected_folders is not None else None
        try:
            if prepare:
                prepare()
            if not self.root.is_dir():
                raise CollectionError('NAS 音频根目录不可用')
            with self.candidate_source() as candidates:
                sources = candidates if selected is None else [
                    item for item in candidates if item['folder'] in selected]
                if not sources:
                    if selected is not None:
                        raise CollectionError('选中的合集已不在本月候选中，请重新生成；已保留原歌单')
                    raise CollectionError('本月暂无已下载完成的合集，请先下载；已保留原歌单')
            items, manifests = [], {}
            with self.db() as con:
                completed = {r['folder']: dict(r) for r in con.execute('select * from completions')}
            for source in sources:
                folder, title = source['folder'], source['title']
                reason_code = 'invalid'
                try:
                    manifest = self.scan(folder)
                    record = completed.get(folder)
                    if not record or record['status'] != 'complete':
                        reason_code = 'unconfirmed' if not record else 'incomplete'
                        raise CollectionError('未确认下载完整' if not record else '下载未完成，请等待完成后重试')
                    if len(title.encode('utf-8')) > 256:
                        raise CollectionError('合集名称超过设备长度限制')
                    manifest = self._prepare_metadata(token, source, manifest, state)
                    if not self.update_integration(token, state):
                        return
                    stable_id = hashlib.sha256(folder.encode()).hexdigest()
                    items.append({'title': title, 'track_count': len(manifest), '_id': stable_id})
                    manifests[folder] = manifest
                except (CollectionError, ValueError, OSError) as error:
                    # Human-readable reasons are controlled local messages only.
                    reason = str(error) if isinstance(error, CollectionError) else '合集无法读取'
                    skipped.append({'title': title, 'folder': folder, 'reason': reason, 'code': reason_code})
            if not items:
                raise CollectionError('没有可发布的合集，请查看跳过原因；已保留原歌单')
            if len(items) > MAX_ITEMS:
                raise CollectionError('合集超过 500 项，未发布新歌单')
            items.sort(key=lambda item: (item['track_count'], item['_id']))
            for number, item in enumerate(items, 1):
                item.pop('_id')
                item['number'] = number
            snapshot = {'schema_version': 1, 'revision': token,
                        'generated_at': datetime.now(timezone.utc).isoformat(), 'items': items}
            if len(encoded(snapshot).encode()) > MAX_BYTES:
                raise CollectionError('歌单超过设备容量，未发布新歌单')
            for folder, manifest in manifests.items():
                if self.scan(folder) != manifest:
                    raise CollectionError('生成期间音频发生变化，请重新生成')
            # Lock order matches download queueing: catalog first, device DB second.
            # Hold the source guard through commit so refresh cannot race publication.
            with self.candidate_source() as current_candidates:
                # 只比较选中的合集：未选合集的增减与本次发布无关。
                current_sources = current_candidates if selected is None else [
                    item for item in current_candidates if item['folder'] in selected]
                if current_sources != sources:
                    raise CollectionError('生成期间本月合集列表发生变化，请重新生成')
                with self.db() as con:
                    con.execute('begin immediate')
                    current = con.execute('select token from generation where id=1').fetchone()
                    if current['token'] != token:
                        return
                    for folder, manifest in manifests.items():
                        row = con.execute('select * from completions where folder=?', (folder,)).fetchone()
                        if not row or row['status'] != 'complete' or row['manifest'] != encoded(manifest):
                            raise CollectionError('生成期间下载状态发生变化，请重新生成')
                    con.execute('insert into publication values(1,?,?) on conflict(id) do update '
                                'set snapshot=excluded.snapshot,targets=excluded.targets', (encoded(snapshot), '{}'))
                    state['phase'] = 'syncing'
                    state['device_published'] = True
                    con.execute("update generation set skipped=?,integration=? where id=1", (encoded(skipped), encoded(state)))
            self._sync_ma(token, sources, selected, manifests, state)
        except Exception as exc:
            message = str(exc) if isinstance(exc, (CollectionError, GenerationChanged)) else '生成失败，请检查 NAS 音频目录'
            logger.warning('Device directory generation failed (%s)', type(exc).__name__)
            with self.db() as con:
                con.execute("update generation set status='failed',error=?,skipped=? where token=?",
                            (message, encoded(skipped), token))

    def resolve(self, number, revision):
        with self.db() as con:
            row = con.execute('select snapshot from publication where id=1').fetchone()
        if not row:
            return 404, {'code': 'directory_missing', 'message': '尚未生成歌单'}
        snapshot = json.loads(row['snapshot'])
        if revision != snapshot['revision']:
            return 409, {'code': 'revision_expired', 'message': '歌单已更新，请刷新后重新选择'}
        item = next((item for item in snapshot['items'] if item['number'] == number), None)
        if not item:
            return 404, {'code': 'number_missing', 'message': '编号不存在'}
        return 200, {**item, 'revision': revision}
