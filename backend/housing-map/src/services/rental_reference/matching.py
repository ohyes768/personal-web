"""Persistent, sequential Xingfuli source matching; never collects rent samples."""
from __future__ import annotations

import copy
import datetime as dt
import json
import threading
import time
import uuid

from src.services.xingfuli_transport import DEFAULT_XINGFULI_DELAY
from src.services.community_registry import now
from src.services.rental_reference.association import eligible_communities, read_review
from src.services.rental_reference.probe import PREFIX as PROBE_PREFIX, ProbeService, read_state
from src.services.rental_reference.association import PREFIX as REVIEW_PREFIX
from src.services.rental_reference.providers import active_sources, rejected_rental_communities
from src.services.rental_reference.refresh import RefreshAlreadyRunning, RefreshNotRunning
from src.services.rental_reference.storage import _atomic_write_json
from src.services.rental_reference.discovery_checkpoint import clear_checkpoint


def source_reviews(registry):
    """Project stored Xingfuli probe evidence into the existing review list."""
    communities, _ = eligible_communities(registry)
    selected = active_sources(registry, xingfuli_only=True)
    items = []
    for community in communities:
        cid = community['community_id']
        if cid in selected:
            continue
        state = read_state(registry, cid)
        review = read_review(registry, cid)
        stage = state.get('stage', 'idle')
        reason = ('skipped' if review.get('decision') == 'skipped' else
                  'needs_selection' if stage == 'needs_homepage_selection' else
                  'search_failed' if stage in {'upstream_failed', 'entry_not_found'} else
                  'search_deferred' if stage in {'cooling_down', 'deferred', 'interrupted', 'cancelled'} else 'missing')
        items.append(dict(community_id=cid, community_name=community['community_name'],
                          reason=reason, message=state.get('message', ''), candidates=[]))
    return items


