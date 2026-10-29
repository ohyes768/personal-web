"""Persistent, sequential Xingfuli source matching; never collects rent samples."""
from __future__ import annotations

import copy
import datetime as dt
import json
import threading
import time
import uuid

from src.services.community_registry import now
from src.services.rental_reference.association import eligible_communities, read_review
from src.services.rental_reference.probe import ProbeService, read_state
from src.services.rental_reference.providers import active_sources
from src.services.rental_reference.refresh import RefreshAlreadyRunning, RefreshNotRunning
from src.services.rental_reference.storage import _atomic_write_json


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
    def __init__(self, registry, *, directory, discovery_factory=None, delay=5,
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
            return copy.deepcopy(self._job)

    def resume(self):
        if self._resume_on_startup:
            self._resume_on_startup = False
            return self.start()

    def _save(self, **fields):
        with self._mutex:
            self._job.update(fields)
            self.directory.mkdir(parents=True, exist_ok=True)
            _atomic_write_json(self._path, self._job)

    def start(self):
        with self._mutex:
            if self.busy() or (self._busy and self._busy()):
                raise RefreshAlreadyRunning('已有租金采集或来源匹配任务正在运行')
            communities, _ = eligible_communities(self.registry)
            selected = active_sources(self.registry, xingfuli_only=True)
            with self.registry.db() as db:
                rejected = {row[0] for row in db.execute('SELECT cid FROM rejected')}
            eligible = {c['community_id'] for c in communities if c['community_id'] not in selected
                        and c['community_id'] not in rejected
                        and read_review(self.registry, c['community_id']).get('decision') != 'skipped'}
            resume = self._job.get('phase') in {'cancelled', 'interrupted', 'cooling_down'} and self._job.get('remaining')
            remaining = [cid for cid in self._job['remaining'] if cid in eligible] if resume else [
                c['community_id'] for c in communities if c['community_id'] in eligible]
            outcomes = self._job.get('outcomes', {}) if resume else {}
            self._cancel.clear()
            self._stopping = False
            self._save(job_id=uuid.uuid4().hex, running=True, phase='running', stage='matching',
                       total=len(remaining) + len(outcomes), processed=len(outcomes),
                       remaining=remaining, outcomes=outcomes, errors=[], error=None,
                       association={**{name: list(outcomes.values()).count(name) for name in ('matched', 'pending', 'missing', 'failed', 'skipped')},
                                    'checked': len(outcomes), 'deferred': len(remaining)},
                       started_at=now(), finished_at=None)
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
                    self._save(current_community_id=cid, phase='running', cooldown_until=None)
                    self._probe.start(cid, automatic=True)
                    while self._probe.busy():
                        if self._cancel.wait(.1):
                            self._probe.shutdown()
                            break
                    state = self._probe.status(cid)
                    if self._cancel.is_set():
                        break
                    stage = state.get('stage')
                    if stage == 'cooling_down' and self._cooldown() > time.time():
                        continue
                    outcome = {'bound_pending_collection': 'matched', 'needs_homepage_selection': 'pending',
                               'homepage_not_found': 'missing', 'entry_not_found': 'missing'}.get(stage, 'failed')
                with self._mutex:
                    self._job['outcomes'][cid] = outcome
                    self._job['remaining'].pop(0)
                    counts = {name: list(self._job['outcomes'].values()).count(name)
                              for name in ('matched', 'pending', 'missing', 'failed', 'skipped')}
                    counts['checked'] = len(self._job['outcomes'])
                    counts['deferred'] = len(self._job['remaining'])
                    self._save(processed=len(self._job['outcomes']), association=counts)
        except Exception as exc:
            phase = 'failed'
            self._save(error=str(exc), errors=[{'message': str(exc)}])
        finally:
            if self._cancel.is_set():
                phase = 'interrupted' if self._stopping else 'cancelled'
            self._save(running=self._stopping, phase=phase, current_community_id=None, finished_at=now())
