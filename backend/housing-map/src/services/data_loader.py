"""数据加载工具

移植自源项目 web/src/lib/data-loader.ts，清洗规则逐条对齐。
从 backend/housing-map/data/ 目录加载 11 个运行时数据文件。
"""

import json
import re
from pathlib import Path

# 数据目录: backend/housing-map/data (src/services/data_loader.py -> parents[2] = 服务根)
DATA_DIR = Path(__file__).resolve().parents[2] / "data"


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

# POI 展示范围（高德抓取半径过大, 会带入主城区北部设施）
POI_BOUNDS = {"lat_min": 30.12, "lat_max": 30.26, "lng_min": 120.09, "lng_max": 120.29}


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
    data = load_json(get_data_paths()["communities"], [])
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "communities" in data:
        return data["communities"]
    return []


def load_coordinates() -> dict[str, dict]:
    raw = load_json(get_data_paths()["coordinates"], {})
    # 错区防护: 地理编码结果地址不含"滨江区"的坐标不可信
    # (如湖头陈村社区匹配到萧山同名村, 且错位位置可能落在滨江坐标围栏内, 围栏挡不住)
    result: dict[str, dict] = {}
    for cid, co in raw.items():
        if co.get("formatted_address") and "滨江区" not in co["formatted_address"]:
            continue
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


def load_price_snapshots(path: Path | None = None) -> dict[str, dict]:
    """价格快照: 同小区 monthly_deal_avg_latest(签约均价) 优先于
    visible_listing_unit_price_avg(挂牌样本均价)"""
    if path is None:
        path = get_data_paths()["price_snapshots"]
    result: dict[str, dict] = {}

    try:
        if path.exists():
            content = path.read_text(encoding="utf-8")
            lines = [line for line in content.split("\n") if line]

            for line in lines:
                try:
                    record = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue  # 忽略无效行
                if not isinstance(record, dict):
                    continue
                # TS: record.avg_price !== undefined (null 视为有效, 保留进结果)
                if record.get("community_id") and "avg_price" in record:
                    existing = result.get(record["community_id"])
                    snapshot = {
                        "price": record["avg_price"],
                        "date": record.get("snapshot_date") or "",
                        "listing_count": record.get("listing_count") or 0,
                        "deal_count": record.get("deal_count") or 0,
                        "price_type": record.get("price_type") or "",
                    }
                    # 优先 monthly_deal_avg_latest(签约均价)，否则用挂牌样本均价
                    if existing is None:
                        result[record["community_id"]] = snapshot
                    elif record.get("price_type") == "monthly_deal_avg_latest":
                        result[record["community_id"]] = snapshot
    except OSError as exc:
        print(f"加载价格快照失败: {exc}")

    return result
