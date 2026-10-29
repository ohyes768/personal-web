"""Filtering, dedup, grouping and yield math for rental reference samples.

Pure functions only - no IO, no global state. Sale price context and the
"now" clock are supplied by the caller.
"""
from __future__ import annotations

import datetime as dt
import math
import re
from collections.abc import Sequence

AREA_BANDS = ('lt90', '90to144', 'gte144')
RESIDENTIAL_TYPES = {'住宅', '普通住宅'}
SALE_PRICE_BASES = {'signed', 'listing'}
STALE_AFTER = dt.timedelta(days=30)
MIN_GROUP_SAMPLES = 3
XINGFULI_LIST_API_EVIDENCE = 'xingfuli_list_api_v1'

_LAYOUT_ROOMS = re.compile(r'(\d+)室')


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def parse_utc(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.UTC)
    return parsed


def is_stale(captured_at: str | None, *, now: dt.datetime) -> bool:
    """True unless the snapshot is a valid UTC timestamp within 30 days."""
    captured = parse_utc(captured_at)
    if captured is None:
        return True
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.UTC)
    return now - captured > STALE_AFTER


def area_band_for(area_m2: float | None) -> str | None:
    if not _finite(area_m2) or area_m2 <= 0:
        return None
    if area_m2 < 90:
        return 'lt90'
    if area_m2 < 144:
        return '90to144'
    return 'gte144'


def bedrooms_of(layout: str | None) -> int | None:
    if not layout:
        return None
    match = _LAYOUT_ROOMS.search(layout)
    return int(match.group(1)) if match else None


def _exclusion_reason(row: dict) -> str | None:
    mode = row.get('rental_mode')
    flags = row.get('quality_flags') or []
    if mode == 'unknown' or 'unknown_rental_mode' in flags:
        return 'unknown_rental_mode'
    if mode != 'whole' or 'shared_rental' in flags:
        return 'shared_rental'
    rent, area = row.get('monthly_rent_yuan'), row.get('area_m2')
    if not _finite(rent) or rent <= 0 or not _finite(area) or area <= 0:
        return 'non_positive_value'
    if 'suspected_partition' in flags:
        return 'suspect_partition'
    prop_type = row.get('property_type')
    if 'non_residential' in flags or (
            prop_type is not None and prop_type not in RESIDENTIAL_TYPES):
        return 'non_residential'
    if 'outside_sampling_quota' in flags:
        return 'outside_sampling_quota'
    list_verified = (row.get('source') == 'xingfuli'
                     and row.get('verification_method') == XINGFULI_LIST_API_EVIDENCE
                     and row.get('property_type_origin') == 'community_directory'
                     and prop_type in RESIDENTIAL_TYPES
                     and (bedrooms_of(row.get('layout')) or 0) > 0)
    if not row.get('detail_fetched') and not list_verified:
        return 'detail_not_verified'
    return None


def dedupe_by_listing_id(samples: Sequence[dict]) -> tuple[list[dict], int]:
    """Keep the first occurrence of each source listing ID, count the rest."""
    seen: set[str] = set()
    unique, skipped = [], 0
    for row in samples:
        listing_id = row.get('source_listing_id')
        if listing_id is not None and listing_id in seen:
            skipped += 1
            continue
        if listing_id is not None:
            seen.add(listing_id)
        unique.append(row)
    return unique, skipped


def filter_candidates(samples: Sequence[dict]) -> tuple[list[dict], list[dict]]:
    """Split samples into statistic candidates and excluded rows with reasons."""
    candidates, excluded = [], []
    for row in samples:
        reason = _exclusion_reason(row)
        if reason is None:
            candidates.append(row)
        else:
            excluded.append({'source_listing_id': row.get('source_listing_id'),
                             'exclusion_reason': reason, 'sample': row})
    return candidates, excluded


def _duplicate_key(row: dict) -> tuple:
    return (row.get('source_community_id'), bedrooms_of(row.get('layout')),
            row.get('area_m2'), row.get('monthly_rent_yuan'), row.get('floor'))


