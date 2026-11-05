"""数据加载工具

移植自源项目 web/src/lib/data-loader.ts，清洗规则逐条对齐。
从 backend/housing-map/data/ 目录加载 11 个运行时数据文件。
"""

import json
import os
import re
from pathlib import Path

from src.services.price_policy import (
    PRICE_KIND_COUNTS,
    PRICE_KIND_DEAL,
    PRICE_KIND_LISTING,
    project_price_record,
    shanghai_today,
)

# 数据目录: backend/housing-map/data (src/services/data_loader.py -> parents[2] = 服务根)
DATA_DIR = Path(os.environ['HOUSING_DATA_DIR']) if os.environ.get('HOUSING_DATA_DIR') else Path(__file__).resolve().parents[2] / "data"


def get_data_paths() -> dict[str, Path]:
    return {
        "communities": DATA_DIR / "binjiang_communities.json",
        "coordinates": DATA_DIR / "binjiang_coordinates.json",
        "pois": DATA_DIR / "binjiang_pois.json",
        "price_snapshots": DATA_DIR / "price_snapshots.jsonl",
        "property_types": DATA_DIR / "property_types.json",
        "polygons": DATA_DIR / "binjiang_polygons_merged.json",
        "subway_stations": DATA_DIR / "binjiang_subway_stations.json",
        "community_ages": DATA_DIR / "community_ages.json",
        "community_attrs": DATA_DIR / "community_attrs.json",
        "transit_routes": DATA_DIR / "binjiang_transit_routes.geojson",
        "transit_stops": DATA_DIR / "binjiang_transit_stops.geojson",
    }


# ---------------------------------------------------------------------------
# 名称清洗
# ---------------------------------------------------------------------------

def clean_station_name(name: str) -> str:
    """清洗地铁站名称，移除出入口后缀 ("西浦路地铁站A口" -> "西浦路地铁站")"""
    name = re.sub(r"[A-Za-z0-9]+口$", "", name)
    name = re.sub(r"出入口$", "", name)
    name = re.sub(r"地铁站$", "", name)
    name = re.sub(r"\(地铁站\)$", "", name)
    return name.strip()


# 医院类清洗: 社康/诊所不展示; 科室/楼栋后缀剥离后归并到医院主体名
HOSPITAL_SKIP = re.compile(r"卫生服务|卫生服务中心|卫生院|诊所|门诊部|医务室|晒背驿站")
HOSPITAL_SUFFIX = re.compile(
    r"\d+号.*$"
    r"|(?:急诊|发热|肠道|肝病|骨科|高压氧治疗|健康管理|健康促进|胸痛|感染性疾病|放射科"
    r"|整形外科|整形|推拿科|骨伤科|儿科|牙科|结核|核医学|母婴室|国际医学部|康复中心楼"
    r"|行政综合楼|行政区|行政楼|科教楼|体检|问诊室|美容中心|勤务|配置|预约|卒中|创伤"
    r"|驾驶人?|眼科|骨刺科|病案科|病理科|手足外科|皮肤风湿|免疫科|生殖医学|放疗|化疗"
    r"|动物实验|成人康复)(?:中心|部|科|室|区)?$"
    r"|(?:住院[一二三四五六七八九十]?(?:部|楼)?|门诊楼|门诊部|门诊|病房楼|中心楼|病区)$"
    r"|[-—]$"
)
# 俗称/简写 -> 正式名
HOSPITAL_ALIASES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^邵逸夫医院$"), "浙江大学医学院附属邵逸夫医院"),
    (re.compile(r"^浙江大学医学院邵逸夫医院$"), "浙江大学医学院附属邵逸夫医院"),
]

# POI 展示范围（高德抓取半径过大, 会带入远处设施）
# = 覆盖范围 (滨江∪萧山板块) 围栏的外接框, 随 boundary.py 围栏集合自动扩展
def _scope_bounds() -> dict[str, float]:
    from src.core.boundary import BINJIANG_BOUNDARY, XIAOSHAN_BORDER_BOUNDARIES

    pts = [p for poly in (BINJIANG_BOUNDARY, *XIAOSHAN_BORDER_BOUNDARIES.values()) for p in poly]
    lngs, lats = [p[0] for p in pts], [p[1] for p in pts]
    return {"lat_min": min(lats), "lat_max": max(lats), "lng_min": min(lngs), "lng_max": max(lngs)}


