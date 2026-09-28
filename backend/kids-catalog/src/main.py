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
from src.collector import collect_latest

logger = logging.getLogger(__name__)
MONTHLY_SECONDS = 30 * 24 * 3600



class Catalog:
    def __init__(self, data_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True)
        self.path = data_dir / "kids_catalog.sqlite3"
        with self.db() as con:
            con.executescript('''
              create table if not exists albums (
                id integer primary key, platform text not null, album_id text not null,
                title text not null, url text not null, age_evidence text not null,
                age_confidence text not null, sale_type integer, last_seen text not null,
                unique(platform, album_id));
              create table if not exists jobs (
                id integer primary key, album_id integer not null unique, status text not null,
                reason text, created_at text not null, updated_at text not null,
                foreign key(album_id) references albums(id));
            ''')
            # Databases created before sale_type existed gain the column in place.
            columns = {row['name'] for row in con.execute('pragma table_info(albums)')}
            if 'sale_type' not in columns:
                con.execute('alter table albums add column sale_type integer')

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
                con.execute('''insert into albums(platform,album_id,title,url,age_evidence,age_confidence,sale_type,last_seen)
                  values(?,?,?,?,?,?,?,?) on conflict(platform,album_id) do update set
                  title=excluded.title,url=excluded.url,age_evidence=excluded.age_evidence,
                  age_confidence=excluded.age_confidence,sale_type=excluded.sale_type,last_seen=excluded.last_seen''',
                  (row['platform'], str(row['album_id']), row['title'], row['url'],
                   row['age_evidence'], row['age_confidence'], row.get('sale_type'), now))
        return len(albums)

    def list(self):
        with self.db() as con:
            return [dict(row) for row in con.execute('''select a.*, coalesce(j.status,'not_downloaded') download_status,
              j.reason from albums a left join jobs j on j.album_id=a.id order by a.platform,a.title''')]

    def queue(self, album_pk: int):
        now = datetime.now().isoformat()
        with self.db() as con:
            album = con.execute('select id from albums where id=?', (album_pk,)).fetchone()
            if not album:
                raise KeyError(album_pk)
            job = con.execute('select id,status,reason from jobs where album_id=?', (album_pk,)).fetchone()
            if job:
                return dict(job, job_id=job['id'])
            # An authorised provider resolver will replace this guarded outcome.
            con.execute('insert into jobs(album_id,status,reason,created_at,updated_at) values(?,?,?,?,?)',
                        (album_pk, 'needs_authorization', '未配置已授权的媒体地址', now, now))
            job_id = con.execute('select last_insert_rowid()').fetchone()[0]
            return {'job_id': job_id, 'status': 'needs_authorization', 'reason': '未配置已授权的媒体地址'}


def create_app(data_dir: Path | None = None, music_dir: Path | None = None,
               collector=collect_latest, auto_refresh_seconds: int | None = None):
    catalog = Catalog(data_dir or Path(os.getenv('KIDS_DATA_DIR', '/app/data')))
    app = FastAPI(title='Kids Catalog API')
    app.state.catalog = catalog
    app.state.music_dir = music_dir or Path(os.getenv('KIDS_MUSIC_DIR', '/music'))

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

    return app


app = create_app(auto_refresh_seconds=MONTHLY_SECONDS)