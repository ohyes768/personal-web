"""Real filesystem multi-profile contracts; no network or Hermes runtime claims."""
import json
import time
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from tests.test_api import (roots, env as base_env, source_repo, upstream_repo, client,
                      PASSWORD, _register_via_task, _await_task)
from src.config import Settings
from src.db import SkillStateStore, DeploymentRecord
from src.services.targets import TargetResolver

PROFILE = 'hermes:profile:ohyes768'


@pytest.fixture
def env(base_env, roots, monkeypatch):
    roots.profiles = roots.targets / 'profiles'
    roots.profile = roots.profiles / 'ohyes768' / 'skills'
    roots.profile.mkdir(parents=True)
    monkeypatch.setenv('SKILL_MANAGER_HERMES_PROFILES_ROOT',str(roots.profiles))
    monkeypatch.setenv('SKILL_MANAGER_HERMES_TARGETS', json.dumps([
        dict(id='hermes', name='默认环境', profile_name='default', skills_root=str(roots.hermes)),
        dict(id=PROFILE, name='ohyes768', profile_name='ohyes768', skills_root=str(roots.profile)),
    ]))


def preview(client, ids=None, **kwargs):
    body = kwargs or {'skill_ids': ids or ['alpha'], 'target_ids': ['hermes', PROFILE]}
    response = client.post('/api/skills/install/preview', json=body)
    assert response.status_code == 200, response.text
    return response.json()


def execute(client, plan):
    response = client.post('/api/skills/install', json={'plan_id': plan['plan_id'], 'request_id': plan['plan_id'], 'password': PASSWORD})
    assert response.status_code == 202, response.text
    task_id = response.json()['task_id']
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        task = client.get(f'/api/skills/install/tasks/{task_id}').json()
        if task['state'] == 'done':
            return task
        time.sleep(.01)
    pytest.fail('install task timed out')


def test_catalog_two_and_three_targets_without_source_changes(client, roots):
    items = client.get('/api/skills/install-targets').json()['items']
    assert {i['id'] for i in items} == {'hermes', PROFILE}
    assert all(i['available'] and i['configured'] for i in items)
    extra = roots.profiles / 'third' / 'skills'
    extra.mkdir(parents=True)
    response = client.post('/api/skills/install-targets',json={'profile_name':'third','name':'Third','password':PASSWORD})
    assert response.status_code==201
    assert len(client.get('/api/skills/install-targets').json()['items']) == 3


@pytest.mark.requires_symlink
def test_two_targets_and_independent_unpublish(client, roots):
    plan = preview(client)
    assert {i['target'] for i in plan['items']} == {'hermes', PROFILE}
    task = execute(client, plan)
    assert all(i['status'] == 'success' for i in task['results'])
    assert (roots.hermes/'alpha').resolve() == (roots.profile/'alpha').resolve() == roots.source_root/'alpha'
    card = client.get('/api/skills').json()['items'][0]
    assert set(card['deployments']) == {'hermes', PROFILE}
    assert client.request('DELETE', f'/api/skills/alpha/targets/{PROFILE}', json={'password': PASSWORD}).status_code == 200
    assert (roots.hermes/'alpha').is_symlink() and not (roots.profile/'alpha').exists()
    assert (roots.source_root/'alpha/SKILL.md').is_file()


@pytest.mark.requires_symlink
def test_partial_conflict_retries_only_failed_pair(client, roots):
    (roots.profile/'alpha').mkdir()
    plan = preview(client)
    task = execute(client, plan)
    assert [(r['target'], r['status']) for r in task['results']] == [('hermes', 'success'), (PROFILE, 'blocked')]
    original = (roots.hermes/'alpha').lstat().st_ino
    (roots.profile/'alpha').rmdir()
    retry = preview(client, items=[{'skill_id': 'alpha', 'targets': [PROFILE]}])
    assert len(retry['items']) == 1
    assert execute(client, retry)['results'][0]['status'] == 'success'
    assert (roots.hermes/'alpha').lstat().st_ino == original


@pytest.mark.parametrize('body', [
    {'skill_ids': ['alpha'], 'target_ids': []},
    {'skill_ids': ['alpha'], 'target_ids': ['hermes:profile:unknown']},
    {'skill_ids': ['alpha'], 'target_ids': ['../outside']},
    {'items': []}, {'items': [{'skill_id':'alpha','targets':[]} ]},
    {'items': [{'skill_id':'alpha','targets':['hermes']}], 'skill_ids':['alpha']},
])
def test_bad_target_inputs_have_no_install_side_effects(client, roots, body):
    assert client.post('/api/skills/install/preview', json=body).status_code == 400
    assert not list(roots.hermes.iterdir()) and not list(roots.profile.iterdir())
    assert not client.app.state.store.list_deployments()


