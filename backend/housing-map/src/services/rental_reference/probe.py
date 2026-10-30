"""按需探查幸福里小区主页与真实租房入口。

用户不提供链接：系统自行搜索平台、列出候选小区主页，用户只做一次主页选择，
随后由系统在该主页内找到真实租房入口并核验归属。主页选择本身不是租金绑定，
只有入口核验通过才创建可采集的来源。
"""
from __future__ import annotations

import json
import logging
import os
import threading
import uuid

from src.services.xingfuli_transport import DEFAULT_XINGFULI_DELAY
from src.services.community_registry import dump, now
from src.services.fang_rentals import RentalCrawlCancelled
from src.services.rental_reference.xingfuli_sources import (
    bind_source,
    candidate_from_homepage,
    community_names,
    rental_name_key,
    evaluate,
)
from src.services.xingfuli_discovery import CHANNEL_ORDER, SEARCH_PAGE_SIZE, XingfuliDiscovery
from src.services.rental_reference.discovery_checkpoint import DiscoveryCheckpoint, DiscoveryBudgetExhausted

logger = logging.getLogger(__name__)

PREFIX = 'rental_probe:'
SCHEMA_VERSION = '1'
DEFAULT_BUDGET = 12
MAX_CANDIDATES = 4
MAX_SEED_TRIES = 3

STAGE_IDLE = 'idle'
STAGE_SEARCHING = 'searching_homepage'
STAGE_NEEDS_SELECTION = 'needs_homepage_selection'
STAGE_RESOLVING = 'resolving_entry'
STAGE_BOUND = 'bound_pending_collection'
STAGE_NO_HOMEPAGE = 'homepage_not_found'
STAGE_NO_ENTRY = 'entry_not_found'
STAGE_NO_LISTINGS = 'no_rental_listings'
STAGE_FAILED = 'upstream_failed'
STAGE_COOLING = 'cooling_down'
STAGE_DEFERRED = 'deferred'
STAGE_CANCELLED = 'cancelled'
STAGE_INTERRUPTED = 'interrupted'


class ProbeAlreadyRunning(RuntimeError):
    """409: another probe job holds the single probe slot."""


class ProbeNotRunning(RuntimeError):
    """409: there is no active probe job to cancel."""


class ProbeConflict(RuntimeError):
    """409: the candidate changed, or the community is no longer probeable."""


class ProbeInvalid(RuntimeError):
    """422: the request contradicts the recorded probe state."""


def state_key(community_id):
    return PREFIX + community_id


def read_state(registry, community_id):
    raw = registry.read_meta(state_key(community_id))
    return json.loads(raw) if raw else {}