POI_BOUNDS = _scope_bounds()


def in_poi_bounds(lat: float, lng: float) -> bool:
    return (
        POI_BOUNDS["lat_min"] <= lat <= POI_BOUNDS["lat_max"]
        and POI_BOUNDS["lng_min"] <= lng <= POI_BOUNDS["lng_max"]
    )


def clean_hospital_name(name: str) -> str:
    n = re.sub(r"[（(][^）)]*[）)]", "", name)
    for _ in range(4):  # 后缀嵌套时最多剥 4 轮
        nxt = HOSPITAL_SUFFIX.sub("", n)
        if nxt == n:
            break
        n = nxt
    # 剥离出俗称/简写后再归一到正式名
    for pattern, canonical in HOSPITAL_ALIASES:
        n = pattern.sub(canonical, n)
    return n.strip()


# 学校类清洗: 高校内部处室/院系/楼栋归并到主体名
# 锚点截断: "杭州医学院滨江校区教务处" -> "杭州医学院滨江校区"
SCHOOL_SKIP = re.compile(r"办事处")
SCHOOL_UNI_ANCHOR = re.compile(r"大学|学院|校区")

_SCHOOL_ANCHOR_PATTERNS = [
    re.compile(r"校区"),
    re.compile(r"大学"),
    re.compile(r"(?:研究院|学校|中学|小学|幼儿园|学院)"),
]


def truncate_school_name(name: str) -> str:
    n = re.sub(r"[（(][^）)]*[）)]", "", name)

    def cut_at_last(pattern: re.Pattern[str]) -> str | None:
        matches = list(pattern.finditer(n))
        if not matches:
            return None
        return n[: matches[-1].end()]

    return (
        cut_at_last(_SCHOOL_ANCHOR_PATTERNS[0])
        or cut_at_last(_SCHOOL_ANCHOR_PATTERNS[1])
        or cut_at_last(_SCHOOL_ANCHOR_PATTERNS[2])
        or n
    )


# ---------------------------------------------------------------------------
# POI 去重与前缀归并
# ---------------------------------------------------------------------------

def deduplicate_pois(pois: list[dict]) -> list[dict]:
    """对 POI 列表去重（同一地铁站同名出入口只保留距离最近的一个）"""
    seen: dict[str, dict] = {}

    for poi in pois:
        # 全类型统一范围过滤: 错位小区与抓取半径过大带入的区外设施不展示
        if not in_poi_bounds(poi["latitude"], poi["longitude"]):
            continue

        poi_type = poi["type"]
        if poi_type != "subway":
            if poi_type == "hospital":
                if HOSPITAL_SKIP.search(poi["name"]):
                    continue
                hospital_name = clean_hospital_name(poi["name"]) or poi["name"]
                key = f"hospital|{hospital_name}"
                if key not in seen or seen[key]["distance"] > poi["distance"]:
                    seen[key] = {**poi, "name": hospital_name}
                continue
            if poi_type == "school":
                if SCHOOL_SKIP.search(poi["name"]):
                    continue
                if SCHOOL_UNI_ANCHOR.search(poi["name"]):
                    # 高校类: 内部处室/院系归并到主体（中小学/幼儿园不含锚词, 原样保留）
                    school_name = truncate_school_name(poi["name"]).strip()
                    final_name = school_name if len(school_name) >= 4 else poi["name"]
                    key = f"school|{final_name}"
                    if key not in seen or seen[key]["distance"] > poi["distance"]:
                        seen[key] = {**poi, "name": final_name}
                else:
                    seen[poi["name"]] = poi
                continue
            seen[poi["name"]] = poi
            continue

        station_name = clean_station_name(poi["name"])
        key = f"{station_name}|{poi_type}"
        if key not in seen or seen[key]["distance"] > poi["distance"]:
            seen[key] = {**poi, "name": station_name or poi["name"]}

    return list(seen.values())


