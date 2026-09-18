from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from fetch_tmsf_price_snapshot import BASE_URL, fetch_html_with_curl, input_value_by_id, strip_tags


DEFAULT_INPUT = "data/binjiang_communities.json"
DEFAULT_OUTPUT = "data/property_types.json"
DEFAULT_TIMEOUT = 15
PROPERTY_TYPES = {"住宅", "公寓", "商贸", "写字楼", "别墅", "排屋", "车位", "其他"}


def load_communities(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as file:
        data = json.load(file)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("communities", [])
    raise ValueError(f"Unsupported input format: {path}")


def load_existing(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        return {}
    return {str(key): value for key, value in data.items() if isinstance(value, dict)}


def extract_property_type(html: str) -> str | None:
    property_type = input_value_by_id(html, "managetypename_auto")
    if property_type:
        return normalize_property_type(property_type)

    text = strip_tags(html)
    match = re.search(r"物业类型\s*([^\s]+)", text)
    if match:
        return normalize_property_type(match.group(1))
    return None


def normalize_property_type(value: str | None) -> str | None:
    if not value:
        return None
    value = strip_tags(value).strip()
    value = re.split(r"[\s|/、,，;；]", value, maxsplit=1)[0].strip()
    if not value:
        return None
    for property_type in PROPERTY_TYPES:
        if property_type in value:
            return property_type
    return value if len(value) <= 10 else None


def fetch_one(community: dict[str, Any], timeout: int) -> dict[str, Any]:
    community_id = str(community.get("community_id") or community.get("communityid") or "")
    community_name = community.get("community_name") or community.get("communityname") or ""
    url = f"{BASE_URL}/esf/xq_indexnew_{community_id}.htm"
    started = time.perf_counter()
    try:
        html = fetch_html_with_curl(url, timeout)
        property_type = extract_property_type(html)
        return {
            "community_id": community_id,
            "community_name": community_name,
            "property_type": property_type,
            "url": url,
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
        }
    except Exception as error:
        return {
            "community_id": community_id,
            "community_name": community_name,
            "property_type": None,
            "url": url,
            "error": str(error),
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
        }


def merge_property_types_into_communities(
    communities: list[dict[str, Any]],
    property_types: dict[str, dict[str, Any]],
    output_json: Path,
    output_csv: Path,
) -> None:
    merged = []
    for community in communities:
        community_id = str(community.get("community_id") or community.get("communityid") or "")
        row = dict(community)
        row["property_type"] = property_types.get(community_id, {}).get("property_type")
        merged.append(row)

    output_json.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

    fieldnames: list[str] = []
    for row in merged:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with output_csv.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(merged)


def print_summary(results: dict[str, dict[str, Any]]) -> None:
    counts: dict[str, int] = {}
    errors = 0
    for result in results.values():
        if result.get("error"):
            errors += 1
        property_type = result.get("property_type") or "NOT_FOUND"
        counts[property_type] = counts.get(property_type, 0) + 1

    print("\n物业类型分布:")
    for property_type, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        print(f"  {property_type}: {count}")
    if errors:
        print(f"错误数: {errors}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="并发抓取 TMSF 小区物业类型")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="输入小区 JSON")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="输出物业类型 JSON")
    parser.add_argument("--limit", type=int, default=None, help="限制数量，测试用")
    parser.add_argument("--concurrency", type=int, default=8, help="并发数，建议 4-8")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="单请求超时秒数")
    parser.add_argument("--only-missing", action="store_true", help="只抓取已有输出中缺失物业类型的小区")
    parser.add_argument("--merge-communities", action="store_true", help="同时输出带 property_type 的小区清单")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    communities = load_communities(input_path)
    if args.limit is not None:
        communities = communities[: args.limit]

    existing = load_existing(output_path)
    if args.only_missing:
        communities = [
            community
            for community in communities
            if not existing.get(str(community.get("community_id") or community.get("communityid") or ""), {}).get("property_type")
        ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    results = dict(existing)
    print(f"待抓取 {len(communities)} 个小区，并发 {args.concurrency}")

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
        futures = {executor.submit(fetch_one, community, args.timeout): community for community in communities}
        for index, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            community_id = result["community_id"]
            results[community_id] = result
            status = result.get("property_type") or ("ERROR" if result.get("error") else "NOT_FOUND")
            print(f"[{index}/{len(communities)}] {community_id} {result['community_name']} -> {status} ({result['elapsed_ms']}ms)")

            if index % 25 == 0:
                output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    elapsed = time.perf_counter() - started
    print(f"\n完成，写入 {output_path}，耗时 {elapsed:.1f}s")
    print_summary(results)

    if args.merge_communities:
        merged_json = input_path.with_name(input_path.stem + "_with_property_type.json")
        merged_csv = input_path.with_name(input_path.stem + "_with_property_type.csv")
        all_communities = load_communities(input_path)
        merge_property_types_into_communities(all_communities, results, merged_json, merged_csv)
        print(f"已合并输出 {merged_json} 和 {merged_csv}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
