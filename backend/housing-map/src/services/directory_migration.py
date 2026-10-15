"""Explicit, offline, fingerprinted rollout; preview never initializes/writes production."""
import hashlib
import json
import shutil
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from src.services.community_registry import CommunityRegistry, dump, now
from src.services.directory_policy import KEY, VERSION
from src.services.directory_workflow import materialize, inventory, auction_tasks
from src.services.community_admission import property_facts


class SnapshotRegistry(CommunityRegistry):
    def __init__(self, connection, path):
        self.connection, self.path = connection, path

    @contextmanager
    def db(self):
        yield self.connection


def file_manifest(data_dir):
    excluded = {'directory-backup', 'diagnostics', '__pycache__'}
    files = {}
    for path in sorted(Path(data_dir).rglob('*')):
        rel = path.relative_to(data_dir)
        if path.name == 'community_registry.sqlite3':
            continue
        if path.is_file() and not excluded.intersection(rel.parts):
            if path.suffix in {'.json', '.jsonl', '.geojson'}:
                files[str(rel)] = hashlib.sha256(path.read_bytes()).hexdigest()
            elif path.suffix == '.sqlite3':
                with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as conn:
                    files[str(rel)] = hashlib.sha256('\n'.join(conn.iterdump()).encode()).hexdigest()
    return files


def fingerprint(db, manifest):
    tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    values = {name: sorted([list(r) for r in db.execute('SELECT * FROM "' + name.replace('"', '""') + '"')], key=dump) for name in tables}
    return hashlib.sha256(dump({'rule': VERSION, 'tables': values, 'schema': [r[0] for r in db.execute("SELECT sql FROM sqlite_master ORDER BY name")], 'files': manifest}).encode()).hexdigest()


def preview(data_dir):
    data_dir = Path(data_dir).resolve()
    path = data_dir / 'community_registry.sqlite3'
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as source, sqlite3.connect(':memory:') as db:
        source.backup(db)
        db.row_factory = sqlite3.Row
        registry = SnapshotRegistry(db, path)
        files = file_manifest(data_dir)
        snapshot = fingerprint(db, files)
        from src.services.community_admission import community_views
        old = {c['community_id']: c for c in community_views(registry, data_dir)}
        previous = db.execute('SELECT value FROM meta WHERE key=?', (KEY,)).fetchone()
        db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (KEY, VERSION))
        materialize(registry, db, property_facts(data_dir))
        rows = inventory(registry, data_dir)
        catalog_ids = {r['community_id'] for r in rows}
        for c in community_views(registry, data_dir):
            if c['community_id'] not in catalog_ids:
                rows.append({**c, 'sources': [s for s in registry.sources() if s['community_id'] == c['community_id']]})
        changes = []
        for row in rows:
            prior = old.get(row['community_id'], {})
            a = prior.get('admission', {})
            changes.append(dict(community_id=row['community_id'], name=row['community_name'],
                source_ids=[s['id'] for s in row['sources']], before=prior.get('admission_state', 'unlinked'),
                after=row['admission_state'], reason=row['exclusion_reason'], qualification=row['qualification'],
                map_before=prior.get('map_status'), map_after=row.get('map_status'),
                rental_sources=sum(s['source'] == 'fang' for s in row['sources']),
                auction_sources=sum(s['source'] == 'laipai' for s in row['sources']),
                facts_state=row['facts_state'], catalog_visible=row['community_id'] in catalog_ids, manual_protected=a.get('decision_kind') == 'manual',
                manual_conflict=a.get('decision_kind') == 'manual' and a.get('state') != row['admission_state']))
        new_views = community_views(registry, data_dir)
        if file_manifest(data_dir) != files:
            raise ValueError('业务文件在预演期间变化，请重试')
        return dict(version=VERSION, snapshot_id=snapshot, active=bool(previous and previous[0] == VERSION),
                    files=files, changes=changes, totals={
                        'admitted': sum(c['admission_state'] == 'admitted' for c in new_views),
                        'excluded': sum(r['admission_state'] != 'admitted' and r['community_id'] in catalog_ids for r in rows),
                        'historical_only': sum(r['community_id'] not in catalog_ids for r in rows),
                        'incomplete': sum(r['facts_state'] == 'incomplete' for r in rows),
                        'auction_pending': len(auction_tasks(registry, data_dir)),
                        'manual_conflicts': sum(r['manual_conflict'] for r in changes)})


