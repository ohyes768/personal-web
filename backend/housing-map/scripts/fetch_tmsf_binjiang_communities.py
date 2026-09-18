from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from fetch_tmsf_price_snapshot import (
    BASE_URL,
    PriceSnapshot,
    build_snapshots,
    fetch_html,
    parse_tendency_page,
    write_outputs,
)


COMMUNITY_LIST_URL = f"{BASE_URL}/include/hzweb/index_search_newCommunitylist.js"
BINJIANG_PREFIX = "滨江"


@dataclass
class Community:
    community_id: str
    community_name: str
    community_alias: str | None
    district: str | None
    subdistrict: str | None
    area_remark: str | None
    listing_count_hint: int | None
    rent_count_hint: int | None
    recent_deal_count_hint: int | None
    sign_price_hint: int | None
    source: str
    source_url: str
    crawled_at: str


def parse_community_list_js(js_text: str) -> list[dict[str, Any]]:
    match = re.search(r"var\s+data_(?:new)?Communitylist\s*=\s*(\[.*\])\s*;?\s*$", js_text, flags=re.S)
    if not match:
        raise ValueError("Cannot find data_communitylist JSON array in TMSF community list JS")
    data = json.loads(match.group(1))
    if not isinstance(data, list):
        raise ValueError("data_communitylist is not a JSON array")
    return data


def normalize_community(row: dict[str, Any], crawled_at: str) -> Community:
    area_remark = clean_string(row.get("arearmk"))
    district = subdistrict = None
    if area_remark:
        area_parts = area_remark.split()
        district = area_parts[0] if area_parts else None
        subdistrict = area_parts[1] if len(area_parts) > 1 else clean_string(row.get("areaname"))
    return Community(
        community_id=str(row["communityid"]),
        community_name=clean_string(row.get("communityname")) or "",
        community_alias=clean_string(row.get("communityabb")),
        district=district,
        subdistrict=subdistrict,
        area_remark=area_remark,
        listing_count_hint=optional_int(row.get("gpnum")),
        rent_count_hint=optional_int(row.get("czcount")),
        recent_deal_count_hint=optional_int(row.get("signnum")),
        sign_price_hint=optional_int(row.get("signprice")),
        source="tmsf_community_list_js",
        source_url=COMMUNITY_LIST_URL,
        crawled_at=crawled_at,
    )


def clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def fetch_binjiang_communities() -> list[Community]:
    js_text = fetch_html(COMMUNITY_LIST_URL, timeout=30)
    crawled_at = dt.datetime.now(dt.UTC).isoformat()
    communities: list[Community] = []
    seen_ids: set[str] = set()
    for row in parse_community_list_js(js_text):
        area_remark = clean_string(row.get("arearmk")) or ""
        if not area_remark.startswith(BINJIANG_PREFIX):
            continue
        community = normalize_community(row, crawled_at)
        if community.community_id in seen_ids:
            continue
        seen_ids.add(community.community_id)
        communities.append(community)
    communities.sort(key=lambda item: (item.subdistrict or "", item.community_name, item.community_id))
    return communities


def write_communities(communities: list[Community], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [asdict(community) for community in communities]

    json_path = output_dir / "binjiang_communities.json"
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_path = output_dir / "binjiang_communities.csv"
    fieldnames = list(Community.__dataclass_fields__.keys())
    with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def fetch_price_snapshots_for_communities(
    communities: list[Community],
    timeout: int,
    sleep_seconds: float,
    price_mode: str,
    concurrency: int,
) -> list[Any]:
    snapshots = []
    if concurrency <= 1:
        for index, community in enumerate(communities, start=1):
            community_snapshots = fetch_price_snapshots_for_one(community, timeout, price_mode)
            snapshots.extend(community_snapshots)
            print(f"[ok] {index}/{len(communities)} {community.community_id} {community.community_name}: {len(community_snapshots)} snapshots")
            if index < len(communities):
                time.sleep(sleep_seconds)
        return snapshots

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(fetch_price_snapshots_for_one, community, timeout, price_mode): community
            for community in communities
        }
        for index, future in enumerate(as_completed(futures), start=1):
            community = futures[future]
            try:
                community_snapshots = future.result()
            except Exception as error:
                print(f"[error] {index}/{len(communities)} {community.community_id} {community.community_name}: {error}")
                community_snapshots = []
            snapshots.extend(community_snapshots)
            print(f"[ok] {index}/{len(communities)} {community.community_id} {community.community_name}: {len(community_snapshots)} snapshots")
    return snapshots


