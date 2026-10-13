import subprocess

import pytest

from src.config import Settings
from src.db import SkillStateStore
from src.services.git_cache import GitCacheService

URL = 'https://github.com/example/pack'


def git(*args, cwd=None):
    return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def pack_env(tmp_path):
    roots = {key: tmp_path / key for key in ('source', 'cache', 'hermes', 'openclaw', 'state')}
    for root in roots.values():
        root.mkdir()
    settings = Settings(skills_source_root=roots['source'], github_skill_cache_root=roots['cache'], hermes_skills_root=roots['hermes'], openclaw_skills_root=roots['openclaw'], state_dir=roots['state'], admin_password='test')
    upstream = tmp_path / 'upstream'
    upstream.mkdir()
    git('init', '-b', 'main', cwd=upstream)
    git('config', 'user.email', 'test@example.com', cwd=upstream)
    git('config', 'user.name', 'Test', cwd=upstream)
    skill = upstream / 'skills' / 'alpha'
    skill.mkdir(parents=True)
    (skill / 'SKILL.md').write_text('---\nname: alpha\ndescription: Alpha\n---\nold', encoding='utf-8')
    git('add', '.', cwd=upstream)
    git('commit', '-m', 'initial', cwd=upstream)
    store = SkillStateStore(roots['state'] / 'state.db')
    cache = GitCacheService(settings, store, {URL: upstream.as_posix()})
    return settings, store, cache, upstream


def service(env):
    from src.services.packs import PackService
    return PackService(*env[:3])


def test_add_deduplicates_rootless_repository(pack_env):
    svc = service(pack_env)
    pack = svc.add(URL)
    assert pack.skill_count == 1
    assert pack.inventory[0].path == 'skills/alpha'
    assert svc.add(URL + '.git').id == pack.id
    assert len(svc.list()) == 1
    assert not (pack_env[0].github_skill_cache_root / 'staging').exists()


def test_check_is_read_only_and_update_refuses_dirty(pack_env):
    from src.services.packs import PackError
    svc = service(pack_env)
    pack = svc.add(URL)
    cache = pack_env[2].repo_cache_dir(URL)
    (pack_env[3] / 'skills/alpha/SKILL.md').write_text('---\nname: alpha\n---\nnew')
    git('add', '.', cwd=pack_env[3])
    git('commit', '-m', 'new', cwd=pack_env[3])
    assert svc.check_update(pack.id).has_update
    assert git('rev-parse', 'HEAD', cwd=cache) == pack.current_revision
    (cache / 'dirty').write_text('local')
    with pytest.raises(PackError, match='本地修改') as exc:
        svc.update(pack.id)
    assert exc.value.code == 'dirty_worktree'


@pytest.mark.requires_symlink
def test_root_link_survives_update(pack_env):
    svc = service(pack_env)
    pack = svc.add(URL)
    assert svc.install(pack.id, ['hermes']).items[0].status == 'success'
    link = pack_env[0].hermes_skills_root / pack.id
    inode = link.lstat().st_ino
    destination = link.readlink()
    assert destination == pack_env[2].repo_cache_dir(URL)
    (pack_env[3] / 'skills/alpha/SKILL.md').write_text('---\nname: alpha\n---\nnew')
    git('add', '.', cwd=pack_env[3])
    git('commit', '-m', 'new', cwd=pack_env[3])
    svc.update(pack.id)
    assert link.lstat().st_ino == inode and link.readlink() == destination
    assert 'new' in (link / 'skills/alpha/SKILL.md').read_text()
    assert not svc.get(pack.id).deployments['hermes'].verified
    svc.uninstall(pack.id, 'hermes')
    assert not link.exists()


def test_ff_update_detached_and_diverged_refusal(pack_env):
    from src.services.packs import PackError
    svc = service(pack_env); pack = svc.add(URL)
    path = pack_env[2].repo_cache_dir(URL)
    git('checkout', '--detach', cwd=path)
    (pack_env[3] / 'skills/alpha/SKILL.md').write_text('---\nname: alpha\n---\nupdated')
    git('add', '.', cwd=pack_env[3]); git('commit', '-m', 'new', cwd=pack_env[3])
    updated = svc.update(pack.id)
    assert updated.current_revision != pack.current_revision
    assert git('symbolic-ref', '--short', 'HEAD', cwd=path) == 'main'
    git('config', 'user.email', 'test@example.com', cwd=path); git('config', 'user.name', 'Test', cwd=path)
    (path / 'local').write_text('local'); git('add', '.', cwd=path); git('commit', '-m', 'local', cwd=path)
    with pytest.raises(PackError) as exc: svc.update(pack.id)
    assert exc.value.code == 'branch_diverged'

