"""data_loader 模块测试: 清洗规则对齐源 data-loader.ts"""

import json

from src.services.data_loader import (
    clean_hospital_name,
    clean_station_name,
    deduplicate_pois,
    in_poi_bounds,
    load_price_snapshots,
    truncate_school_name,
)


# ---------------------------------------------------------------------------
# 地铁站名清洗
# ---------------------------------------------------------------------------

def test_clean_station_name_strips_exit_suffix():
    # TS 链式 replace 依次剥掉 A口 与 地铁站 后缀, 最终只留路名主体
    assert clean_station_name("西浦路地铁站A口") == "西浦路"
    assert clean_station_name("西浦路地铁站B口") == "西浦路"


def test_clean_station_name_strips_paren_and_station():
    assert clean_station_name("西浦路(地铁站)") == "西浦路"
    assert clean_station_name("聚才路地铁站") == "聚才路"


def test_clean_station_name_plain_unchanged():
    assert clean_station_name("西浦路站").strip() == "西浦路站"


# ---------------------------------------------------------------------------
# 医院名清洗
# ---------------------------------------------------------------------------

def test_clean_hospital_name_removes_parens():
    assert clean_hospital_name("浙江大学医学院附属邵逸夫医院(下沙院区)") == "浙江大学医学院附属邵逸夫医院"


def test_clean_hospital_name_strips_building_suffix():
    assert clean_hospital_name("某某医院3号楼") == "某某医院"


def test_clean_hospital_name_alias_normalized():
    # 俗称归一到正式名
    assert clean_hospital_name("邵逸夫医院") == "浙江大学医学院附属邵逸夫医院"


# ---------------------------------------------------------------------------
# 学校名清洗
# ---------------------------------------------------------------------------

def test_truncate_school_name_at_campus_anchor():
    # 锚点截断: "杭州医学院滨江校区教务处" -> "杭州医学院滨江校区"
    assert truncate_school_name("杭州医学院滨江校区教务处") == "杭州医学院滨江校区"


def test_truncate_school_name_at_university():
    assert truncate_school_name("浙江大学计算机学院") == "浙江大学"


# ---------------------------------------------------------------------------
# POI 围栏与去重
# ---------------------------------------------------------------------------

def test_in_poi_bounds():
    assert in_poi_bounds(30.18, 120.19) is True
    assert in_poi_bounds(30.40, 120.19) is False  # 纬度越界 (主城区北部)
    assert in_poi_bounds(30.18, 120.05) is False  # 经度越界


def test_deduplicate_subway_keeps_nearest():
    # 同一地铁站多个出入口只保留距离最近的一个, 名称清洗后归并
    pois = [
        {"name": "西浦路地铁站B口", "type": "subway", "distance": 224, "latitude": 30.1687, "longitude": 120.1376},
        {"name": "西浦路地铁站A口", "type": "subway", "distance": 196, "latitude": 30.1690, "longitude": 120.1377},
    ]
    result = deduplicate_pois(pois)
    assert len(result) == 1
    assert result[0]["name"] == "西浦路"
    assert result[0]["distance"] == 196


def test_deduplicate_filters_out_of_bounds():
    pois = [
        {"name": "区外商场", "type": "mall", "distance": 500, "latitude": 30.40, "longitude": 120.19},
        {"name": "区内商场", "type": "mall", "distance": 500, "latitude": 30.18, "longitude": 120.19},
    ]
    result = deduplicate_pois(pois)
    assert [p["name"] for p in result] == ["区内商场"]


def test_deduplicate_skips_community_hospital():
    pois = [
        {"name": "浦沿街道社区卫生服务中心", "type": "hospital", "distance": 300, "latitude": 30.18, "longitude": 120.19},
    ]
    assert deduplicate_pois(pois) == []


# ---------------------------------------------------------------------------
# 价格快照口径优先级
# ---------------------------------------------------------------------------

def _write_jsonl(tmp_path, records):
    path = tmp_path / "price_snapshots.jsonl"
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )
    return path


def test_price_deal_type_wins_over_listing(tmp_path):
    # monthly_deal_avg_latest (签约) 优先于 visible_listing_unit_price_avg (挂牌)
    path = _write_jsonl(tmp_path, [
        {"community_id": "A", "avg_price": 100, "price_type": "visible_listing_unit_price_avg",
         "listing_count": 5, "deal_count": 0, "snapshot_date": "2026-09-01"},
        {"community_id": "A", "avg_price": 200, "price_type": "monthly_deal_avg_latest",
         "listing_count": 6, "deal_count": 2, "snapshot_date": "2026-09-02"},
        {"community_id": "B", "avg_price": 300, "price_type": "visible_listing_unit_price_avg",
         "listing_count": 7, "deal_count": 0, "snapshot_date": "2026-09-01"},
    ])
    result = load_price_snapshots(path)
    assert result["A"]["price"] == 200
    assert result["A"]["price_type"] == "monthly_deal_avg_latest"
    assert result["B"]["price"] == 300


def test_price_deal_first_listing_later_does_not_overwrite(tmp_path):
    # 签约价先出现时, 后到的挂牌价不能覆盖
    path = _write_jsonl(tmp_path, [
        {"community_id": "A", "avg_price": 200, "price_type": "monthly_deal_avg_latest",
         "listing_count": 6, "deal_count": 2, "snapshot_date": "2026-09-02"},
        {"community_id": "A", "avg_price": 100, "price_type": "visible_listing_unit_price_avg",
         "listing_count": 5, "deal_count": 0, "snapshot_date": "2026-09-01"},
    ])
    result = load_price_snapshots(path)
    assert result["A"]["price"] == 200
    assert result["A"]["price_type"] == "monthly_deal_avg_latest"


def test_price_invalid_line_skipped(tmp_path):
    path = tmp_path / "price_snapshots.jsonl"
    path.write_text(
        json.dumps({"community_id": "A", "avg_price": 100, "price_type": "x",
                    "listing_count": 1, "deal_count": 0, "snapshot_date": "d"})
        + "\nnot-json\n\n",
        encoding="utf-8",
    )
    result = load_price_snapshots(path)
    assert set(result.keys()) == {"A"}


def test_price_missing_file_returns_empty(tmp_path):
    assert load_price_snapshots(tmp_path / "nope.jsonl") == {}
