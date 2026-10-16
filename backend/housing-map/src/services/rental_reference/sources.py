"""Confirmed rental sources and reviewable candidates; JSON is migration input only."""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote, urlsplit

from src.services.fang_rentals import BASE_URL, FangClient, _links, enrich_detail, parse_listing_page, validate_url

logger = logging.getLogger(__name__)


def database_path(mappings_path: Path) -> Path:
    return mappings_path.with_name('rental_sources.sqlite3')


@contextmanager
def connection(path: Path):
    with sqlite3.connect(path, timeout=10) as db:
        db.row_factory = sqlite3.Row
        yield db


def confirmed_pairs(path: Path) -> list[tuple[str, str]]:
    with connection(path) as db:
        return [(r['source_id'], r['community_id']) for r in db.execute(
            'SELECT source_id, community_id FROM mappings ORDER BY community_id')]


class SourceStore:
    def __init__(self, mappings_path: Path):
        from src.services.community_registry import existing_registry
        self.registry = existing_registry(mappings_path.parent)
        self.path = database_path(mappings_path)
        if self.registry:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with connection(self.path) as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS mappings (
                    community_id TEXT PRIMARY KEY, source_id TEXT NOT NULL UNIQUE,
                    payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS candidates (
                    community_id TEXT NOT NULL, source_id TEXT NOT NULL,
                    payload TEXT NOT NULL, rejected INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (community_id, source_id));
            ''')
            db.execute('BEGIN IMMEDIATE')
            if not db.execute("SELECT 1 FROM meta WHERE key='imported'").fetchone():
                seed = mappings_path if mappings_path.exists() else mappings_path.parent.parent / 'seed-data' / mappings_path.name
                if seed.exists():
                    # Use the legacy validator before marking import complete.
                    from src.services.rental_reference.refresh import load_legacy_mappings
                    pairs = set(load_legacy_mappings(seed))
                    payload = json.loads(seed.read_text(encoding='utf-8-sig'))
                    for entry in payload['mappings']:
                        sid, cid = entry['source_community_id'], entry['community_id']
                        if (sid, cid) in pairs:
                            item = {**entry, 'source_url': f'{BASE_URL}/hz/house-xm{sid}/'}
                            db.execute('INSERT INTO mappings VALUES (?, ?, ?)',
                                       (cid, sid, json.dumps(item, ensure_ascii=False)))
                db.execute("INSERT INTO meta VALUES ('imported', '1')")

    def get(self, community_id: str) -> dict:
        if self.registry:
            candidates = [r for r in self.registry.sources() if r['source'] == 'fang' and r['status'] == 'pending'
                          and any(c['community_id'] == community_id for c in self.registry.candidates(r))]
            return {'mapping': self.all_mappings().get(community_id), 'candidates': [self._rental(r) for r in candidates]}
        with connection(self.path) as db:
            row = db.execute('SELECT payload FROM mappings WHERE community_id=?', (community_id,)).fetchone()
            candidates = db.execute('SELECT payload FROM candidates WHERE community_id=? AND rejected=0', (community_id,)).fetchall()
            return {'mapping': json.loads(row[0]) if row else None,
                    'candidates': [json.loads(r[0]) for r in candidates]}

    def all_mappings(self) -> dict:
        if self.registry:
            return {r['community_id']: self._rental(r) for r in self.registry.sources()
                    if r['source'] == 'fang' and r['status'] == 'matched'}
        with connection(self.path) as db:
            return {r['community_id']: json.loads(r['payload']) for r in db.execute('SELECT * FROM mappings')}

    def pending_counts(self) -> dict:
        if self.registry:
            return {}
        with connection(self.path) as db:
            return {r['community_id']: r['count'] for r in db.execute(
                'SELECT community_id, COUNT(*) AS count FROM candidates WHERE rejected=0 GROUP BY community_id')}

    def save_candidates(self, community_id: str, candidates: list[dict], *, restore: bool = False) -> None:
        if self.registry:
            for c in candidates:
                self.registry.ingest({'source': 'fang', 'source_kind': 'community',
                    'source_id': c['source_community_id'], 'name': c['source_name'],
                    'address': c.get('source_address'), 'district': '滨江', 'source_url': c['source_url']})
            return
        with connection(self.path) as db:
            for candidate in candidates:
                # Rejected candidates stay rejected on repeat searches.
                db.execute('''INSERT INTO candidates (community_id, source_id, payload) VALUES (?, ?, ?)
                    ON CONFLICT(community_id, source_id) DO UPDATE SET payload=excluded.payload,
                    rejected=CASE WHEN ? THEN 0 ELSE candidates.rejected END''',
                           (community_id, candidate['source_community_id'], json.dumps(candidate, ensure_ascii=False), restore))

    def confirm(self, community_id: str, source_id: str) -> dict:
        if self.registry:
            r = next((r for r in self.registry.sources() if r['source'] == 'fang' and r['source_id'] == source_id), None)
            if not r:
                raise ValueError('请先查找来源')
            self.registry.associate(r['id'], community_id)
            return self.all_mappings()[community_id]
        with connection(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT payload FROM candidates WHERE community_id=? AND source_id=? AND rejected=0',
                             (community_id, source_id)).fetchone()
            if row is None:
                raise ValueError('请先查找并核对来源候选，再确认关联')
            item = {**json.loads(row[0]), 'community_id': community_id, 'status': 'verified',
                    'verified_at': dt.datetime.now(dt.UTC).isoformat()}
            try:
                db.execute('''INSERT INTO mappings VALUES (?, ?, ?) ON CONFLICT(community_id)
                    DO UPDATE SET source_id=excluded.source_id, payload=excluded.payload''',
                           (community_id, source_id, json.dumps(item, ensure_ascii=False)))
            except sqlite3.IntegrityError as exc:
                raise ValueError('这个来源已关联其他小区，请先解除原关联') from exc
            return item

    def remove(self, community_id: str) -> None:
        if self.registry:
            for r in self.registry.sources():
                if r['source'] == 'fang' and r['community_id'] == community_id and r['status'] == 'matched':
                    self.registry.unlink(r['id'])
            return
        with connection(self.path) as db:
            db.execute('DELETE FROM mappings WHERE community_id=?', (community_id,))

    def reject(self, community_id: str, source_id: str) -> None:
        if self.registry:
            r = next((r for r in self.registry.sources() if r['source'] == 'fang' and r['source_id'] == source_id), None)
            if r:
                self.registry.unlink(r['id'], community_id)
            return
        with connection(self.path) as db:
            db.execute('UPDATE candidates SET rejected=1 WHERE community_id=? AND source_id=?', (community_id, source_id))

    @staticmethod
    def _rental(r):
        return {**r, 'source_community_id': r['source_id'], 'source_name': r['name'],
                'source_address': r.get('address'), 'status': 'verified', 'verified_at': r.get('associated_at')}


def source_page(url: str) -> str:
    validate_url(url)
    parts = urlsplit(url)
    match = re.fullmatch(r'/(?:hz/)?house-xm(\d+)/?', parts.path)
    if not match or parts.query or parts.fragment:
        raise ValueError('请粘贴房天下杭州小区租房页链接（house-xm 编号），不是单套房源链接')
    return f'{BASE_URL}/hz/house-xm{match[1]}/'


def discover(community: dict, *, keyword: str = '', source_url: str = '', client_factory=FangClient) -> list[dict]:
    """One public list request and at most one detail request; never auto-confirm."""
    name = keyword.strip() or community.get('community_alias') or community['community_name']
    url = source_page(source_url) if source_url else f'{BASE_URL}/hz/house/kw{quote(name, safe="")}/'
    client = client_factory(timeout=15)
    stage = 'fetch'
    html = ''
    actual_keyword = None
    logger.info('Rental discovery start community_id=%s name=%r url=%s',
                community.get('community_id'), name, url)
    try:
        html = client.fetch(url)
        stage = 'keyword_validation'
        if not source_url:
            # Fang dropped the ?keyword= query; the kw path term counts as
            # applied only when the selected-conditions bar echoes the name.
            applied = re.search(r'class="term">关键字：([^<]*)<', html)
            actual_keyword = applied.group(1).strip() if applied else None
            if actual_keyword != name:
                raise ValueError('来源搜索未应用关键词，拒绝使用全市房源作为候选')
            if '没有找到相符的房源' in html:
                # Zero rentals: the remaining page is city-wide recommendations,
                # never candidates.
                logger.info('Rental discovery no-match community_id=%s name=%r',
                            community.get('community_id'), name)
                return []
        stage = 'parse_listing'
        rows, _ = parse_listing_page(html, url)  # challenge/changed HTML must fail explicitly
        found: dict[str, dict] = {}
        for row in rows:
            sid = row.get('source_community_id')
            label = row.get('community_name')
            if not sid or not label:
                continue
            found.setdefault(sid, {'source': 'fang', 'source_community_id': sid,
                                  'source_name': label, 'source_url': f'{BASE_URL}/hz/house-xm{sid}/',
                                  'source_address': None, 'evidence': [],
                                  'found_at': dt.datetime.now(dt.UTC).isoformat()})
        if source_url:
            sid = re.search(r'house-xm(\d+)', url).group(1)
            if not rows:
                # An explicit recognized empty list still identifies a valid community.
                label = next((label.removesuffix('租房') for href, label in _links(html)
                              if urlsplit(href).path.rstrip('/') == urlsplit(url).path.rstrip('/')
                              and label.endswith('租房')), None)
                if label:
                    found[sid] = {'source': 'fang', 'source_community_id': sid,
                                  'source_name': label, 'source_url': url,
                                  'source_address': None, 'evidence': [],
                                  'found_at': dt.datetime.now(dt.UTC).isoformat()}
            found = {sid: found[sid]} if sid in found else {}
        # Rental list has no authoritative district/address; disclose gaps.
        if rows:
            row = dict(rows[0]); row['quality_flags'] = list(row['quality_flags'])
            try:
                import time
                time.sleep(2)
                enrich_detail(row, client.fetch(row['source_url']))
                candidate = found.get(row.get('source_community_id'))
                if candidate:
                    candidate['source_address'] = row.get('address')
            except Exception:
                logger.warning('Rental discovery detail unavailable community_id=%s url=%s; candidate address remains missing',
                               community.get('community_id'), row['source_url'], exc_info=True)
        for item in found.values():
            names = [community.get('community_name', ''), community.get('community_alias', '')]
            item['evidence'] = [
                '名称与地图名称/别名一致' if item['source_name'] in names else '名称存在差异，请核对别名与分期',
                f"地图区域：{community.get('district', '')} {community.get('subdistrict', '')}".strip(),
                '来源地址可供人工核对' if item['source_address'] else '来源地址尚不可得，需打开来源核对位置',
                '尚未核对坐标与分期；确认前请核对是否同一小区',
            ]
        logger.info('Rental discovery complete community_id=%s name=%r candidates=%s',
                    community.get('community_id'), name, min(len(found), 10))
        return list(found.values())[:10]
    except Exception as exc:
        # Log bounded metadata only: never dump response HTML, headers or cookies.
        title = re.search(r'<title[^>]*>(.*?)</title>', html, re.I | re.S)
        logger.warning('Rental discovery failed community_id=%s name=%r url=%s stage=%s '
                       'html_chars=%s title=%r actual_keyword=%r error_type=%s',
                       community.get('community_id'), name, url, stage, len(html),
                       re.sub(r'\s+', ' ', title.group(1))[:160] if title else None,
                       actual_keyword[:160] if actual_keyword is not None else None,
                       type(exc).__name__, exc_info=True)
        raise
    finally:
        client.close()
