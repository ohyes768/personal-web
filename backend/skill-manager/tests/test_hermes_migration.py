import importlib.util
from pathlib import Path
import sqlite3

from src.db import SkillStateStore


def test_retired_rows_archived_with_backup_and_idempotence(tmp_path):
    path = tmp_path / 'state.sqlite3'
    SkillStateStore(path)
    with sqlite3.connect(path) as conn:
        conn.execute("DELETE FROM state_migration WHERE id='hermes_only_v1'")
        for target in ('openclaw', 'hermes'):
            conn.execute("INSERT INTO deployment VALUES (?,?,?,?,?,?,?,?)", ('alpha',target,'v1','/source','/source','active','now','',))
    store = SkillStateStore(path)
    assert [r.target for r in store.list_deployments()] == ['hermes']
    assert path.with_name(path.name+'.before-hermes-only').exists()
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT target FROM retired_deployment').fetchall() == [('openclaw',)]
    SkillStateStore(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM retired_deployment').fetchone()[0] == 1


def test_cleanup_only_unchanged_owned_links(tmp_path):
    spec = importlib.util.spec_from_file_location('cleanup', Path(__file__).parents[1] / 'scripts/cleanup_retired_target.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    root = tmp_path / 'old-root'; root.mkdir()
    db = tmp_path / 'old.sqlite'
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE deployment (skill_id TEXT,target TEXT,current_link_target TEXT,status TEXT)')
        for name in ('owned','foreign','file'):
            conn.execute('INSERT INTO deployment VALUES (?,?,?,?)', (name,'openclaw','/old/source','active'))
    (root/'owned').symlink_to('/old/source')
    (root/'foreign').symlink_to('/different/source')
    (root/'file').write_text('keep')
    assert module.cleanup(db, root)[0]['status'] == 'would_remove'
    assert (root/'owned').is_symlink()
    module.cleanup(db, root, True)
    assert not (root/'owned').is_symlink()
    assert (root/'foreign').is_symlink()
    assert (root/'file').read_text() == 'keep'
    assert all(r['status'] != 'removed' for r in module.cleanup(db, root, True))
