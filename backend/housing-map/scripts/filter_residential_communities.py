"""Split the tmsf community list by residential classification.

Outputs three side files in the data directory:
- binjiang_residential_communities.json
- binjiang_pending_communities.json
- binjiang_non_residential_communities.json

Each set preserves the original community payload so the directory import can
drop the unwanted rows without rewriting IDs.

The import pipeline can then ignore non_residential entries on first prepare,
while keeping their sources so the records are still inspectable.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.residential_classifier import (
    RESIDENTIAL_STATE_NON_RESIDENTIAL,
    RESIDENTIAL_STATE_PENDING,
    RESIDENTIAL_STATE_RESIDENTIAL,
    classify,
    classify_directory,
)


def _load(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _snapshot(path: Path, backup_dir: Path) -> None:
    if not path.exists():
        return
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_dir / path.name)


def split_communities(*, communities, property_types, fang_samples_by_community=None) -> dict[str, list]:
    report = classify_directory(communities=communities, property_types=property_types, fang_samples_by_community=fang_samples_by_community or {})
    buckets = {state: [] for state in (RESIDENTIAL_STATE_RESIDENTIAL, RESIDENTIAL_STATE_PENDING, RESIDENTIAL_STATE_NON_RESIDENTIAL)}
    index_by_id = {str(item.get("community_id") or item.get("communityid") or ""): item for item in communities}
    for entry in report["entries"]:
        community = index_by_id.get(entry["community_id"])
        if community is None:
            continue
        enriched = dict(community)
        enriched["residential_state"] = entry["state"]
        enriched["residential_evidence"] = entry["evidence"]
        buckets[entry["state"]].append(enriched)
    return {"report": report, "buckets": buckets}


def main() -> int:
    parser = argparse.ArgumentParser(description="Split communities by residential classification")
    parser.add_argument("--communities", default="data/binjiang_communities.json")
    parser.add_argument("--property-types", default="data/property_types.json")
    parser.add_argument("--fang-samples", default="data/rental_samples.json")
    parser.add_argument("--data-dir", default="data", help="Directory to write the split files")
    parser.add_argument("--backup-dir", default="data/diagnostics/pre-residential")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    communities = _load(Path(args.communities)) or []
    if isinstance(communities, dict):
        communities = communities.get("communities", [])
    property_types = _load(Path(args.property_types)) or {}
    fang_samples = _load(Path(args.fang_samples)) or {}

    backup_dir = Path(args.backup_dir)
    _snapshot(Path(args.communities), backup_dir)
    _snapshot(Path(args.property_types), backup_dir)
    _snapshot(Path(args.fang_samples), backup_dir)

    result = split_communities(communities=communities, property_types=property_types, fang_samples_by_community=fang_samples)
    summary = result["report"]["summary"]

    _dump(data_dir / "binjiang_residential_communities.json", result["buckets"][RESIDENTIAL_STATE_RESIDENTIAL])
    _dump(data_dir / "binjiang_pending_communities.json", result["buckets"][RESIDENTIAL_STATE_PENDING])
    _dump(data_dir / "binjiang_non_residential_communities.json", result["buckets"][RESIDENTIAL_STATE_NON_RESIDENTIAL])
    _dump(data_dir / "residential_classification.json", result["report"])

    print("total=" + str(summary["total"]) + " residential=" + str(summary["residential"]) + " non_residential=" + str(summary["non_residential"]) + " pending=" + str(summary["pending"]) + " unknown=" + str(summary["unknown"]))
    print("conflicts=" + str(len(result["report"]["conflicts"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
