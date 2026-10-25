"""Explicit, preview-first registration of the two researched rental sources."""
import hashlib
import json
import math
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

from src.services.community_registry import CommunityRegistry, dump, normalized, now
from src.services.rental_reference.association import eligible_communities
from src.services.xingfuli_rentals import list_url

PILOTS = (
    dict(source_id='6581030816598458638', seed_listing_id='7502229388495274018', name='风雅钱塘',
         names=['风雅钱塘', '风雅钱塘世纪花园'], address='月明路1076号', longitude=120.20749, latitude=30.202261),
    dict(source_id='6854812199240614151', seed_listing_id='7694922441520431153', name='欣盛东方郡',
         names=['欣盛东方郡', '东方郡'], address='春晓路198号', longitude=120.213989, latitude=30.197716),
)


class ReadOnlyRegistry(CommunityRegistry):
    def __init__(self, path):
        self.path = Path(path)
        if not self.path.is_file():
            raise ValueError('现有小区目录不存在；试点导入不会新建目录')

    @contextmanager
    def db(self):
        with sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True) as db:
            db.row_factory = sqlite3.Row
            yield db


def _snapshot(db, cid):
    # Protect the eligibility/identity evidence checked before the write transaction.
    content = []
    for sql in [
        'SELECT * FROM communities WHERE id=?',
        'SELECT * FROM sources WHERE cid=? ORDER BY id',
        'SELECT * FROM community_admission WHERE cid=?',
        'SELECT * FROM rejected WHERE cid=? ORDER BY rid',
    ]:
        content.append([dict(r) for r in db.execute(sql, (cid,))])
    content.append([dict(r) for r in db.execute('SELECT * FROM meta WHERE key=?', ('directory_flow_version',))])
    return hashlib.sha256(dump(content).encode()).hexdigest()


def _position_matches(pilot, community):
    if community.get('coordinate_system') != 'gcj02':
        return False
    lon, lat = community.get('longitude'), community.get('latitude')
    if not all(isinstance(v, (float, int)) and math.isfinite(v) for v in (lon, lat)):
        return False
    dx = (lon - pilot['longitude']) * math.cos(math.radians(lat)) * 111320
    dy = (lat - pilot['latitude']) * 111320
    return math.hypot(dx, dy) <= 100


def preview(registry):
    eligible, _ = eligible_communities(registry)
    sources = registry.sources()
    report = []
    for pilot in PILOTS:
        item = {k: pilot[k] for k in ('source_id', 'seed_listing_id', 'name', 'address')}
        item['source_url'] = list_url(pilot['seed_listing_id'])
        matches = [c for c in eligible if {normalized(n) for n in [c['community_name'],
                   c.get('community_alias'), *c.get('aliases', [])] if n}
                   & {normalized(n) for n in pilot['names']}]
        existing = next((r for r in sources if r['source'] == 'xingfuli' and r['source_id'] == pilot['source_id']), None)
        if existing:
            item.update(status='enabled' if existing['status'] == 'matched' else 'protected',
                        community_id=existing.get('community_id'), reason='已有来源决定，不重新关联')
        elif len(matches) != 1:
            item.update(status='unverified', reason='未找到唯一的当前已收录同名住宅')
        else:
            c = matches[0]; cid = c['community_id']
            with registry.db() as db:
                other = db.execute("SELECT 1 FROM sources WHERE source='xingfuli' AND cid=? AND status='matched'", (cid,)).fetchone()
                imported = db.execute('SELECT 1 FROM meta WHERE key=?', ('xingfuli_pilot:' + pilot['source_id'],)).fetchone()
                snapshot = _snapshot(db, cid)
            if other or imported:
                item.update(status='protected', reason='已有幸福里关联或历史导入决定')
            elif normalized(c.get('address')) != normalized(pilot['address']) and not _position_matches(pilot, c):
                item.update(status='unverified', reason='名称匹配，但地址/坐标证据不足')
            else:
                item.update(status='ready', community_id=cid, snapshot=snapshot, reason='名称、住宅资格及地址/位置已核对')
        report.append(item)
    return report


def apply(registry):
    report = preview(registry)
    with registry.db() as db:
        for item in report:
            if item['status'] != 'ready':
                continue
            cid, sid = item['community_id'], item['source_id']
            if _snapshot(db, cid) != item['snapshot']:
                raise ValueError('小区资料或关联已变化，请重新预览')
            if db.execute("SELECT 1 FROM sources WHERE source='xingfuli' AND sid=?", (sid,)).fetchone():
                raise ValueError('幸福里来源决定已变化，请重新预览')
            payload = dict(source='xingfuli', source_id=sid, source_kind='community', name=item['name'],
                           district='滨江', address=item['address'], seed_listing_id=item['seed_listing_id'],
                           source_url=item['source_url'], auto_association_disabled=True, updated_at=now())
            rid = uuid.uuid4().hex
            db.execute('INSERT INTO sources(id,source,kind,sid,payload) VALUES (?,?,?,?,?)',
                       (rid, 'xingfuli', 'community', sid, dump(payload)))
            registry._associate(db, rid, cid, method='manual', evidence=['已审阅幸福里试点；完整名及地址/位置一致'])
            db.execute('INSERT INTO meta VALUES (?,?)', ('xingfuli_pilot:' + sid, now()))
            item['status'] = 'imported'
    return report
