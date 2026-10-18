"""Rental snapshot storage: publish/read with an atomic pointer swap.

Layout under the caller-supplied rentals dir (production caller passes
data/rentals/; this module never hardcodes the path):

    runs/<run_id>/batch.json    one full batch, keyed by internal community id
    runs/<run_id>/report.json   run report (errors, truncated seeds)
    current.json                pointer to the published run (os.replace swap)
    rental_publish.lock         OS file lock shared by CLI and web publisher

Publish semantics (design.md): a community is adopted only when its crawl was
complete (status complete/empty_ok) and keeps its own captured_at; failed
communities keep the previous published samples with their original captured
date, or stay absent without history. A run with no adoptable community - or
a set cancel_event at any stage - never switches the pointer, and readers only
ever see fully written batches.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import tempfile
import threading
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

POINTER_VERSION = 1
KNOWN_STATUSES = frozenset(
    {'complete', 'empty_ok', 'truncated', 'partial_detail', 'list_failed'})
ADOPTABLE_STATUSES = frozenset({'complete', 'empty_ok'})
_RUN_ID_PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]*')


@dataclass(frozen=True)
class CommunityBatch:
    """One community's crawl outcome, already mapped to the internal community id."""

    community_id: str
    source: str
    source_community_id: str | None
    status: str
    captured_at: str
    samples: Sequence[dict] = ()
    quality: Mapping[str, object] = field(default_factory=dict)
    pages_fetched: int = 0
    pages_truncated: bool = False
    detail_success: int = 0
    detail_failed: int = 0
    duplicate_ids: int = 0
    errors: Sequence[dict] = ()


@dataclass(frozen=True)
class PublishResult:
    """Outcome of one publish attempt; carried_over communities kept old data."""

    published: bool
    run_id: str
    reason: str | None
    published_at: str | None
    adopted: tuple[str, ...] = ()
    carried_over: tuple[str, ...] = ()
    absent: tuple[str, ...] = ()


