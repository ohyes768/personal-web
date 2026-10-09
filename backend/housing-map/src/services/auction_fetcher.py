"""来拍公开住宅拍卖接口；来源为辅助机构，非阿里直接数据。"""
import html
import math
import re
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

BASE_URL = "https://api.faeping.com/api/webV1"
BINJIANG_CODE = 330108


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AuctionClient:
    def __init__(self, session=None, attempts=2):
        if session is None:
            from curl_cffi.requests import Session
            session = Session(impersonate="chrome")
        self.session = session
        self.attempts = attempts

    def close(self):
        self.session.close()

    def _get(self, path, params=None):
        for attempt in range(self.attempts):
            try:
                response = self.session.get(BASE_URL + path, params=params,
                                            headers={"client": "PC", "Accept": "application/json"}, timeout=20)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict) or payload.get("status") != 200:
                    raise RuntimeError("auction upstream business error")
                if not isinstance(payload.get("data"), dict):
                    raise RuntimeError("invalid auction upstream data")
                return payload["data"]
            except Exception:
                if attempt + 1 == self.attempts:
                    raise
                time.sleep(0.7)

    def list_page(self, page):
        data = self._get("/searchObject", {"organization_type": 1, "province": 330000,
                         "city": 330100, "second_class": "residence", "perPage": 12, "page": page})
        count = data.get("count")
        if not isinstance(data.get("list"), list) or isinstance(count, bool) or not str(count).isdigit():
            raise RuntimeError("invalid auction page")
        data["count"] = int(count)
        return data

    def detail(self, auction_id):
        if not str(auction_id).isdigit():
            raise ValueError("invalid auction id")
        return self._get("/auction/" + str(auction_id))


def positive_number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(str(value).replace(",", ""))
        return number if math.isfinite(number) and number > 0 else None
    except (ValueError, TypeError):
        return None


def money(value):
    if positive_number(value) is None:
        return None
    try:
        number = Decimal(str(value).replace(",", ""))
        return int(number) if number == number.to_integral_value() else None
    except (InvalidOperation, ValueError):
        return None


def plain_text(value):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))).strip()


def normalize_auction(data, communities):
    if str(data.get("area_code")) != str(BINJIANG_CODE) or data.get("second_class") != "residence":
        return None
    if not str(data.get("auction_id", "")).isdigit() or not str(data.get("object_id", "")).isdigit():
        raise RuntimeError("missing auction identity")
    title = plain_text(data.get("object_title"))
    address = plain_text(data.get("object_address")) or title
    if not title or ("区" in address and "滨江区" not in address):
        raise RuntimeError("auction address conflicts with district")
    status = data.get("auction_status")
    known = {"todo", "doing", "done", "pause", "failure", "break", "revocation", "debt"}
    status = status if isinstance(status, str) and status in known else "unknown"
    source_detail = data.get("auction_object_detail") or {}
    additional = data.get("auction_additional") or {}
    facts = {}
    for cells in re.findall(r"<tr\b[^>]*>(.*?)</tr>", str(data.get("obj_fact") or ""), re.S | re.I):
        values = [plain_text(cell) for cell in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", cells, re.S | re.I)]
        for index in range(len(values) - 1):
            facts[values[index]] = values[index + 1]
    announcement = plain_text(additional.get("announcement"))
    area = positive_number(source_detail.get("gross_floor_area"))
    area_source = "structured" if area else None
    if not area:
        area_match = re.fullmatch(r"([\d.]+)\s*(?:平方米|㎡)", facts.get("建筑面积", ""))
        area = positive_number(area_match.group(1)) if area_match else None
        area_source = "investigation_table" if area else None
    if not area:
        match = re.search(r"建筑(?:总)?面积\s*[（(]?\s*(?:㎡|m²)?\s*[）)]?\s*[:：为]?\s*([\d.]+)\s*(?:平方米|㎡)", announcement)
        area = positive_number(match.group(1)) if match else None
        area_source = "announcement" if area else None
    name = plain_text(data.get("cell_name"))
    matches = set()
    for community in communities:
        names = {community.get("community_name"), community.get("community_alias")}
        if name and name in names and community.get("community_id"):
            matches.add(str(community["community_id"]))
    community_id = next(iter(matches)) if len(matches) == 1 else None
    deal_price = money(data.get("deal_price")) if status == "done" else None
    url = data.get("from_where_url")
    url = url if isinstance(url, str) and urlparse(url).scheme in {"https", "http"} and urlparse(url).hostname else None
    # Only whitelisted property facts are retained, never full announcements or contacts.
    risk = {}
    labels = {"is_empty": "是否已腾空", "rent_desc": "租赁情况", "transfer_desc": "过户情况",
              "other_fee_desc": "其他介绍", "tax_desc": "税费情况"}
    for field, label in labels.items():
        text = plain_text(source_detail.get(field)) or facts.get(label, "")
        if text:
            risk[field] = re.sub(r"\d{7,}", "[已省略]", text)[:1000]
    return {"source": "laipai", "auction_id": str(data["auction_id"]),
            "asset_id": str(data["object_id"]), "title": title, "address": address,
            "district": "滨江区", "property_use": "residence", "community_name": name,
            "community_id": community_id, "match_confidence": 1 if community_id else 0,
            "status": status, "source_status": data.get("auction_status"), "round": data.get("bid_times"),
            "start_price_yuan": money(data.get("start_price")),
            "appraisal_price_yuan": money(data.get("appraise_price")), "deal_price_yuan": deal_price,
            "area_m2": area, "area_source": area_source,
            "deal_unit_price": round(deal_price / area) if deal_price and area else None,
            "start_at": data.get("start_time"), "end_at": data.get("end_time"),
            "court": (data.get("court_info") or {}).get("court_name"),
            "auction_platform": data.get("from_where"), "original_url": url,
            "source_url": f"https://www.laipaiya.com/entrust_detail/{data['auction_id']}",
            "risk_notes": risk, "captured_at": now_iso()}
