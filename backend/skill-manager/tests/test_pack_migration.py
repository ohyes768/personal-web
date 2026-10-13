from src.models import RegistrySkill
from tests.test_github_packs import URL, pack_env, service
from src.db import DeploymentRecord


def test_migration_preserves_legacy_offline(pack_env, monkeypatch):
    _, store, cache, _ = pack_env
    store.upsert_registry_skill(RegistrySkill(id='legacy-alpha', name='Alpha', source='github', path='skills/alpha', repository=URL, tags=['old']))
    store.upsert_deployment(DeploymentRecord('legacy-alpha','hermes','old','old','snapshot','active','then'))
    monkeypatch.setattr(cache, '_run_git', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('git during migration')))
    svc = service(pack_env)
    svc.migrate_legacy()
    svc.migrate_legacy()
    assert len(svc.list()) == 1
    pack = svc.list()[0]
    assert pack.source_missing
    assert pack.deployments['hermes'].status == 'legacy_pending'
    assert store.get_pack_for_skill('legacy-alpha') == pack.id
    assert store.get_registry_skill('legacy-alpha').tags == ['old']
    assert store.get_deployment('legacy-alpha','hermes').status == 'active'


def test_deleted_pack_tombstone_does_not_remigrate(pack_env):
    _, store, _, _ = pack_env
    store.upsert_registry_skill(RegistrySkill(id='legacy-alpha', name='Alpha', source='github', path='skills/alpha', repository=URL))
    svc = service(pack_env); svc.migrate_legacy(); pack_id = store.get_pack_for_skill('legacy-alpha')
    store.delete_pack(pack_id)
    svc.migrate_legacy()
    assert svc.list() == []
    assert store.get_pack_for_skill('legacy-alpha') == pack_id

def test_pack_ids_separate_owner_repo_boundaries(pack_env):
    svc = service(pack_env)
    left = svc._id('https://github.com/a-b/c')
    right = svc._id('https://github.com/a/b-c')
    assert left != right
    assert len(left) <= 63 and len(right) <= 63

def test_migration_does_not_overwrite_existing_pack_metadata(pack_env):
    _, store, _, _ = pack_env
    store.upsert_registry_skill(RegistrySkill(id='legacy-alpha', name='Alpha', source='github', path='skills/alpha', repository=URL, tags=['legacy']))
    svc = service(pack_env); svc.migrate_legacy()
    pack = store.list_packs()[0]; pack.tags = ['edited']; store.upsert_pack(pack)
    svc.migrate_legacy()
    assert store.get_pack(pack.id).tags == ['edited']
