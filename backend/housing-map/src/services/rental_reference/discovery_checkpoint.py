"""Durable successful discovery steps; identity decisions are always recomputed."""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import os
import time

from src.services.community_registry import dump
from src.services.fang_rentals import RentalCrawlCancelled

logger = logging.getLogger(__name__)
PREFIX = 'rental_discovery_steps:'
VERSION = 1
TTL = 24 * 3600


class DiscoveryCheckpoint:
    def __init__(self, registry, community, client, cancel, budget, progress):
        self.registry, self.client = registry, client
        self.cancel, self.budget, self.progress = cancel, budget, progress
        self.key = PREFIX + community['community_id']
        identity = {key: community.get(key) for key in (
            'community_id', 'community_name', 'community_alias', 'aliases', 'address',
            'district', 'longitude', 'latitude', 'coordinate_system')}
        self.fingerprint = hashlib.sha256(dump(identity).encode()).hexdigest()
        self.enabled = os.getenv('HOUSING_XINGFULI_DISCOVERY_CACHE', '1') != '0'
        self.search_complete = True
        self.steps = {}
        self.fresh_homepages = set()
        self.started = time.monotonic()
        self.initial_requests = client.request_count
        self.diagnostics = dict(requests=0, cache_hits=0, early_stop=False,
                                wait_seconds=0, http_seconds=0, elapsed_seconds=0)
        with registry.db() as db:
            row = db.execute('SELECT value FROM meta WHERE key=?', (self.key,)).fetchone()
        try:
            state = json.loads(row[0]) if row else {}
            if state.get('version') == VERSION and state.get('fingerprint') == self.fingerprint:
                if isinstance(state.get('steps'), dict):
                    self.steps = state['steps']
        except (ValueError, TypeError, AttributeError):
            logger.warning('Ignoring damaged discovery checkpoint community_id=%s', community['community_id'])

    @property
    def request_count(self):
        return self.client.request_count - self.initial_requests

    def report(self, step=None):
        self.diagnostics.update(requests=self.request_count,
                                wait_seconds=getattr(self.client, 'wait_seconds', 0),
                                http_seconds=getattr(self.client, 'http_seconds', 0),
                                elapsed_seconds=round(time.monotonic() - self.started, 3))
        self.progress(step, copy.deepcopy(self.diagnostics))

    def _call(self, method, args, *, cached=False, refresh=False):
        if self.cancel.is_set():
            raise RentalCrawlCancelled([], None)
        key = dump([method, *args])
        step = self.steps.get(key)
        if cached and not refresh and self.enabled and isinstance(step, dict):
            expires = step.get('expires_at')
            value = step.get('value')
            if (isinstance(expires, (int, float)) and math.isfinite(expires)
                    and time.time() < expires <= time.time() + TTL
                    and self._valid(method, args, value) and isinstance(step.get('complete'), bool)):
                self.search_complete = step['complete']
                self.diagnostics['cache_hits'] += 1
                self.report(method)
                return copy.deepcopy(value)
        if self.request_count >= self.budget:
            raise DiscoveryBudgetExhausted('本轮探查请求额度已用完，请稍后重试')
        self.report(method)
        try:
            value = getattr(self.client, method)(*args)
            if method == 'search':
                self.search_complete = getattr(self.client, 'search_complete', True)
            # Only parsed, successful search/homepage facts are persisted.
            if cached and self.enabled:
                self.steps[key] = dict(value=value, complete=self.search_complete, expires_at=time.time() + TTL)
                state = dict(version=VERSION, fingerprint=self.fingerprint, steps=self.steps)
                with self.registry.db() as db:
                    db.execute('INSERT INTO meta(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                               (self.key, dump(state)))
            return value
        finally:
            self.report(method)

    @staticmethod
    def _valid(method, args, value):
        if not isinstance(value, dict):
            return False
        if method == 'search':
            return all(isinstance(nid, str) and isinstance(group, dict)
                       and isinstance(group.get('name'), str) and isinstance(group.get('seeds'), list)
                       for nid, group in value.items())
        return (value.get('neighborhood_id') == args[0] and isinstance(value.get('name'), str)
                and isinstance(value.get('address'), str) and isinstance(value.get('seeds'), list)
                and all(isinstance(seed, str) for seed in value['seeds'])
                and value.get('coordinate_system') in {'gcj02', None}
                and all(key in value and (value[key] is None or (
                    isinstance(value[key], (int, float)) and math.isfinite(value[key])))
                    for key in ('longitude', 'latitude')))

    def search(self, name, channel):
        return self._call('search', (name, channel), cached=True)

    def homepage(self, nid, *, fresh=False):
        before = self.request_count
        value = self._call('homepage', (nid,), cached=True, refresh=fresh)
        if self.request_count > before:
            self.fresh_homepages.add(nid)
        return value

    def listing_owner(self, seed):
        return self._call('listing_owner', (seed,))

    def listing_owner_from_list(self, seed, nid):
        return self._call('listing_owner_from_list', (seed, nid))


class DiscoveryBudgetExhausted(RuntimeError):
    pass


def clear_checkpoint(registry, cid):
    with registry.db() as db:
        db.execute('DELETE FROM meta WHERE key=?', (PREFIX + cid,))
