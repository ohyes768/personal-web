"""Cross-source residential classification for the community directory.

Inputs:
- tmsf property types from scripts/fetch_tmsf_property_type.py
- directory communities (tmsf ids)

Outputs: per-community state of residential | non_residential | pending | unknown.
Used by filter_residential_communities.py to decide what to keep in the
residential directory.

房天下已退役：旧租金样本不再参与用途判断，历史来源只在目录里只读留存。
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

RESIDENTIAL_TYPES = frozenset({"住宅", "别墅", "排屋"})
# 普通住宅 is a recognized residential label; it is normalized, never truncated.
RESIDENTIAL_LABELS = frozenset({"住宅", "普通住宅"})
NON_RESIDENTIAL_TYPES = frozenset({"写字楼", "商贸", "车位", "非住宅"})
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
    if text in RESIDENTIAL_LABELS:
        return text
    if text in NON_RESIDENTIAL_TYPES:
        return text
    if text in {"公寓", "其他"}:
        return text
    return (text[:100] or None)


def classify(*, community_id, tmsf_property_type=None, name=""):
    """Classify a community using the tmsf property type."""
    tmsf = normalize_property_type(tmsf_property_type)
    if tmsf in RESIDENTIAL_TYPES:
        state = RESIDENTIAL_STATE_RESIDENTIAL
    elif tmsf in NON_RESIDENTIAL_TYPES:
        state = RESIDENTIAL_STATE_NON_RESIDENTIAL
    elif tmsf:
        state = RESIDENTIAL_STATE_PENDING
    else:
        state = RESIDENTIAL_STATE_UNKNOWN

    return {
        "community_id": str(community_id),
        "name": name,
        "state": state,
        "tmsf_property_type": tmsf,
        "evidence": {"tmsf": tmsf},
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
    meaningful = set(states) - {RESIDENTIAL_STATE_UNKNOWN}
    return next(iter(meaningful)) if len(meaningful) == 1 else RESIDENTIAL_STATE_PENDING


def classify_directory(*, communities, property_types):
    """Classify every community and return the report."""
    entries = []
    for community in communities:
        cid = str(community.get("community_id") or community.get("communityid") or "")
        tmsf_record = property_types.get(cid) or {}
        entries.append(classify(community_id=cid, tmsf_property_type=tmsf_record.get("property_type"),
                                name=str(community.get("community_name") or community.get("communityname") or "")))

    state_counts = Counter(entry["state"] for entry in entries)

    return {
        "summary": {
            "total": len(entries),
            RESIDENTIAL_STATE_RESIDENTIAL: state_counts.get(RESIDENTIAL_STATE_RESIDENTIAL, 0),
            RESIDENTIAL_STATE_NON_RESIDENTIAL: state_counts.get(RESIDENTIAL_STATE_NON_RESIDENTIAL, 0),
            RESIDENTIAL_STATE_PENDING: state_counts.get(RESIDENTIAL_STATE_PENDING, 0),
            RESIDENTIAL_STATE_UNKNOWN: state_counts.get(RESIDENTIAL_STATE_UNKNOWN, 0),
        },
        "entries": entries,
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


def main():
    parser = argparse.ArgumentParser(description="Cross-source residential classification")
    parser.add_argument("--communities", default="data/binjiang_communities.json", help="tmsf community list json")
    parser.add_argument("--property-types", default="data/property_types.json", help="tmsf property types json")
    parser.add_argument("--output", default="data/residential_classification.json", help="report json")
    args = parser.parse_args()

    communities = _load_communities(Path(args.communities))
    property_types = _load_property_types(Path(args.property_types))
    report = classify_directory(communities=communities, property_types=property_types)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = report["summary"]
    print("total=" + str(summary["total"]) + " residential=" + str(summary["residential"]) + " non_residential=" + str(summary["non_residential"]) + " pending=" + str(summary["pending"]) + " unknown=" + str(summary["unknown"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
