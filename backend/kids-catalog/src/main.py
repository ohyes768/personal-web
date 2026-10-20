import logging
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from src.collector import collect_latest
from src.downloader import AlbumOfflineError, Downloader, sanitize_filename
from src.device_collections import CollectionError, DeviceCollections
from src.music_assistant import MusicAssistant

logger = logging.getLogger(__name__)
MONTHLY_SECONDS = 30 * 24 * 3600
PAID_SKIP_REASON = "付费专辑不下载（整张跳过）"



class Catalog:
    def __init__(self, data_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True)
        self.path = data_dir / "kids_catalog.sqlite3"
        with self.db() as con:
            con.executescript('''
              create table if not exists albums (
                id integer primary key, platform text not null, album_id text not null,
                title text not null, url text not null, age_evidence text not null,
                age_confidence text not null, sale_type integer, track_count integer,
                last_seen text not null,
                unique(platform, album_id));
              create table if not exists jobs (
                id integer primary key, album_id integer not null unique, status text not null,
                reason text, created_at text not null, updated_at text not null,
                total_tracks integer default 0, downloaded_tracks integer default 0,
                size_bytes integer,
                foreign key(album_id) references albums(id));
            ''')
            # Databases created before sale_type existed gain the column in place.
            columns = {row['name'] for row in con.execute('pragma table_info(albums)')}
            for column in ('sale_type', 'track_count'):
                if column not in columns:
                    con.execute(f'alter table albums add column {column} integer')
            job_columns = {row['name'] for row in con.execute('pragma table_info(jobs)')}
            for column in ('total_tracks', 'downloaded_tracks'):
                if column not in job_columns:
                    con.execute(f'alter table jobs add column {column} integer default 0')
            if 'size_bytes' not in job_columns:
                con.execute('alter table jobs add column size_bytes integer')

    @contextmanager
    def db(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()

    def refresh(self, albums: list[dict[str, Any]]):
        now = datetime.now().isoformat()
        with self.db() as con:
            for row in albums:
                con.execute('''insert into albums(platform,album_id,title,url,age_evidence,age_confidence,sale_type,track_count,last_seen)
                  values(?,?,?,?,?,?,?,?,?) on conflict(platform,album_id) do update set
                  title=excluded.title,url=excluded.url,age_evidence=excluded.age_evidence,
                  age_confidence=excluded.age_confidence,sale_type=excluded.sale_type,
                  track_count=excluded.track_count,last_seen=excluded.last_seen''',
                  (row['platform'], str(row['album_id']), row['title'], row['url'],
                   row['age_evidence'], row['age_confidence'], row.get('sale_type'),
                   row.get('track_count'), now))
            # 本期榜单之外的历史专辑（旧付费、被淘汰的）连同下载记录一并清出目录。
            con.execute('delete from jobs where album_id in (select id from albums where last_seen != ?)', (now,))
            con.execute('delete from albums where last_seen != ?', (now,))
        return len(albums)

    def list(self):
        with self.db() as con:
            rows = [dict(row) for row in con.execute('''select a.*, coalesce(j.status,'not_downloaded') download_status,
              j.reason, coalesce(j.total_tracks,0) total_tracks, coalesce(j.downloaded_tracks,0) downloaded_tracks,
              j.size_bytes
              from albums a left join jobs j on j.album_id=a.id order by a.platform,a.title''')]
        self._backfill_sizes(rows)
        return rows

    @contextmanager
    def device_candidates(self):
        """Hold catalog mutations while checking/publishing the current done list."""
        with self.db() as con:
            con.execute('begin immediate')
            rows = con.execute("select a.platform,a.album_id,a.title from albums a join jobs j "
                               "on a.id=j.album_id where j.status='done' order by a.platform,a.album_id").fetchall()
            candidates = [{'folder': sanitize_filename(row['title']), 'title': row['title'],
                           'source_id': f"{row['platform']}:{row['album_id']}"} for row in rows]
            if len({item['folder'] for item in candidates}) != len(candidates):
                raise CollectionError('本月多个合集对应同一下载目录，请核对合集名称')
            yield candidates

    def _backfill_sizes(self, rows: "list[dict[str, Any]]"):
        """旧版本下载完的任务没有 size_bytes：扫一次目录补上并持久化，避免每次列表重扫。

        目录已被清理的记 0（算过、无文件），前端对 0 不显示。
        """
        for row in rows:
            if row['download_status'] not in ('done', 'partial') or row['size_bytes'] is not None:
                continue
            size = self.downloader.album_size_bytes(row['platform'], row['title'])
            with self.db() as con:
                con.execute('update jobs set size_bytes=? where album_id=?', (size or 0, row['id']))
            row['size_bytes'] = size or 0

    def queue(self, album_pk: int):
        """把专辑加入下载队列；付费专辑整张跳过（策略 A），免费专辑后台线程下载。"""
        now = datetime.now().isoformat()
        with self.db() as con:
            album = con.execute(
                'select id,platform,album_id,title,sale_type from albums where id=?', (album_pk,)).fetchone()
            if not album:
                raise KeyError(album_pk)
            job = con.execute('select id,status,reason from jobs where album_id=?', (album_pk,)).fetchone()
            if job:
                # failed 与旧版占位状态（needs_authorization）允许重试，其余幂等返回。
                if job['status'] not in ('failed', 'needs_authorization'):
                    return dict(job, job_id=job['id'])
                con.execute('delete from jobs where id=?', (job['id'],))
            if album['sale_type'] == 1:
                status, reason = 'skipped_paid', PAID_SKIP_REASON
            else:
                status, reason = 'queued', None
            con.execute('insert into jobs(album_id,status,reason,created_at,updated_at) values(?,?,?,?,?)',
                        (album_pk, status, reason, now, now))
            job_id = con.execute('select last_insert_rowid()').fetchone()[0]
            result = {'job_id': job_id, 'status': status, 'reason': reason}
            if status == 'queued' and hasattr(self, 'collections'):
                self.collections.mark_downloading(sanitize_filename(album['title']))
        if status == 'queued':
            threading.Thread(target=self._run_download, daemon=True,
                             args=(job_id, album['platform'], album['album_id'], album['title']),
                             name=f'download-{album_pk}').start()
        return result

    def _run_download(self, job_id: int, platform: str, album_id: str, title: str):
        logger.info("开始下载专辑 %s《%s》", platform, title)

        def on_progress(done: int, total: int):
            with self.db() as con:
                con.execute('update jobs set status=?,downloaded_tracks=?,total_tracks=?,updated_at=? where id=?',
                            ('running', done, total, datetime.now().isoformat(), job_id))

        try:
            report = self.downloader.download_album(platform, album_id, title, on_progress=on_progress)
        except AlbumOfflineError as exc:
            logger.info("专辑《%s》已被平台下架: %s", title, exc)
            self._finish(job_id, 'unavailable', f'平台已下架: {exc}')
            self.collections.mark_failed(sanitize_filename(title))
            return
        except Exception as exc:
            logger.warning("专辑《%s》下载失败", title, exc_info=True)
            self._finish(job_id, 'failed', f'下载失败: {exc}')
            self.collections.mark_failed(sanitize_filename(title))
            return
        logger.info("专辑《%s》下载完成: 成功 %d 跳过 %d 失败 %d", title, report.downloaded, report.skipped, report.failed)
        if report.downloaded and not (report.skipped or report.failed):
            self._finish(job_id, 'done', None, report.size_bytes)
            if hasattr(self, 'collections'):
                try:
                    self.collections.confirm(sanitize_filename(title), expected=report.downloaded)
                except (ValueError, OSError):
                    self.collections.mark_failed(sanitize_filename(title))
                    logger.warning('下载完成，但设备合集文件校验未通过')
        elif report.downloaded:
            self._finish(job_id, 'partial',
                         f'完成 {report.downloaded}，跳过受限 {report.skipped}，失败 {report.failed}',
                         report.size_bytes)
        else:
            self._finish(job_id, 'failed',
                         f'未能下载任何曲目（跳过受限 {report.skipped}，失败 {report.failed}）')
        if (report.skipped or report.failed or not report.downloaded) and hasattr(self, 'collections'):
            self.collections.mark_failed(sanitize_filename(title))

    def _finish(self, job_id: int, status: str, reason: str | None, size_bytes: int | None = None):
        with self.db() as con:
            con.execute('update jobs set status=?,reason=?,size_bytes=?,updated_at=? where id=?',
                        (status, reason, size_bytes, datetime.now().isoformat(), job_id))


class ConfirmCollection(BaseModel):
    folder: str = Field(min_length=1, max_length=256)


def create_app(data_dir: Path | None = None, music_dir: Path | None = None,
               collector=collect_latest, downloader: Downloader | None = None,
               auto_refresh_seconds: int | None = None, ma_client=None):
    catalog = Catalog(data_dir or Path(os.getenv('KIDS_DATA_DIR', '/app/data')))
    app = FastAPI(title='Kids Catalog API')
    app.state.catalog = catalog
    app.state.music_dir = music_dir or Path(os.getenv('KIDS_MUSIC_DIR', '/music'))
    catalog.downloader = downloader or Downloader(app.state.music_dir)
    collections = DeviceCollections(catalog.path.parent, app.state.music_dir,
                                    ma_client or MusicAssistant(), catalog.device_candidates)
    app.state.collections = collections
    catalog.collections = collections

    def import_completed_downloads():
        # Old done jobs are evidence only when counts match actual valid files.
        # Never overwrite an existing ledger entry, including incomplete downloads.
        with catalog.db() as con:
            rows = con.execute("select a.platform,a.title,j.downloaded_tracks,j.total_tracks "
                               "from albums a join jobs j on a.id=j.album_id where j.status='done'").fetchall()
        with collections.db() as con:
            known = {row['folder'] for row in con.execute('select folder from completions')}
        for row in rows:
            folder = sanitize_filename(row['title'])
            if folder in known or not row['total_tracks'] or row['downloaded_tracks'] != row['total_tracks']:
                continue
            try:
                collections.confirm(folder, expected=row['total_tracks'], only_missing=True)
            except (ValueError, OSError):
                pass

    # Preserve legacy completion evidence before monthly refresh can retire jobs.
    # Only stat the file manifest here; expensive audio validation happens at generation.
    with catalog.db() as con:
        legacy = con.execute("select a.title,j.total_tracks from albums a join jobs j on a.id=j.album_id "
                             "where j.status='done' and j.total_tracks>0 and j.downloaded_tracks=j.total_tracks").fetchall()
    for row in legacy:
        collections.record_legacy(sanitize_filename(row['title']), row['total_tracks'])

    if auto_refresh_seconds:
        def _monthly_refresh():
            while True:
                try:
                    count = catalog.refresh(collector())
                    logger.info("月度自动刷新完成，共 %d 张专辑", count)
                except Exception:
                    logger.warning("月度自动刷新失败", exc_info=True)
                time.sleep(auto_refresh_seconds)

        threading.Thread(target=_monthly_refresh, daemon=True, name='monthly-refresh').start()

    @app.get('/health')
    def health():
        return {'ok': True}

    @app.get('/api/albums')
    def albums():
        return {'albums': catalog.list()}

    @app.post('/api/refresh')
    def refresh():
        latest = collector()
        return {'count': catalog.refresh(latest), 'albums': latest}

    @app.post('/api/albums/{album_id}/download')
    def download(album_id: int):
        try:
            return catalog.queue(album_id)
        except KeyError:
            raise HTTPException(status_code=404, detail='专辑不存在')

    @app.get('/api/collections')
    def collection_status():
        return collections.read()

    @app.post('/api/collections/generate', status_code=202)
    def generate_collections():
        if not collections.start(import_completed_downloads):
            raise HTTPException(409, detail={'code': 'generation_running', 'message': '正在生成歌单，请稍候'})
        return {'status': 'running'}

    @app.post('/api/collections/confirm')
    def confirm_collection(body: ConfirmCollection):
        try:
            return {'track_count': collections.confirm(body.folder)}
        except (ValueError, OSError) as exc:
            message = str(exc) if isinstance(exc, CollectionError) else '目录不可读取或路径无效'
            raise HTTPException(422, detail=message) from None

    @app.get('/api/device/v1/collections')
    def device_directory():
        snapshot = collections.read()['snapshot']
        if snapshot is None:
            raise HTTPException(404, detail={'code': 'directory_missing', 'message': '尚未生成歌单'})
        return snapshot

    @app.get('/api/device/v1/collections/by-number/{number}')
    def device_target(number: int, revision: str):
        status, result = collections.resolve(number, revision)
        if status != 200:
            raise HTTPException(status, detail=result)
        return result

    return app


app = create_app(auto_refresh_seconds=MONTHLY_SECONDS)
