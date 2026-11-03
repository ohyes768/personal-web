"""Confirmed rental sources live in the authoritative community registry.

Fang is retired: there is no second mapping database, no legacy discovery and
no candidate pool. Without a registry the source management endpoints are
unavailable (503), never silently rebuilt from an old file.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class SourceRegistryUnavailable(RuntimeError):
    """503: the authoritative community registry is not available."""


class SourceStore:
    """Read/write adapter over the community registry's rental sources."""

    def __init__(self, mappings_path):
        from src.services.community_registry import existing_registry
        self.registry = existing_registry(mappings_path.parent)
        if not self.registry:
            raise SourceRegistryUnavailable('小区目录尚未准备好')

    def get(self, community_id: str) -> dict:
        """Current mapping and its candidate list.

        Candidates are always empty: the retired Fang candidate pool is not
        exposed and cannot be confirmed.
        """
        return {'mapping': self.all_mappings().get(community_id), 'candidates': []}

    def all_mappings(self) -> dict:
        from src.services.rental_reference.providers import active_sources
        return {cid: self._rental(r) for cid, r in active_sources(self.registry).items()}

    def pending_counts(self) -> dict:
        return {}

    def remove(self, community_id: str) -> None:
        """Unlink the current (Xingfuli) source; never falls back to Fang."""
        from src.services.rental_reference.providers import active_sources
        r = active_sources(self.registry).get(community_id)
        if r:
            self.registry.unlink(r['id'])

    @staticmethod
    def _rental(r):
        # The platform address is display evidence only: it stays out of the
        # source's own address so it cannot become the community's address.
        return {**r, 'source_community_id': r['source_id'], 'source_name': r['name'],
                'source_address': r.get('address') or r.get('platform_address'),
                'status': 'verified', 'verified_at': r.get('associated_at')}