def apply(data_dir, plan, backup_dir, *, maintenance=False):
    if not maintenance:
        raise ValueError('执行迁移需先停止后端与CLI采集，使用maintenance确认维护窗口')
    if plan.get('version') != VERSION:
        raise ValueError('迁移规则已变化，请重新预演')
    data_dir, backup_dir = Path(data_dir).resolve(), Path(backup_dir).resolve()
    if backup_dir == data_dir or data_dir in backup_dir.parents:
        raise ValueError('备份必须放在数据目录之外')
    path = data_dir / 'community_registry.sqlite3'
    # Instantiate without schema initialization; no implicit prepare/import.
    registry = CommunityRegistry.__new__(CommunityRegistry)
    registry.path = path
    with registry.db() as db:
        current_files = file_manifest(data_dir)
        if fingerprint(db, current_files) != plan['snapshot_id']:
            raise ValueError('预演快照已变化，请重新预演')
        previous = db.execute('SELECT value FROM meta WHERE key=?', (KEY,)).fetchone()
        if previous and previous[0] == VERSION:
            return {'already_applied': True}
        for r in db.execute("SELECT value FROM meta WHERE key IN ('collection_job','directory_position_job')"):
            if json.loads(r[0]).get('running'):
                raise ValueError('存在未结束的采集任务，请先取消或重启恢复中断状态')
        rental_job = data_dir / 'rentals' / 'refresh_job.json'
        if rental_job.exists() and json.loads(rental_job.read_text()).get('running'):
            raise ValueError('租金采集尚未结束，请先停止采集')
        backup_dir.mkdir(parents=True, exist_ok=False)
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as src, sqlite3.connect(backup_dir / path.name) as dst:
            src.backup(dst)
        for name in current_files:
            target = backup_dir / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.suffix == '.sqlite3':
                with sqlite3.connect((data_dir / name).as_uri() + '?mode=ro', uri=True) as src, sqlite3.connect(target) as dst:
                    src.backup(dst)
            else:
                shutil.copy2(data_dir / name, target)
        (backup_dir / 'plan.json').write_text(dump(plan))
        if file_manifest(data_dir) != current_files:
            raise ValueError('备份期间业务文件变化，请重新预演')
        db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (KEY, VERSION))
        db.execute("INSERT OR REPLACE INTO meta VALUES ('auto_review_enabled','false')")
        created = materialize(registry, db, property_facts(data_dir))
        registry._event(db, None, 'directory_flow_migration', {'version': VERSION, 'snapshot_id': plan['snapshot_id'],
                                                            'backup_dir': str(backup_dir), 'created': created})
        after = fingerprint(db, current_files)
        receipt = dict(version=VERSION, snapshot_id=plan['snapshot_id'], after_snapshot=after,
                       files=current_files, created=created, executed_at=now())
        (backup_dir / 'receipt.json').write_text(dump(receipt))
    return receipt


def rollback(data_dir, backup_dir, *, maintenance=False):
    if not maintenance:
        raise ValueError('回滚需先停止后端与CLI采集并确认maintenance')
    data_dir, backup_dir = Path(data_dir).resolve(), Path(backup_dir).resolve()
    receipt = json.loads((backup_dir / 'receipt.json').read_text())
    target = data_dir / 'community_registry.sqlite3'
    with sqlite3.connect(target) as db:
        db.execute('BEGIN IMMEDIATE')
        if fingerprint(db, file_manifest(data_dir)) != receipt['after_snapshot']:
            raise ValueError('迁移后已有新数据，禁止整库回滚；请按审计定向恢复')
        # Restore tables within the same transaction, retaining the lock throughout.
        db.execute('ATTACH DATABASE ? AS previous', (str(backup_dir / target.name),))
        db.execute('PRAGMA defer_foreign_keys=ON')
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        for name in tables:
            safe = '"' + name.replace('"', '""') + '"'
            db.execute('DELETE FROM ' + safe)
        for name in tables:
            safe = '"' + name.replace('"', '""') + '"'
            db.execute('INSERT INTO main.' + safe + ' SELECT * FROM previous.' + safe)
    return {'rolled_back': True}