class RentalPublishLock:
    """OS file lock (msvcrt/fcntl) shared by CLI and web publishers; sidecar kept.

    Mirrors the auction StoreLock pattern: exclusive per-file-region lock, the
    lock file is deliberately retained because OS releases it on close/crash.
    """

    def __init__(self, path: Path):
        self.path = Path(str(path) + '.lock')
        self.file = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open('a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                if self.path.stat().st_size == 0:
                    self.file.write(b'0')
                    self.file.flush()
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            raise BlockingIOError('rental publish is already running') from exc
        return self

    def __exit__(self, *args):
        self.file.close()


def _atomic_write_json(path: Path, payload: object) -> None:
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


def _community_record(batch: CommunityBatch) -> dict:
    return {
        'community_id': batch.community_id,
        'source': batch.source,
        'source_community_id': batch.source_community_id,
        'captured_at': batch.captured_at,
        'samples': [dict(row) for row in batch.samples],
        'quality': dict(batch.quality),
        'origin': 'this_run',
        'status': batch.status,
    }


def _validate_batches(batches: Sequence[CommunityBatch]) -> None:
    if not batches:
        raise ValueError('no community batches to publish')
    seen: set[str] = set()
    for batch in batches:
        if not isinstance(batch, CommunityBatch):
            raise TypeError('batches must be CommunityBatch instances')
        if not isinstance(batch.community_id, str) or not batch.community_id:
            raise ValueError('community_id must be a non-empty string')
        if batch.status not in KNOWN_STATUSES:
            raise ValueError(f'unknown community status: {batch.status!r}')
        if batch.community_id in seen:
            raise ValueError(f'duplicate community_id in batch list: {batch.community_id}')
        seen.add(batch.community_id)


def _validate_run_id(run_id: str) -> None:
    if not _RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError(f'invalid run_id: {run_id!r}')


def _new_run_id() -> str:
    stamp = dt.datetime.now(dt.UTC).strftime('%Y%m%dT%H%M%SZ')
    return f'{stamp}-{uuid.uuid4().hex[:8]}'


def _cancelled(cancel_event: threading.Event | None) -> bool:
    return cancel_event is not None and cancel_event.is_set()


def publish_run(rentals_dir: Path, batches: Sequence[CommunityBatch], *,
                run_id: str | None = None,
                report: Mapping[str, object] | None = None,
                cancel_event: threading.Event | None = None,
                preserved_sources: Mapping[str, str] | None = None) -> PublishResult:
    """Write a new batch and atomically switch the current pointer.

    Communities with complete/empty_ok status are adopted; failed communities
    carry over the previous published samples (original captured_at) or stay
    absent. No adoptable community, or a set cancel_event at any stage,
    publishes nothing and leaves current.json untouched. Raises BlockingIOError
    when another publisher (CLI or web) holds the shared lock.
    """
    run_id = run_id if run_id is not None else _new_run_id()
    _validate_run_id(run_id)
    _validate_batches(batches)
    base = PublishResult(published=False, run_id=run_id, reason=None, published_at=None)
    if _cancelled(cancel_event):
        return replace(base, reason='cancelled')

    adoptable = [b for b in batches if b.status in ADOPTABLE_STATUSES]
    failed = [b for b in batches if b.status not in ADOPTABLE_STATUSES]
    if not adoptable:
        return replace(base, reason='all_failed')

    with RentalPublishLock(rentals_dir / 'rental_publish'):
        if _cancelled(cancel_event):
            return replace(base, reason='cancelled')
        previous = load_current(rentals_dir)
        previous_communities = previous['communities'] if previous else {}
        communities: dict[str, dict] = {}
        # Explicitly retain eligible cache hits. Omitted/removed sources must not
        # be resurrected from the previous snapshot.
        for cid, sid in (preserved_sources or {}).items():
            entry = previous_communities.get(cid)
            if entry and entry.get('source_community_id') == sid:
                communities[cid] = {**entry, 'origin': 'cached'}
        adopted: list[str] = []
        carried_over: list[str] = []
        absent: list[str] = []
        for batch in adoptable:
            communities[batch.community_id] = _community_record(batch)
            adopted.append(batch.community_id)
        for batch in failed:
            kept = previous_communities.get(batch.community_id)
            if kept is None or kept.get('source_community_id') != batch.source_community_id:
                absent.append(batch.community_id)
                continue
            communities[batch.community_id] = {**kept, 'origin': 'carried_over',
                                               'status': 'carried_over'}
            carried_over.append(batch.community_id)
        partial = {'adopted': tuple(adopted), 'carried_over': tuple(carried_over),
                   'absent': tuple(absent)}
        if _cancelled(cancel_event):
            return replace(base, reason='cancelled', **partial)
        published_at = dt.datetime.now(dt.UTC).isoformat()
        run_dir = rentals_dir / 'runs' / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(run_dir / 'batch.json', {
            'version': POINTER_VERSION, 'run_id': run_id,
            'published_at': published_at, 'communities': communities})
        _atomic_write_json(run_dir / 'report.json',
                           dict(report) if report is not None
                           else {'version': POINTER_VERSION})
        if _cancelled(cancel_event):
            # Batch files stay on disk for diagnostics but are never pointed at.
            return replace(base, reason='cancelled', **partial)
        _atomic_write_json(rentals_dir / 'current.json', {
            'version': POINTER_VERSION, 'run_id': run_id,
            'published_at': published_at})
    return PublishResult(published=True, run_id=run_id, reason=None,
                         published_at=published_at, **partial)


def load_current(rentals_dir: Path) -> dict | None:
    """Return the published run or None; corrupt files never raise to callers.

    A corrupt or missing pointer, or an unreadable pointed-at batch, means "no
    published data". A single corrupt community entry inside an otherwise valid
    batch is degraded: dropped from communities and reported with a reason.
    """
    pointer_path = Path(rentals_dir) / 'current.json'
    if not pointer_path.exists():
        return None
    try:
        pointer = json.loads(pointer_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if (not isinstance(pointer, dict) or pointer.get('version') != POINTER_VERSION
            or not isinstance(pointer.get('run_id'), str) or not pointer['run_id']):
        return None
    batch_path = Path(rentals_dir) / 'runs' / pointer['run_id'] / 'batch.json'
    try:
        batch = json.loads(batch_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(batch, dict) or not isinstance(batch.get('communities'), dict):
        return None
    communities: dict[str, dict] = {}
    degraded: dict[str, str] = {}
    for key, entry in batch['communities'].items():
        problem = _community_problem(entry)
        if problem is None:
            communities[str(key)] = entry
        else:
            degraded[str(key)] = problem
    return {'run_id': pointer['run_id'], 'published_at': pointer.get('published_at'),
            'communities': communities, 'degraded': degraded}


def _community_problem(entry: object) -> str | None:
    if not isinstance(entry, dict):
        return 'entry is not an object'
    if not isinstance(entry.get('community_id'), str) or not entry['community_id']:
        return 'missing community_id'
    if not isinstance(entry.get('samples'), list):
        return 'samples is not a list'
    if not isinstance(entry.get('captured_at'), str) or not entry['captured_at']:
        return 'missing captured_at'
    if not isinstance(entry.get('quality', {}), dict):
        return 'quality is not an object'
    return None