def merge_prefix_names(result: dict, poi_type: str) -> None:
    """全局前缀归并: "主体+后缀"型名称并入已存在的"主体"名

    兜住词表无法穷举的变体, 如 "邵逸夫医院眼科"->"邵逸夫医院"。
    分隔符 -·、 忽略后再比前缀。
    """
    # 保持插入序（与 TS Set 迭代序一致, 平局时先到者胜）
    all_names: list[str] = []
    name_seen: set[str] = set()
    for data in result.values():
        for p in data["pois"].get(poi_type) or []:
            if p["name"] not in name_seen:
                name_seen.add(p["name"])
                all_names.append(p["name"])
    if len(all_names) < 2:
        return

    def normalize(s: str) -> str:
        return re.sub(r"[-·、_]", "", s)

    rename: dict[str, str] = {}
    for n in all_names:
        norm = normalize(n)
        best: str | None = None
        for m in all_names:
            if m == n:
                continue
            norm_m = normalize(m)
            if len(norm_m) >= 4 and len(norm_m) < len(norm) and norm.startswith(norm_m):
                if best is None or len(norm_m) > len(normalize(best)):
                    best = m
        if best:
            rename[n] = best
    if not rename:
        return

    for data in result.values():
        poi_list = data["pois"].get(poi_type)
        if not poi_list:
            continue
        seen: dict[str, dict] = {}
        for p in poi_list:
            renamed = {**p, "name": rename[p["name"]]} if p["name"] in rename else p
            existing = seen.get(renamed["name"])
            if existing is None or renamed["distance"] < existing["distance"]:
                seen[renamed["name"]] = renamed
        data["pois"][poi_type] = list(seen.values())


# ---------------------------------------------------------------------------
# 加载器
# ---------------------------------------------------------------------------

def load_json(path: Path, fallback):
    """文件不存在/解析失败返回 fallback（不抛错）"""
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"加载文件失败 {path}: {exc}")
    return fallback


def load_communities() -> list[dict]:
    from src.services.community_registry import existing_registry
    registry = existing_registry(get_data_paths()["communities"].parent)
    if registry:
        tmsf = {r['community_id']: r['source_id'] for r in registry.sources()
                if r['source'] == 'tmsf' and r['status'] == 'matched'}
        return [{**c, 'tmsf_id': tmsf.get(c['community_id'])} for c in registry.communities()]
    data = load_json(get_data_paths()["communities"], [])
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "communities" in data:
        return data["communities"]
    return []


def load_display_communities(*, drop_ids=()) -> list[dict]:
    """Display projection only; load_communities remains the historical/collection identity set."""
    from src.services.community_registry import existing_registry
    from src.services.community_directory import prepare_directory
    from src.services.community_admission import community_views
    data_dir = get_data_paths()['communities'].parent
    if not existing_registry(data_dir):
        return load_communities()
    registry = prepare_directory(data_dir)
    identities = {c['community_id']: c for c in load_communities()}
    return [{**identities[c['community_id']], **c} for c in community_views(registry, data_dir, drop_ids=drop_ids)
            if c['map_status'] == 'displayed']


def load_coordinates() -> dict[str, dict]:
    raw = load_json(get_data_paths()["coordinates"], {})
    from src.services.community_registry import existing_registry
    registry = existing_registry(get_data_paths()["communities"].parent)
    if registry:
        from src.services.community_admission import community_views
        for c in community_views(registry, get_data_paths()['communities'].parent):
            if c.get('coordinate_system', 'gcj02') != 'gcj02':
                continue
            if c.get('longitude') and c.get('latitude'):
                raw[c['community_id']] = {'longitude': c['longitude'], 'latitude': c['latitude'],
                                          'formatted_address': c.get('position_formatted_address', c.get('address', ''))}
    # 错区防护: 地址不含"滨江区/萧山区"的坐标不可信 (跨市错配)。
    # 萧山区地址还须落在萧山板块围栏内, 防"失准到萧山城区中心"的点混入。
    # (滨江小区错配到萧山同名地名的情况仍由地址字符串挡, 见湖头陈村案例)
    from src.core.boundary import is_in_xiaoshan_border

    result: dict[str, dict] = {}
    for cid, co in raw.items():
        address = co.get("formatted_address") or ""
        if "滨江区" in address:
            result[cid] = co
        elif "萧山区" in address and is_in_xiaoshan_border(co.get("longitude") or 0, co.get("latitude") or 0):
            result[cid] = co
    return result