def fetch_price_snapshots_for_one(community: Community, timeout: int, price_mode: str) -> list[PriceSnapshot]:
    if price_mode == "full":
        index_url = f"{BASE_URL}/esf/xq_indexnew_{community.community_id}.htm"
        tendency_url = f"{BASE_URL}/esf/xq_xqtendency_{community.community_id}.htm"
        index_html = fetch_html(index_url, timeout)
        tendency_html = fetch_html(tendency_url, timeout)
        snapshots = build_snapshots(community.community_id, index_html, tendency_html)
        for snapshot in snapshots:
            apply_community_hints(snapshot, community)
        return snapshots

    if price_mode not in {"tendency-only", "hybrid"}:
        raise ValueError(f"Unsupported price mode: {price_mode}")

    snapshots = fetch_tendency_only_snapshot(community, timeout)
    if snapshots or price_mode == "tendency-only":
        return snapshots
    if not community.listing_count_hint or community.listing_count_hint <= 0:
        return []

    index_url = f"{BASE_URL}/esf/xq_indexnew_{community.community_id}.htm"
    index_html = fetch_html(index_url, timeout)
    snapshots = build_snapshots(community.community_id, index_html, "")
    for snapshot in snapshots:
        apply_community_hints(snapshot, community)
        if snapshot.price_type == "visible_listing_unit_price_avg":
            snapshot.confidence_score = 0.6
            snapshot.raw_payload["fallback_reason"] = "missing_tendency_price"
    return snapshots


def fetch_tendency_only_snapshot(community: Community, timeout: int) -> list[PriceSnapshot]:
    tendency_url = f"{BASE_URL}/esf/xq_xqtendency_{community.community_id}.htm"
    try:
        tendency_html = fetch_html(tendency_url, timeout)
    except Exception:
        return []
    tendency_data = parse_tendency_page(tendency_html)
    today = dt.date.today().isoformat()
    crawled_at = dt.datetime.now(dt.UTC).isoformat()
    snapshots: list[PriceSnapshot] = []
    latest_monthly_avg = tendency_data.get("latest_monthly_avg")
    monthly_trend = tendency_data.get("monthly_trend")

    if latest_monthly_avg:
        snapshots.append(
            PriceSnapshot(
                community_id=community.community_id,
                community_name=community.community_name,
                snapshot_date=today,
                source="tmsf",
                price_type="monthly_deal_avg_latest",
                avg_price=latest_monthly_avg,
                listing_count=community.listing_count_hint,
                deal_count=community.recent_deal_count_hint,
                sample_count=len(monthly_trend.get("line", [])) if monthly_trend else 0,
                min_price=None,
                max_price=None,
                source_url=tendency_url,
                confidence_score=0.88,
                raw_payload={
                    "community": {
                        "district": community.district,
                        "subdistrict": community.subdistrict,
                        "area_remark": community.area_remark,
                    },
                    "list_hints": {
                        "listing_count": community.listing_count_hint,
                        "deal_count": community.recent_deal_count_hint,
                        "sign_price": community.sign_price_hint,
                    },
                    "tendency": tendency_data,
                    "monthly_trend": monthly_trend,
                },
                crawled_at=crawled_at,
            )
        )

    if community.sign_price_hint and community.sign_price_hint > 0:
        snapshots.append(
            PriceSnapshot(
                community_id=community.community_id,
                community_name=community.community_name,
                snapshot_date=today,
                source="tmsf_community_list_js",
                price_type="list_sign_price",
                avg_price=community.sign_price_hint,
                listing_count=community.listing_count_hint,
                deal_count=community.recent_deal_count_hint,
                sample_count=community.recent_deal_count_hint or 0,
                min_price=None,
                max_price=None,
                source_url=COMMUNITY_LIST_URL,
                confidence_score=0.72,
                raw_payload={
                    "list_hints": {
                        "listing_count": community.listing_count_hint,
                        "deal_count": community.recent_deal_count_hint,
                        "sign_price": community.sign_price_hint,
                    }
                },
                crawled_at=crawled_at,
            )
        )
    return snapshots


def apply_community_hints(snapshot: PriceSnapshot, community: Community) -> None:
    snapshot.community_name = community.community_name
    if snapshot.listing_count is None:
        snapshot.listing_count = community.listing_count_hint
    if snapshot.deal_count is None:
        snapshot.deal_count = community.recent_deal_count_hint


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch TMSF Binjiang community list and optional price snapshots.")
    parser.add_argument("--output-dir", default="data", help="Output directory, default: data")
    parser.add_argument("--with-prices", action="store_true", help="Also fetch detail/tendency pages for price snapshots")
    parser.add_argument("--max-communities", type=int, default=None, help="Limit communities for MVP tests")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout seconds")
    parser.add_argument("--sleep", type=float, default=2.0, help="Delay between detail page requests")
    parser.add_argument("--price-mode", choices=["full", "tendency-only", "hybrid"], default="full", help="Price fetch mode")
    parser.add_argument("--concurrency", type=int, default=1, help="Concurrent price fetch workers")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    communities = fetch_binjiang_communities()
    if args.max_communities is not None:
        communities = communities[: args.max_communities]

    write_communities(communities, output_dir)
    print(f"[done] wrote {len(communities)} Binjiang communities to {output_dir}")

    if args.with_prices:
        snapshots = fetch_price_snapshots_for_communities(
            communities,
            args.timeout,
            args.sleep,
            args.price_mode,
            args.concurrency,
        )
        write_outputs(snapshots, output_dir)
        print(f"[done] wrote {len(snapshots)} price snapshots to {output_dir}")
    return 0 if communities else 1


if __name__ == "__main__":
    raise SystemExit(main())