class SourceMatchingService:
    def __init__(self, registry, *, directory, discovery_factory=None, delay=DEFAULT_XINGFULI_DELAY,
                 busy=None, task_lock=None):
        self.registry = registry
        self.directory = directory
        self._path = directory / 'source_matching_job.json'
        self._mutex = task_lock if task_lock is not None else threading.RLock()
        self._busy = busy
        self._cancel = threading.Event()
        self._thread = None
        self._stopping = False
        self._probe = ProbeService(registry, directory=directory, delay=delay,
                                    discovery_factory=discovery_factory, task_lock=self._mutex, xingfuli_only=True)
        self._job = dict(running=False, phase='idle', total=0, processed=0,
                         association={}, remaining=[], outcomes={}, errors=[])
        if self._path.exists():
            self._job = json.loads(self._path.read_text(encoding='utf-8'))
        self._resume_on_startup = bool(self._job.get('running'))
        if self._resume_on_startup:
            self._job.update(running=False, phase='interrupted')

    def busy(self):
        with self._mutex:
            return bool(self._thread and self._thread.is_alive())

    def status(self):
        with self._mutex:
            state = copy.deepcopy(self._job)
            state['incremental_count'] = len(self._targets('incremental'))
            cid = state.get('current_community_id')
            if cid:
                probe = self._probe.status(cid)
                state['current_step'] = probe.get('current_step')
                state['diagnostics'] = self._diagnostics(probe.get('diagnostics', {}))
            return state

    def _diagnostics(self, current=None):
        diagnostics = list(self._job.get('completed_diagnostics', {}).values())
        if current:
            diagnostics.append(current)
        return {key: round(sum(item.get(key, 0) for item in diagnostics), 3)
                for key in ('requests', 'cache_hits', 'wait_seconds', 'http_seconds', 'elapsed_seconds')}

    def _eligible(self):
        communities, _ = eligible_communities(self.registry)
        selected = active_sources(self.registry, xingfuli_only=True)
        with self.registry.db() as db:
            rejected = rejected_rental_communities(db)
            skipped = {row[0][len(REVIEW_PREFIX):] for row in db.execute(
                'SELECT key,value FROM meta WHERE key LIKE ?', (REVIEW_PREFIX + '%',))
                if json.loads(row[1]).get('decision') == 'skipped'}
        return [c['community_id'] for c in communities if c['community_id'] not in selected
                and c['community_id'] not in rejected
                and c['community_id'] not in skipped]

    def _targets(self, mode):
        eligible = self._eligible()
        if mode == 'full':
            return eligible
        remaining = [cid for cid in self._job.get('remaining', []) if cid in eligible]
        outcomes = {**self._job.get('history', {}), **self._job.get('outcomes', {})}
        with self.registry.db() as db:
            stages = {row[0][len(PROBE_PREFIX):]: json.loads(row[1]).get('stage') for row in db.execute(
                'SELECT key,value FROM meta WHERE key LIKE ?', (PROBE_PREFIX + '%',))}
        for cid in eligible:
            stage = stages.get(cid)
            completed = outcomes.get(cid) in {'pending', 'missing', 'matched', 'skipped'} or (
                cid not in outcomes and stage in {'needs_homepage_selection', 'homepage_not_found', 'entry_not_found'})
            if cid not in remaining and not completed:
                remaining.append(cid)
        return remaining

    def resume(self):
        if self._resume_on_startup:
            self._resume_on_startup = False
            return self.start(_startup=True)

    def _save(self, **fields):
        with self._mutex:
            self._job.update(fields)
            self.directory.mkdir(parents=True, exist_ok=True)
            _atomic_write_json(self._path, self._job)

    def start(self, mode=None, *, _startup=False):
        with self._mutex:
            if mode not in {None, 'full', 'incremental'}:
                raise ValueError('未知来源匹配模式')
            if self.busy() or (self._busy and self._busy()):
                raise RefreshAlreadyRunning('已有租金采集或来源匹配任务正在运行')
            resume = mode != 'full' and self._job.get('phase') in {'cancelled', 'interrupted', 'cooling_down'} and self._job.get('remaining')
            effective_mode = mode or ('incremental' if resume else 'full')
            remaining = self._targets(effective_mode)
            if _startup:
                remaining = [cid for cid in self._job.get('remaining', []) if cid in self._eligible()]
            outcomes = {cid: value for cid, value in self._job.get('outcomes', {}).items()
                        if cid not in remaining} if resume else {}
            # Keep completion history across empty/repeated incremental runs.
            history = dict(self._job.get('history', {}))
            history.update(self._job.get('outcomes', {}))
            if effective_mode == 'full' and not _startup:
                for cid in remaining:
                    clear_checkpoint(self.registry, cid)
            self._cancel.clear()
            self._stopping = False
            self._save(job_id=uuid.uuid4().hex, mode=effective_mode, history=history,
                       running=True, phase='running', stage='matching',
                       completed_diagnostics={},
                       total=len(remaining) + len(outcomes), processed=len(outcomes),
                       remaining=remaining, outcomes=outcomes, errors=[], error=None,
                       association={**{name: list(outcomes.values()).count(name) for name in ('matched', 'pending', 'missing', 'failed', 'skipped', 'incomplete')},
                                    'checked': len(outcomes), 'deferred': len(remaining)},
                       started_at=now(), finished_at=None, diagnostics={}, current_step=None,
                       current_community_id=None, current_community_name=None)
            self._thread = threading.Thread(target=self._run, name='rental-source-matching', daemon=True)
            self._thread.start()
            return self.status()

    def cancel(self):
        with self._mutex:
            if not self.busy():
                raise RefreshNotRunning('当前没有正在运行的来源匹配任务')
            self._cancel.set()
            if self._probe.busy():
                self._probe.cancel(self._job['current_community_id'])
            self._save(phase='cancelling')
            return self.status()

    def shutdown(self, timeout=30):
        with self._mutex:
            if not self.busy():
                return True
            self._stopping = True
            self._cancel.set()
        self._probe.shutdown(timeout)
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def _cooldown(self):
        path = self.directory / 'xingfuli_request_state.json'
        state = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        return float(state.get('cooldown_until') or 0)

    def _run(self):
        phase = 'done'
        try:
            while self._job['remaining'] and not self._cancel.is_set():
                state = None
                until = self._cooldown()
                if until > time.time():
                    self._save(phase='cooling_down', cooldown_until=dt.datetime.fromtimestamp(until, dt.UTC).isoformat())
                    self._cancel.wait(min(30, until - time.time()))
                    continue
                cid = self._job['remaining'][0]
                current, _ = eligible_communities(self.registry)
                if cid not in {c['community_id'] for c in current} or cid in active_sources(self.registry, xingfuli_only=True):
                    outcome = 'skipped'
                elif read_review(self.registry, cid).get('decision') == 'skipped':
                    outcome = 'skipped'
                else:
                    name = next(c['community_name'] for c in current if c['community_id'] == cid)
                    self._save(current_community_id=cid, current_community_name=name,
                               phase='running', cooldown_until=None)
                    self._probe.start(cid, automatic=True)
                    while self._probe.busy():
                        if self._cancel.wait(.1):
                            self._probe.shutdown()
                            break
                    state = self._probe.status(cid)
                    self._save(diagnostics=self._diagnostics(state.get('diagnostics', {})),
                               current_step=state.get('current_step'))
                    if self._cancel.is_set():
                        break
                    stage = state.get('stage')
                    if stage == 'cooling_down' and self._cooldown() > time.time():
                        continue
                    outcome = {'bound_pending_collection': 'matched', 'needs_homepage_selection': 'pending',
                               'homepage_not_found': 'missing', 'entry_not_found': 'missing',
                               'deferred': 'incomplete'}.get(stage, 'failed')
                with self._mutex:
                    if state is not None:
                        self._job.setdefault('completed_diagnostics', {})[cid] = state.get('diagnostics', {})
                    self._job['outcomes'][cid] = outcome
                    self._job['remaining'].pop(0)
                    counts = {name: list(self._job['outcomes'].values()).count(name)
                              for name in ('matched', 'pending', 'missing', 'failed', 'skipped', 'incomplete')}
                    counts['checked'] = len(self._job['outcomes'])
                    counts['deferred'] = len(self._job['remaining'])
                    self._save(processed=len(self._job['outcomes']), association=counts,
                               diagnostics=self._diagnostics(), current_community_id=None,
                               current_community_name=None)
        except Exception as exc:
            phase = 'failed'
            self._save(error=str(exc), errors=[{'message': str(exc)}])
        finally:
            if self._cancel.is_set():
                phase = 'interrupted' if self._stopping else 'cancelled'
            self._save(running=self._stopping, phase=phase, current_community_id=None,
                       current_community_name=None, finished_at=now())