def write_state(registry, community_id, **fields):
    with registry.db() as db:
        row = db.execute('SELECT value FROM meta WHERE key=?', (state_key(community_id),)).fetchone()
        state = json.loads(row[0]) if row else {}
        state.update(fields)
        state['schema_version'] = SCHEMA_VERSION
        state['community_id'] = community_id
        state['revision'] = int(state.get('revision') or 0) + 1
        state['updated_at'] = now()
        db.execute('INSERT INTO meta(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                   (state_key(community_id), dump(state)))
    return state


def _related(query, platform_name):
    """Whether a platform name plausibly answers the searched name."""
    left, right = rental_name_key(query), rental_name_key(platform_name)
    if not left or not right:
        return False
    return left == right or left in right or right in left


def _search_names(community):
    names, seen = [], set()
    for name in community_names(community):
        key = rental_name_key(name)
        if key and key not in seen:
            names.append(name)
            seen.add(key)
    # The main name first, then at most one alias; every extra name costs a
    # request from a bounded budget.
    return names[:2]


class ProbeService:
    """Single-slot background probe of one community's Xingfuli source."""

    def __init__(self, registry, *, directory=None, delay=DEFAULT_XINGFULI_DELAY, timeout=20, budget=DEFAULT_BUDGET,
                 discovery_factory=None, busy=None, task_lock=None, xingfuli_only=False):
        self.registry = registry
        self.directory = directory
        self.delay = delay
        self.timeout = timeout
        self.budget = budget
        self.early_stop = os.getenv('HOUSING_XINGFULI_EARLY_STOP', '1') != '0'
        self._discovery_factory = discovery_factory or self._default_discovery
        self._busy = busy
        self._mutex = task_lock if task_lock is not None else threading.RLock()
        self._automatic = False
        self._require_strong = False
        self._xingfuli_only = xingfuli_only
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._job_id: str | None = None
        self._community_id: str | None = None

    def _default_discovery(self, **kwargs):
        return XingfuliDiscovery(**kwargs)

    # ------------------------------------------------------------- public

    def status(self, community_id):
        state = read_state(self.registry, community_id)
        state.setdefault('stage', STAGE_IDLE)
        state.setdefault('revision', 0)
        state['running'] = self._running_for(community_id)
        if state['stage'] == STAGE_NEEDS_SELECTION and state.get('candidates'):
            try:
                community = self._community(community_id)
            except ProbeInvalid:
                return state
            for candidate in state['candidates']:
                manual = evaluate(community, candidate, allow_subdivision=True)
                candidate['manual_selectable'] = manual['selectable']
                candidate['manual_scope'] = manual['manual_scope']
        return state

    def busy(self):
        """True while a probe job holds the slot."""
        with self._mutex:
            return bool(self._thread and self._thread.is_alive())

    def start(self, community_id, *, automatic=False):
        """Start looking for the community's homepage; 202 semantics."""
        with self._mutex:
            if self._thread is not None and self._thread.is_alive():
                if self._community_id == community_id:
                    return self.status(community_id)
                raise ProbeAlreadyRunning('已有其他小区的探查任务在进行')
            if self._busy and self._busy():
                raise ProbeAlreadyRunning('租金更新进行中，请稍后再探查')
            community = self._community(community_id)
            self._automatic = automatic
            self._cancel.clear()
            self._job_id = uuid.uuid4().hex
            self._community_id = community_id
            write_state(self.registry, community_id, stage=STAGE_SEARCHING, job_id=self._job_id,
                        message='正在查找幸福里小区主页', candidates=None, selected_page=None, error=None,
                        diagnostics={}, current_step=None)
            self._spawn(community, 'search')
        return self.status(community_id)

    def select(self, community_id, candidate_id, revision):
        """Remember the chosen homepage and continue to its rental entry."""
        with self._mutex:
            if self._thread is not None and self._thread.is_alive():
                raise ProbeAlreadyRunning('已有探查任务在进行，请等它结束')
            if self._busy and self._busy():
                raise ProbeAlreadyRunning('租金更新进行中，请稍后再探查')
            state = read_state(self.registry, community_id)
            if not state:
                raise ProbeInvalid('尚未开始探查')
            if revision is not None and int(revision) != int(state.get('revision') or 0):
                raise ProbeConflict('候选已更新，请刷新后重新选择')
            candidate = next((c for c in state.get('candidates') or []
                              if c.get('candidate_id') == candidate_id), None)
            if candidate is None:
                raise ProbeConflict('候选已更新，请刷新后重新选择')
            community = self._community(community_id)
            self._automatic = False
            judgement = evaluate(community, candidate, allow_subdivision=True)
            if not judgement['selectable']:
                raise ProbeInvalid(('；'.join(judgement['conflicts']) or '主页名称与目录小区不匹配') + '，不能绑定到该小区')
            self._cancel.clear()
            self._job_id = uuid.uuid4().hex
            self._community_id = community_id
            write_state(self.registry, community_id, stage=STAGE_RESOLVING, job_id=self._job_id,
                        selected_page=candidate, message='正在寻找该主页的租房入口', error=None,
                        current_step=None, diagnostics={})
            self._spawn(community, 'entry')
        return self.status(community_id)

    def retry(self, community_id):
        """Retry the failed stage: the entry first, otherwise the search."""
        with self._mutex:
            if self._thread is not None and self._thread.is_alive():
                raise ProbeAlreadyRunning('已有探查任务在进行，请等它结束')
            if self._busy and self._busy():
                raise ProbeAlreadyRunning('租金更新进行中，请稍后再探查')
            state = read_state(self.registry, community_id)
            community = self._community(community_id)
            self._automatic = False
            mode = 'entry' if state.get('selected_page') and state.get('stage') != STAGE_NEEDS_SELECTION else 'search'
            self._cancel.clear()
            self._job_id = uuid.uuid4().hex
            self._community_id = community_id
            write_state(self.registry, community_id, stage=STAGE_SEARCHING if mode == 'search' else STAGE_RESOLVING,
                        job_id=self._job_id, message='正在重试', error=None, current_step=None, diagnostics={},
                        **({'selected_page': None, 'candidates': None} if mode == 'search' else {}))
            self._spawn(community, mode)
        return self.status(community_id)

    def cancel(self, community_id):
        """Stop the running probe; a chosen homepage survives the cancellation."""
        with self._mutex:
            if not self._running_for(community_id):
                raise ProbeNotRunning('没有正在进行的探查任务')
            self._cancel.set()
            write_state(self.registry, community_id, stage=STAGE_CANCELLED, message='探查已取消')
        return self.status(community_id)

    def shutdown(self, timeout: float = 30.0) -> bool:
        with self._mutex:
            thread = self._thread
            if thread is None or not thread.is_alive():
                return True
            self._cancel.set()
        thread.join(timeout)
        return not thread.is_alive()

    # ------------------------------------------------------------ internals

    def _running_for(self, community_id):
        return bool(self._thread and self._thread.is_alive() and self._community_id == community_id)

    def _community(self, community_id):
        from src.services.rental_reference.association import eligible_communities
        communities, _ = eligible_communities(self.registry)
        community = next((c for c in communities if c['community_id'] == community_id), None)
        if not community:
            raise ProbeInvalid('小区已删除或不是有效滨江住宅，请刷新')
        # A community that already has a source keeps it; the probe never
        # replaces an existing Fang or Xingfuli association.
        from src.services.rental_reference.xingfuli_sources import active_source
        try:
            existing = active_source(self.registry, community_id)
            if self._xingfuli_only and existing and existing.get('source') == 'fang':
                existing = None
        except ValueError:
            existing = True
        if existing:
            raise ProbeInvalid('小区已有租金来源，无需探查')
        return community

    def _spawn(self, community, mode):
        thread = threading.Thread(target=self._run, args=(community, mode),
                                  name='rental-probe', daemon=True)
        self._thread = thread
        thread.start()

    def _client(self):
        kwargs = dict(delay=self.delay, timeout=self.timeout, cancel_event=self._cancel)
        if self.directory is not None:
            kwargs['directory'] = self.directory
        return self._discovery_factory(**kwargs)

    def _run(self, community, mode):
        community_id = community['community_id']
        self._require_strong = mode == 'search' or self._automatic
        try:
            if mode == 'search':
                self._search(community)
            else:
                self._resolve_entry(community)
        except DiscoveryBudgetExhausted as exc:
            write_state(self.registry, community_id, stage=STAGE_DEFERRED, message=str(exc))
        except RentalCrawlCancelled:
            write_state(self.registry, community_id, stage=STAGE_CANCELLED, message='探查已取消')
        except Exception as exc:
            logger.exception('Rental probe failed community_id=%s mode=%s', community_id, mode)
            stage = STAGE_COOLING if '冷却' in str(exc) else STAGE_FAILED
            write_state(self.registry, community_id, stage=stage, message=str(exc) or '探查失败',
                        error=str(exc) or '探查失败')

    def _search(self, community):
        community_id = community['community_id']
        client = self._checkpoint_client(community)
        candidates = []
        seen = set()
        page_errors = []   # request failures; the search did not finish cleanly
        degraded = False   # a later page repeated without new identities
        truncated = False  # MAX_CANDIDATES reached before channels finished
        for name in _search_names(community):
            for channel in CHANNEL_ORDER:
                channel_seen = set()
                page_fingerprints = set()
                offset = 0
                while True:
                    try:
                        found = client.search(name, channel, offset)
                    except ValueError as exc:
                        logger.warning('Rental probe search failed community_id=%s channel=%s offset=%s error=%s',
                                       community_id, channel, offset, exc)
                        if '冷却' in str(exc):
                            write_state(self.registry, community_id, stage=STAGE_COOLING,
                                        message='幸福里请求冷却中，请稍后重试')
                            return
                        page_errors.append(str(exc))
                        break
                    new_ids = {nid for nid in found if nid not in channel_seen}
                    channel_seen.update(found)
                    for neighborhood_id, group in found.items():
                        platform_name = group['name']
                        if neighborhood_id in seen or not _related(name, platform_name):
                            continue
                        seen.add(neighborhood_id)
                        try:
                            homepage = client.community_info(neighborhood_id)
                        except ValueError as exc:
                            page_errors.append(str(exc))
                            logger.warning('Rental probe homepage failed community_id=%s id=%s error=%s',
                                           community_id, neighborhood_id, exc)
                            continue
                        candidate = candidate_from_homepage(homepage, discovered_via=channel)
                        judgement = evaluate(community, candidate, allow_name_only=True, allow_partial_name=True)
                        candidate['candidate_id'] = f"{channel}:{neighborhood_id}"
                        candidate['evidence'] = judgement['evidence']
                        candidate['evidence_gaps'] = judgement['gaps']
                        candidate['conflicts'] = judgement['conflicts']
                        candidate['strong'] = judgement['strong']
                        candidates.append(candidate)
                        if len(candidates) >= MAX_CANDIDATES:
                            truncated = True
                            break
                    if truncated:
                        break
                    page_fingerprint = client.search_page_fingerprint
                    repeated_page = (page_fingerprint in page_fingerprints if page_fingerprint
                                     else not new_ids and not client.search_complete)
                    if page_fingerprint:
                        page_fingerprints.add(page_fingerprint)
                    if offset > 0 and repeated_page:
                        # The raw listing page repeated, not merely the same
                        # neighborhood across different listing cards.
                        degraded = True
                        break
                    if client.search_complete:
                        break
                    offset += SEARCH_PAGE_SIZE
                if truncated:
                    break
                if self.early_stop and not page_errors and not degraded and not truncated \
                        and len(candidates) == 1 and candidates[0]['strong'] and not candidates[0]['conflicts']:
                    client.diagnostics['early_stop'] = True
                    client.report('resolving_entry')
                    write_state(self.registry, community_id, stage=STAGE_RESOLVING,
                                selected_page=candidates[0], message='正在核验租房入口')
                    self._resolve_entry(community, candidates[0], client)
                    return
            if truncated:
                break
        if not candidates:
            if page_errors:
                write_state(self.registry, community_id, stage=STAGE_FAILED, candidates=[],
                            message=f'幸福里搜索请求失败：{page_errors[-1]}，可重试')
            else:
                write_state(self.registry, community_id, stage=STAGE_NO_HOMEPAGE,
                            candidates=[], message='未找到幸福里小区主页，请检查名称')
            return
        strong = [c for c in candidates if c['strong'] and not c['conflicts']]
        if not page_errors and not degraded and not truncated \
                and len(candidates) == 1 and len(strong) == 1:
            write_state(self.registry, community_id, stage=STAGE_RESOLVING,
                        selected_page=candidates[0], message='正在寻找该主页的租房入口')
            self._resolve_entry(community, candidates[0], client)
            return
        write_state(self.registry, community_id, stage=STAGE_NEEDS_SELECTION, candidates=candidates,
                    message='搜索分页返回重复房源，无法确认唯一候选，请核对小区主页' if degraded else '请选择对应的小区主页')

    def _resolve_entry(self, community, candidate=None, client=None):
        community_id = community['community_id']
        state = read_state(self.registry, community_id)
        candidate = candidate or state.get('selected_page')
        if not candidate:
            write_state(self.registry, community_id, stage=STAGE_NEEDS_SELECTION,
                        message='请选择对应的小区主页')
            return
        client = client or self._checkpoint_client(community)
        # A restored/selected identity must be fresh before fetching entry
        # seeds and verifying live list ownership. Cold search already read it.
        if isinstance(client, DiscoveryCheckpoint) and candidate['neighborhood_id'] not in client.fresh_communities:
            homepage = client.community_info(candidate['neighborhood_id'], fresh=True)
            fresh_candidate = candidate_from_homepage(homepage, discovered_via=candidate.get('discovered_via', 'homepage'))
            fresh_candidate['candidate_id'] = candidate.get('candidate_id', 'homepage:' + candidate['neighborhood_id'])
            judgement = evaluate(community, fresh_candidate, allow_name_only=True, allow_partial_name=True,
                                 allow_subdivision=not self._require_strong)
            fresh_candidate.update(evidence=judgement['evidence'], evidence_gaps=judgement['gaps'],
                                   conflicts=judgement['conflicts'], strong=judgement['strong'])
            if not judgement['selectable'] or (self._require_strong and not judgement['strong']):
                reason = '；'.join(judgement['conflicts']) or '主页身份信息已变化'
                write_state(self.registry, community_id, stage=STAGE_NEEDS_SELECTION,
                            selected_page=None, candidates=[fresh_candidate],
                            message=reason + '，请重新探查')
                return
            candidate = fresh_candidate
        entry = client.rental_entry(candidate['neighborhood_id'])
        candidate = {**candidate, 'rent_total': entry['rent_total'], 'seeds': entry['seeds']}
        write_state(self.registry, community_id, selected_page=candidate)
        seeds = list(entry['seeds'])[:MAX_SEED_TRIES]
        if not seeds:
            empty = entry['rent_total'] == 0
            write_state(self.registry, community_id, stage=STAGE_NO_LISTINGS if empty else STAGE_NO_ENTRY,
                        message='该小区当前暂无在租房源，暂时无法采集租金；可稍后重新查询，无需更换主页' if empty
                        else '平台显示有租房房源，但未返回可核验的房源入口；请稍后重试')
            return
        for seed in seeds:
            if client.request_count >= self.budget:
                write_state(self.registry, community_id, stage=STAGE_DEFERRED,
                            message='本轮探查请求额度已用完，请稍后重试')
                return
            try:
                verified_seed = client.verified_rental_seed(seed, candidate['neighborhood_id'])
            except ValueError as exc:
                logger.warning('Rental probe list verification failed community_id=%s seed=%s error=%s',
                               community_id, seed, exc)
                if '冷却' in str(exc):
                    raise
                continue
            if not verified_seed:
                continue
            if self._cancel.is_set():
                write_state(self.registry, community_id, stage=STAGE_CANCELLED, message='探查已取消')
                return
            self._bind(community, candidate, verified_seed)
            return
        write_state(self.registry, community_id, stage=STAGE_NO_ENTRY,
                    message='租房房源归属核验未通过，暂未关联来源；请稍后重试或核对主页范围')

    def _checkpoint_client(self, community):
        return DiscoveryCheckpoint(self.registry, community, self._client(), self._cancel, self.budget,
                                   lambda step, diagnostics: write_state(
                                       self.registry, community['community_id'],
                                       current_step={'community_info': 'homepage',
                                                     'rental_entry': 'resolving_entry'}.get(step, step),
                                       diagnostics=diagnostics))

    def _bind(self, community, candidate, seed):
        community_id = community['community_id']
        from src.services.rental_reference.xingfuli_sources import has_source
        # The decision must still hold at write time: another tab may have
        # unbound, rejected or re-bound the community meanwhile.
        if has_source(self.registry, community_id, xingfuli_only=self._xingfuli_only):
            write_state(self.registry, community_id, stage=STAGE_FAILED,
                        message='小区已有租金来源，请刷新后重试')
            return
        judgement = evaluate(community, candidate, allow_name_only=True, allow_partial_name=True,
                             allow_subdivision=not self._require_strong)
        evidence = [*judgement['evidence'], '主页租房入口已核验', f'房源种子 {seed}']
        try:
            from src.services.rental_reference.storage import RentalPublishLock
            with self._mutex, RentalPublishLock(self.directory / 'rental_publish'):
                current = self._community(community_id)
                current_judgement = evaluate(current, candidate, allow_name_only=True, allow_partial_name=True,
                                             allow_subdivision=not self._require_strong)
                if not current_judgement['selectable']:
                    raise ValueError('小区身份信息已变化，请重新探查')
                if self._require_strong and not current_judgement['strong']:
                    raise ValueError('小区身份信息已变化，请重新探查')
                if self._cancel.is_set():
                    raise ValueError('探查已取消')
                if self._automatic:
                    from src.services.rental_reference.association import read_review
                    if read_review(self.registry, community_id).get('decision') == 'skipped':
                        raise ValueError('用户已跳过该小区，请显式重新处理')
                bind_source(self.registry, community, candidate, seed=seed,
                            method='auto' if self._automatic else 'manual', evidence=evidence,
                            allow_reprocessed=not self._automatic)
        except ValueError as exc:
            write_state(self.registry, community_id, stage=STAGE_FAILED, message=str(exc) or '关联失败')
            return
        write_state(self.registry, community_id, stage=STAGE_BOUND, candidates=None,
                    message='已关联幸福里来源，等待下一轮采集', bound_at=now())
