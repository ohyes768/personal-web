import pytest

from src.db import DeploymentRecord, HistoryEntry, SkillStateStore
from src.models import CreateExportTarget, UpdateExportTarget


def test_deleted_defaults_are_not_reseeded_and_edits_persist(tmp_path):
    path = tmp_path / 'state.sqlite3'
    store = SkillStateStore(path)
    store.update_export_target('windows-claude', UpdateExportTarget(name='我的 Claude', enabled=False))
    store.delete_export_target('windows-codex')
    restarted = SkillStateStore(path)
    assert restarted.get_export_target('windows-codex') is None
    assert restarted.get_export_target('windows-claude').name == '我的 Claude'
    assert not restarted.get_export_target('windows-claude').enabled


@pytest.mark.parametrize('change,code', [('disable', 'target_disabled'), ('delete', 'invalid_target')])
def test_record_export_rechecks_configuration_after_snapshot(tmp_path, change, code):
    store = SkillStateStore(tmp_path / 'state.sqlite3')
    store.create_export_target(CreateExportTarget(id='device', name='设备'))
    assert store.get_export_target('device').enabled
    if change == 'disable':
        store.update_export_target('device', UpdateExportTarget(enabled=False))
    else:
        store.delete_export_target('device')
    record = DeploymentRecord('alpha', 'device', '', 'alpha', 'export', 'active', '', 'hash')
    history = HistoryEntry('alpha', 'device', 'export', 'ok', None, 'export', '', None, '')
    with pytest.raises(ValueError, match=code):
        store.record_export(record, history)
    assert not store.list_deployments()
    assert not store.list_history()


def test_any_deployment_row_prevents_deletion(tmp_path):
    store = SkillStateStore(tmp_path / 'state.sqlite3')
    store.upsert_deployment(DeploymentRecord('alpha', 'windows-codex', '', 'alpha', 'export', 'removed', ''))
    with pytest.raises(ValueError, match='target_in_use'):
        store.delete_export_target('windows-codex')
    assert store.get_export_target('windows-codex').deployment_count == 1
