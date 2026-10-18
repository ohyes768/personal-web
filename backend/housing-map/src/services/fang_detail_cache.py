"""Cache verified static details; current list data always owns prices/membership."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import math
import time
from pathlib import Path

from src.services.rental_reference.storage import _atomic_write_json

logger = logging.getLogger(__name__)


class FangDetailCache:
    def __init__(self, directory: Path, *, clock=time.time, ttl=7 * 86400):
        self.directory = Path(directory) / 'fang_details'
        self.clock, self.ttl = clock, ttl
        self.hits = 0

    def _discard(self, path):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning('Cannot remove expired Fang cache entry %s', path.name)

    def prune(self, limit=1000):
        """Bound maintenance work on startup; cache reads also discard expired entries."""
        from itertools import islice
        for path in islice(self.directory.glob('*.json'), limit):
            try:
                item = json.loads(path.read_text(encoding='utf-8'))
                age = self.clock() - item['verified_at']
                if not math.isfinite(age) or age < 0 or age >= self.ttl:
                    self._discard(path)
            except (OSError, ValueError, KeyError, TypeError):
                self._discard(path)

    def _path(self, row):
        if not row.get('source_listing_id') or not row.get('source_community_id'):
            return None
        key = f"fang:{row['source_community_id']}:{row['source_listing_id']}"
        return self.directory / (hashlib.sha256(key.encode()).hexdigest() + '.json')

    def get(self, row):
        path = self._path(row)
        if path is None:
            return None
        try:
            item = json.loads(path.read_text(encoding='utf-8'))
            age = self.clock() - item['verified_at']
            if (item.get('version') != 1 or not math.isfinite(age) or age < 0 or age >= self.ttl
                    or item.get('source_listing_id') != row['source_listing_id']
                    or item.get('source_community_id') != row['source_community_id']):
                self._discard(path)
                return None
            if any(item[k] is not None and not isinstance(item[k], str) for k in ('address', 'property_type')):
                raise ValueError('invalid static fields')
            self.hits += 1
            return dict(address=item['address'], property_type=item['property_type'],
                        detail_verified_at=dt.datetime.fromtimestamp(item['verified_at'], dt.UTC).isoformat(),
                        detail_fetched=True)
        except FileNotFoundError:
            return None
        except (OSError, ValueError, TypeError, KeyError):
            logger.warning('Fang detail cache miss due to invalid entry %s', path.name)
            self._discard(path)
            return None

    def put(self, row):
        path = self._path(row)
        if path is None or not row.get('detail_fetched'):
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        try:
            verified_at = self.clock()
            row['detail_verified_at'] = dt.datetime.fromtimestamp(verified_at, dt.UTC).isoformat()
            _atomic_write_json(path, dict(version=1, source_listing_id=row['source_listing_id'],
                source_community_id=row['source_community_id'], verified_at=verified_at,
                address=row.get('address'), property_type=row.get('property_type')))
        except OSError:
            logger.warning('Fang detail cache write failed', exc_info=True)


def enrich_cached(row, fetch, cache=None):
    from src.services.fang_rentals import enrich_detail
    cached = cache.get(row) if cache else None
    if cached is not None:
        row.update(cached)
        if row['property_type'] and row['property_type'] not in {'住宅', '普通住宅'}:
            if 'non_residential' not in row['quality_flags']:
                row['quality_flags'].append('non_residential')
        return True
    enrich_detail(row, fetch(row['source_url']))
    row['detail_verified_at'] = dt.datetime.now(dt.UTC).isoformat()
    if cache:
        cache.put(row)
    return False
