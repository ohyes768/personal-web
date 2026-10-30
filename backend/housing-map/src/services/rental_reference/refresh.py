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
import logging
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
    load_current,
)
from src.services.fang_detail_cache import FangDetailCache
from src.services.fang_request_policy import FangRequestPolicy, FangRequestCancelled
from src.services.rental_reference.providers import active_sources, same_source, source_url
from src.services.xingfuli_rentals import MAX_SAMPLES, XingfuliClient
from src.services.xingfuli_transport import DEFAULT_XINGFULI_DELAY
from src.services.rental_reference.statistics import select_valid

JOB_FILE_NAME = 'refresh_job.json'
DEFAULT_MAX_PAGES = 10
DEFAULT_DELAY_SECONDS = 5.0
DEFAULT_TIMEOUT_SECONDS = 20.0
MAX_ERRORS_KEPT = 20

logger = logging.getLogger(__name__)


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
        return [(r['source_id'], cid) for cid, r in active_sources(registry).items() if cid in valid_ids]
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
        'request_count': 0, 'detail_cache_hits': 0, 'reused_communities': 0,
        'deferred_count': 0, 'cooldown_until': None, 'new_sources_deferred': 0,
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
    source: str = 'fang'
    seed_listing_id: str | None = None
    community_name: str = ''
    property_type: str = '住宅'


