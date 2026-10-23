"""Cross-source residential classification for the community directory.

Inputs:
- tmsf property types from scripts/fetch_tmsf_property_type.py
- fang rental samples carrying property_type and source community id
- directory communities (tmsf ids) plus matching fang ids

Outputs: per-community state of residential | non_residential | pending | unknown,
and a structured conflict report. Used by filter_residential_communities.py to
decide what to keep in the residential directory.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

RESIDENTIAL_TYPES = frozenset({"住宅", "别墅", "排屋"})
FANG_RESIDENTIAL_TYPES = frozenset({"住宅", "普通住宅"})
NON_RESIDENTIAL_TYPES = frozenset({"写字楼", "商贸", "车位"})
RESIDENTIAL_STATE_RESIDENTIAL = "residential"
RESIDENTIAL_STATE_NON_RESIDENTIAL = "non_residential"
RESIDENTIAL_STATE_PENDING = "pending"
RESIDENTIAL_STATE_UNKNOWN = "unknown"

def normalize_property_type(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text in RESIDENTIAL_TYPES:
        return text
    if text in FANG_RESIDENTIAL_TYPES:
        return text
    if text in NON_RESIDENTIAL_TYPES:
        return text
    if text in {"公寓", "其他"}:
        return text
    return (text[:100] or None)


def _fang_property_from_samples(samples):
    counter = Counter()
    for sample in samples or []:
        prop = normalize_property_type(sample.get("property_type"))
        if prop:
            counter[prop] += 1
    return counter


def classify(*, community_id, tmsf_property_type=None, fang_samples=None, name=""):
    """Classify a community using tmsf property type and fang rental samples."""
    tmsf = normalize_property_type(tmsf_property_type)
    fang_counter = _fang_property_from_samples(fang_samples)
    fang_dominant = fang_counter.most_common(1)[0][0] if fang_counter else None
    fang_residential = any(prop in FANG_RESIDENTIAL_TYPES for prop in fang_counter)
    fang_non_residential = any(prop in NON_RESIDENTIAL_TYPES for prop in fang_counter)
    fang_other = any(prop in {"公寓", "其他"} for prop in fang_counter)

    evidence = {
        "tmsf": tmsf,
        "fang": dict(fang_counter),
    }

    fang_ambiguous = any(prop not in FANG_RESIDENTIAL_TYPES | NON_RESIDENTIAL_TYPES for prop in fang_counter)
    if (fang_residential and fang_non_residential) or fang_ambiguous:
        state = RESIDENTIAL_STATE_PENDING
    elif tmsf in RESIDENTIAL_TYPES:
        state = RESIDENTIAL_STATE_PENDING if fang_non_residential else RESIDENTIAL_STATE_RESIDENTIAL
    elif tmsf in NON_RESIDENTIAL_TYPES:
        state = RESIDENTIAL_STATE_PENDING if fang_residential else RESIDENTIAL_STATE_NON_RESIDENTIAL
    elif tmsf:
        state = RESIDENTIAL_STATE_PENDING
    else:
        if fang_residential and not fang_non_residential:
            state = RESIDENTIAL_STATE_RESIDENTIAL
        elif fang_non_residential and not fang_residential:
            state = RESIDENTIAL_STATE_NON_RESIDENTIAL
        elif fang_other or fang_counter:
            state = RESIDENTIAL_STATE_PENDING
        else:
            state = RESIDENTIAL_STATE_UNKNOWN

    return {
        "community_id": str(community_id),
        "name": name,
        "state": state,
        "tmsf_property_type": tmsf,
        "fang_property_counts": dict(fang_counter),
        "fang_dominant": fang_dominant,
        "evidence": evidence,
    }


def classify_sources(records, property_types=None):
    """Compute directory state from current effective source associations.

    Existing standalone results are looked up by TMSF identity, never by local ID.
    Integrated facts supersede legacy file results; a failed attempt retains an
    already recorded fact. Enrichment copies the last legacy fact before an attempt.
    """
    property_types = property_types or {}
    states = []
    for record in records:
        if record.get('status') == 'ignored':
            continue
        if record['source'] == 'tmsf':
            prop = record.get('property_type')
            if not record.get('property_type_checked_at') and not prop and record.get('source_kind') != 'project':
                prop = property_types.get(record['source_id'], {}).get('property_type')
            state = classify(community_id='', tmsf_property_type=prop)['state']
            if record.get('property_type_conflict') or state == RESIDENTIAL_STATE_UNKNOWN:
                state = RESIDENTIAL_STATE_PENDING
            states.append(state)
        elif record['source'] == 'amap':
            # Map categories are a discovery hint, not legal residential-use evidence.
            continue
        elif record['source'] == 'fang':
            states.append(classify(community_id='', fang_samples=record.get('samples', []))['state'])
    meaningful = set(states) - {RESIDENTIAL_STATE_UNKNOWN}
    return next(iter(meaningful)) if len(meaningful) == 1 else RESIDENTIAL_STATE_PENDING


def classify_directory(*, communities, property_types, fang_samples_by_community=None):
    """Classify every community and return the report."""
    samples_lookup = fang_samples_by_community or {}
    entries = []
    for community in communities:
        cid = str(community.get("community_id") or community.get("communityid") or "")
        tmsf_record = property_types.get(cid) or {}
        fang_samples = samples_lookup.get(cid) or samples_lookup.get(community.get("fang_source_id") or "") or []
        entries.append(classify(community_id=cid, tmsf_property_type=tmsf_record.get("property_type"), fang_samples=fang_samples, name=str(community.get("community_name") or community.get("communityname") or "")))

    state_counts = Counter(entry["state"] for entry in entries)
    conflicts = []
    for entry in entries:
        tmsf = entry["tmsf_property_type"]
        fang_residential = any(prop in FANG_RESIDENTIAL_TYPES for prop in (entry["fang_property_counts"] or {}))
        fang_non_residential = any(prop in NON_RESIDENTIAL_TYPES for prop in (entry["fang_property_counts"] or {}))
        if tmsf in RESIDENTIAL_TYPES and fang_non_residential:
            conflicts.append({**entry, "kind": "fang_non_residential_overrides_tmsf_residential"})
        elif tmsf in NON_RESIDENTIAL_TYPES and fang_residential:
            conflicts.append({**entry, "kind": "fang_residential_overrides_tmsf_non_residential"})
        elif tmsf in {"公寓", "其他"} and fang_residential and fang_non_residential:
            conflicts.append({**entry, "kind": "fang_mixed"})

    return {
        "summary": {
            "total": len(entries),
            RESIDENTIAL_STATE_RESIDENTIAL: state_counts.get(RESIDENTIAL_STATE_RESIDENTIAL, 0),
            RESIDENTIAL_STATE_NON_RESIDENTIAL: state_counts.get(RESIDENTIAL_STATE_NON_RESIDENTIAL, 0),
            RESIDENTIAL_STATE_PENDING: state_counts.get(RESIDENTIAL_STATE_PENDING, 0),
            RESIDENTIAL_STATE_UNKNOWN: state_counts.get(RESIDENTIAL_STATE_UNKNOWN, 0),
        },
        "entries": entries,
        "conflicts": conflicts,
    }


def _load_communities(path):
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("communities", [])
    raise ValueError("Unsupported input format: " + str(path))


def _load_property_types(path):
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        return {}
    return {str(k): v for k, v in data.items() if isinstance(v, dict)}


def _load_fang_samples(path):
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, list):
        result = {}
        for row in data:
            sid = str(row.get("source_community_id") or row.get("fang_source_id") or "")
            if sid:
                result.setdefault(sid, []).append(row)
        return result
    if isinstance(data, dict):
        return {str(k): list(v) for k, v in data.items() if isinstance(v, list)}
    raise ValueError("Unsupported fang samples format: " + str(path))


def main():
    parser = argparse.ArgumentParser(description="Cross-source residential classification")
    parser.add_argument("--communities", default="data/binjiang_communities.json", help="tmsf community list json")
    parser.add_argument("--property-types", default="data/property_types.json", help="tmsf property types json")
    parser.add_argument("--fang-samples", default="data/rental_samples.json", help="optional fang rental samples json")
    parser.add_argument("--output", default="data/residential_classification.json", help="report json")
    args = parser.parse_args()

    communities = _load_communities(Path(args.communities))
    property_types = _load_property_types(Path(args.property_types))
    fang_samples = _load_fang_samples(Path(args.fang_samples))
    report = classify_directory(communities=communities, property_types=property_types, fang_samples_by_community=fang_samples)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = report["summary"]
    print("total=" + str(summary["total"]) + " residential=" + str(summary["residential"]) + " non_residential=" + str(summary["non_residential"]) + " pending=" + str(summary["pending"]) + " unknown=" + str(summary["unknown"]))
    print("conflicts=" + str(len(report["conflicts"])))
    if report["conflicts"]:
        for conflict in report["conflicts"][:5]:
            print("  - " + str(conflict["community_id"]) + " " + str(conflict["name"]) + ": " + str(conflict["kind"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