def mark_suspect_duplicates(candidates: Sequence[dict]) -> tuple[list[dict], list[dict]]:
    """Flag same community/layout/area/rent/floor rows; keep them out of counts."""
    first_seen: dict[tuple, str] = {}
    valid, suspects = [], []
    for row in candidates:
        key = _duplicate_key(row)
        if key in first_seen:
            suspects.append({'duplicate_of': first_seen[key], 'sample': row})
        else:
            first_seen[key] = row.get('source_listing_id')
            valid.append(row)
    return valid, suspects


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _percentile(values: Sequence[float], q: float) -> float:
    """Linear interpolation, matching the numpy 'linear' method."""
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def select_valid(samples: Sequence[dict]) -> tuple[list[dict], dict]:
    """Dedup -> filter -> suspect-mark pipeline shared with the API layer.

    Returns the valid candidate rows plus the audit trail (excluded rows with
    reasons, suspect duplicates, skipped duplicate source IDs) so route code
    never re-implements the filtering rules.
    """
    unique, skipped = dedupe_by_listing_id(samples)
    candidates, excluded = filter_candidates(unique)
    valid, suspects = mark_suspect_duplicates(candidates)
    return valid, {'excluded': excluded, 'suspect_duplicates': suspects,
                   'duplicate_source_ids_skipped': skipped}


def group_stats(valid: Sequence[dict], *, bedrooms: int | str | None,
                band: str | None) -> dict:
    """One (band, bedrooms) lens over valid samples.

    ``band=None`` merges every area band; ``bedrooms='4plus'`` matches layouts
    with four or more rooms. Single statistics entry for the API layer's
    "all-area" / "4-plus" scopes; _group_stats delegates here so the median
    and percentile math lives in exactly one place.
    """

    def in_scope(row: dict) -> bool:
        if band is not None and area_band_for(row['area_m2']) != band:
            return False
        if bedrooms is None:
            return True
        if bedrooms == '4plus':
            count = bedrooms_of(row.get('layout'))
            return count is not None and count >= 4
        return bedrooms_of(row.get('layout')) == bedrooms

    rows = [row for row in valid if in_scope(row)]
    unit_rents = [row['monthly_rent_yuan'] / row['area_m2'] for row in rows]
    rents = [row['monthly_rent_yuan'] for row in rows]
    reference = None
    if len(rows) >= MIN_GROUP_SAMPLES:
        reference = {
            'median_monthly_rent_yuan': _median(rents),
            'median_unit_rent_yuan_m2_month': _median(unit_rents),
            'p25_unit_rent_yuan_m2_month': _percentile(unit_rents, 0.25),
            'p75_unit_rent_yuan_m2_month': _percentile(unit_rents, 0.75),
        }
    return {'area_band': band, 'bedrooms': bedrooms, 'sample_count': len(rows),
            'candidates': rows, 'rent_reference': reference}


def _group_stats(valid: Sequence[dict], *, bedrooms: int | None, band: str) -> dict:
    return group_stats(valid, bedrooms=bedrooms, band=band)


def compute_rental_statistics(samples: Sequence[dict]) -> dict:
    """Full pipeline: ID dedup -> filter -> suspect-dup marking -> grouping.

    Groups cover each area band x each bedroom count, plus a per-band merged
    "all layouts" group recomputed from that band's valid samples (never an
    average of per-layout medians).
    """
    unique, skipped = dedupe_by_listing_id(samples)
    candidates, excluded = filter_candidates(unique)
    valid, suspects = mark_suspect_duplicates(candidates)
    groups = []
    for band in AREA_BANDS:
        band_rows = [row for row in valid if area_band_for(row['area_m2']) == band]
        bedroom_values = sorted({b for row in band_rows
                                 if (b := bedrooms_of(row.get('layout'))) is not None})
        for bedrooms in bedroom_values:
            groups.append(_group_stats(valid, bedrooms=bedrooms, band=band))
        if band_rows:
            groups.append(_group_stats(valid, bedrooms=None, band=band))
    return {'groups': groups, 'excluded': excluded, 'suspect_duplicates': suspects,
            'duplicate_source_ids_skipped': skipped}


def estimate_yield(unit_rent_yuan_m2_month: float | None,
                   sale_unit_price_yuan_m2: float | None, *,
                   sale_price_basis: str | None,
                   sale_price_date: str | None,
                   stale: bool) -> dict | None:
    """Gross annualized yield (%) and rent-to-sale ratio, or None.

    Returns None when the snapshot is stale, the basis is not one of
    signed/listing, or any input is missing, non-positive or non-finite.
    """
    if stale or sale_price_basis not in SALE_PRICE_BASES:
        return None
    if not _finite(unit_rent_yuan_m2_month) or unit_rent_yuan_m2_month <= 0:
        return None
    if not _finite(sale_unit_price_yuan_m2) or sale_unit_price_yuan_m2 <= 0:
        return None
    return {
        'annualized_gross_yield_pct':
            unit_rent_yuan_m2_month * 12 / sale_unit_price_yuan_m2 * 100,
        'rent_to_sale_ratio': sale_unit_price_yuan_m2 / unit_rent_yuan_m2_month,
        'sale_price_basis': sale_price_basis,
        'sale_price_date': sale_price_date,
    }