class RentalRefreshService:
    """Single-slot rental refresh: worker thread + persisted job state.

    Concurrency model: one RLock guards the in-memory job and job-file writes;
    _update_job/_add_error/_snapshot take it themselves, so workers and API
    threads can interleave freely.
    """

    def __init__(self, rentals_dir: Path, mappings_path: Path, *,
                 fetch_factory: Callable[..., object] = FangClient,
                 xingfuli_factory: Callable[..., object] = XingfuliClient,
                 discovery_factory: Callable[..., object] | None = None,
                 auto_discover: bool = False,
                 xingfuli_only: bool = False, task_lock=None, busy=None,
                 max_pages: int = DEFAULT_MAX_PAGES,
                 delay: float | None = None,
                 timeout: float = DEFAULT_TIMEOUT_SECONDS,
                 details: bool = True,
                 reuse_hours: float = 6,
                 max_errors_kept: int = MAX_ERRORS_KEPT):
        self.rentals_dir = Path(rentals_dir)
        self.mappings_path = Path(mappings_path)
        self._fetch_factory = fetch_factory
        self._xingfuli_factory = xingfuli_factory
        self._discovery_factory = discovery_factory
        # Automatic source discovery reaches the platform; it is switched off
        # by default so an offline run never calls out, and so the feature can
        # be rolled back without touching the recorded sources.
        self._auto_discover = auto_discover
        self._xingfuli_only = xingfuli_only
        self._busy = busy
        self._max_pages = max_pages
        self._delay = delay if delay is not None else (DEFAULT_XINGFULI_DELAY if xingfuli_only else DEFAULT_DELAY_SECONDS)
        self._xingfuli_delay = delay if delay is not None else DEFAULT_XINGFULI_DELAY
        self._timeout = timeout
        self._details = details
        self._reuse_hours = reuse_hours
        self._max_errors_kept = max_errors_kept
        self._mutex = task_lock if task_lock is not None else threading.RLock()
        self._cancel_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._job_path = self.rentals_dir / JOB_FILE_NAME
        self._scope_cache: tuple | None = None
        self._snapshot_cache: tuple | None = None
        self._job = self._load_job_file()
        self._recover_interrupted_job()

    # ------------------------------------------------------------- public

    @staticmethod
    def _file_key(path: Path):
        """文件指纹；台账/快照变了才算数，没变就复用已算好的结果。"""
        try:
            stat = path.stat()
        except OSError:
            return None
        return (stat.st_mtime_ns, stat.st_size)

    def _scope_key(self):
        from src.services.community_registry import registry_path
        from src.services.rental_reference.sources import database_path
        return (self._file_key(registry_path(self.mappings_path.parent)),
                self._file_key(self.mappings_path),
                self._file_key(database_path(self.mappings_path)))

    def _scope(self):
        """采集范围：已收录住宅 × 已关联来源。

        待采集数量与“继续采集”共用这一份名单，避免数量和实际下手的对象
        各算各的。范围按台账文件指纹缓存，台账不变就不重算。
        """
        key = self._scope_key()
        with self._mutex:
            cached = self._scope_cache
            if cached is not None and cached[0] == key:
                return cached[1]
        from src.services.community_registry import existing_registry
        from src.services.rental_reference.association import eligible_communities
        registry = existing_registry(self.mappings_path.parent)
        if not registry:
            plans = [_SeedPlan(f'{BASE_URL}/hz/house-xm{sid}/', cid, sid)
                     for sid, cid in load_verified_mappings(self.mappings_path)]
            scope = (registry, {}, {}, plans)
        else:
            eligible = {c['community_id']: c for c in eligible_communities(registry)[0]}
            selected = active_sources(registry, xingfuli_only=self._xingfuli_only)
            plans = [_SeedPlan(source_url(r), cid, r['source_id'], r['source'],
                               r.get('seed_listing_id'), eligible[cid]['community_name'],
                               eligible[cid].get('effective_property_type') or eligible[cid].get('property_type') or '住宅')
                     for cid, r in selected.items() if cid in eligible]
            plans.sort(key=lambda p: p.source == 'fang')
            scope = (registry, eligible, selected, plans)
        with self._mutex:
            self._scope_cache = (key, scope)
        return scope

    def _published_entries(self) -> dict:
        """已发布快照里各小区的条目（按快照指针文件指纹缓存）。"""
        key = self._file_key(self.rentals_dir / 'current.json')
        with self._mutex:
            cached = self._snapshot_cache
            if cached is not None and cached[0] == key:
                return cached[1]
        entries = (load_current(self.rentals_dir) or {}).get('communities', {})
        with self._mutex:
            self._snapshot_cache = (key, entries)
        return entries

    def _collected(self, plan, entry, outcomes):
        """这个小区是否已经采集成功并发布。

        完成 = 当前来源与快照一致 + 快照状态可采用 + 最近一次采集也成功。
        换过来源、采集失败、结果不完整（截断/列表失败）或采集完没发布的，
        都算没采完，重新采。
        """
        if not same_source(entry, plan.source, plan.source_community_id) or entry.get('status') not in ADOPTABLE_STATUSES:
            return False
        outcome = (outcomes or {}).get(plan.community_id)
        if outcome and same_source(outcome, plan.source, plan.source_community_id):
            if outcome.get('status') not in ADOPTABLE_STATUSES:
                return False
            # A completed crawl that never published (cancel/failure) is unfinished.
            return entry.get('captured_at') == outcome.get('captured_at')
        return True

    def continuation_count(self) -> int | None:
        """待采集数量：范围内尚未采集成功的小区数；算不出时返回 None（数量未知）。"""
        try:
            _registry, _eligible, _selected, plans = self._scope()
            entries = self._published_entries()
            with self._mutex:
                outcomes = dict(self._job.get('community_outcomes') or {})
            return sum(not self._collected(plan, entries.get(plan.community_id), outcomes)
                       for plan in plans)
        except Exception as exc:
            # 台账坏了也要让状态接口活着：数量未知比假装 0 更诚实。
            logger.warning('待采集数量计算失败：%s', exc)
            return None

    def start(self, mode='all') -> dict:
        """Start a refresh job and return its snapshot (202 semantics).

        Raises RefreshAlreadyRunning (409) when the single slot is taken and
        NoVerifiedMappings (422) when the ledger has nothing verified to crawl.
        Crawl limits are service configuration, never request parameters.
        """
        if mode not in {'all', 'continue'}:
            raise ValueError('未知租金采集模式')
        with self._mutex:
            if self._has_active_thread():
                raise RefreshAlreadyRunning('rental refresh job is already running')
            if self._busy and self._busy():
                raise RefreshAlreadyRunning('租金来源匹配正在运行，请结束后再更新租金数据')
            registry, _eligible, _selected, plans = self._scope()
            if self._xingfuli_only and not any(plan.source == 'xingfuli' for plan in plans):
                raise NoVerifiedMappings('请先匹配租金来源，再更新租金数据')
            if not plans and not registry:
                raise NoVerifiedMappings('no verified rental community mappings')
            self._cancel_event.clear()
            job = _initial_job()
            # last_success_at survives jobs: a failed rerun must still be able
            # to show when rentals were last published successfully (R2).
            job['last_success_at'] = self._job.get('last_success_at')
            job['community_outcomes'] = copy.deepcopy(self._job.get('community_outcomes') or {})
            job['mode'] = mode
            job.update(job_id=uuid.uuid4().hex, running=True, phase='crawling',
                       total_communities=len(plans), started_at=_utc_now())
            self._job = job
            self._write_job_file()
            thread = threading.Thread(
                target=self._execute,
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
            if self._busy and self._busy():
                raise RefreshAlreadyRunning('租金来源匹配正在运行，请结束后修改关联')
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
            value = self._snapshot()
        value['continuable'] = self.continuation_count()
        return value

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

    def _execute(self) -> None:
        progress = CrawlProgress(total_seeds=0)
        ordered: list[_SeedPlan] = []
        plans: dict[str, _SeedPlan] = {}
        batches: list[CommunityBatch] = []
        crawl_errors: list[dict] = []
        truncated_seeds: list[str] = []
        client = None
        xingfuli_client = None
        outcome_phase = 'failed'
        result_summary: dict | None = None
        reused = {}
        policy = None
        request_count = 0
        crawl_paused = None
        cache = FangDetailCache(self.rentals_dir)
        cache.prune()
        def skip_seed(seed):
            registry, eligible, selected, _scoped = self._scope()
            if not registry:
                return False
            plan = plans[seed]
            if plan.community_id not in eligible:
                return True
            current = selected.get(plan.community_id)
            return not current or (current['source'], current['source_id']) != (plan.source, plan.source_community_id)
        try:
            registry, eligible, selected, scoped = self._scope()
            ordered = scoped
            plans = {plan.seed: plan for plan in ordered}
            progress = CrawlProgress(total_seeds=len(plans))
            if registry:
                self._update_job(stage='checking')
                self._update_job(stage='crawling', total_communities=len(plans))
            self._update_job(stage='crawling')
            previous = load_current(self.rentals_dir)
            entries = (previous or {}).get('communities', {})
            with self._mutex:
                outcomes = dict(self._job.get('community_outcomes') or {})
            now = dt.datetime.now(dt.UTC)
            for plan in ordered:
                entry = entries.get(plan.community_id)
                if (not same_source(entry, plan.source, plan.source_community_id)
                        or not self._collected(plan, entry, outcomes) or skip_seed(plan.seed)):
                    continue
                try:
                    age = (now - dt.datetime.fromisoformat(entry['captured_at'])).total_seconds()
                except (KeyError, TypeError, ValueError):
                    continue
                if 0 <= age < self._reuse_hours * 3600:
                    reused[plan.community_id] = (plan.source, plan.source_community_id)
            if self._job.get('mode') == 'continue':
                # 继续采集只补没采完的：已采完的保留原数据，不重爬也不重发。
                reused = {p.community_id: (p.source, p.source_community_id) for p in ordered
                          if self._collected(p, entries.get(p.community_id), outcomes)}
            ordered = [plan for plan in ordered if plan.community_id not in reused]
            progress.processed_seeds = len(reused)
            self._update_job(reused_communities=len(reused), processed_communities=len(reused))
            needs_discovery = not self._xingfuli_only and registry and any(cid not in selected for cid in eligible)
            if any(p.source == 'fang' for p in ordered) or needs_discovery:
                client = self._fetch_factory(timeout=self._timeout)
                if isinstance(client, FangClient):
                    policy = FangRequestPolicy(self.rentals_dir, cancel_event=self._cancel_event)
                    client.policy = policy
                    client.detail_cache = cache
            def fetch(url):
                nonlocal request_count
                request_count += 1
                return client.fetch(url)
            def results():
                nonlocal xingfuli_client
                for plan in ordered:
                    if plan.source != 'xingfuli':
                        continue
                    if skip_seed(plan.seed):
                        continue
                    self._update_job(current_community_id=plan.community_id)
                    if xingfuli_client is None:
                        xingfuli_client = self._xingfuli_factory(timeout=self._timeout, directory=self.rentals_dir,
                            cancel_event=self._cancel_event, delay=self._xingfuli_delay)
                    result = xingfuli_client.crawl(plan.source_community_id, plan.seed_listing_id,
                        community_name=plan.community_name, property_type=plan.property_type,
                        max_pages=self._max_pages, details=self._details, cancel_event=self._cancel_event)
                    progress.processed_seeds += 1
                    progress.pages_fetched += result.pages_fetched
                    progress.details_fetched += result.detail_success + result.detail_failed
                    yield result
                yield from crawl_runs([p.seed for p in ordered if p.source == 'fang'], fetch=fetch,
                        max_pages=self._max_pages, delay=self._delay, details=self._details,
                        cancel_event=self._cancel_event, progress=progress, skip_seed=skip_seed, detail_cache=cache)
            for index, seed_result in enumerate(results()):
                plan = plans[seed_result.seed]
                crawl_paused = crawl_paused or seed_result.pause_reason
                next_plan = ordered[index + 1] if index + 1 < len(ordered) else None
                captured_at = (seed_result.samples[0]['captured_at']
                               if seed_result.samples else _utc_now())
                # Failed seeds keep their samples for diagnostics only; passing
                # them to publish_run with a failed status is what triggers the
                # carried_over/absent logic instead of dropping the community.
                quality = {'duplicate_source_ids_skipped': seed_result.duplicate_ids}
                if plan.source == 'xingfuli':
                    # 列表抽样快照：记录检查行数和统计过滤后的有效数
                    quality['sampling'] = {
                        'mode': 'list_api',
                        'quota': MAX_SAMPLES,
                        'qualified': len(select_valid(seed_result.samples)[0]),
                        'sampled': len(seed_result.samples),
                    }
                batches.append(CommunityBatch(
                    community_id=plan.community_id, source=plan.source,
                    source_community_id=plan.source_community_id,
                    status=seed_result.status, captured_at=captured_at,
                    samples=seed_result.samples,
                    quality=quality,
                    pages_fetched=seed_result.pages_fetched,
                    pages_truncated=seed_result.pages_truncated,
                    detail_success=seed_result.detail_success,
                    detail_failed=seed_result.detail_failed,
                    duplicate_ids=seed_result.duplicate_ids,
                    errors=seed_result.errors))
                crawl_errors.extend(seed_result.errors)
                if seed_result.pages_truncated:
                    truncated_seeds.append(seed_result.seed)
                with self._mutex:
                    self._job.setdefault('community_outcomes', {})[plan.community_id] = dict(
                        source=plan.source, source_community_id=plan.source_community_id,
                        status=seed_result.status, captured_at=captured_at)
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
                            self._job['failed_count'] + (0 if succeeded or seed_result.deferred else 1),
                        'deferred_count': self._job['deferred_count'] + int(seed_result.deferred),
                        'detail_cache_hits': self._job['detail_cache_hits'] + seed_result.detail_cache_hits,
                        'request_count': (policy.request_count if policy else request_count)
                                         + (xingfuli_client.request_count if xingfuli_client else 0),
                    })
                    errors = self._job['errors']
                    for error in seed_result.errors:
                        errors['total'] += 1
                        if len(errors['items']) < self._max_errors_kept:
                            errors['items'].append(
                                {'community_id': plan.community_id, **error})
                    self._write_job_file()
            if registry and not self._xingfuli_only:
                from src.services.rental_reference.association import prepare_sources
                from src.services.rental_reference.sources import discover
                # A paused crawl must not immediately start searching via another client.
                pairs, association = prepare_sources(registry, self._cancel_event,
                    lambda values: self._update_job(stage='discovering', association=values),
                    lambda community: discover(community, client_factory=self._fetch_factory, client=client),
                    delay=self._delay, budget=5, paused_reason=crawl_paused)
                self._update_job(association=association,
                    new_sources_deferred=sum(cid not in {p.community_id for p in plans.values()} for _, cid in pairs))
                xingfuli_association = self._discover_xingfuli_sources(registry, eligible, selected)
                if xingfuli_association:
                    self._update_job(xingfuli_association=xingfuli_association)
            if self._cancel_event.is_set():
                raise RentalCrawlCancelled([], None)
            self._update_job(phase='publishing', stage='publishing', current_community_id=None)
            report = {'seeds': [plan.seed for plan in ordered],
                      'errors': crawl_errors,
                      'truncated_seeds': truncated_seeds,
                      'pages_fetched': progress.pages_fetched,
                      'details_fetched': progress.details_fetched}
            batches = [batch for batch in batches if not skip_seed(next(
                plan.seed for plan in ordered if plan.community_id == batch.community_id))]
            reused = {cid: sid for cid, sid in reused.items()
                      if not skip_seed(next(p.seed for p in plans.values() if p.community_id == cid))}
            if not batches:
                if reused or not plans:
                    outcome_phase = 'done'
                    result_summary = {'published': False, 'reason': 'cached' if reused else 'no_sources'}
                    return
                result_summary = {'published': False, 'reason': 'sources_changed'}
                self._update_job(success_count=0, failed_count=len(ordered))
                self._add_error({'stage': 'publish', 'error': '小区或来源关联已变更，本次未发布，保留原数据'})
                return
            publish = publish_run(self.rentals_dir, batches, report=report,
                                  cancel_event=self._cancel_event, preserved_sources=reused)
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
                if policy and self._details and ordered and all(b.status in ADOPTABLE_STATUSES for b in batches):
                    policy.mark_complete()
            elif publish.reason == 'cancelled':
                outcome_phase = 'cancelled'
            # all_failed keeps outcome_phase 'failed'; the pointer never moved.
        except (RentalCrawlCancelled, FangRequestCancelled) as cancelled:
            outcome_phase = 'cancelled'
            result_summary = {'published': False, 'reason': 'cancelled',
                              'completed_communities': len(getattr(cancelled, 'completed', []))}
        except BlockingIOError as exc:
            outcome_phase = 'failed'
            self._add_error({'stage': 'publish', 'error': str(exc)})
        except Exception as exc:  # worker must never die silently
            outcome_phase = 'failed'
            self._add_error({'stage': 'worker',
                             'error': f'{type(exc).__name__}: {exc}'})
        finally:
            self._update_job(detail_cache_hits=cache.hits)
            if policy is not None:
                # status uses a fresh uncancelled reader after worker cancellation.
                try:
                    state = FangRequestPolicy(self.rentals_dir).status()
                    until = state['cooldown_until']
                    self._update_job(request_count=policy.request_count + (xingfuli_client.request_count if xingfuli_client else 0),
                        cooldown_until=dt.datetime.fromtimestamp(until, dt.UTC).isoformat() if until > dt.datetime.now(dt.UTC).timestamp() else None)
                except Exception as exc:
                    self._add_error({'stage': 'request_state', 'error': str(exc)})
            if xingfuli_client is not None:
                if policy is None:
                    self._update_job(request_count=request_count + xingfuli_client.request_count)
                if xingfuli_client.cooldown_until:
                    self._update_job(cooldown_until=max(filter(None, [self._job.get('cooldown_until'), xingfuli_client.cooldown_until])))
                try:
                    xingfuli_client.close()
                except Exception:
                    pass
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

    def _discover_xingfuli_sources(self, registry, eligible, selected):
        """Bind the Xingfuli sources whose identity the platform proves.

        Only communities without any rental source are searched, and the
        request budget is bounded; the rest stays for the on-demand probe.
        """
        if not self._auto_discover:
            return {}
        from src.services.rental_reference.xingfuli_sources import auto_discover
        from src.services.xingfuli_discovery import XingfuliDiscovery
        missing = [c for cid, c in eligible.items() if cid not in selected]
        if not missing:
            return {}
        factory = self._discovery_factory or XingfuliDiscovery
        discovery = factory(timeout=self._timeout, directory=self.rentals_dir,
                            cancel_event=self._cancel_event, delay=self._xingfuli_delay)
        try:
            report = auto_discover(registry, discovery, missing, budget=5, cancel=self._cancel_event)
        except Exception as exc:
            # The discovery is an optional stage: it must never break the run,
            # but the failure stays visible in the job report.
            logger.exception('Xingfuli source discovery failed')
            self._add_error({'stage': 'xingfuli_discovery', 'error': str(exc) or '幸福里来源发现失败'})
            return {}
        # The discovery spends real requests; the job counts every HTTP hop.
        with self._mutex:
            self._job['request_count'] = self._job.get('request_count', 0) + discovery.request_count
        return report

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
