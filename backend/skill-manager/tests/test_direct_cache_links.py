"""GitHub installations use live repository directories, never per-skill snapshots."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.api.routes import _plan_one, list_skills
from src.config import Settings
from src.db import GithubCheckRecord, SkillStateStore
from src.models import RegistrySkill, SkillSource, TargetKey
from src.services.git_cache import CacheValidationError, GitCacheService
from src.services.install import InstallManager
from src.services.publisher import InvalidSourceError, Publisher, resolve_github_source
from src.services.registry import RegistryService


@pytest.fixture
def context(tmp_path):
    for name in ('source', 'cache', 'state', 'hermes'):
        (tmp_path / name).mkdir()
    settings = Settings(skills_source_root=tmp_path/'source', github_skill_cache_root=tmp_path/'cache',
        state_dir=tmp_path/'state', hermes_skills_root=tmp_path/'hermes', admin_password='test')
    store = SkillStateStore(settings.state_dir/'state.sqlite3')
    cache = GitCacheService(settings, store)
    registry = RegistryService(store, settings.skills_source_root)
    repo = cache.repo_cache_dir('https://github.com/owner/repo')
    (repo/'.git').mkdir(parents=True)
    for name in ('alpha', 'beta'):
        (repo/'skills'/name).mkdir(parents=True)
        (repo/'skills'/name/'SKILL.md').write_text(name)
    (repo/'SKILL.md').write_text('root skill')
    cache.current_revision = Mock(return_value='v1')
    return SimpleNamespace(settings=settings, store=store, cache=cache, registry=registry,
        publisher=Publisher(settings, store), repo=repo)


def skill(name='alpha', path='skills/alpha'):
    return RegistrySkill(id=name, name=name, source=SkillSource.GITHUB,
        repository='https://github.com/owner/repo', path=path, shared_paths=['legacy-missing-tools'])


@pytest.mark.parametrize('path', ['.', 'skills/alpha', 'skills/beta'])
def test_resolves_exact_registered_directory_without_creating_snapshot(context, path):
    source = resolve_github_source(context.settings, skill(path=path), context.repo)
    assert source == (context.repo/path).resolve()
    assert not (context.settings.github_skill_cache_root/'staging').exists()
    assert not (source/'legacy-missing-tools').exists()


@pytest.mark.parametrize('path', ['../outside', '/outside'])
def test_direct_source_rejects_path_escape(context, path):
    with pytest.raises(InvalidSourceError):
        resolve_github_source(context.settings, skill(path=path), context.repo)


def test_direct_source_requires_skill_file_and_controlled_repository(context, tmp_path):
    with pytest.raises(InvalidSourceError, match='outside the GitHub cache root'):
        resolve_github_source(context.settings, skill(), tmp_path/'outside')
    with pytest.raises(InvalidSourceError, match='does not exist'):
        resolve_github_source(context.settings, skill(path='missing'), context.repo)


@pytest.mark.requires_symlink
def test_direct_source_rejects_symlink_to_another_repository(context):
    outside = context.settings.github_skill_cache_root/'other'
    outside.mkdir()
    (outside/'SKILL.md').write_text('outside')
    (context.repo/'escape').symlink_to(outside, target_is_directory=True)
    with pytest.raises(InvalidSourceError, match='escapes the repository root'):
        resolve_github_source(context.settings, skill(path='escape'), context.repo)


def test_install_execution_passes_cached_subdirectory_to_publisher(context):
    s = skill()
    manager = InstallManager()
    preview = manager.preview([s], context.settings, context.registry, context.cache, context.publisher,
        lambda s, target: _plan_one(context.settings, context.store, context.cache, context.publisher, s, target))
    plan = manager.plans[preview['plan_id']]
    plan.task_id = 'unit-test'
    manager.tasks[plan.task_id] = {'results': []}
    context.publisher.publish = Mock(return_value=SimpleNamespace(action='add'))
    manager._execute(plan, context.settings, context.registry, context.cache, context.publisher)
    assert manager.tasks[plan.task_id]['results'][0]['status'] == 'success'
    context.publisher.publish.assert_called_once_with(s.id, TargetKey.HERMES, (context.repo/s.path).resolve(), 'v1')
    assert not (context.settings.github_skill_cache_root/'staging').exists()


@pytest.mark.parametrize('removed_name', ['alpha', 'beta'])
def test_member_removed_by_repository_update_does_not_fail_other_installs(context, removed_name):
    members = [skill('alpha', 'skills/alpha'), skill('beta', 'skills/beta')]
    for s in members:
        context.registry.upsert(s)
    context.store.upsert_github_check(GithubCheckRecord(skill_id='alpha', repository=str(members[0].repository),
        remote_revision='v2', remote_tags='', cached_revision='v1', result='ok', error=None, checked_at='now'))
    manager = InstallManager()
    preview = manager.preview(members, context.settings, context.registry, context.cache, context.publisher,
        lambda s, target: _plan_one(context.settings, context.store, context.cache, context.publisher, s, target))
    plan = manager.plans[preview['plan_id']]
    plan.task_id = 'removed-member'
    manager.tasks[plan.task_id] = {'results': []}
    def checkout(selected, _revision):
        context.cache.current_revision.return_value = 'v2'
        (context.repo/f'skills/{removed_name}/SKILL.md').unlink()
        if selected.id == removed_name:
            raise CacheValidationError('selected member removed after checkout')
    context.cache.ensure_cached = Mock(side_effect=checkout)
    context.publisher.publish = Mock(return_value=SimpleNamespace(action='add'))
    manager._execute(plan, context.settings, context.registry, context.cache, context.publisher)
    results = manager.tasks[plan.task_id]['results']
    normal = next(r for r in results if r['skill_id'] != removed_name)
    removed = next(r for r in results if r['skill_id'] == removed_name)
    assert normal['status'] == 'success'
    assert removed['status'] in ('error', 'blocked')
    assert removed['registered'] is True
    context.publisher.publish.assert_called_once()


def test_listing_refreshes_sibling_update_badges_from_current_cache_head(context):
    for name in ('alpha', 'beta'):
        s = skill(name, f'skills/{name}')
        context.registry.upsert(s)
        context.store.upsert_github_check(GithubCheckRecord(skill_id=name, repository=str(s.repository),
            remote_revision='v2', remote_tags='', cached_revision='v1', result='ok', error=None, checked_at='now'))
    context.cache.current_revision.return_value = 'v2'
    response = list_skills(context.registry, context.store, context.settings, context.cache, context.publisher)
    assert all(not card.update.has_update and card.update.cached_revision == 'v2' for card in response.items)
    # A shared repository is inspected only once for this list response.
    context.cache.current_revision.assert_called_once()


def test_sibling_with_older_check_uses_latest_repository_check(context):
    for name, revision, checked in [('alpha', 'v1', '2026-10-14T01:00:00+00:00'),
                                    ('beta', 'v2', '2026-10-14T02:00:00+00:00')]:
        s = skill(name, f'skills/{name}')
        context.registry.upsert(s)
        context.store.upsert_github_check(GithubCheckRecord(skill_id=name, repository=str(s.repository),
            remote_revision=revision, remote_tags='', cached_revision='v1', result='ok', error=None, checked_at=checked))
    context.cache.current_revision.return_value = 'v2'
    cards = list_skills(context.registry, context.store, context.settings, context.cache, context.publisher).items
    assert all(card.update.remote_revision == 'v2' and not card.update.has_update for card in cards)
    assert {card.update.skill_id for card in cards} == {'alpha', 'beta'}


@pytest.mark.requires_symlink
def test_stable_direct_link_still_plans_update_when_repository_head_is_old(context):
    s = skill()
    (context.settings.hermes_skills_root/s.id).symlink_to(context.repo/s.path, target_is_directory=True)
    context.store.upsert_github_check(GithubCheckRecord(skill_id=s.id, repository=str(s.repository),
        remote_revision='v2', remote_tags='', cached_revision='v1', result='ok', error=None, checked_at='now'))
    plan = _plan_one(context.settings, context.store, context.cache, context.publisher, s, TargetKey.HERMES)
    assert plan.action == 'update'
    context.cache.current_revision.return_value = 'v2'
    current = _plan_one(context.settings, context.store, context.cache, context.publisher, s, TargetKey.HERMES)
    assert current.action == 'unchanged'
    assert current.current_revision == 'v2'


@pytest.mark.requires_symlink
def test_retained_snapshot_link_is_stale_until_migrated(context):
    s = skill()
    context.registry.upsert(s)
    old = context.settings.github_skill_cache_root/'staging'/s.id/'v1'
    old.mkdir(parents=True)
    (old/'SKILL.md').write_text('old')
    context.publisher.publish(s.id, TargetKey.HERMES, old, 'v1')
    context.cache.current_revision.return_value = 'v2'
    card = list_skills(context.registry, context.store, context.settings, context.cache, context.publisher).items[0]
    assert card.deployments['hermes'].stale is True
    assert card.deployments['hermes'].revision == 'v1'


@pytest.mark.requires_symlink
def test_direct_links_read_repository_changes_without_reinstalling(context):
    for name in ('alpha', 'beta'):
        s = skill(name, f'skills/{name}')
        context.publisher.publish(s.id, TargetKey.HERMES,
            resolve_github_source(context.settings, s, context.repo), 'v1')
    for name in ('alpha', 'beta'):
        (context.repo/'skills'/name/'SKILL.md').write_text(f'{name}-v2')
        link = context.settings.hermes_skills_root/name
        assert link.resolve() == (context.repo/'skills'/name).resolve()
        assert (link/'SKILL.md').read_text() == f'{name}-v2'