def load_property_types() -> dict[str, dict]:
    return load_json(get_data_paths()["property_types"], {})


def load_transit_routes() -> dict:
    return load_json(get_data_paths()["transit_routes"], {"features": []})


def load_transit_stops() -> dict:
    return load_json(get_data_paths()["transit_stops"], {"features": []})


def load_subway_stations() -> list[dict]:
    return load_json(get_data_paths()["subway_stations"], [])


def load_community_ages() -> dict[str, dict]:
    return load_json(get_data_paths()["community_ages"], {})


def load_community_attrs() -> dict[str, dict]:
    return load_json(get_data_paths()["community_attrs"], {})


def load_polygons() -> dict[str, dict]:
    data = load_json(get_data_paths()["polygons"], {})
    if isinstance(data, dict) and "polygons" in data:
        return data["polygons"]
    return data


def load_pois() -> dict[str, dict]:
    raw = load_json(get_data_paths()["pois"], {})

    # 对每个小区的每类 POI 进行去重
    result: dict[str, dict] = {}
    for community_id, data in raw.items():
        deduplicated: dict[str, list[dict]] = {}
        for poi_type, poi_list in (data.get("pois") or {}).items():
            deduplicated[poi_type] = deduplicate_pois(poi_list)
        result[community_id] = {"pois": deduplicated}
    # 全局前缀归并: 兜住词表无法穷举的 "主体+科室/院系" 变体
    merge_prefix_names(result, "hospital")
    merge_prefix_names(result, "school")
    return result


# 价格槽: 当前有效签约 / 当前有效挂牌 / 过期签约历史; counts 为套数（独立采集时间）
_PRICE_SLOTS = ("deal", "listing", "history_deal", "counts")


def _record_order_key(record: dict) -> tuple[str, str]:
    """记录新旧排序键: crawled_at 优先, snapshot_date 兜底（字符串本身可比）。"""
    return (str(record.get("crawled_at") or ""), str(record.get("snapshot_date") or ""))


def _new_price_slots() -> dict[str, tuple[tuple[str, str], dict] | None]:
    return {key: None for key in _PRICE_SLOTS}


def _offer_slot(slots: dict, key: str, order_key: tuple[str, str], value) -> None:
    """同槽按采集时间取最新, 与记录在文件中的先后顺序无关。"""
    if value is None:
        return
    existing = slots[key]
    if existing is None or order_key > existing[0]:
        slots[key] = (order_key, value)


def _public_price_entry(entry: dict) -> dict:
    """对外的价格条目: 价格所属月份、采集时间、来源 URL、陈旧标记。"""
    return {
        "price": entry["price"],
        "month": entry["month"],
        "captured_at": entry["captured_at"],
        "source_url": entry["source_url"],
        "stale": entry["stale"],
    }


def _counts_entry(record: dict) -> dict:
    """套数快照与它自己的采集时间; 套数更新不冒充价格更新（R3）。"""
    return {
        "listing_count": record.get("listing_count") or 0,
        "deal_count": record.get("deal_count") or 0,
        "captured_at": record.get("crawled_at") or record.get("snapshot_date") or None,
    }


def _has_counts(record: dict) -> bool:
    """记录是否真的带着套数: 缺套数的新记录不得把旧套数标成本轮采集（R3）。"""
    return record.get("listing_count") is not None or record.get("deal_count") is not None


def _assemble_price_entry(slots: dict, refresh) -> dict:
    """组装单小区条目: 兼容 price/price_type/date + 新字段, 缺失一律 None。

    兼容字段只来自有效当前价（有效签约优先、挂牌兜底）; 无有效价时
    price=None 但历史与套数照常返回（前端可显示"暂无近期价格"）。
    """
    deal = slots["deal"][1] if slots["deal"] else None
    listing = slots["listing"][1] if slots["listing"] else None
    history_deal = slots["history_deal"][1] if slots["history_deal"] else None
    counts = slots["counts"][1] if slots["counts"] else None
    current = deal or listing
    if current is not None:
        price_type = "monthly_deal_avg_latest" if deal is not None else "listing_avg"
        date_value = current.get("captured_date") or current.get("captured_at")
        price = current["price"]
    else:
        price_type = price = date_value = None
    return {
        "price": price,
        "price_type": price_type,
        "date": date_value,
        "deal": _public_price_entry(deal) if deal else None,
        "listing": _public_price_entry(listing) if listing else None,
        "history_deal": _public_price_entry(history_deal) if history_deal else None,
        "counts": counts,
        "refresh": refresh if isinstance(refresh, dict) else None,
    }