def test_missing_cache_update_repairs_same_location(pack_env):
    from src.services.publisher import force_remove_tree
    svc = service(pack_env); pack = svc.add(URL)
    path = pack_env[2].repo_cache_dir(URL); force_remove_tree(path)
    assert svc.get(pack.id).source_missing
    assert not svc.update(pack.id).source_missing
    assert path.exists()

def test_conflicts_and_no_openclaw_config_block(pack_env):
    svc = service(pack_env); pack = svc.add(URL)
    (pack_env[0].hermes_skills_root / pack.id).mkdir()
    assert svc.plan(pack.id, ['hermes']).items[0].action == 'blocked'
    assert svc.plan(pack.id, ['openclaw']).items[0].action == 'blocked'

def test_repo_lock_refuses_concurrent_write(pack_env):
    from src.services.packs import PackError
    svc = service(pack_env)
    with svc._lock(URL):
        with pytest.raises(PackError) as exc: svc.add(URL)
    assert exc.value.code == 'repo_busy'


@pytest.mark.requires_symlink
def test_legacy_conversion_failure_restores_links_and_database(pack_env, monkeypatch):
    from src.models import RegistrySkill
    from src.db import DeploymentRecord
    svc = service(pack_env); pack = svc.add(URL)
    store = pack_env[1]
    store.upsert_registry_skill(RegistrySkill(id='legacy-alpha', name='Alpha', source='github', repository=URL, path='skills/alpha'))
    snapshot = pack_env[0].github_skill_cache_root / 'staging' / 'legacy-alpha'; snapshot.mkdir(parents=True)
    (snapshot / 'SKILL.md').write_text('old')
    old = pack_env[0].hermes_skills_root / 'legacy-alpha'; old.symlink_to(snapshot, target_is_directory=True)
    store.upsert_deployment(DeploymentRecord('legacy-alpha','hermes','old','old',str(snapshot),'active','then'))
    svc.migrate_legacy()
    assert svc.get(pack.id).skill_count == 1
    original = store.append_pack_history
    monkeypatch.setattr(store, 'append_pack_history', lambda *a, **kw: (_ for _ in ()).throw(OSError('audit failure')))
    result = svc.install(pack.id, ['hermes'])
    assert result.items[0].status == 'error'
    assert old.is_symlink() and old.resolve() == snapshot
    assert not (pack_env[0].hermes_skills_root / pack.id).exists()
    assert store.get_deployment('legacy-alpha','hermes').status == 'active'
    assert svc.get(pack.id).deployments['hermes'].status == 'legacy_pending'
    monkeypatch.setattr(store, 'append_pack_history', original)
    assert svc.install(pack.id, ['hermes']).items[0].status == 'success'
    assert not old.exists()
    assert store.get_deployment('legacy-alpha','hermes').status == 'removed'
    svc.uninstall(pack.id, 'hermes'); svc.delete(pack.id)
    assert store.get_pack_for_skill('legacy-alpha') == pack.id
    assert store.get_registry_skill('legacy-alpha') is not None

@pytest.mark.requires_symlink
def test_restart_restores_interrupted_conversion(pack_env):
    from src.models import RegistrySkill
    from src.db import DeploymentRecord
    svc = service(pack_env); pack = svc.add(URL); store = pack_env[1]
    store.upsert_registry_skill(RegistrySkill(id='legacy-alpha', name='Alpha', source='github', repository=URL, path='skills/alpha'))
    snapshot = pack_env[0].github_skill_cache_root / 'snapshot'; snapshot.mkdir()
    old = pack_env[0].hermes_skills_root / 'legacy-alpha'; old.symlink_to(snapshot, target_is_directory=True)
    record = DeploymentRecord('legacy-alpha','hermes','old','old',str(snapshot),'active','then')
    store.upsert_deployment(record); svc.migrate_legacy(); pack = svc.get(pack.id)
    svc._write_conversion_journal(pack, 'hermes', [record], None, False)
    (pack_env[0].hermes_skills_root / pack.id).symlink_to(pack_env[2].repo_cache_dir(URL), target_is_directory=True)
    old.unlink()
    restarted = service(pack_env)
    restarted.recover_conversions()
    assert old.is_symlink()
    assert not (pack_env[0].hermes_skills_root / pack.id).exists()
    assert restarted.get(pack.id).deployments['hermes'].status == 'legacy_pending'