def test_wrong_password_has_no_side_effects(client, roots):
    plan = preview(client)
    assert client.post('/api/skills/install', json={'plan_id':plan['plan_id'],'request_id':'x','password':'wrong'}).status_code == 401
    assert not client.app.state.store.list_deployments()


@pytest.mark.parametrize('change', ['replace_root', 'occupy_link', 'source', 'config'])
def test_changes_invalidate_plan(client, roots, change):
    plan = preview(client)
    if change == 'replace_root':
        roots.profile.rename(roots.targets/'old-profile')
        roots.profile.mkdir()
    elif change == 'config':
        client.app.state.store.mutate_install_target(PROFILE,1,'renamed')
    elif change == 'occupy_link':
        (roots.profile/'alpha').mkdir()
    else:
        (roots.source_root/'alpha/SKILL.md').write_text('changed')
    response = client.post('/api/skills/install', json={'plan_id':plan['plan_id'],'request_id':'x','password':PASSWORD})
    assert response.status_code == 409 and response.json()['code'] == 'stale_plan'
    assert not client.app.state.store.list_deployments()


@pytest.mark.requires_symlink
def test_idempotent_submit(client, roots):
    plan = preview(client)
    task = execute(client, plan)
    count = len(client.app.state.store.list_history())
    duplicate = client.post('/api/skills/install', json={'plan_id':plan['plan_id'],'request_id':plan['plan_id'],'password':PASSWORD})
    assert duplicate.json()['task_id'] == task['task_id']
    assert len(client.app.state.store.list_history()) == count


def test_missing_target_degrades_without_creating_directory(client, roots):
    roots.profile.rmdir()
    items = client.get('/api/skills/install-targets').json()['items']
    assert next(i for i in items if i['id'] == PROFILE)['available'] is False
    assert not roots.profile.exists()
    assert preview(client, skill_ids=['alpha'])['items'][0]['target'] == 'hermes'
    assert client.post('/api/skills/alpha/export', json={'target':'windows-codex'}).status_code == 200


@pytest.mark.requires_symlink
def test_active_target_cannot_change_root_and_offline_records_protect_source(client, roots):
    skill_id = _register_via_task(client)
    execute(client, preview(client, [skill_id]))
    store = client.app.state.store
    settings = Settings()
    settings.hermes_targets[1].skills_root = roots.targets/'replacement'
    settings.hermes_targets[1].skills_root.mkdir()
    # Env named targets no longer override the persistent identity after seed.
    assert TargetResolver(settings,store).root(PROFILE)==roots.profile
    settings.hermes_profiles_root = roots.targets/'unavailable-profiles'
    settings.hermes_profiles_root.mkdir()
    resolver = TargetResolver(settings, store)
    unavailable = next(i for i in resolver.catalog() if i.id == PROFILE)
    assert unavailable.configured and not unavailable.available
    # A historical profile is still a link installation, never an export.
    client.app.state.settings = settings
    client.app.state.publisher.targets = resolver
    response = client.get('/api/skills')
    card = next(i for i in response.json()['items'] if i['id'] == skill_id)
    assert card['deployments'][PROFILE]['link_missing']
    client.request('DELETE', f'/api/skills/{skill_id}/targets/hermes', json={'password':PASSWORD})
    assert client.request('DELETE', f'/api/skills/{skill_id}', json={'password':PASSWORD}).status_code == 409
    assert client.delete(f'/api/skills/{skill_id}/exports/{PROFILE}').status_code == 400


@pytest.mark.parametrize('kind', ['duplicate_id', 'overlap', 'relative', 'empty'])
def test_config_rejects_ambiguous_roots(env, roots, kind):
    config = json.loads(__import__('os').environ['SKILL_MANAGER_HERMES_TARGETS'])
    if kind == 'duplicate_id': config[1]['id'] = 'hermes'
    if kind == 'overlap': config[1]['skills_root'] = str(roots.hermes/'nested')
    if kind == 'relative': config[1]['skills_root'] = 'relative'
    if kind == 'empty': config = []
    with pytest.raises(ValidationError):
        Settings(hermes_targets=config)

@pytest.mark.requires_symlink
def test_candidate_registers_once_and_retries_exact_target_pairs(client, roots, monkeypatch):
    scan_created = client.post('/api/skills/github/scan', json={'repository':'https://github.com/example/two-skills'}).json()
    scan = _await_task(client, scan_created['task_id'])
    registry = client.app.state.registry
    upserts = Mock(wraps=registry.upsert)
    monkeypatch.setattr(registry, 'upsert', upserts)
    candidate = dict(path=scan['candidates'][0]['path'], name='new', tags=[], summary='')
    # Only the named target is chosen; legacy default does not get a link.
    first = preview(client, scan_task_id=scan['task_id'], candidates=[{**candidate, 'targets':[PROFILE]}])
    result = execute(client, first)['results'][0]
    assert result['status'] == 'success' and result['target'] == PROFILE
    assert upserts.call_count == 1
    assert not list(roots.hermes.iterdir())
    # Same scanned identity resolves to its registration and doesn't re-register.
    retry = preview(client, scan_task_id=scan['task_id'], candidates=[{**candidate, 'targets':['hermes', PROFILE]}])
    assert execute(client, retry)['results'][0]['status'] == 'success'
    assert upserts.call_count == 1


