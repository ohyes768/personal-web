"""Web-triggered rental refresh background service (design.md "Web refresh").

One rental crawl/publish job at a time, independent from the auction job and
the price refresh: own cancel event, own worker thread and own job file
(refresh_job.json under the rentals dir). Only the final publish takes the
shared CLI/web rental_publish lock, so a CLI publish simply makes the web job
fail with an explainable lock error instead of blocking at start.

Job phases: idle -> crawling -> publishing -> done | failed | cancelled,
cancelling while a cancel is pending, interrupted when a restart finds the job
file marked running without a live worker in this process. A cancel at any
stage never publishes: crawl_runs raises RentalCrawlCancelled and publish_run
re-checks the cancel event at every stage.

The FastAPI layer wraps start/cancel/shutdown in asyncio.to_thread like the
auction refresh does; this module only uses plain threads and events.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
import tempfile
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from src.services.fang_rentals import (
    BASE_URL,
    CrawlProgress,
    FangClient,
    RentalCrawlCancelled,
    crawl_runs,
)
from src.services.rental_reference.storage import (
    ADOPTABLE_STATUSES,
    CommunityBatch,
    publish_run,
)

JOB_FILE_NAME = 'refresh_job.json'
DEFAULT_MAX_PAGES = 10
DEFAULT_DELAY_SECONDS = 2.0
DEFAULT_TIMEOUT_SECONDS = 20.0
MAX_ERRORS_KEPT = 20


class RefreshAlreadyRunning(RuntimeError):
    """409: a rental refresh job is already active (CLI or web share one slot)."""


class RefreshNotRunning(RuntimeError):
    """409: there is no active rental refresh job to cancel."""


class NoVerifiedMappings(RuntimeError):
    """422: the ledger has no verified mapping, so there is nothing to crawl."""


class MappingFileError(RuntimeError):
    """503: the mapping file exists but is unreadable or structurally invalid."""


def load_verified_mappings(path: Path) -> list[tuple[str, str]]:
    from src.services.community_registry import existing_registry
    registry = existing_registry(path.parent)
    if registry:
        from src.services.community_address import effective_address
        sources = registry.sources()
        valid_ids = {c['community_id'] for c in registry.communities() if effective_address(c.get('address'),
                     [r for r in sources if r['community_id'] == c['community_id'] and r['status'] == 'matched'])}
        from src.services.directory_workflow import is_enabled, admitted
        if is_enabled(registry):
            valid_ids = {c['community_id'] for c in admitted(registry, path.parent)}
        return [(r['source_id'], r['community_id']) for r in sources
                if r['source'] == 'fang' and r['status'] == 'matched' and r['community_id'] in valid_ids and registry.resolve(r['community_id'])]
    from src.services.rental_reference.sources import database_path, confirmed_pairs, connection
    db_path = database_path(path)
    if db_path.exists():
        try:
            with connection(db_path) as db:
                initialized = db.execute("SELECT 1 FROM meta WHERE key='imported'").fetchone()
            if initialized:
                return confirmed_pairs(db_path)
        except Exception as exc:
            raise MappingFileError(f'unreadable rental source database: {exc}') from exc
    return load_legacy_mappings(path)


def load_legacy_mappings(path: Path) -> list[tuple[str, str]]:
    """Verified (source_community_id, internal community_id) pairs in file order.

    A missing file means zero mappings (the caller maps that to 422). A present
    but invalid file is server-side data corruption (503), never silently
    skipped: a typo in the ledger must not silently shrink the crawl scope.
    """
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise MappingFileError(f'unreadable rental mapping file: {exc}') from exc
    if (not isinstance(payload, dict) or payload.get('version') != 1
            or not isinstance(payload.get('mappings'), list)):
        raise MappingFileError('invalid rental mapping file structure')
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for entry in payload['mappings']:
        if (not isinstance(entry, dict)
                or not isinstance(entry.get('source_community_id'), str)
                or not entry['source_community_id']
                or not isinstance(entry.get('community_id'), str)
                or not entry['community_id']):
            raise MappingFileError('invalid rental mapping entry')
        if entry.get('source') != 'fang' or entry.get('status') != 'verified':
            continue
        if entry['source_community_id'] in seen:
            raise MappingFileError(
                f'duplicate source_community_id: {entry["source_community_id"]}')
        seen.add(entry['source_community_id'])
        pairs.append((entry['source_community_id'], entry['community_id']))
    return pairs


def _utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def _initial_job() -> dict:
    return {
        'job_id': None, 'running': False, 'phase': 'idle',
        'total_communities': 0, 'processed_communities': 0,
        'current_community_id': None, 'pages_fetched': 0, 'details_fetched': 0,
        'success_count': 0, 'failed_count': 0,
        'started_at': None, 'finished_at': None, 'last_success_at': None,
        'errors': {'total': 0, 'items': []}, 'result': None,
    }


def _atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@dataclass(frozen=True)
class _SeedPlan:
    seed: str
    community_id: str
    source_community_id: str


class RentalRefreshService:
    """Single-slot rental refresh: worker thread + persisted job state.

    Concurrency model: one RLock guards the in-memory job and job-file writes;
    _update_job/_add_error/_snapshot take it themselves, so workers and API
    threads can interleave freely.
    """

    def __init__(self, rentals_dir: Path, mappings_path: Path, *,
                 fetch_factory: Callable[..., object] = FangClient,
                 max_pages: int = DEFAULT_MAX_PAGES,
                 delay: float = DEFAULT_DELAY_SECONDS,
                 timeout: float = DEFAULT_TIMEOUT_SECONDS,
                 details: bool = True,
                 max_errors_kept: int = MAX_ERRORS_KEPT):
        self.rentals_dir = Path(rentals_dir)
        self.mappings_path = Path(mappings_path)
        self._fetch_factory = fetch_factory
        self._max_pages = max_pages
        self._delay = delay
        self._timeout = timeout
        self._details = details
        self._max_errors_kept = max_errors_kept
        self._mutex = threading.RLock()
        self._cancel_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._job_path = self.rentals_dir / JOB_FILE_NAME
        self._job = self._load_job_file()
        self._recover_interrupted_job()

    # ------------------------------------------------------------- public

    def start(self) -> dict:
        """Start a refresh job and return its snapshot (202 semantics).

        Raises RefreshAlreadyRunning (409) when the single slot is taken and
        NoVerifiedMappings (422) when the ledger has nothing verified to crawl.
        Crawl limits are service configuration, never request parameters.
        """
        with self._mutex:
            if self._has_active_thread():
                raise RefreshAlreadyRunning('rental refresh job is already running')
            mappings = load_verified_mappings(self.mappings_path)
            from src.services.community_registry import existing_registry
            registry = existing_registry(self.mappings_path.parent)
            if not mappings and not registry:
                raise NoVerifiedMappings('no verified rental community mappings')
            plans = [_SeedPlan(seed=f'{BASE_URL}/hz/house-xm{source_id}/',
                               community_id=community_id,
                               source_community_id=source_id)
                     for source_id, community_id in mappings]
            self._cancel_event.clear()
            job = _initial_job()
            # last_success_at survives jobs: a failed rerun must still be able
            # to show when rentals were last published successfully (R2).
            job['last_success_at'] = self._job.get('last_success_at')
            job.update(job_id=uuid.uuid4().hex, running=True, phase='crawling',
                       total_communities=len(plans), started_at=_utc_now())
            self._job = job
            self._write_job_file()
            thread = threading.Thread(
                target=self._execute,
                args=({plan.seed: plan for plan in plans},),
                name='rental-refresh', daemon=True)
            self._thread = thread
            thread.start()
            return self._snapshot()

    def change_sources(self, action):
        """Serialize source edits with web start and CLI publishing."""
        from src.services.rental_reference.storage import RentalPublishLock
        with self._mutex:
            if self._has_active_thread():
                raise RefreshAlreadyRunning('请等待租金更新结束后修改关联')
            try:
                with RentalPublishLock(self.rentals_dir / 'rental_publish'):
                    return action()
            except BlockingIOError as exc:
                raise RefreshAlreadyRunning('租金发布正在进行，请稍后修改关联') from exc

    def cancel(self) -> dict:
        """Request cancellation; the phase stays cancelling until the worker stops."""
        with self._mutex:
            if not self._has_active_thread():
                raise RefreshNotRunning('no active rental refresh job')
            self._cancel_event.set()
            self._update_job(phase='cancelling')
            return self._snapshot()

    def status(self) -> dict:
        """Current job snapshot; after a restart this comes from the job file."""
        with self._mutex:
            return self._snapshot()

    def shutdown(self, timeout: float = 30.0) -> bool:
        """Cancel any active job and join the worker; False on join timeout.

        Called from the FastAPI shutdown hook. A timed-out worker is reported,
        never blocked on forever; the daemon thread cannot keep the process up.
        """
        with self._mutex:
            thread = self._thread
            if not self._has_active_thread() or thread is None:
                return True
            self._cancel_event.set()
            # The worker finalizes under this same mutex. Never overwrite its
            # terminal phase with a stale "running" snapshot after releasing it.
            if self._job.get('running'):
                self._job['phase'] = 'cancelling'
                self._write_job_file()
        thread.join(timeout)
        return not thread.is_alive()

    # ------------------------------------------------------------ worker

    def _execute(self, plans: dict[str, _SeedPlan]) -> None:
        progress = CrawlProgress(total_seeds=len(plans))
        ordered = list(plans.values())
        batches: list[CommunityBatch] = []
        crawl_errors: list[dict] = []
        truncated_seeds: list[str] = []
        client = None
        outcome_phase = 'failed'
        result_summary: dict | None = None
        def skip_seed(seed):
            from src.services.community_registry import existing_registry
            registry = existing_registry(self.mappings_path.parent)
            if not registry:
                return False
            plan = plans[seed]
            if registry:
                from src.services.rental_reference.association import eligible_communities
                if plan.community_id not in {c['community_id'] for c in eligible_communities(registry)[0]}:
                    return True
            return not any(r['source'] == 'fang' and r['source_id'] == plan.source_community_id
                           and r['community_id'] == plan.community_id and r['status'] == 'matched'
                           for r in registry.sources())
        try:
            from src.services.community_registry import existing_registry
            registry = existing_registry(self.mappings_path.parent)
            if registry:
                from src.services.rental_reference.association import prepare_sources
                from src.services.rental_reference.sources import discover
                self._update_job(stage='checking')
                pairs, association = prepare_sources(registry, self._cancel_event,
                    lambda values: self._update_job(stage='discovering', association=values),
                    lambda community: discover(community, client_factory=self._fetch_factory), delay=self._delay)
                ordered = [_SeedPlan(f'{BASE_URL}/hz/house-xm{sid}/', cid, sid) for sid, cid in pairs]
                plans = {plan.seed: plan for plan in ordered}
                progress = CrawlProgress(total_seeds=len(plans))
                self._update_job(stage='crawling', total_communities=len(plans), association=association)
                if not plans:
                    if self._cancel_event.is_set():
                        outcome_phase = 'cancelled'
                    else:
                        outcome_phase = 'done'
                    result_summary = {'published': False, 'reason': 'no_sources'}
                    return
            self._update_job(stage='crawling')
            client = self._fetch_factory(timeout=self._timeout)
            for index, seed_result in enumerate(crawl_runs(
                    [plan.seed for plan in ordered], fetch=client.fetch,
                    max_pages=self._max_pages, delay=self._delay,
                    details=self._details, cancel_event=self._cancel_event,
                    progress=progress, skip_seed=skip_seed)):
                plan = plans[seed_result.seed]
                next_plan = ordered[index + 1] if index + 1 < len(ordered) else None
                captured_at = (seed_result.samples[0]['captured_at']
                               if seed_result.samples else _utc_now())
                # Failed seeds keep their samples for diagnostics only; passing
                # them to publish_run with a failed status is what triggers the
                # carried_over/absent logic instead of dropping the community.
                batches.append(CommunityBatch(
                    community_id=plan.community_id, source='fang',
                    source_community_id=plan.source_community_id,
                    status=seed_result.status, captured_at=captured_at,
                    samples=seed_result.samples,
                    quality={'duplicate_source_ids_skipped': seed_result.duplicate_ids},
                    pages_fetched=seed_result.pages_fetched,
                    pages_truncated=seed_result.pages_truncated,
                    detail_success=seed_result.detail_success,
                    detail_failed=seed_result.detail_failed,
                    duplicate_ids=seed_result.duplicate_ids,
                    errors=seed_result.errors))
                crawl_errors.extend(seed_result.errors)
                if seed_result.pages_truncated:
                    truncated_seeds.append(seed_result.seed)
                succeeded = seed_result.status in ADOPTABLE_STATUSES
                # current_community_id points at the upcoming seed: per-seed
                # snapshots land only after a seed finishes, so the "current"
                # community is the next one being worked on.
                with self._mutex:
                    self._job.update({
                        'processed_communities': progress.processed_seeds,
                        'current_community_id':
                            next_plan.community_id if next_plan else None,
                        'pages_fetched': progress.pages_fetched,
                        'details_fetched': progress.details_fetched,
                        'success_count':
                            self._job['success_count'] + (1 if succeeded else 0),
                        'failed_count':
                            self._job['failed_count'] + (0 if succeeded else 1),
                    })
                    errors = self._job['errors']
                    for error in seed_result.errors:
                        errors['total'] += 1
                        if len(errors['items']) < self._max_errors_kept:
                            errors['items'].append(
                                {'community_id': plan.community_id, **error})
                    self._write_job_file()
            self._update_job(phase='publishing', stage='publishing', current_community_id=None)
            report = {'seeds': [plan.seed for plan in ordered],
                      'errors': crawl_errors,
                      'truncated_seeds': truncated_seeds,
                      'pages_fetched': progress.pages_fetched,
                      'details_fetched': progress.details_fetched}
            batches = [batch for batch in batches if not skip_seed(next(
                plan.seed for plan in ordered if plan.community_id == batch.community_id))]
            if not batches:
                result_summary = {'published': False, 'reason': 'sources_changed'}
                self._update_job(success_count=0, failed_count=len(ordered))
                self._add_error({'stage': 'publish', 'error': '小区或来源关联已变更，本次未发布，保留原数据'})
                return
            publish = publish_run(self.rentals_dir, batches, report=report,
                                  cancel_event=self._cancel_event)
            result_summary = {
                'published': publish.published, 'run_id': publish.run_id,
                'reason': publish.reason, 'published_at': publish.published_at,
                'adopted': list(publish.adopted),
                'carried_over': list(publish.carried_over),
                'absent': list(publish.absent),
            }
            if publish.published:
                outcome_phase = 'done'
                self._update_job(last_success_at=publish.published_at)
            elif publish.reason == 'cancelled':
                outcome_phase = 'cancelled'
            # all_failed keeps outcome_phase 'failed'; the pointer never moved.
        except RentalCrawlCancelled as cancelled:
            outcome_phase = 'cancelled'
            result_summary = {'published': False, 'reason': 'cancelled',
                              'completed_communities': len(cancelled.completed)}
        except BlockingIOError as exc:
            outcome_phase = 'failed'
            self._add_error({'stage': 'publish', 'error': str(exc)})
        except Exception as exc:  # worker must never die silently
            outcome_phase = 'failed'
            self._add_error({'stage': 'worker',
                             'error': f'{type(exc).__name__}: {exc}'})
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass
            with self._mutex:
                self._job.update({'running': False, 'phase': outcome_phase,
                                  'finished_at': _utc_now(),
                                  'current_community_id': None,
                                  'result': result_summary})
                self._write_job_file()

    # ------------------------------------------------------------- state

    def _has_active_thread(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _update_job(self, **fields) -> None:
        with self._mutex:
            self._job.update(fields)
            self._write_job_file()

    def _add_error(self, entry: dict) -> None:
        with self._mutex:
            errors = self._job['errors']
            errors['total'] += 1
            if len(errors['items']) < self._max_errors_kept:
                errors['items'].append(entry)
            self._write_job_file()

    def _snapshot(self) -> dict:
        with self._mutex:
            return copy.deepcopy(self._job)

    def _write_job_file(self) -> None:
        # Caller holds self._mutex (RLock), so job mutations and their write
        # are serialized against cancel()/status() from API threads.
        _atomic_write_json(self._job_path, self._job)

    def _load_job_file(self) -> dict:
        try:
            payload = json.loads(self._job_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return _initial_job()
        if (not isinstance(payload, dict) or not isinstance(payload.get('phase'), str)
                or not isinstance(payload.get('running'), bool)
                or not isinstance(payload.get('errors'), dict)):
            return _initial_job()
        return payload

    def _recover_interrupted_job(self) -> None:
        """Mark a persisted running job interrupted once this process has no worker.

        The publish lock is never deleted here: the OS releases the file lock
        when the previous process died, and the sidecar lock file is
        deliberately retained (see storage.RentalPublishLock). Age-based
        lock-file cleanup could kill a live CLI publisher, so recovery only
        rewrites the job state and lets the next publish contest the lock.
        """
        with self._mutex:
            if self._has_active_thread():
                return
            if self._job.get('running'):
                self._job.update(running=False, phase='interrupted',
                                 finished_at=self._job.get('finished_at') or _utc_now(),
                                 current_community_id=None)
                self._write_job_file()
