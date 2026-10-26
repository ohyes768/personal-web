"""Offline, preview-first rollout of the candidate/location/use admission pipeline."""
import json
import shutil
import sqlite3
from pathlib import Path

from src.services.collection_pipeline import KEY, RULE, enabled
from src.services.community_admission import property_facts
from src.services.community_registry import CommunityRegistry, dump, now
from src.services.directory_migration import SnapshotRegistry, file_manifest, fingerprint
from src.services.directory_policy import enabled as flow_enabled
from src.services.directory_workflow import inventory, materialize


def activate(registry, db, data_dir):
    if not flow_enabled(db):
        raise ValueError('请先完成透明售房网名单流程迁移')
    db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (KEY, RULE))
    for row in db.execute('SELECT id,payload FROM communities').fetchall():
        payload = json.loads(row['payload'])
        payload[KEY] = RULE
        db.execute('UPDATE communities SET payload=? WHERE id=?', (dump(payload), row['id']))
    return materialize(registry, db, property_facts(data_dir))


def preview(data_dir):
    data_dir = Path(data_dir).resolve()
    path = data_dir / 'community_registry.sqlite3'
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as source, sqlite3.connect(':memory:') as db:
        source.backup(db)
        db.row_factory = sqlite3.Row
        registry = SnapshotRegistry(db, path)
        files = file_manifest(data_dir)
        snapshot = fingerprint(db, files)
        old = {r['community_id']: r for r in inventory(registry, data_dir)}
        active_before = enabled(db)
        created = activate(registry, db, data_dir)
        rows = inventory(registry, data_dir)
        changes = []
        for row in rows:
            prior = old.get(row['community_id'], {})
            admission = row.get('admission') or {}
            changes.append(dict(community_id=row['community_id'], name=row['community_name'],
                before=prior.get('admission_state', 'unlinked'), after=row['admission_state'],
                workflow_state=row.get('workflow_state', 'pending'), qualification=row['qualification'],
                reason=row['exclusion_reason'], source_ids=[s['id'] for s in row['sources']],
                map_before=prior.get('map_status'), map_after=row.get('map_status'),
                leaving_collection_targets=prior.get('admission_state') == 'admitted' and row['admission_state'] != 'admitted',
                preserved_rental_sources=sum(s['source'] in {'fang', 'xingfuli'} for s in row['sources']),
                preserved_auction_sources=sum(s['source'] == 'laipai' for s in row['sources']),
                manual_protected=admission.get('decision_kind') == 'manual'))
        if file_manifest(data_dir) != files or fingerprint(source, files) != snapshot:
            raise ValueError('预演期间资料变化，请重新预演')
        return dict(version=RULE, snapshot_id=snapshot, active=active_before, files=files, changes=changes,
            totals=dict(created_candidates=created, admitted=sum(r['after'] == 'admitted' for r in changes),
                pending=sum(r['workflow_state'] == 'pending' for r in changes),
                excluded=sum(r['workflow_state'] == 'excluded' for r in changes),
                withdrawn=sum(r['leaving_collection_targets'] for r in changes)))


def apply(data_dir, plan, backup_dir, *, maintenance=False):
    if not maintenance:
        raise ValueError('执行需停止后端、定时任务与CLI，确认维护窗口 maintenance')
    if plan.get('version') != RULE:
        raise ValueError('迁移版本变化，请重新预演')
    data_dir, backup_dir = Path(data_dir).resolve(), Path(backup_dir).resolve()
    if data_dir == backup_dir or data_dir in backup_dir.parents:
        raise ValueError('备份必须位于数据目录之外')
    path = data_dir / 'community_registry.sqlite3'
    registry = CommunityRegistry.__new__(CommunityRegistry)
    registry.path = path
    with registry.db() as db:
        files = file_manifest(data_dir)
        if fingerprint(db, files) != plan['snapshot_id']:
            raise ValueError('预演快照已变化，请重新预演')
        if enabled(db):
            return {'already_applied': True}
        for row in db.execute("SELECT value FROM meta WHERE key IN ('collection_job','directory_position_job','directory_use_review_job')"):
            if json.loads(row[0]).get('running'):
                raise ValueError('存在运行中的采集任务，请先停止')
        rental_job = data_dir / 'rentals' / 'refresh_job.json'
        if rental_job.exists() and json.loads(rental_job.read_text(encoding='utf-8')).get('running'):
            raise ValueError('租金采集尚未结束，请先停止')
        backup_dir.mkdir(parents=True, exist_ok=False)
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as source, sqlite3.connect(backup_dir / path.name) as target:
            source.backup(target)
        for name in files:
            target = backup_dir / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.suffix == '.sqlite3':
                with sqlite3.connect((data_dir / name).as_uri() + '?mode=ro', uri=True) as source, sqlite3.connect(target) as dest:
                    source.backup(dest)
            else:
                shutil.copy2(data_dir / name, target)
        (backup_dir / 'plan.json').write_text(dump(plan), encoding='utf-8')
        if file_manifest(data_dir) != files:
            raise ValueError('备份期间业务文件变化，请重新预演')
        created = activate(registry, db, data_dir)
        registry._event(db, None, 'collection_pipeline_migration', {'version': RULE,
            'snapshot_id': plan['snapshot_id'], 'created': created, 'backup_dir': str(backup_dir)})
        receipt = dict(version=RULE, snapshot_id=plan['snapshot_id'], files=files,
                       after_snapshot=fingerprint(db, files), created=created, executed_at=now())
        (backup_dir / 'receipt.json').write_text(dump(receipt), encoding='utf-8')
    return receipt


def rollback(data_dir, backup_dir, *, maintenance=False):
    from src.services.directory_migration import rollback as restore
    receipt = json.loads((Path(backup_dir) / 'receipt.json').read_text(encoding='utf-8'))
    if receipt.get('version') != RULE:
        raise ValueError('备份不是住宅采集流程迁移记录')
    return restore(data_dir, backup_dir, maintenance=maintenance)
