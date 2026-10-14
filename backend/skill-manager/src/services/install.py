"""One source snapshot per Skill and filesystem identity per target pair."""
from copy import deepcopy
from dataclasses import dataclass
import secrets
import threading
import time

from fastapi import HTTPException
from src.models import RegistrySkill, SkillSource, is_install_target
from src.services.exporting import dir_hash
from src.services.operation_lock import operation_lock
from src.services.publisher import resolve_github_source, resolve_registry_source
from src.services.targets import TargetUnavailable


def error(code, message, status=409):
    raise HTTPException(status, detail={"code": code, "message": message})


@dataclass
class Plan:
    skills: list[RegistrySkill]
    states: dict
    targets: dict
    items: list[dict]
    affected: list[dict]
    expires: float
    task_id: str = ""
    request_id: str = ""


class InstallManager:
    def __init__(self):
        self.plans = {}
        self.tasks = {}
        self.lock = threading.RLock()

    def _prune(self):
        now = time.monotonic()
        self.plans = {k: p for k, p in self.plans.items() if p.expires > now or (p.task_id and self.tasks.get(p.task_id, {}).get('state') == 'running')}
        self.tasks = {k: t for k, t in self.tasks.items() if t['state'] == 'running' or t['_expires'] > now}

    def source_state(self, skill, settings, registry, cache):
        current = registry.get(skill.id)
        registered = current.model_dump(mode='json') if current else None
        if skill.source == SkillSource.GITHUB:
            cache.ensure_skill_path_cached(skill)
            source = resolve_github_source(settings, skill, cache.repo_cache_dir(str(skill.repository)))
            if any(p.is_symlink() for p in source.rglob('*') if '.git' not in p.relative_to(source).parts):
                error('invalid_source', '源目录含符号链接，请改为受控普通文件', 400)
            check = cache.store.latest_repository_check(str(skill.repository))
            revision = check.remote_revision if current and check and check.result == 'ok' else cache.current_revision(skill)
            return {'registered': registered, 'revision': revision, 'cache_revision': cache.current_revision(skill), 'hashes': [(skill.path, dir_hash(source))]}
        return {'registered': registered, 'revision': '', 'hashes': dir_hash(resolve_registry_source(settings, skill))}

    def affected_installations(self, skills, states, registry, cache, publisher):
        repositories = {cache.normalize_repository(str(s.repository)).lower() for s in skills if s.source == SkillSource.GITHUB and states.get(s.id) and states[s.id]['revision'] != states[s.id]['cache_revision']}
        known = {s.id: s for s in registry.list_skills()}
        rows = []
        for record in publisher.store.list_deployments():
            skill = known.get(record.skill_id)
            if record.status != 'active' or not is_install_target(record.target) or not skill or skill.source != SkillSource.GITHUB:
                continue
            if cache.normalize_repository(str(skill.repository)).lower() not in repositories:
                continue
            try:
                fingerprint = publisher.targets.fingerprint(record.target, skill.id)
            except TargetUnavailable:
                fingerprint = None
            rows.append({'skill_id': skill.id, 'name': skill.name, 'target': record.target, 'fingerprint': fingerprint})
        return sorted(rows, key=lambda row: (row['skill_id'], row['target']))

    def preview(self, skills, settings, registry, cache, publisher, planner, pairs=None):
        pairs = pairs or {s.id: ['hermes'] for s in skills}
        with operation_lock, self.lock:
            self._prune()
            if len(self.plans) >= 100:
                error('capacity', '安装服务繁忙，请稍后重试', 429)
            items, states, targets = [], {}, {}
            for skill in skills:
                source_error = ''
                try:
                    states[skill.id] = self.source_state(skill, settings, registry, cache)
                except Exception as exc:
                    states[skill.id] = None
                    source_error = str(exc.detail.get('message', '来源不可用')) if isinstance(exc, HTTPException) and isinstance(exc.detail, dict) else str(exc)
                for target in pairs[skill.id]:
                    state = states[skill.id]
                    try:
                        targets[skill.id, target] = publisher.targets.fingerprint(target, skill.id)
                        if not state:
                            raise ValueError(source_error)
                        item = planner(skill, target)
                        item.planned_revision = state['revision']
                        items.append(item.model_dump(mode='json') | {'name': skill.name, 'path': skill.path})
                    except Exception as exc:
                        targets.setdefault((skill.id, target), None)
                        items.append({'skill_id': skill.id, 'name': skill.name, 'path': skill.path, 'target': target, 'action': 'blocked', 'reason': str(exc), 'planned_revision': ''})
            affected = self.affected_installations(skills, states, registry, cache, publisher)
            plan_id = secrets.token_urlsafe(24)
            self.plans[plan_id] = Plan(skills, states, targets, items, affected, time.monotonic() + 600)
            return {'plan_id': plan_id, 'items': items, 'affected_installations': [{k: v for k, v in row.items() if k != 'fingerprint'} for row in affected], 'expires_in': 600}

    def start(self, plan_id, request_id, settings, registry, cache, publisher):
        with operation_lock, self.lock:
            self._prune()
            plan = self.plans.get(plan_id)
            if not plan:
                error('plan_expired', '安装计划已过期，请重新预览', 410)
            if plan.task_id:
                if plan.request_id != request_id:
                    error('already_submitted', '此安装计划已提交')
                return {'task_id': plan.task_id}
            try:
                for skill in plan.skills:
                    state = plan.states[skill.id]
                    if state is not None and state != self.source_state(skill, settings, registry, cache):
                        error('stale_plan', '来源或登记已变化，请重新预览')
                for (skill_id, target), state in plan.targets.items():
                    if state is not None and state != publisher.targets.fingerprint(target, skill_id):
                        error('stale_plan', '目标目录或链接已变化，请重新预览')
                if plan.affected != self.affected_installations(plan.skills, plan.states, registry, cache, publisher):
                    error('stale_plan', '共享仓库影响范围已变化，请重新预览')
            except HTTPException:
                raise
            except Exception:
                error('stale_plan', '来源或目标已不可用，请重新预览')
            task_id = secrets.token_urlsafe(24)
            plan.task_id, plan.request_id = task_id, request_id
            self.tasks[task_id] = {'task_id': task_id, 'state': 'running', 'stage': 'preparing', 'results': [], '_expires': time.monotonic() + 1800}
            threading.Thread(target=self._execute, args=(plan, settings, registry, cache, publisher), daemon=True).start()
            return {'task_id': task_id}

    def _execute(self, plan, settings, registry, cache, publisher):
        try:
            with operation_lock:
                for skill in plan.skills:
                    state = plan.states[skill.id]
                    items = [i for i in plan.items if i['skill_id'] == skill.id]
                    # A target mutation can win the lock between start() and
                    # this worker. Recheck before checkout or registration.
                    for item in items:
                        if item['action'] == 'blocked':
                            continue
                        try:
                            if plan.targets[skill.id,item['target']] != publisher.targets.fingerprint(item['target'],skill.id):
                                raise ValueError('目标配置或链接已变化，请重新预览')
                        except Exception as exc:
                            item.update(action='blocked',reason=str(exc))
                    registered = bool(state and state['registered'])
                    source, source_error = None, ''
                    try:
                        if state and any(i['action'] != 'blocked' and (not registered or i['action'] != 'unchanged') for i in items):
                            if state != self.source_state(skill, settings, registry, cache):
                                raise ValueError('来源或登记已变化，请重新预览')
                            if skill.source == SkillSource.GITHUB:
                                if cache.current_revision(skill) != state['revision']:
                                    try:
                                        cache.ensure_cached(skill, state['revision'])
                                    finally:
                                        if cache.current_revision(skill) != state['cache_revision']:
                                            if cache.current_revision(skill) != state['revision']:
                                                raise ValueError('缓存未取得确认版本，请重新预览')
                                            # Only the confirmed checkout's content changes are accepted.
                                            for other in plan.skills:
                                                expected = plan.states[other.id]
                                                if expected and other.repository == skill.repository:
                                                    try:
                                                        prepared = self.source_state(other, settings, registry, cache)
                                                        expected['cache_revision'] = prepared['cache_revision']
                                                        expected['hashes'] = prepared['hashes']
                                                    except Exception as exc:
                                                        for item in plan.items:
                                                            if item['skill_id'] == other.id:
                                                                item.update(action='blocked', reason=str(exc))
                                source = resolve_github_source(settings, skill, cache.repo_cache_dir(str(skill.repository)))
                            else:
                                source = resolve_registry_source(settings, skill)
                            self._stage(plan.task_id, 'registering')
                            if not registered:
                                registry.upsert(skill)
                                registered = True
                    except Exception as exc:
                        source_error = str(exc)
                    for item in items:
                        target = item['target']
                        result = {'skill_id': skill.id, 'target': target, 'name': skill.name, 'registered': registered, 'status': 'blocked', 'action': 'none', 'error': item.get('reason', '')}
                        try:
                            if not state or item['action'] == 'blocked':
                                continue
                            if source_error:
                                raise ValueError(source_error)
                            if plan.targets[skill.id, target] != publisher.targets.fingerprint(target, skill.id):
                                raise ValueError('目标目录或链接已变化，请重新预览')
                            if item['action'] == 'unchanged':
                                result.update(status='success', action='unchanged', error='')
                                continue
                            self._stage(plan.task_id, 'installing')
                            outcome = publisher.publish(skill.id, target, source, state['revision'])
                            result.update(status='success', action=outcome.action, error='')
                        except Exception as exc:
                            result.update(status='error', error=str(exc))
                        finally:
                            with self.lock:
                                self.tasks[plan.task_id]['results'].append(result)
        finally:
            with self.lock:
                self.tasks[plan.task_id].update(state='done', stage='done', _expires=time.monotonic() + 1800)

    def _stage(self, task_id, stage):
        with self.lock:
            self.tasks[task_id]['stage'] = stage

    def get(self, task_id):
        with self.lock:
            self._prune()
            task = self.tasks.get(task_id)
            if not task:
                error('task_not_found', '安装任务不存在或已回收；服务重启后请刷新安装状态再重试', 404)
            return {k: deepcopy(v) for k, v in task.items() if not k.startswith('_')}
