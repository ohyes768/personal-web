"""UI target CRUD operates only on authorized profile skills directories."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import json

import pytest
from tests.test_profiles import roots, base_env, env, source_repo, upstream_repo, client, PASSWORD, PROFILE, preview, execute
from src.config import Settings
from src.db import DeploymentRecord, SkillStateStore
from src.services.targets import TargetResolver


def add_profile(roots,name='third'):
    path=roots.profiles/name/'skills'
    path.mkdir(parents=True)
    return path


def create(client,name='third',password=PASSWORD):
    return client.post('/api/skills/install-targets',json={'profile_name':name,'name':name,'password':password})


def mutate(client,target,revision=1,method='PATCH',**fields):
    return client.request(method,'/api/skills/install-targets/'+target,json={'password':PASSWORD,'expected_revision':revision,**fields})


def test_profile_discovery_and_create_no_restart(client,roots):
    path=add_profile(roots)
    (roots.profiles/'broken').mkdir()
    (roots.profiles/'plain').write_text('not a directory')
    rows=client.get('/api/skills/install-targets/profiles').json()['items']
    assert {r['profile_name'] for r in rows}=={'ohyes768','third','broken'}
    assert next(r for r in rows if r['profile_name']=='broken')['available'] is False
    assert next(r for r in rows if r['profile_name']=='ohyes768')['existing_target_id']==PROFILE
    response=create(client)
    assert response.status_code==201,response.text
    target=response.json()
    assert target['install_path']==str(path) and target['editable'] and target['deletable']
    assert client.app.state.publisher.targets.root(target['id'])==path
    assert create(client).status_code==409
    assert not list(path.iterdir())


def test_rename_delete_restore_and_env_does_not_overwrite(client,roots):
    renamed=mutate(client,PROFILE,name='New name')
    assert renamed.status_code==200 and renamed.json()['config_revision']==2
    reboot=TargetResolver(Settings(),SkillStateStore.from_settings(Settings()))
    assert next(r for r in reboot.catalog() if r.id==PROFILE).name=='New name'
    assert mutate(client,PROFILE,name='stale').json()['code']=='target_changed'
    assert mutate(client,PROFILE,2,'DELETE').status_code==200
    assert roots.profile.exists()
    assert next(r for r in TargetResolver(Settings(),client.app.state.store).catalog() if r.id==PROFILE).removed
    assert client.post('/api/skills/install/preview',json={'skill_ids':['alpha'],'target_ids':[PROFILE]}).status_code==400
    restored=create(client,'ohyes768')
    assert restored.status_code==201 and restored.json()['id']==PROFILE
    assert restored.json()['config_revision']==4
    with closing(client.app.state.store._connect()) as conn:
        audit=[dict(r) for r in conn.execute('SELECT * FROM target_config_history')]
    assert [r['action'] for r in audit]==['rename','delete','restore']
    assert PASSWORD not in json.dumps(audit)


@pytest.mark.requires_symlink
def test_active_and_missing_link_block_deletion_until_unpublish(client,roots):
    assert all(r['status']=='success' for r in execute(client,preview(client))['results'])
    assert mutate(client,PROFILE,1,'DELETE').json()['code']=='target_in_use'
    assert (roots.profile/'alpha').is_symlink()
    (roots.profile/'alpha').unlink()
    assert mutate(client,PROFILE,1,'DELETE').status_code==409
    # Restore a legitimate managed link before normal explicit unpublish.
    (roots.profile/'alpha').symlink_to(roots.source_root/'alpha',target_is_directory=True)
    assert client.request('DELETE',f'/api/skills/alpha/targets/{PROFILE}',json={'password':PASSWORD}).status_code==200
    assert mutate(client,PROFILE,1,'DELETE').status_code==200
    assert roots.profile.exists() and (roots.hermes/'alpha').is_symlink()
    assert client.app.state.store.get_deployment('alpha',PROFILE).status=='removed'
    assert client.app.state.store.list_history(target=PROFILE)


@pytest.mark.parametrize('name',['../outside','ohyes768/skills','.', '..', 'missing', '\\escape'])
def test_invalid_profile_no_side_effect(client,roots,name):
    assert create(client,name).status_code==400
    assert len(client.app.state.store.list_install_targets())==2


def test_password_default_and_uneditable_fields(client,roots):
    add_profile(roots)
    assert create(client,password='wrong').status_code==401
    assert mutate(client,'hermes',1,'DELETE').json()['code']=='reserved_target'
    assert mutate(client,'hermes',name='Changed').status_code==400
    assert mutate(client,PROFILE,name=' ',profile_name='third').status_code==400
    assert mutate(client,PROFILE,name=' ').status_code==400
    assert mutate(client,PROFILE,name=None).status_code==400
    assert len(client.app.state.store.list_install_targets())==2


@pytest.mark.requires_symlink
def test_redirected_and_overlapping_profiles_rejected(client,roots):
    outside=roots.targets/'outside'
    (outside/'skills').mkdir(parents=True)
    (roots.profiles/'escape').symlink_to(outside,target_is_directory=True)
    assert create(client,'escape').status_code==400
    (roots.profiles/'__probe__').symlink_to(outside,target_is_directory=True)
    assert client.get('/api/skills/install-targets/profiles').status_code==200
    add_profile(roots,'linked')
    (roots.profiles/'linked'/'skills').rmdir()
    (roots.profiles/'linked'/'skills').symlink_to(roots.profile,target_is_directory=True)
    assert create(client,'linked').status_code==400


@pytest.mark.parametrize('change',['rename','delete'])
def test_config_mutation_invalidates_existing_install_plan(client,roots,change):
    plan=preview(client)
    response=mutate(client,PROFILE,name='New') if change=='rename' else mutate(client,PROFILE,1,'DELETE')
    assert response.status_code==200
    result=client.post('/api/skills/install',json={'plan_id':plan['plan_id'],'request_id':'x','password':PASSWORD})
    assert result.status_code==409 and result.json()['code']=='stale_plan'
    assert not client.app.state.store.list_deployments()


def test_history_only_catalog_cannot_grant_write_access(client,roots):
    add_profile(roots,'untrusted')
    store=client.app.state.store
    with closing(store._connect()) as conn, conn:
        conn.execute('INSERT INTO install_target (id,profile_name,name,last_root) VALUES (?,?,?,?)',('hermes:profile:untrusted','untrusted','Unknown',str(roots.profiles/'untrusted'/'skills')))
    resolver=TargetResolver(Settings(),store)
    record=next(r for r in resolver.catalog() if r.profile_name=='untrusted')
    assert not record.configured and not record.available


def test_concurrent_duplicate_create_and_revision_guard(client,roots):
    add_profile(roots)
    with ThreadPoolExecutor(2) as pool:
        responses=list(pool.map(lambda _:create(client),range(2)))
    assert sorted(r.status_code for r in responses)==[201,409]
    with ThreadPoolExecutor(2) as pool:
        responses=list(pool.map(lambda name:mutate(client,PROFILE,name=name),['One','Two']))
    assert sorted(r.status_code for r in responses)==[200,409]


def test_legacy_ui_schema_backup_and_seed_preserve_installations(client,roots):
    store=client.app.state.store
    store.upsert_deployment(DeploymentRecord('alpha',PROFILE,'old','source','source','active','original'))
    with closing(store._connect()) as conn,conn:
        conn.execute('ALTER TABLE install_target RENAME TO ui_targets')
        conn.execute("CREATE TABLE install_target (id TEXT PRIMARY KEY,provider TEXT NOT NULL DEFAULT 'hermes',profile_name TEXT NOT NULL,name TEXT NOT NULL,last_root TEXT NOT NULL)")
        conn.execute('INSERT INTO install_target SELECT id,provider,profile_name,name,last_root FROM ui_targets')
        conn.execute('DROP TABLE ui_targets')
        conn.execute("DELETE FROM state_migration WHERE id='install_targets_ui_v1'")
    migrated=SkillStateStore(store.db_path)
    assert store.db_path.with_name(store.db_path.name+'.before-target-ui').exists()
    resolver=TargetResolver(Settings(),migrated)
    assert resolver.root(PROFILE)==roots.profile
    assert migrated.get_deployment('alpha',PROFILE).published_at=='original'
    assert next(t for t in resolver.catalog() if t.id==PROFILE).active_installation_count==1


@pytest.mark.requires_symlink
def test_install_delete_race_cannot_leave_removed_target_active(client,roots):
    plan=preview(client,items=[{'skill_id':'alpha','targets':[PROFILE]}])
    def install():
        return client.post('/api/skills/install',json={'plan_id':plan['plan_id'],'request_id':'race','password':PASSWORD})
    with ThreadPoolExecutor(2) as pool:
        installing=pool.submit(install)
        deleting=pool.submit(lambda:mutate(client,PROFILE,1,'DELETE'))
        installed=installing.result();removed=deleting.result()
    if installed.status_code==202:
        import time
        task_id=installed.json()['task_id']
        for _ in range(300):
            state=client.get('/api/skills/install/tasks/'+task_id).json()
            if state['state']=='done':break
            time.sleep(.01)
        assert state['state']=='done'
    else:
        assert installed.status_code==409
    row=client.app.state.store.get_install_target(PROFILE)
    record=client.app.state.store.get_deployment('alpha',PROFILE)
    if row['removed_at']:
        assert removed.status_code==200
        assert not record or record.status!='active'
        assert not (roots.profile/'alpha').exists()
    else:
        assert removed.status_code==409 and record.status=='active'


def test_candidate_discovery_does_not_read_profile_credentials(client,roots,monkeypatch):
    from pathlib import Path
    (roots.profiles/'ohyes768'/'auth.json').write_text('test credential must not be read')
    def refuse_read(*args,**kwargs):
        pytest.fail('profile discovery must not read file content')
    monkeypatch.setattr(Path,'read_text',refuse_read)
    monkeypatch.setattr(Path,'read_bytes',refuse_read)
    response=client.get('/api/skills/install-targets/profiles')
    assert response.status_code==200
    assert 'credential' not in response.text
