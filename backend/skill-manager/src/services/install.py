"""Hermes install plans and bounded, credential-free background execution."""
from pathlib import Path
from copy import deepcopy
from dataclasses import dataclass
import os
import secrets
import threading
import time

from fastapi import HTTPException
from src.models import RegistrySkill, SkillSource, TargetKey
from src.services.exporting import dir_hash
from src.services.operation_lock import operation_lock
from src.services.publisher import resolve_registry_source


def error(code, message, status=409):
    raise HTTPException(status, detail={"code": code, "message": message})


@dataclass
class Plan:
    skills: list[RegistrySkill]
    states: list[dict | None]
    items: list[dict]
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
        link = settings.hermes_skills_root / skill.id
        target_state = ('link', os.readlink(link)) if link.is_symlink() else ('occupied', link.stat().st_mtime_ns) if link.exists() else ('missing',)
        current = registry.get(skill.id)
        registered = current.model_dump(mode='json') if current else None
        if skill.source == SkillSource.GITHUB:
            cache.ensure_skill_path_cached(skill)
            root = cache.repo_cache_dir(str(skill.repository)).resolve()
            paths = [skill.path, *skill.shared_paths]
            if any('.git' in Path(path).parts for path in paths):
                error('invalid_source', 'Git内部数据不能作为共享资源', 400)
            hashes = []
            for path in paths:
                source = (root / path).resolve()
                if not source.is_relative_to(root) or not source.exists():
                    error('invalid_source', 'Skill或共享资源路径不可用', 400)
                if source.is_dir():
                    if any(p.is_symlink() for p in source.rglob('*') if '.git' not in p.relative_to(source).parts):
                        error('invalid_source', '源目录含符号链接，请改为受控普通文件', 400)
                    hashes.append((path, dir_hash(source)))
                else:
                    import hashlib
                    hashes.append((path, hashlib.sha256(source.read_bytes()).hexdigest()))
            check = cache.store.get_github_check(skill.id)
            revision = check.remote_revision if current and check and check.result == 'ok' else cache.current_revision(skill)
            return {'target': target_state, 'registered': registered, 'revision': revision, 'cache_revision': cache.current_revision(skill), 'hashes': hashes}
        return {'target': target_state, 'registered': registered, 'revision': '', 'hashes': dir_hash(resolve_registry_source(settings, skill))}

    def preview(self, skills, settings, registry, cache, publisher, planner):
        with operation_lock, self.lock:
            self._prune()
            if len(self.plans) >= 100:
                error('capacity', '安装服务繁忙，请稍后重试', 429)
            items, states = [], []
            for skill in skills:
                try:
                    state = self.source_state(skill, settings, registry, cache)
                    item = planner(skill)
                    item.planned_revision = state['revision']
                    # Candidate plans must not use unrelated ID check records.
                    if skill.source == SkillSource.GITHUB and not state['registered']:
                        source = publisher.planned_staging_dir(skill.id, state['revision']).resolve()
                        link = settings.hermes_skills_root / skill.id
                        if item.action != 'blocked':
                            item.action = 'unchanged' if link.is_symlink() and link.resolve() == source else 'update' if link.is_symlink() else 'add'
                    states.append(state)
                    items.append(item.model_dump(mode='json') | {'name': skill.name, 'path': skill.path})
                except Exception as exc:
                    states.append(None)
                    items.append({'skill_id': skill.id, 'name': skill.name, 'path': skill.path, 'target': 'hermes', 'action': 'blocked', 'reason': str(exc.detail.get('message', '来源不可用')) if isinstance(exc, HTTPException) and isinstance(exc.detail, dict) else str(exc), 'planned_revision': ''})
            plan_id = secrets.token_urlsafe(24)
            self.plans[plan_id] = Plan(skills, states, items, time.monotonic() + 600)
            return {'plan_id': plan_id, 'items': items, 'expires_in': 600}

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
            with operation_lock:
                for skill, state in zip(plan.skills, plan.states):
                    if state is not None:
                        try:
                            if state != self.source_state(skill, settings, registry, cache):
                                error('stale_plan', '来源或登记已变化，请重新预览')
                        except HTTPException:
                            raise
                        except Exception:
                            error('stale_plan', '来源已不可用，请重新预览')
            task_id = secrets.token_urlsafe(24)
            plan.task_id, plan.request_id = task_id, request_id
            self.tasks[task_id] = {'task_id': task_id, 'state': 'running', 'stage': 'preparing', 'results': [], '_expires': time.monotonic() + 1800}
            threading.Thread(target=self._execute, args=(plan, settings, registry, cache, publisher), daemon=True).start()
            return {'task_id': task_id}

    def _execute(self, plan, settings, registry, cache, publisher):
        try:
            for skill, state, item in zip(plan.skills, plan.states, plan.items):
                registered = state is not None and state['registered'] is not None
                result = {'skill_id': skill.id, 'name': skill.name, 'registered': registered, 'status': 'blocked', 'error': item.get('reason', '')}
                try:
                    if state is None or item['action'] == 'blocked':
                        continue
                    with operation_lock:
                        if registered and item['action'] == 'unchanged':
                            result.update(status='success', action='unchanged', error='')
                            continue
                        if state != self.source_state(skill, settings, registry, cache):
                            raise ValueError('来源或登记已变化，请重新预览')
                        if skill.source == SkillSource.GITHUB:
                            if cache.current_revision(skill) != state['revision']:
                                cache.ensure_cached(skill, state['revision'])
                                for other, expected in zip(plan.skills, plan.states):
                                    if other.id != skill.id and expected is not None and other.repository == skill.repository:
                                        prepared = self.source_state(other, settings, registry, cache)
                                        expected['cache_revision'] = prepared['cache_revision']
                                        expected['hashes'] = prepared['hashes']
                            if cache.current_revision(skill) != state['revision']:
                                raise ValueError('缓存未取得确认版本，请重新预览')
                            source = publisher.stage_github_skill(skill, state['revision'], cache.repo_cache_dir(str(skill.repository)))
                        else:
                            source = resolve_registry_source(settings, skill)
                        self._stage(plan.task_id, 'registering')
                        if not registered:
                            registry.upsert(skill)
                            registered = True
                        self._stage(plan.task_id, 'installing')
                        outcome = publisher.publish(skill.id, TargetKey.HERMES, source, state['revision'])
                        result.update(status='success', action=outcome.action, error='')
                except Exception as exc:
                    result.update(status='error', error=str(exc))
                finally:
                    result['registered'] = registered
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
