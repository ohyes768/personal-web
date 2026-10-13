"""Import current data once, then use the registry as the sole editable directory."""
import json
import shutil
import sqlite3
from pathlib import Path

from src.services.community_registry import CommunityRegistry, dump


def read(path, fallback):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else fallback


def prepare_directory(data_dir):
    data_dir = Path(data_dir)
    store = CommunityRegistry(data_dir / 'community_registry.sqlite3')
    with store.db() as db:
        ready = db.execute("SELECT 1 FROM meta WHERE key='prepared'").fetchone()
    if ready:
        return store
    # Backup existing editable files; startup never seeds/overwrites an established directory.
    backup = data_dir / 'directory-backup'
    backup.mkdir(exist_ok=True)
    for name in ('binjiang_communities.json', 'rental_sources.sqlite3', 'rental_community_mappings.json', 'auction_community_mappings.json'):
        path = data_dir / name
        if path.exists() and not (backup / name).exists():
            if name.endswith('.sqlite3'):
                with sqlite3.connect(path) as src, sqlite3.connect(backup / name) as dst:
                    src.backup(dst)
            else:
                shutil.copy2(path, backup / name)
    coords = read(data_dir / 'binjiang_coordinates.json', {})
    communities_path = data_dir / 'binjiang_communities.json'
    residential_path = data_dir / 'binjiang_residential_communities.json'
    if residential_path.exists():
        communities = read(residential_path, [])
        if isinstance(communities, dict):
            communities = communities.get('communities', [])
    else:
        communities = read(communities_path, [])
        if isinstance(communities, dict):
            communities = communities.get('communities', [])
    excluded_non_residential = read(data_dir / 'binjiang_non_residential_communities.json', [])
    if isinstance(excluded_non_residential, dict):
        excluded_non_residential = excluded_non_residential.get('communities', [])
    excluded_ids = {str(item.get('community_id') or item.get('communityid') or '') for item in excluded_non_residential}
    communities = [c for c in communities if str(c.get('community_id') or c.get('communityid') or '') not in excluded_ids]
    # Whole import is recoverable: insert-if-absent plus completion marker, no reset of decisions.
    with store.db() as db:
        for item in communities:
            cid = str(item['community_id'])
            coord = coords.get(cid, {})
            payload = {**item, 'aliases': [item['community_alias']] if item.get('community_alias') else [],
                       'address': coord.get('formatted_address', ''), 'coordinate_system': 'gcj02',
                       'longitude': coord.get('longitude'), 'latitude': coord.get('latitude')}
            db.execute('INSERT OR IGNORE INTO communities(id,payload) VALUES (?,?)', (cid, dump(payload)))
            source_payload = {'source': 'tmsf', 'source_kind': 'community', 'source_id': cid,
                              'name': item['community_name'], 'district': item.get('district'),
                              'address': payload['address'], 'source_url': item.get('source_url'),
                              'aliases': payload['aliases']}
            db.execute("INSERT OR IGNORE INTO sources(id,source,kind,sid,payload,cid,status,method) VALUES (?,'tmsf','community',?,?,?,'matched','import')",
                       ('tmsf-' + cid, cid, dump(source_payload), cid))
        mappings = []
        old_db = data_dir / 'rental_sources.sqlite3'
        if old_db.exists():
            with sqlite3.connect(old_db) as src:
                mappings = [json.loads(r[0]) for r in src.execute('SELECT payload FROM mappings')]
                candidates = src.execute('SELECT community_id,payload,rejected FROM candidates').fetchall()
        else:
            mappings = [m for m in read(data_dir / 'rental_community_mappings.json', {}).get('mappings', []) if m.get('status') == 'verified']
            candidates = []
        for item in mappings:
            _import_fang(db, item, item.get('community_id'), 'matched')
        for cid, raw, rejected in candidates:
            item = json.loads(raw)
            rid = _import_fang(db, item, None, 'pending')
            if rejected:
                db.execute('INSERT OR IGNORE INTO rejected VALUES (?,?)', (rid, cid))
        auctions = read(data_dir / 'auction_records.json', {}).get('records', [])
        explicit = {}
        for m in read(data_dir / 'auction_community_mappings.json', {}).get('mappings', []):
            kind = 'asset' if m.get('asset_id') else 'auction'
            explicit[(kind, str(m.get(kind + '_id')))] = m['community_id']
        for item in auctions:
            if not item.get('community_name'):
                continue
            kind = 'asset' if item.get('asset_id') else 'auction'
            sid = str(item.get(kind + '_id'))
            cid = explicit.get((kind, sid))
            payload = {'name': item['community_name'], 'district': '滨江', 'address': item.get('address'), 'source_url': item.get('source_url'), 'auction_ids': [str(item['auction_id'])]}
            db.execute("INSERT OR IGNORE INTO sources(id,source,kind,sid,payload,cid,status,method) VALUES (?,'laipai',?,?,?,?,?,?)",
                       ('laipai-' + kind + '-' + sid, kind, sid, dump(payload), cid, 'matched' if cid else 'pending', 'manual' if cid else None))
            old = db.execute("SELECT id,payload FROM sources WHERE source='laipai' AND kind=? AND sid=?", (kind, sid)).fetchone()
            previous = json.loads(old['payload'])
            previous['auction_ids'] = list(dict.fromkeys([*previous.get('auction_ids', []), str(item['auction_id'])]))
            db.execute('UPDATE sources SET payload=? WHERE id=?', (dump(previous), old['id']))
        db.execute("INSERT INTO meta VALUES ('prepared','1')")
    store.auto_associate()
    return store


def _import_fang(db, item, cid, status):
    sid = str(item['source_community_id'])
    rid = 'fang-' + sid
    payload = {'name': item['source_name'], 'address': item.get('source_address'), 'district': '滨江',
               'associated_at': item.get('verified_at'),
               'source_url': item.get('source_url') or f'https://zu.fang.com/hz/house-xm{sid}/'}
    db.execute("INSERT OR IGNORE INTO sources(id,source,kind,sid,payload,cid,status,method) VALUES (?,'fang','community',?,?,?,?,?)",
               (rid, sid, dump(payload), cid, status, 'manual' if cid else None))
    return rid
