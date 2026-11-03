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
        from src.services.community_admission import migrate_admission
        migrate_admission(store, data_dir)
        mark_legacy_addresses(store, data_dir)
        return store
    # Backup existing editable files; startup never seeds/overwrites an established directory.
    backup = data_dir / 'directory-backup'
    backup.mkdir(exist_ok=True)
    for name in ('binjiang_communities.json', 'rental_sources.sqlite3', 'rental_community_mappings.json', 'auction_community_mappings.json'):
        path = data_dir / name
        if path.exists() and not (backup / name).exists():
            if name.endswith('.sqlite3'):
                try:
                    with sqlite3.connect(path) as src, sqlite3.connect(backup / name) as dst:
                        src.backup(dst)
                except sqlite3.Error:
                    # A corrupt legacy database must not block the directory; keep the raw bytes.
                    shutil.copy2(path, backup / name)
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
                       'address': item.get('address') or '', 'geographic_address': coord.get('formatted_address', ''), 'coordinate_system': 'gcj02',
                       'longitude': coord.get('longitude'), 'latitude': coord.get('latitude')}
            db.execute('INSERT OR IGNORE INTO communities(id,payload) VALUES (?,?)', (cid, dump(payload)))
            source_payload = {'source': 'tmsf', 'source_kind': 'community', 'source_id': cid,
                              'name': item['community_name'], 'district': item.get('district'),
                              'address': payload['address'], 'source_url': item.get('source_url'),
                              'aliases': payload['aliases']}
            db.execute("INSERT OR IGNORE INTO sources(id,source,kind,sid,payload,cid,status,method) VALUES (?,'tmsf','community',?,?,?,'matched','import')",
                       ('tmsf-' + cid, cid, dump(source_payload), cid))
        # 房天下已退役：旧租金映射/候选库不再导入，只保留文件备份。
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
    from src.services.community_admission import migrate_admission
    migrate_admission(store, data_dir)
    return store


def mark_legacy_addresses(store, data_dir):
    """Mark only identifiable imported geocoder addresses; defer correction to verified fetches."""
    coords = read(Path(data_dir) / 'binjiang_coordinates.json', {})
    with store.db() as db:
        if db.execute("SELECT 1 FROM meta WHERE key='source_address_provenance_v1'").fetchone():
            return
        for row in db.execute("SELECT * FROM sources WHERE source='tmsf' AND method='import'").fetchall():
            source = json.loads(row['payload'])
            coord = coords.get(row['sid'], {})
            legacy = coord.get('formatted_address')
            if not legacy or source.get('address') != legacy or source.get('address_checked_at'):
                continue
            source.update(address_origin='legacy_geocoder', address_verification_pending=True,
                          geographic_address=legacy)
            db.execute('UPDATE sources SET payload=? WHERE id=?', (dump(source), row['id']))
            master_row = db.execute('SELECT payload FROM communities WHERE id=?', (row['cid'],)).fetchone()
            if master_row:
                master = json.loads(master_row['payload'])
                manually_edited = db.execute("SELECT 1 FROM events WHERE cid=? AND action='edit' LIMIT 1", (row['cid'],)).fetchone()
                if master.get('address') == legacy and master.get('address_origin') != 'manual' and not manually_edited:
                    master.update(address_origin='legacy_geocoder', geographic_address=legacy)
                    db.execute('UPDATE communities SET payload=? WHERE id=?', (dump(master), row['cid']))
            store._event(db, row['cid'], 'address_verification_pending', {'record_id': row['id'], 'legacy_address': legacy})
        db.execute("INSERT INTO meta VALUES ('source_address_provenance_v1','1')")
