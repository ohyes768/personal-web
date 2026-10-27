"""Explicit preview/apply for Amap subject addresses; disabling preserves later writes."""
import json

from src.services.community_address import POLICY_KEY as KEY, POLICY_RULE as RULE
from src.services.community_registry import CommunityRegistry, dump
from src.services.collection_pipeline import enabled as pipeline_enabled
from src.services import collection_pipeline_migration as rollout


def enabled(db):
    row = db.execute('SELECT value FROM meta WHERE key=?', (KEY,)).fetchone()
    return bool(row and row[0] == RULE)


def activate(registry, db, data_dir):
    if not pipeline_enabled(db):
        raise ValueError('请先启用候选楼盘主体流程')
    db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (KEY, RULE))
    for row in db.execute('SELECT id,payload FROM communities').fetchall():
        payload = json.loads(row['payload'])
        payload[KEY] = RULE
        db.execute('UPDATE communities SET payload=? WHERE id=?', (dump(payload), row['id']))
    from src.services.directory_workflow import materialize
    from src.services.community_admission import property_facts
    return materialize(registry, db, property_facts(data_dir))


def preview(data_dir):
    return rollout.preview(data_dir, activate_rule=activate, rule=RULE, is_enabled=enabled)


def apply(data_dir, plan, backup_dir, *, maintenance=False):
    return rollout.apply(data_dir, plan, backup_dir, maintenance=maintenance,
                         activate_rule=activate, rule=RULE, is_enabled=enabled)


def disable(data_dir, *, maintenance=False):
    if not maintenance:
        raise ValueError('关闭规则需要 maintenance 维护窗口')
    from pathlib import Path
    registry = CommunityRegistry.__new__(CommunityRegistry)
    registry.path = Path(data_dir) / 'community_registry.sqlite3'
    with registry.db() as db:
        for row in db.execute("SELECT value FROM meta WHERE key IN ('collection_job','directory_position_job','directory_use_review_job')"):
            if json.loads(row[0]).get('running'):
                raise ValueError('存在运行中的采集任务，请先停止')
        db.execute('DELETE FROM meta WHERE key=?', (KEY,))
        for row in db.execute('SELECT id,payload FROM communities').fetchall():
            payload = json.loads(row['payload'])
            payload.pop(KEY, None)
            db.execute('UPDATE communities SET payload=? WHERE id=?', (dump(payload), row['id']))
        registry._event(db, None, 'admission_address_policy_disabled', {'version': RULE})
    return {'disabled': True, 'version': RULE}