@pytest.mark.requires_symlink
def test_shared_update_reports_unselected_profile_and_updates_cache_once(client, roots, monkeypatch, upstream_repo, tmp_path):
    from tests.test_api import run_git, CANONICAL_URL
    from src.api.dependencies import get_git_cache
    scan_created = client.post('/api/skills/github/scan', json={'repository':CANONICAL_URL}).json()
    scan = _await_task(client, scan_created['task_id'])
    candidates = [dict(path=c['path'], name=c['name'], tags=[], summary='') for c in scan['candidates']]
    initial = preview(client, scan_task_id=scan['task_id'], candidates=candidates, target_ids=['hermes', PROFILE])
    results = execute(client, initial)['results']
    ids = list(dict.fromkeys(r['skill_id'] for r in results))
    work = tmp_path/'new-upstream'
    run_git('clone', str(upstream_repo.bare), str(work))
    run_git('config', 'user.name', 'Fixture', cwd=work)
    run_git('config', 'user.email', 'fixture@example.com', cwd=work)
    for c in candidates:
        (work/c['path']/'SKILL.md').write_text('version two')
    run_git('commit', '-am', 'v2', cwd=work)
    run_git('push', cwd=work)
    assert client.post('/api/skills/check-updates', json={'skill_ids':ids}).status_code == 200
    plan = preview(client, skill_ids=ids, target_ids=['hermes'])
    assert {(i['skill_id'],i['target']) for i in plan['affected_installations']} == {(id,t) for id in ids for t in ['hermes',PROFILE]}
    cache = client.app.dependency_overrides[get_git_cache]()
    prepares = Mock(wraps=cache.ensure_cached)
    monkeypatch.setattr(cache, 'ensure_cached', prepares)
    assert all(r['status'] == 'success' for r in execute(client, plan)['results'])
    assert prepares.call_count == 1
    assert all((roots.profile/id/'SKILL.md').read_text() == 'version two' for id in ids)
    cards = client.get('/api/skills').json()['items']
    for card in cards:
        if card['id'] in ids:
            assert not card['update']['has_update']
            assert card['deployments'][PROFILE]['revision'] == card['deployments']['hermes']['revision']


@pytest.mark.requires_symlink
def test_affected_installation_set_change_requires_new_confirmation(client, roots, monkeypatch):
    from src.db import GithubCheckRecord
    skill_id = _register_via_task(client)
    store = client.app.state.store
    record = store.get_registry_skill(skill_id)
    cache = client.app.dependency_overrides[__import__('src.api.dependencies', fromlist=['get_git_cache']).get_git_cache]()
    store.upsert_github_check(GithubCheckRecord(skill_id, str(record.repository), 'future', '', cache.current_revision(record), 'ok', None, 'now'))
    plan = preview(client, skill_ids=[skill_id], target_ids=['hermes'])
    store.upsert_deployment(DeploymentRecord(skill_id, PROFILE, '', '', '', 'active', 'now'))
    response = client.post('/api/skills/install', json={'plan_id':plan['plan_id'],'request_id':'x','password':PASSWORD})
    assert response.status_code == 409 and response.json()['code'] == 'stale_plan'


def test_first_catalog_does_not_redirect_legacy_hermes(env, roots):
    from contextlib import closing
    store = SkillStateStore.from_settings(Settings())
    store.upsert_deployment(DeploymentRecord('alpha','hermes','v1','source','source','active','old'))
    settings = Settings()
    settings.hermes_targets[0].skills_root = roots.targets/'new-default'
    settings.hermes_targets[0].skills_root.mkdir()
    with pytest.raises(ValueError, match='original HERMES_SKILLS_ROOT'):
        TargetResolver(settings,store)
    settings = Settings()
    resolver = TargetResolver(settings,store)
    assert resolver.root('hermes') == roots.hermes
    assert store.get_deployment('alpha','hermes').published_at == 'old'
    assert store.get_deployment('alpha',PROFILE) is None
    # Simulate the pre-profile schema and ensure the additive migration backs up.
    with closing(store._connect()) as conn, conn:
        conn.execute('DROP TABLE install_target')
        conn.execute("DELETE FROM state_migration WHERE id='install_targets_ui_v1'")
    upgraded = SkillStateStore(store.db_path)
    assert store.db_path.with_name(store.db_path.name+'.before-hermes-profiles').exists()
    assert upgraded.get_deployment('alpha','hermes').source_revision == 'v1'
    assert len(TargetResolver(Settings(),upgraded).catalog()) == 2
    assert upgraded.get_deployment('alpha',PROFILE) is None