def test_local_skill_name_collision_blocks_pack(pack_env):
    svc = service(pack_env); pack = svc.add(URL)
    local = pack_env[0].hermes_skills_root / 'local'; local.mkdir()
    (local / 'SKILL.md').write_text('---\nname: alpha\n---\nlocal')
    assert svc.plan(pack.id, ['hermes']).items[0].action == 'blocked'

def test_update_to_only_hidden_skill_preserves_head(pack_env):
    from src.services.packs import PackError
    from src.services.publisher import force_remove_tree
    svc = service(pack_env); pack = svc.add(URL)
    force_remove_tree(pack_env[3] / 'skills')
    hidden = pack_env[3] / '.hidden'; hidden.mkdir()
    (hidden / 'SKILL.md').write_text('---\nname: hidden\n---')
    git('add', '-A', cwd=pack_env[3]); git('commit', '-m', 'no visible skill', cwd=pack_env[3])
    with pytest.raises(PackError) as exc: svc.update(pack.id)
    assert exc.value.code == 'no_skills'
    assert git('rev-parse','HEAD',cwd=pack_env[2].repo_cache_dir(URL)) == pack.current_revision

@pytest.mark.parametrize('kind', ['duplicate', 'root_overlap'])
def test_candidate_incompatibility_does_not_change_head(pack_env, kind):
    from src.services.packs import PackError
    svc = service(pack_env); pack = svc.add(URL)
    upstream = pack_env[3]
    if kind == 'duplicate':
        directory = upstream / 'skills' / 'beta'; directory.mkdir()
        (directory / 'SKILL.md').write_text('---\nname: alpha\n---\nDuplicate')
    else:
        (upstream / 'SKILL.md').write_text('---\nname: root\n---\nRoot')
    git('add', '.', cwd=upstream); git('commit', '-m', 'incompatible inventory', cwd=upstream)
    with pytest.raises(PackError) as exc: svc.update(pack.id)
    assert exc.value.code == 'target_incompatible'
    assert git('rev-parse', 'HEAD', cwd=pack_env[2].repo_cache_dir(URL)) == pack.current_revision

def test_candidate_name_conflict_keeps_live_checkout(pack_env):
    from src.services.packs import PackError
    from src.models import PackDeployment
    svc = service(pack_env); pack = svc.add(URL)
    pack.deployments['hermes'] = PackDeployment(status='active')
    pack_env[1].upsert_pack(pack)
    local = pack_env[0].hermes_skills_root / 'local'; local.mkdir()
    (local / 'SKILL.md').write_text('---\nname: beta\n---\nLocal')
    (pack_env[3] / 'skills/alpha/SKILL.md').write_text('---\nname: beta\n---\nRenamed')
    git('add', '.', cwd=pack_env[3]); git('commit', '-m', 'name collision', cwd=pack_env[3])
    with pytest.raises(PackError) as exc: svc.update(pack.id)
    assert exc.value.code == 'target_incompatible'
    assert git('rev-parse', 'HEAD', cwd=pack_env[2].repo_cache_dir(URL)) == pack.current_revision

def test_unknown_conversion_target_does_not_block_service(pack_env):
    from src.services.packs import PackError
    svc = service(pack_env); pack = svc.add(URL)
    journal = svc._write_conversion_journal(pack, 'hermes', [], None, False)
    (pack_env[0].hermes_skills_root / pack.id).mkdir()
    restarted = service(pack_env)
    assert restarted.list()[0].id == pack.id
    assert any('转换' in message for message in restarted.get(pack.id).diagnostics)
    with pytest.raises(PackError) as exc: restarted.recover_conversions()
    assert exc.value.code == 'conversion_failed'
    assert journal.exists()

def test_missing_cache_repair_rejects_incompatible_inventory(pack_env):
    from src.services.packs import PackError
    from src.services.publisher import force_remove_tree
    svc = service(pack_env); pack = svc.add(URL)
    path = pack_env[2].repo_cache_dir(URL); force_remove_tree(path)
    directory = pack_env[3] / 'skills/beta'; directory.mkdir()
    (directory / 'SKILL.md').write_text('---\nname: alpha\n---\nDuplicate')
    git('add', '.', cwd=pack_env[3]); git('commit', '-m', 'duplicate', cwd=pack_env[3])
    with pytest.raises(PackError) as exc: svc.update(pack.id)
    assert exc.value.code == 'target_incompatible'
    assert not path.exists()

