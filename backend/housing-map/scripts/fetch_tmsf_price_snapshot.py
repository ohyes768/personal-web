from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import json
import re
import shutil
import statistics
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


BASE_URL = "https://www.tmsf.com"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


@dataclass
class PriceSnapshot:
    community_id: str
    community_name: str | None
    snapshot_date: str
    source: str
    price_type: str
    avg_price: int | None
    listing_count: int | None
    deal_count: int | None
    sample_count: int
    min_price: int | None
    max_price: int | None
    source_url: str
    confidence_score: float
    raw_payload: dict[str, Any]
    crawled_at: str


def fetch_html(url: str, timeout: int) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset()
            return decode_response_bytes(response.read(), charset)
    except urllib.error.HTTPError as error:
        if error.code != 405:
            raise
    return fetch_html_with_curl(url, timeout)


def decode_response_bytes(content: bytes, charset: str | None = None) -> str:
    if charset and charset.lower() not in {"iso-8859-1", "latin-1", "latin1"}:
        return content.decode(charset, errors="replace")

    for encoding in ("utf-8", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode(charset or "utf-8", errors="replace")


def fetch_html_with_curl(url: str, timeout: int) -> str:
    curl_path = shutil.which("curl.exe") or shutil.which("curl")
    if not curl_path:
        raise RuntimeError("urllib got HTTP 405 and curl is not available for fallback")
    completed = subprocess.run(
        [
            curl_path,
            "-sSL",
            "--compressed",
            "--max-time",
            str(timeout),
            "-A",
            DEFAULT_USER_AGENT,
            "-H",
            "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
            url,
        ],
        check=True,
        capture_output=True,
    )
    return decode_response_bytes(completed.stdout)


def strip_tags(value: str) -> str:
    value = re.sub(r"<script\b[^>]*>.*?</script>", "", value, flags=re.I | re.S)
    value = re.sub(r"<style\b[^>]*>.*?</style>", "", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def first_int(pattern: str, text: str, flags: int = re.S) -> int | None:
    match = re.search(pattern, text, flags)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def first_text(pattern: str, text: str, flags: int = re.S) -> str | None:
    match = re.search(pattern, text, flags)
    if not match:
        return None
    return strip_tags(match.group(1))


def input_value_by_id(text: str, input_id: str) -> str | None:
    pattern = rf"<input\b(?=[^>]*\bid=[\"']{re.escape(input_id)}[\"'])[^>]*>"
    match = re.search(pattern, text, flags=re.I | re.S)
    if not match:
        return None
    value_match = re.search(r"\bvalue=[\"']([^\"']*)[\"']", match.group(0), flags=re.I | re.S)
    if not value_match:
        return None
    return strip_tags(value_match.group(1))


def parse_index_page(index_html: str) -> dict[str, Any]:
    community_name = first_text(r'<span\s+class="big">\s*(.*?)\s*(?:<!--|</span>)', index_html)
    if not community_name:
        community_name = input_value_by_id(index_html, "communityname_auto")
    if not community_name:
        community_name = first_text(r"<title>\s*(.*?)\s*-小区详情", index_html)
    location_text = first_text(r"所属城区：</font>(.*?)</p>", index_html)
    district = subdistrict = address = None
    if location_text:
        pieces = [piece.strip() for piece in re.split(r"\s*\|\s*", location_text, maxsplit=1)]
        area_parts = pieces[0].split()
        district = area_parts[0] if area_parts else None
        subdistrict = area_parts[1] if len(area_parts) > 1 else None
        address = pieces[1] if len(pieces) > 1 else None
    else:
        area_name = input_value_by_id(index_html, "areaname_auto")
        if area_name:
            area_parts = area_name.split()
            district = area_parts[0] if area_parts else None
            subdistrict = area_parts[1] if len(area_parts) > 1 else None
        address = first_text(r'<span\s+class="toverF\s+max150">\s*(.*?)\s*</span>', index_html)

    listing_count = first_int(r"二手房（\s*([0-9,]+)\s*套\s*）", index_html)
    if listing_count is None:
        listing_count = first_int(r"在售房源：\s*<font[^>]*>\s*([0-9,]+)\s*</font>\s*套", index_html)
    if listing_count is None:
        listing_count = first_int(r"挂牌房源数.*?bold[^>]*>\s*([0-9,]+)\s*套", index_html)

    deal_count = first_int(r"近30日签约\s*<font[^>]*>\s*([0-9,]+)\s*</font>\s*套", index_html)
    deal_avg_price = first_int(r'<span\s+class="bigsale2"[^>]*>\s*([0-9,]+)\s*</span>\s*元/㎡', index_html)
    listing_avg_price = first_int(r"挂牌均价\s*(?:</?[^>]+>\s*)*([0-9,]+)\s*元/㎡", index_html)
    listing_unit_prices = [
        int(value.replace(",", ""))
        for value in re.findall(r"<text>\s*([0-9,]+)\s*元/㎡\s*</text>", index_html)
    ]

    return {
        "community_name": community_name,
        "district": district,
        "subdistrict": subdistrict,
        "address": address,
        "listing_count": listing_count,
        "deal_count": deal_count,
        "deal_avg_price": deal_avg_price,
        "listing_avg_price": listing_avg_price,
        "listing_unit_prices": listing_unit_prices,
    }


def parse_tendency_page(tendency_html: str) -> dict[str, Any]:
    current_avg = first_int(r"小区均价：\s*(?:</?[^>]+>\s*)*([0-9,]+)\s*元/㎡", tendency_html)
    monthly = parse_tendency_var("tendency2", tendency_html)
    latest_month = latest_monthly_avg = None
    if monthly and monthly.get("ticks") and monthly.get("line"):
        ticks = monthly["ticks"]
        line = monthly["line"]
        if len(ticks) == len(line) and line:
            latest_month = ticks[-1]
            latest_monthly_avg = int(line[-1])

    return {
        "current_avg_price": current_avg,
        "monthly_trend": monthly,
        "latest_month": latest_month,
        "latest_monthly_avg": latest_monthly_avg,
    }


def parse_tendency_var(var_name: str, text: str) -> dict[str, Any] | None:
    match = re.search(rf"var\s+{re.escape(var_name)}\s*=\s*'(.+?)';", text, flags=re.S)
    if not match:
        return None
    try:
        parsed = json.loads(html.unescape(match.group(1)))
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
        return parsed[0]
    return None


def build_snapshots(community_id: str, index_html: str, tendency_html: str) -> list[PriceSnapshot]:
    index_data = parse_index_page(index_html)
    tendency_data = parse_tendency_page(tendency_html)
    today = dt.date.today().isoformat()
    crawled_at = dt.datetime.now(dt.UTC).isoformat()
    index_url = f"{BASE_URL}/esf/xq_indexnew_{community_id}.htm"
    tendency_url = f"{BASE_URL}/esf/xq_xqtendency_{community_id}.htm"

    snapshots: list[PriceSnapshot] = []
    common_raw = {
        "community": {
            "district": index_data["district"],
            "subdistrict": index_data["subdistrict"],
            "address": index_data["address"],
        },
        "index": {
            "listing_count": index_data["listing_count"],
            "deal_count": index_data["deal_count"],
            "deal_avg_price": index_data["deal_avg_price"],
            "listing_avg_price": index_data["listing_avg_price"],
        },
        "tendency": {
            "current_avg_price": tendency_data["current_avg_price"],
            "latest_month": tendency_data["latest_month"],
            "latest_monthly_avg": tendency_data["latest_monthly_avg"],
        },
    }

    if index_data["deal_avg_price"] or tendency_data["current_avg_price"]:
        snapshots.append(
            PriceSnapshot(
                community_id=community_id,
                community_name=index_data["community_name"],
                snapshot_date=today,
                source="tmsf",
                price_type="recent_deal_avg",
                avg_price=index_data["deal_avg_price"] or tendency_data["current_avg_price"],
                listing_count=index_data["listing_count"],
                deal_count=index_data["deal_count"],
                sample_count=index_data["deal_count"] or 0,
                min_price=None,
                max_price=None,
                source_url=index_url,
                confidence_score=0.86,
                raw_payload=common_raw,
                crawled_at=crawled_at,
            )
        )

    if tendency_data["latest_monthly_avg"]:
        snapshots.append(
            PriceSnapshot(
                community_id=community_id,
                community_name=index_data["community_name"],
                snapshot_date=today,
                source="tmsf",
                price_type="monthly_deal_avg_latest",
                avg_price=tendency_data["latest_monthly_avg"],
                listing_count=index_data["listing_count"],
                deal_count=index_data["deal_count"],
                sample_count=len(tendency_data["monthly_trend"].get("line", [])) if tendency_data["monthly_trend"] else 0,
                min_price=None,
                max_price=None,
                source_url=tendency_url,
                confidence_score=0.9,
                raw_payload={**common_raw, "monthly_trend": tendency_data["monthly_trend"]},
                crawled_at=crawled_at,
            )
        )

    if index_data["listing_avg_price"]:
        snapshots.append(
            PriceSnapshot(
                community_id=community_id,
                community_name=index_data["community_name"],
                snapshot_date=today,
                source="tmsf",
                price_type="listing_avg",
                avg_price=index_data["listing_avg_price"],
                listing_count=index_data["listing_count"],
                deal_count=index_data["deal_count"],
                sample_count=index_data["listing_count"] or 0,
                min_price=None,
                max_price=None,
                source_url=index_url,
                confidence_score=0.82,
                raw_payload=common_raw,
                crawled_at=crawled_at,
            )
        )

    listing_unit_prices = index_data["listing_unit_prices"]
    if listing_unit_prices:
        snapshots.append(
            PriceSnapshot(
                community_id=community_id,
                community_name=index_data["community_name"],
                snapshot_date=today,
                source="tmsf",
                price_type="visible_listing_unit_price_avg",
                avg_price=round(statistics.mean(listing_unit_prices)),
                listing_count=index_data["listing_count"],
                deal_count=index_data["deal_count"],
                sample_count=len(listing_unit_prices),
                min_price=min(listing_unit_prices),
                max_price=max(listing_unit_prices),
                source_url=index_url,
                confidence_score=0.62,
                raw_payload={**common_raw, "visible_listing_unit_prices": listing_unit_prices},
                crawled_at=crawled_at,
            )
        )

    return snapshots


def write_outputs(snapshots: list[PriceSnapshot], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [asdict(snapshot) for snapshot in snapshots]

    jsonl_path = output_dir / "price_snapshots.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")

    csv_path = output_dir / "price_snapshots.csv"
    fieldnames = list(rows[0].keys()) if rows else list(PriceSnapshot.__dataclass_fields__.keys())
    with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            row = {**row, "raw_payload": json.dumps(row["raw_payload"], ensure_ascii=False)}
            writer.writerow(row)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch low-frequency TMSF community price snapshots.")
    parser.add_argument("--community-id", action="append", required=True, help="TMSF community id, e.g. 10001734")
    parser.add_argument("--output-dir", default="data", help="Output directory, default: data")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout seconds")
    parser.add_argument("--sleep", type=float, default=2.0, help="Delay between communities")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    all_snapshots: list[PriceSnapshot] = []
    for index, community_id in enumerate(args.community_id):
        community_id = community_id.strip()
        index_url = f"{BASE_URL}/esf/xq_indexnew_{community_id}.htm"
        tendency_url = f"{BASE_URL}/esf/xq_xqtendency_{community_id}.htm"
        try:
            index_html = fetch_html(index_url, args.timeout)
            tendency_html = fetch_html(tendency_url, args.timeout)
        except Exception as error:  # 单小区失败(超时/限流等)跳过, 不中断整批
            print(f"[error] {community_id}: {type(error).__name__}: {error}")
            continue

        snapshots = build_snapshots(community_id, index_html, tendency_html)
        all_snapshots.extend(snapshots)
        print(f"[ok] {community_id}: {len(snapshots)} snapshots")
        if index < len(args.community_id) - 1:
            time.sleep(args.sleep)

    write_outputs(all_snapshots, Path(args.output_dir))
    print(f"[done] wrote {len(all_snapshots)} snapshots to {args.output_dir}")
    return 0 if all_snapshots else 1


if __name__ == "__main__":
    raise SystemExit(main())
