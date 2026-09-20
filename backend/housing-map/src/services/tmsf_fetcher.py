"""透明售房网小区价格采集。

目标站点会拒绝普通 Python HTTP 客户端；此模块使用 curl_cffi 的 Chrome
TLS/HTTP 指纹，保留轻量镜像，不依赖 Chromium。解析和输出集中于此，
HTTP refresh 与命令行脚本使用同一实现。
"""

from __future__ import annotations

import csv
import datetime as dt
import html
import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable


BASE_URL = "https://www.tmsf.com"
DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


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


@dataclass
class CommunityFetchResult:
    snapshots: list[PriceSnapshot]
    errors: list[str]


class TmsfClient:
    """用 Chrome 指纹取回 TMSF HTML；Session 可注入以保持单元测试离线。"""

    session_options = {"impersonate": "chrome"}

    def __init__(
        self,
        session_factory: Callable[..., Any] | None = None,
        *,
        max_attempts: int = 2,
        retry_delay_seconds: float = 0.5,
    ):
        self._session_factory = session_factory
        self._session: Any | None = None
        self._max_attempts = max(1, max_attempts)
        self._retry_delay_seconds = max(0, retry_delay_seconds)

    def fetch_text(self, url: str, timeout: int) -> str:
        last_error: Exception | None = None
        for attempt in range(self._max_attempts):
            try:
                response = self._session_or_create().get(
                    url,
                    timeout=timeout,
                    headers=DEFAULT_HEADERS,
                )
                response.raise_for_status()
                return decode_response_bytes(response.content, getattr(response, "encoding", None))
            except Exception as error:
                last_error = error
                if attempt < self._max_attempts - 1 and self._retry_delay_seconds:
                    time.sleep(self._retry_delay_seconds)
        assert last_error is not None
        raise last_error

    def _session_or_create(self) -> Any:
        if self._session is None:
            factory = self._session_factory or _curl_cffi_session
            self._session = factory(**self.session_options)
        return self._session


def _curl_cffi_session(**options: Any) -> Any:
    try:
        from curl_cffi import requests
    except ImportError as error:  # 便于本地部署诊断，而非静默退回普通 urllib
        raise RuntimeError("curl_cffi is required for TMSF fetching") from error
    return requests.Session(**options)