def test_case_preserved_legacy_cache_is_reused(pack_env, monkeypatch):
    from src.models import RegistrySkill
    settings, store, cache, upstream = pack_env
    legacy = settings.github_skill_cache_root / 'repos' / 'example__Pack'
    legacy.parent.mkdir(); git('clone', upstream.as_posix(), legacy.as_posix())
    store.upsert_registry_skill(RegistrySkill(id='legacy-alpha', name='Alpha', source='github', path='skills/alpha', repository='https://github.com/example/Pack'))
    svc = service(pack_env); svc.migrate_legacy()
    monkeypatch.setattr(cache, '_run_git_streaming', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('second clone')))
    pack = svc.add(URL)
    assert not pack.source_missing and pack.skill_count == 1
    assert svc._repo_dir(URL) == legacy
    assert list(legacy.parent.iterdir()) == [legacy]

def test_ambiguous_case_caches_are_diagnosed(pack_env):
    from src.services.packs import PackError
    settings, _, _, _ = pack_env
    root = settings.github_skill_cache_root / 'repos'; root.mkdir()
    (root / 'example__Pack').mkdir()
    # Windows cannot create two names differing only by case; a synthetic directory
    # inventory is enough to exercise ambiguity without pretending symlink semantics.
    from unittest.mock import patch
    with patch('pathlib.Path.iterdir', return_value=iter([root / 'example__Pack', root / 'example__pack'])):
        with pytest.raises(PackError) as exc: service(pack_env)._repo_dir(URL)
    assert exc.value.code == 'cache_ambiguous'

@pytest.mark.parametrize('operation', ['check_update', 'delete'])
def test_mutation_rereads_state_after_repository_lock(pack_env, monkeypatch, operation):
    from contextlib import contextmanager
    from src.models import PackDeployment
    from src.services.packs import PackError
    svc = service(pack_env); pack = svc.add(URL)
    original_lock = svc._lock
    @contextmanager
    def concurrent_change(repository):
        changed = pack_env[1].get_pack(pack.id)
        changed.deployments['hermes'] = PackDeployment(status='active')
        pack_env[1].upsert_pack(changed)
        with original_lock(repository): yield
    monkeypatch.setattr(svc, '_lock', concurrent_change)
    if operation == 'delete':
        with pytest.raises(PackError) as exc: svc.delete(pack.id)
        assert exc.value.code == 'pack_in_use'
        assert pack_env[2].repo_cache_dir(URL).exists()
    else:
        svc.check_update(pack.id)
        assert pack_env[1].get_pack(pack.id).deployments['hermes'].status == 'active'

@pytest.mark.parametrize('operation', ['delete', 'uninstall', 'repair'])
def test_pending_conversion_blocks_destructive_mutation(pack_env, operation):
    from src.services.packs import PackError
    from src.services.publisher import force_remove_tree
    svc = service(pack_env); pack = svc.add(URL)
    journal = svc._write_conversion_journal(pack, 'hermes', [], None, False)
    if operation == 'repair': force_remove_tree(pack_env[2].repo_cache_dir(URL))
    with pytest.raises(PackError) as exc:
        if operation == 'delete': svc.delete(pack.id)
        elif operation == 'uninstall': svc.uninstall(pack.id, 'hermes')
        else: svc.add(URL)
    assert exc.value.code == 'conversion_failed'
    assert journal.exists()

def test_missing_cache_repair_syncs_active_openclaw_groups(pack_env):
    import json
    from src.models import PackDeployment
    from src.services.openclaw_pack_discovery import OpenClawPackDiscovery
    from src.services.publisher import force_remove_tree
    settings, store, cache, upstream = pack_env
    config = settings.state_dir / 'openclaw.json'; config.write_text('{}')
    settings.openclaw_config_path = config
    svc = service(pack_env); pack = svc.add(URL)
    link = settings.openclaw_skills_root / pack.id
    OpenClawPackDiscovery(config, settings.state_dir).sync(pack.id, link, ['skills/alpha'])
    pack.deployments['openclaw'] = PackDeployment(status='active', link_target=str(cache.repo_cache_dir(URL)))
    store.upsert_pack(pack)
    force_remove_tree(cache.repo_cache_dir(URL))
    (upstream / 'skills').rename(upstream / 'codex-skills')
    git('add', '-A', cwd=upstream); git('commit', '-m', 'relocate group', cwd=upstream)
    repaired = svc.update(pack.id)
    assert not repaired.source_missing
    dirs = json.loads(config.read_text())['skills']['load']['extraDirs']
    assert str(link / 'codex-skills') in dirs
    assert str(link / 'skills') not in dirs
    assert (cache.repo_cache_dir(URL) / 'codex-skills/alpha/SKILL.md').is_file()
