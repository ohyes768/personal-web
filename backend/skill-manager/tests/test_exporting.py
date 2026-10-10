import sqlite3

from src.db import SkillStateStore


def test_old_deployment_database_migrates(tmp_path):
    database = tmp_path / 'old.sqlite3'
    with sqlite3.connect(database) as conn:
        conn.execute('CREATE TABLE deployment (skill_id TEXT, target TEXT, source_revision TEXT, source_path TEXT, current_link_target TEXT, status TEXT, published_at TEXT, PRIMARY KEY (skill_id, target))')
        conn.execute("INSERT INTO deployment VALUES ('alpha', 'windows-codex', '', 'alpha', 'export', 'active', '')")
    store = SkillStateStore(database)
    assert store.get_deployment('alpha', 'windows-codex').content_hash == ''
    assert store.get_export_target('windows-codex').deployment_count == 1
    assert SkillStateStore(database).get_deployment('alpha', 'windows-codex').content_hash == ''


def test_snapshot_hash_changes_with_content_and_names(tmp_path):
    from src.services.exporting import dir_hash, snapshot_files
    path = tmp_path / 'a.txt'
    path.write_bytes(b'first')
    first = dir_hash(tmp_path)
    path.write_bytes(b'second')
    second = dir_hash(tmp_path)
    assert first != second
    path.rename(tmp_path / 'b.txt')
    assert second != dir_hash(tmp_path)
    git = tmp_path / '.git'
    git.mkdir()
    (git / 'secret').write_text('excluded')
    assert [name for name, _ in snapshot_files(tmp_path)] == ['b.txt']


def test_startup_republish_skips_export_records(tmp_path):
    from unittest.mock import Mock
    from src.db import DeploymentRecord
    from src.services.migration import republish_active_github_skills

    store = SkillStateStore(tmp_path / 'state.sqlite3')
    store.upsert_deployment(DeploymentRecord('alpha', 'windows-codex', '', 'alpha', 'export', 'active', '', 'hash'))
    store.upsert_deployment(DeploymentRecord('alpha', 'custom-device', '', 'alpha', 'export', 'active', '', 'hash'))
    registry = Mock()
    publisher = Mock()
    assert republish_active_github_skills(Mock(), registry, store, publisher, Mock()) == 0
    registry.get.assert_not_called()
    publisher.stage_github_skill.assert_not_called()
    assert not store.list_history()