def decode_response_bytes(content: bytes, charset: str | None = None) -> str:
    if charset and charset.lower() not in {"iso-8859-1", "latin-1", "latin1"}:
        return content.decode(charset, errors="replace")
    for encoding in ("utf-8", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode(charset or "utf-8", errors="replace")


def strip_tags(value: str) -> str:
    value = re.sub(r"<script\b[^>]*>.*?</script>", "", value, flags=re.I | re.S)
    value = re.sub(r"<style\b[^>]*>.*?</style>", "", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def first_int(pattern: str, text: str, flags: int = re.S) -> int | None:
    match = re.search(pattern, text, flags)
    return int(match.group(1).replace(",", "")) if match else None


def first_text(pattern: str, text: str, flags: int = re.S) -> str | None:
    match = re.search(pattern, text, flags)
    return strip_tags(match.group(1)) if match else None


def input_value_by_id(text: str, input_id: str) -> str | None:
    pattern = rf"<input\b(?=[^>]*\bid=[\"']{re.escape(input_id)}[\"'])[^>]*>"
    match = re.search(pattern, text, flags=re.I | re.S)
    if not match:
        return None
    value_match = re.search(r"\bvalue=[\"']([^\"']*)[\"']", match.group(0), flags=re.I | re.S)
    return strip_tags(value_match.group(1)) if value_match else None


def parse_index_page(index_html: str) -> dict[str, Any]:
    community_name = first_text(r'<span\s+class="big">\s*(.*?)\s*(?:<!--|</span>)', index_html)
    community_name = community_name or input_value_by_id(index_html, "communityname_auto")
    community_name = community_name or first_text(r"<title>\s*(.*?)\s*-小区详情", index_html)
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
    listing_count = listing_count if listing_count is not None else first_int(
        r"在售房源：\s*<font[^>]*>\s*([0-9,]+)\s*</font>\s*套", index_html
    )
    listing_count = listing_count if listing_count is not None else first_int(
        r"挂牌房源数.*?bold[^>]*>\s*([0-9,]+)\s*套", index_html
    )
    return {
        "community_name": community_name,
        "district": district,
        "subdistrict": subdistrict,
        "address": address,
        "listing_count": listing_count,
        "deal_count": first_int(r"近30日签约\s*<font[^>]*>\s*([0-9,]+)\s*</font>\s*套", index_html),
        "deal_avg_price": first_int(r'<span\s+class="bigsale2"[^>]*>\s*([0-9,]+)\s*</span>\s*元/㎡', index_html),
        "listing_avg_price": first_int(r"挂牌均价\s*(?:</?[^>]+>\s*)*([0-9,]+)\s*元/㎡", index_html),
    }


def parse_tendency_var(var_name: str, text: str) -> dict[str, Any] | None:
    match = re.search(rf"var\s+{re.escape(var_name)}\s*=\s*'(.+?)';", text, flags=re.S)
    if not match:
        return None
    try:
        parsed = json.loads(html.unescape(match.group(1)))
    except json.JSONDecodeError:
        return None
    return parsed[0] if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict) else None


def parse_tendency_page(tendency_html: str) -> dict[str, Any]:
    current_avg = first_int(r"小区均价：\s*(?:</?[^>]+>\s*)*([0-9,]+)\s*元/㎡", tendency_html)
    monthly = parse_tendency_var("tendency2", tendency_html)
    latest_month = latest_monthly_avg = None
    if monthly and monthly.get("ticks") and monthly.get("line"):
        ticks = monthly["ticks"]
        line = monthly["line"]
        if len(ticks) == len(line) and line:
            latest_month, latest_monthly_avg = ticks[-1], int(line[-1])
    return {
        "current_avg_price": current_avg,
        "monthly_trend": monthly,
        "latest_month": latest_month,
        "latest_monthly_avg": latest_monthly_avg,
    }


def build_snapshots(community_id: str, index_html: str, tendency_html: str) -> list[PriceSnapshot]:
    index_data = parse_index_page(index_html)
    tendency_data = parse_tendency_page(tendency_html)
    today = dt.date.today().isoformat()
    crawled_at = dt.datetime.now(dt.UTC).isoformat()
    index_url = f"{BASE_URL}/esf/xq_indexnew_{community_id}.htm"
    tendency_url = f"{BASE_URL}/esf/xq_xqtendency_{community_id}.htm"
    common_raw = {
        "community": {key: index_data[key] for key in ("district", "subdistrict", "address")},
        "index": {key: index_data[key] for key in ("listing_count", "deal_count", "deal_avg_price", "listing_avg_price")},
        "tendency": {
            "current_avg_price": tendency_data["current_avg_price"],
            "latest_month": tendency_data["latest_month"],
            "latest_monthly_avg": tendency_data["latest_monthly_avg"],
        },
    }
    snapshots: list[PriceSnapshot] = []
    if tendency_data["latest_monthly_avg"]:
        snapshots.append(PriceSnapshot(
            community_id=community_id, community_name=index_data["community_name"], snapshot_date=today,
            source="tmsf", price_type="monthly_deal_avg_latest", avg_price=tendency_data["latest_monthly_avg"],
            listing_count=index_data["listing_count"], deal_count=index_data["deal_count"],
            sample_count=len(tendency_data["monthly_trend"].get("line", [])) if tendency_data["monthly_trend"] else 0,
            min_price=None, max_price=None, source_url=tendency_url, confidence_score=0.9,
            raw_payload={**common_raw, "monthly_trend": tendency_data["monthly_trend"]}, crawled_at=crawled_at,
        ))
    if index_data["listing_avg_price"]:
        snapshots.append(PriceSnapshot(
            community_id=community_id, community_name=index_data["community_name"], snapshot_date=today,
            source="tmsf", price_type="listing_avg", avg_price=index_data["listing_avg_price"],
            listing_count=index_data["listing_count"], deal_count=index_data["deal_count"],
            sample_count=index_data["listing_count"] or 0, min_price=None, max_price=None,
            source_url=index_url, confidence_score=0.82, raw_payload=common_raw, crawled_at=crawled_at,
        ))
    return snapshots


def fetch_community_snapshots(
    community_id: str,
    *,
    timeout: int,
    fetch_text: Callable[[str, int], str] | None = None,
) -> CommunityFetchResult:
    fetch_text = fetch_text or TmsfClient().fetch_text
    pages = {
        "index": f"{BASE_URL}/esf/xq_indexnew_{community_id}.htm",
        "tendency": f"{BASE_URL}/esf/xq_xqtendency_{community_id}.htm",
    }
    html_by_page = {"index": "", "tendency": ""}
    errors: list[str] = []
    for page_name, url in pages.items():
        try:
            html_by_page[page_name] = fetch_text(url, timeout)
        except Exception as error:
            errors.append(f"{page_name}: {type(error).__name__}: {error}")
    return CommunityFetchResult(
        snapshots=build_snapshots(community_id, html_by_page["index"], html_by_page["tendency"]),
        errors=errors,
    )


def write_outputs(snapshots: list[PriceSnapshot], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [asdict(snapshot) for snapshot in snapshots]
    jsonl_path = output_dir / "price_snapshots.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
    csv_path = output_dir / "price_snapshots.csv"
    fields = list(rows[0]) if rows else list(PriceSnapshot.__dataclass_fields__)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "raw_payload": json.dumps(row["raw_payload"], ensure_ascii=False)})
