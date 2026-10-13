"""One durable community/name directory. Manual decisions always win on reimport."""
from __future__ import annotations

import datetime as dt
import json
import math
import re
import sqlite3
import unicodedata
import uuid
from contextlib import contextmanager
from pathlib import Path


def normalized(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', str(value or ''))).casefold()


def now():
    return dt.datetime.now(dt.UTC).isoformat()


def dump(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class CommunityRegistry:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS communities (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL, deleted INTEGER NOT NULL DEFAULT 0,
                    merged_to TEXT);
                CREATE TABLE IF NOT EXISTS sources (
                    id TEXT PRIMARY KEY, source TEXT NOT NULL, kind TEXT NOT NULL, sid TEXT NOT NULL,
                    payload TEXT NOT NULL, cid TEXT REFERENCES communities(id),
                    status TEXT NOT NULL DEFAULT 'pending', method TEXT, evidence TEXT NOT NULL DEFAULT '[]',
                    ignored_by TEXT, UNIQUE(source,kind,sid));
                CREATE TABLE IF NOT EXISTS rejected (rid TEXT NOT NULL, cid TEXT NOT NULL,
                    PRIMARY KEY(rid,cid));
                CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, cid TEXT,
                    action TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);
            ''')

    @contextmanager
    def db(self):
        with sqlite3.connect(self.path, timeout=15) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE')
            yield db

    def _event(self, db, cid, action, payload):
        db.execute('INSERT INTO events(cid,action,payload,created_at) VALUES (?,?,?,?)',
                   (cid, action, dump(payload), now()))

    @staticmethod
    def _community(row):
        return {**json.loads(row['payload']), 'community_id': row['id'],
                'deleted': bool(row['deleted']), 'merged_to': row['merged_to']}

    @staticmethod
    def _source(row):
        return {**json.loads(row['payload']), 'id': row['id'], 'source': row['source'],
                'source_kind': row['kind'], 'source_id': row['sid'], 'community_id': row['cid'],
                'status': row['status'], 'method': row['method'], 'evidence': json.loads(row['evidence'])}

    def communities(self, deleted=False):
        with self.db() as db:
            return [self._community(r) for r in db.execute(
                'SELECT * FROM communities WHERE deleted=? AND merged_to IS NULL ORDER BY id', (int(deleted),))]

    def sources(self):
        with self.db() as db:
            return [self._source(r) for r in db.execute('SELECT * FROM sources ORDER BY source,sid')]

    def create(self, name, *, district='', address='', aliases=None, community_id=None, **extra):
        if not str(name).strip():
            raise ValueError('小区名称不能为空')
        cid = community_id or f'local-{uuid.uuid4().hex[:16]}'
        item = {**extra, 'community_id': cid, 'community_name': name.strip(),
                'district': district, 'address': address, 'aliases': aliases or [], 'updated_at': now()}
        with self.db() as db:
            db.execute('INSERT INTO communities(id,payload) VALUES (?,?)', (cid, dump(item)))
            self._event(db, cid, 'create', item)
        return item

    def update(self, cid, *, name, aliases, address=None, district=None):
        if not name.strip():
            raise ValueError('小区名称不能为空')
        with self.db() as db:
            row = db.execute('SELECT * FROM communities WHERE id=? AND deleted=0 AND merged_to IS NULL', (cid,)).fetchone()
            if not row:
                raise ValueError('小区不存在或已删除')
            item = json.loads(row['payload'])
            item.update(community_name=name.strip(), aliases=list(dict.fromkeys(a.strip() for a in aliases if a.strip())), updated_at=now())
            if address is not None:
                item['address'] = address
            if district is not None:
                item['district'] = district
            db.execute('UPDATE communities SET payload=? WHERE id=?', (dump(item), cid))
            self._event(db, cid, 'edit', item)

    def create_from_source(self, rid, *, name, aliases, district, address):
        if not name.strip():
            raise ValueError('小区名称不能为空')
        with self.db() as db:
            row = db.execute("SELECT * FROM sources WHERE id=? AND status='pending'", (rid,)).fetchone()
            if not row:
                raise ValueError('来源已关联或删除，请刷新后重试')
            source = json.loads(row['payload'])
            cid = 'local-' + uuid.uuid4().hex[:16]
            item = {'community_id': cid, 'community_name': name.strip(), 'aliases': aliases,
                    'district': district, 'address': address, 'updated_at': now(),
                    **{k: source[k] for k in ('longitude', 'latitude', 'coordinate_system') if k in source}}
            db.execute('INSERT INTO communities(id,payload) VALUES (?,?)', (cid, dump(item)))
            source['associated_at'] = now()
            db.execute("UPDATE sources SET cid=?,status='matched',method='manual',evidence=?,payload=? WHERE id=?",
                       (cid, dump(['人工确认建立新小区']), dump(source), rid))
            self._event(db, cid, 'create_from_source', {'record_id': rid, 'community': item})
            return item

    def candidates(self, record):
        name = normalized(record.get('name'))
        if not name:
            return []
        with self.db() as db:
            rejected = {r[0] for r in db.execute('SELECT cid FROM rejected WHERE rid=?', (record.get('id', ''),))}
        result = []
        for c in self.communities():
            if c['community_id'] in rejected:
                continue
            names = [c['community_name'], c.get('community_alias'), *c.get('aliases', [])]
            exact = name in {normalized(n) for n in names if n}
            similar = any(name in normalized(n) or normalized(n) in name for n in names if n)
            if not exact and not similar:
                continue
            district = normalized(record.get('district')).removesuffix('区')
            same_area = bool(district) and district == normalized(c.get('district')).removesuffix('区')
            same_address = bool(normalized(record.get('address'))) and normalized(record.get('address')) == normalized(c.get('address'))
            same_position = False
            if record.get('coordinate_system') == c.get('coordinate_system') == 'gcj02':
                values = [record.get('longitude'), record.get('latitude'), c.get('longitude'), c.get('latitude')]
                if all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
                    dx = (values[0] - values[2]) * math.cos(math.radians(values[1])) * 111320
                    dy = (values[1] - values[3]) * 111320
                    same_position = math.hypot(dx, dy) <= 100
            result.append({**c, 'eligible': exact and same_area and (same_address or same_position),
                           'evidence': ['完整名称/别名一致' if exact else '名称相似，需人工核对',
                                        '同一区域' if same_area else '区域证据缺失或不同',
                                        '地址一致' if same_address else '位置接近（100米内）' if same_position else '缺少一致地址或位置证据']})
        return sorted(result, key=lambda c: (not c['eligible'], c['community_name']))

    def ingest(self, record):
        for field in ('source', 'source_id', 'name'):
            if not str(record.get(field) or '').strip():
                raise ValueError(f'来源记录缺少 {field}')
        kind = record.get('source_kind', 'community')
        with self.db() as db:
            row = db.execute('SELECT * FROM sources WHERE source=? AND kind=? AND sid=?',
                             (record['source'], kind, str(record['source_id']))).fetchone()
            rid = row['id'] if row else uuid.uuid4().hex
            payload = {**record, 'updated_at': now()}
            if row:
                previous = json.loads(row['payload'])
                payload = {**previous, **payload}
                if record.get('auction_ids'):
                    payload['auction_ids'] = list(dict.fromkeys([*previous.get('auction_ids', []), *record['auction_ids']]))
                if record.get('samples'):
                    samples = {s['source_listing_id']: s for s in previous.get('samples', [])}
                    samples.update({s['source_listing_id']: s for s in record['samples']})
                    payload['samples'] = list(samples.values())
                db.execute('UPDATE sources SET payload=? WHERE id=?', (dump(payload), rid))
            else:
                db.execute('INSERT INTO sources(id,source,kind,sid,payload) VALUES (?,?,?,?,?)',
                           (rid, record['source'], kind, str(record['source_id']), dump(payload)))
        self.auto_associate(rid)
        return next(s for s in self.sources() if s['id'] == rid)

    def auto_associate(self, rid=None):
        count = 0
        for item in self.sources():
            if (rid and item['id'] != rid) or item['status'] != 'pending' or item.get('auto_association_disabled'):
                continue
            candidates = self.candidates(item)
            # Full names must resolve uniquely, even if only one duplicate has address evidence.
            exact = [c for c in candidates if normalized(item['name']) in
                     {normalized(n) for n in [c['community_name'], c.get('community_alias'), *c.get('aliases', [])] if n}]
            if len(exact) == 1 and exact[0]['eligible']:
                try:
                    self.associate(item['id'], exact[0]['community_id'], method='auto', evidence=exact[0]['evidence'])
                    count += 1
                except ValueError:
                    pass  # a concurrent manual decision supersedes discovery
        return count

    def promote_auction_source(self, asset_id, auction_ids):
        """Keep a single legacy round's decisions when its asset identity becomes known."""
        with self.db() as db:
            current = db.execute("SELECT status,payload FROM sources WHERE source='laipai' AND kind='asset' AND sid=?", (asset_id,)).fetchone()
            if current:
                return current['status'] == 'matched' or not json.loads(current['payload']).get('association_identity_conflict')
            legacy = [r for r in db.execute("SELECT id,sid FROM sources WHERE source='laipai' AND kind='auction'")
                      if r['sid'] in auction_ids]
            # Multiple independent decisions need manual reconciliation, never pick one arbitrarily.
            if len(legacy) == 1:
                db.execute("UPDATE sources SET kind='asset',sid=? WHERE id=?", (asset_id, legacy[0]['id']))
            return len(legacy) <= 1

    def associate(self, rid, cid, *, method='manual', evidence=None):
        with self.db() as db:
            c = db.execute('SELECT * FROM communities WHERE id=? AND deleted=0 AND merged_to IS NULL', (cid,)).fetchone()
            r = db.execute('SELECT * FROM sources WHERE id=?', (rid,)).fetchone()
            if not c or not r or r['status'] == 'ignored':
                raise ValueError('来源或目标小区不存在，或已删除')
            if method == 'auto' and (r['status'] != 'pending' or db.execute(
                    'SELECT 1 FROM rejected WHERE rid=? AND cid=?', (rid, cid)).fetchone()):
                raise ValueError('人工决策优先')
            # Current rental snapshots are one-source-per-community; avoid silently hiding another source.
            if r['source'] == 'fang' and db.execute(
                    "SELECT 1 FROM sources WHERE source='fang' AND cid=? AND status='matched' AND id<>?", (cid, rid)).fetchone():
                raise ValueError('该小区已有房天下关联，请先解除原关联')
            payload = json.loads(r['payload'])
            payload['associated_at'] = now()
            db.execute("UPDATE sources SET cid=?,status='matched',method=?,evidence=?,payload=? WHERE id=?",
                       (cid, method, dump(evidence or ['人工确认']), dump(payload), rid))
            self._event(db, cid, 'associate', {'record_id': rid, 'method': method, 'previous_id': r['cid']})

    def unlink(self, rid, cid=None):
        with self.db() as db:
            r = db.execute('SELECT * FROM sources WHERE id=?', (rid,)).fetchone()
            if not r or r['status'] == 'ignored':
                raise ValueError('来源不存在或已删除')
            target = cid or r['cid']
            if target:
                db.execute('INSERT OR IGNORE INTO rejected VALUES (?,?)', (rid, target))
            if not cid or cid == r['cid']:
                db.execute("UPDATE sources SET cid=NULL,status='pending',method=NULL,evidence='[]' WHERE id=?", (rid,))
            self._event(db, target, 'unlink', {'record_id': rid})

    def delete(self, cid, reason=''):
        with self.db() as db:
            row = db.execute('SELECT * FROM communities WHERE id=? AND merged_to IS NULL', (cid,)).fetchone()
            if not row:
                raise ValueError('小区不存在')
            if row['deleted']:
                return
            db.execute('UPDATE communities SET deleted=1 WHERE id=?', (cid,))
            db.execute("UPDATE sources SET status='ignored',ignored_by=? WHERE cid=? AND status<>'ignored'", (cid, cid))
            self._event(db, cid, 'delete', {'reason': reason, 'community': self._community(row)})

    def ignore_source(self, rid, reason=''):
        item = next((s for s in self.sources() if s['id'] == rid), None)
        if not item:
            raise ValueError('来源不存在')
        if item['community_id']:
            return self.delete(item['community_id'], reason)
        with self.db() as db:
            db.execute("UPDATE sources SET status='ignored',ignored_by='source' WHERE id=?", (rid,))
            self._event(db, None, 'ignore', {'record_id': rid, 'reason': reason})

    def restore(self, cid):
        with self.db() as db:
            if not db.execute('SELECT 1 FROM communities WHERE id=? AND deleted=1', (cid,)).fetchone():
                raise ValueError('已删除小区不存在')
            db.execute('UPDATE communities SET deleted=0 WHERE id=?', (cid,))
            db.execute("UPDATE sources SET status='matched',ignored_by=NULL WHERE ignored_by=?", (cid,))
            self._event(db, cid, 'restore', {})

    def restore_source(self, rid):
        with self.db() as db:
            row = db.execute('SELECT * FROM sources WHERE id=?', (rid,)).fetchone()
            if not row or row['ignored_by'] != 'source':
                raise ValueError('请从已删除小区恢复整个小区')
            db.execute("UPDATE sources SET status='pending',ignored_by=NULL WHERE id=?", (rid,))
            self._event(db, None, 'restore_source', {'record_id': rid})

    def merge(self, cid, target):
        if cid == target:
            raise ValueError('不能合并到自己')
        with self.db() as db:
            rows = [db.execute('SELECT * FROM communities WHERE id=? AND deleted=0 AND merged_to IS NULL', (key,)).fetchone() for key in (cid, target)]
            if not all(rows):
                raise ValueError('小区不存在或已删除')
            fang = db.execute("SELECT COUNT(*) FROM sources WHERE source='fang' AND status='matched' AND cid IN (?,?)", (cid, target)).fetchone()[0]
            if fang > 1:
                raise ValueError('两个小区都有租金来源，请先解除错误来源再合并')
            old, keep = [json.loads(r['payload']) for r in rows]
            keep['aliases'] = list(dict.fromkeys([*keep.get('aliases', []), old['community_name'], *old.get('aliases', [])]))
            for key in ('address', 'district', 'longitude', 'latitude', 'coordinate_system'):
                if not keep.get(key) and old.get(key):
                    keep[key] = old[key]
            db.execute('UPDATE communities SET payload=? WHERE id=?', (dump(keep), target))
            db.execute('UPDATE communities SET merged_to=? WHERE id=?', (target, cid))
            db.execute('UPDATE sources SET cid=? WHERE cid=?', (target, cid))
            self._event(db, target, 'merge', {'from_id': cid, 'previous': old})

    def resolve(self, cid):
        with self.db() as db:
            seen = set()
            while cid not in seen:
                seen.add(cid)
                row = db.execute('SELECT * FROM communities WHERE id=?', (cid,)).fetchone()
                if not row or row['deleted']:
                    return None
                if not row['merged_to']:
                    return cid
                cid = row['merged_to']
        return None

    def is_ignored(self, source, kind, sid):
        with self.db() as db:
            if db.execute("SELECT 1 FROM sources WHERE source=? AND kind=? AND sid=? AND status='ignored'",
                          (source, kind, str(sid))).fetchone():
                return True
            if source == 'laipai' and kind == 'auction':
                return any(str(sid) in json.loads(r[0]).get('auction_ids', []) for r in db.execute(
                    "SELECT payload FROM sources WHERE source='laipai' AND status='ignored'"))
            return False

    def events(self, cid=None):
        with self.db() as db:
            rows = db.execute('SELECT * FROM events WHERE cid IS ? ORDER BY seq DESC LIMIT 100', (cid,))
            return [{**dict(r), 'payload': json.loads(r['payload'])} for r in rows]


def existing_registry(data_dir):
    path = Path(data_dir) / 'community_registry.sqlite3'
    return CommunityRegistry(path) if path.exists() else None