def _load_price_refresh_status(data_dir: Path) -> dict[str, dict]:
    """读取每小区价格刷新状态（refresh 服务写侧的 sidecar, 形状见 services/refresh.py）。

    文件缺失/损坏返回空表; 顶层为 {community_id: 状态对象}。条目必须带字符串
    outcome（写侧契约字段）, 否则忽略, 不编造未知字段。
    """
    data = load_json(data_dir / "price_refresh_status.json", {})
    if not isinstance(data, dict):
        return {}
    return {cid: value for cid, value in data.items()
            if isinstance(value, dict) and isinstance(value.get("outcome"), str)}


def load_price_snapshots(path: Path | None = None, *, today=None) -> dict[str, dict]:
    """加载价格快照: 双价投影（签约/挂牌独立返回）+ 兼容选价。

    - 有效性按当前上海日期判断（可注入 today）: 成交月份超过 6 个月的签约价
      只进 history_deal, 不参与当前价; 未知月份不得用采集日期代替。
    - 每条价格含所属月份、采集时间、来源 URL、stale（30 天陈旧, 与月度有效期
      分别计算）。
    - 合并来源按价格类型分别选最新记录, 不按文件顺序整体覆盖。
    - counts_only 记录只贡献套数槽; 缺套数的价格记录不覆盖旧套数采集时间。
    """
    if path is None:
        path = get_data_paths()["price_snapshots"]
    today = shanghai_today(today)
    result: dict[str, dict] = {}

    try:
        if path.exists():
            content = path.read_text(encoding="utf-8")
            records: list[dict] = []
            for line in content.split("\n"):
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue  # 忽略无效行
                if not isinstance(record, dict):
                    continue
                records.append(record)

            for record in records:
                price_type = record.get("price_type")
                if price_type not in (PRICE_KIND_DEAL, PRICE_KIND_LISTING, PRICE_KIND_COUNTS):
                    continue
                if not record.get("community_id"):
                    continue
                if record.get('market_state') == 'new_house' or '/newhouse/' in (record.get('source_url') or ''):
                    continue

                cid = record["community_id"]
                slots = result.setdefault(cid, _new_price_slots())
                order_key = _record_order_key(record)
                if price_type == PRICE_KIND_COUNTS:
                    if _has_counts(record):
                        _offer_slot(slots, "counts", order_key, _counts_entry(record))
                    continue
                entry = project_price_record(record, today=today)
                if entry is not None:
                    slot_key = ("history_deal" if entry["expired"] else
                                ("deal" if price_type == PRICE_KIND_DEAL else "listing"))
                    _offer_slot(slots, slot_key, order_key, entry)
                # 过期/无月份/无挂牌的记录不产出价格条目, 但页面套数仍如实保留
                if _has_counts(record):
                    _offer_slot(slots, "counts", order_key, _counts_entry(record))
    except OSError as exc:
        print(f"加载价格快照失败: {exc}")

    from src.services.community_registry import existing_registry
    registry = existing_registry(path.parent)
    if registry:
        mappings = {r['source_id']: r['community_id'] for r in registry.sources()
                    if r['source'] == 'tmsf' and r['status'] == 'matched'}
        refresh_status = _load_price_refresh_status(path.parent)
        merged: dict[str, dict] = {}
        for sid, slots in result.items():
            cid = mappings.get(sid)
            if not cid or not registry.resolve(cid):
                continue
            target = merged.setdefault(cid, _new_price_slots())
            for key in _PRICE_SLOTS:
                value = slots[key]
                if value is not None:
                    _offer_slot(target, key, value[0], value[1])
        return {cid: _assemble_price_entry(slots, refresh_status.get(cid))
                for cid, slots in merged.items()}
    refresh_status = _load_price_refresh_status(path.parent)
    return {cid: _assemble_price_entry(slots, refresh_status.get(cid))
            for cid, slots in result.items()}
