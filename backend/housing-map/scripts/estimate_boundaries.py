"""小区轮廓估算 CLI:OSM 建筑聚类 → 外轮廓 → 候选输出 + 预览 HTML → 上传接口落盘。

一次性数据补齐工具(任务 10-16-boundary-estimate-script):
  python scripts/estimate_boundaries.py                       # 估算全部无轮廓小区
  python scripts/estimate_boundaries.py --ids 20000608        # 指定小区
  python scripts/estimate_boundaries.py --apply --selection estimate_out/selected.json
                                                              # 勾选结果经上传接口落盘

算法实现在 src/services/boundary_estimate.py,CLI 与后台工作流共用同一套实现。
"""
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.services.boundary_estimate import (  # noqa: E402 - 需先补 sys.path
    CACHE_DIR,
    MIRRORS,
    SNAPSHOT_ALL,
    SNAPSHOT_BUILDINGS,
    SNAPSHOT_RESIDENTIAL,
    USER_AGENT,
    EstimateError,
    EstimateTarget,
    aliases_from_source,
    area_ha,
    build_boundary,
    cache_path_for,
    estimate_one,
    fetch_elements,
    gcj02_to_wgs84,
    select_buildings,
    wgs84_to_gcj02,
)
from src.services.boundary_estimate import load_snapshot as _load_snapshot  # noqa: E402
from src.services.boundary_workflow import effective_polygons, is_displayable  # noqa: E402
from src.services.data_loader import DATA_DIR, load_display_communities  # noqa: E402

POLYGONS_PATH = DATA_DIR / "binjiang_polygons_merged.json"
BINJIANG_BBOX = (30.10, 120.10, 30.26, 120.28)  # 滨江全域
OUT_DIR = PROJECT_ROOT / "estimate_out"
REQUEST_INTERVAL = 10.0

# 兼容旧调用名
_area_ha = area_ha


def load_snapshot(lng, lat):
    """快照读取;绑定本模块的快照路径,便于测试替换。返回 (elements, covered)。"""
    return _load_snapshot(lng, lat, snapshot_all=SNAPSHOT_ALL, snapshot_buildings=SNAPSHOT_BUILDINGS,
                          snapshot_residential=SNAPSHOT_RESIDENTIAL)


def _read_json(path, fallback):
    if not Path(path).exists():
        return fallback
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def target_communities(ids=None, from_api=None):
    """目标 = 展示小区 ∩ 有坐标 ∩ 无可展示轮廓。

    缺口判定与地图渲染口径一致:无条目、无 rings、或来源为 shp 都算缺口;已人工确认的
    覆盖层算已展示,不重复估算。--from-api 时从线上地图接口派生(本地数据不全时用)。"""
    if from_api:
        req = urllib.request.Request(from_api, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)["data"]
        targets = []
        for c in data:
            if not (c.get("latitude") and c.get("longitude")):
                continue
            if c.get("boundary") and c.get("boundary_source") != "shp":
                continue
            targets.append({
                "community_id": str(c["community_id"]),
                "community_name": c["community_name"],
                "community_alias": c.get("community_alias") or "",
                "longitude": c["longitude"],
                "latitude": c["latitude"],
            })
    else:
        targets = load_display_communities()
        polygons = effective_polygons()
        targets = [{**c, "community_id": str(c["community_id"])} for c in targets
                   if c.get("longitude") and c.get("latitude")
                   and not is_displayable(polygons.get(str(c["community_id"])))]
    if ids:
        targets = [t for t in targets if t["community_id"] in ids]
    return targets


def refresh_snapshot(interval=REQUEST_INTERVAL, fetcher=None):
    """全滨江抓取所有 building + residential 面,写入全量快照(具名与否不限)。"""
    s, w, n, e = BINJIANG_BBOX
    query = (
        f"[out:json][timeout:300];"
        f'(way["building"]({s},{w},{n},{e});'
        f'way["landuse"="residential"]({s},{w},{n},{e}););'
        f"out geom;"
    )
    body = urllib.parse.urlencode({"data": query}).encode()
    errors = []
    do_fetch = fetcher or _http_post
    for mirror in MIRRORS:
        try:
            if not fetcher:
                time.sleep(interval)
            elements = do_fetch(mirror, body)
            SNAPSHOT_ALL.write_text(json.dumps({"elements": elements}, ensure_ascii=False), encoding="utf-8")
            print(f"全量快照已写入 {SNAPSHOT_ALL.name}({len(elements)} 要素,来源 {mirror})")
            return len(elements)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{mirror}: {exc}")
    raise RuntimeError("所有 Overpass 镜像均失败:\n" + "\n".join(errors) +
                       "\n提示:本机出口可能无法直连 Overpass,可设置 HTTPS_PROXY 后重试")


def _http_post(url, body):
    req = urllib.request.Request(url, data=body, headers={
        "User-Agent": USER_AGENT,
        "Content-Type": "application/x-www-form-urlencoded",
    })
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.load(resp)["elements"]


# ---------------------------------------------------------------------------
# 输出:候选 geojson + 预览 HTML
# ---------------------------------------------------------------------------

def build_estimate_target(community) -> EstimateTarget:
    """本地目录和 --from-api 都只传递来源里已有的别名。"""
    return EstimateTarget(
        community_id=str(community["community_id"]),
        community_name=community.get("community_name") or "",
        longitude=community["longitude"],
        latitude=community["latitude"],
        aliases=aliases_from_source(community.get("community_alias")),
    )


def estimate_all(ids=None, interval=REQUEST_INTERVAL, fetcher=None, online=False, from_api=None):
    targets = target_communities(ids, from_api=from_api)
    results, failures = [], []
    if online:
        print("模式:在线 Overpass(--online)")
    else:
        print("模式:本地 OSM 快照优先,未覆盖时转在线")
    for index, community in enumerate(targets):
        cid, name = community["community_id"], community["community_name"]
        print(f"[{index + 1}/{len(targets)}] {name} ({cid}) ...", flush=True)
        target = build_estimate_target(community)
        try:
            outcome = estimate_one(
                target,
                snapshot_paths=None if online else {"all": SNAPSHOT_ALL, "buildings": SNAPSHOT_BUILDINGS,
                                                   "residential": SNAPSHOT_RESIDENTIAL},
                cache_dir=CACHE_DIR,
                fetcher=fetcher,
            )
        except EstimateError as exc:
            failures.append({"community_id": cid, "name": name, "error": exc.message})
            continue
        except Exception as exc:  # noqa: BLE001 - 单小区失败不阻断批次
            failures.append({"community_id": cid, "name": name, "error": str(exc)})
            continue
        results.append({
            "community_id": cid,
            "name": name,
            "center": [community["longitude"], community["latitude"]],
            "rings": [outcome.ring],
            "meta": {
                "building_count": len(outcome.members),
                "building_faces": outcome.building_faces,
                "residential_faces": outcome.residential_faces,
                "low_confidence": outcome.low_confidence,
                "estimated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            },
        })
    return results, failures


def _amap_credentials():
    """从 housing-map 前端 env 读 (key, security_js_code)。"""
    values = {}
    for name in (".env.local", ".env"):
        path = PROJECT_ROOT.parents[1] / "apps" / "housing-map" / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            stripped = line.strip()
            for env_key in ("NEXT_PUBLIC_GAODE_MAP_KEY", "NEXT_PUBLIC_GAODE_SECURITY_KEY",
                            "NEXT_PUBLIC_GAODE_MAP_SECURITY_KEY"):
                if stripped.startswith(env_key + "=") and env_key not in values:
                    values[env_key] = stripped.split("=", 1)[1].strip().strip('"').strip("'")
    return values.get("NEXT_PUBLIC_GAODE_MAP_KEY"), values.get("NEXT_PUBLIC_GAODE_SECURITY_KEY")


PREVIEW_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>小区轮廓估算预览</title>
<style>
body{margin:0;font-family:system-ui,sans-serif;display:flex;height:100vh}
#map{flex:1}#side{width:320px;overflow-y:auto;padding:12px;background:#fafaf7;font-size:13px}
.item{border-bottom:1px solid #e5e2da;padding:8px 4px;cursor:pointer}
.item.low{background:#fff4e5}
.small{color:#888;font-size:12px}
button{margin:12px 0;padding:8px 16px;width:100%}
.hint{background:#fff8dc;border:1px solid #e0d8a8;padding:6px;margin-bottom:8px}
</style></head><body>
<div id="map"></div><div id="side">
__KEY_HINT__
<button onclick="exportSelection()">导出勾选 selected.json</button>
<div id="list"></div></div>
<script>window.PREVIEW_DATA = __DATA__;</script>
<script>
window._AMapSecurityConfig = {securityJsCode: '__SECURITY__'};
</script>
<script src="https://webapi.amap.com/maps?v=2.0&key=__KEY__"></script>
<script>
const DATA = window.PREVIEW_DATA;
const map = new AMap.Map('map', {viewMode: '2D', zoom: 15, mapStyle: 'amap://styles/whitesmoke'});
const bounds = [];
DATA.existing.forEach(ring => {
  const poly = new AMap.Polygon({path: ring, strokeColor: '#999', strokeWeight: 1, fillOpacity: 0.03, bubble: true});
  map.add(poly);
});
DATA.candidates.forEach((c, i) => {
  const color = ['#d04a3a','#3a7bd0','#2f9e57','#c78a1f','#7a4ad0'][i % 5];
  const poly = new AMap.Polygon({path: c.rings[0], strokeColor: color, fillColor: color,
    fillOpacity: 0.35, strokeWeight: 2, bubble: true});
  map.add(poly); bounds.push(poly);
  new AMap.CircleMarker({center: c.center, radius: 5, fillColor: '#111', fillOpacity: 1,
    strokeColor: '#fff', strokeWeight: 1}).setMap(map);
});
map.setFitView(bounds);
const list = document.getElementById('list');
DATA.candidates.forEach((c, i) => {
  const div = document.createElement('div');
  div.className = 'item' + (c.meta.low_confidence ? ' low' : '');
  const ha = Math.round(c.area_ha * 10) / 10;
  const faces = c.meta.building_faces + c.meta.residential_faces;
  div.innerHTML = `<label><input type="checkbox" checked data-cid="${c.community_id}">
    <b>${c.name}</b></label>
    <div class="small">${c.community_id} · ${faces} 个参考面(建筑 ${c.meta.building_faces}/住宅面 ${c.meta.residential_faces}) · ${ha} 公顷
    ${c.meta.low_confidence ? ' · <span style="color:#c60">低置信</span>' : ''}</div>`;
  div.querySelector('input').addEventListener('change', e => {
    c._selected = e.target.checked;
    e.target.closest('.item').style.opacity = e.target.checked ? 1 : 0.4;
  });
  div.addEventListener('click', ev => {
    if (ev.target.tagName !== 'INPUT') map.setFitView(bounds.filter((_, j) => DATA.candidates[j].community_id === c.community_id));
  });
  list.appendChild(div);
});
function exportSelection() {
  const picked = DATA.candidates.filter(c => c._selected !== false);
  if (!picked.length) { alert('未勾选任何小区'); return; }
  const blob = new Blob([JSON.stringify(picked.map(c => ({community_id: c.community_id, name: c.name, rings: c.rings, meta: c.meta})), null, 1)],
    {type: 'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = 'selected.json'; a.click();
}
</script></body></html>
"""


def write_outputs(results, failures):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for result in results:
        result["area_ha"] = round(_area_ha(result["rings"][0]), 2)
    candidates_geojson = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"community_id": r["community_id"], "name": r["name"], **r["meta"], "area_ha": r["area_ha"]},
            "geometry": {"type": "Polygon", "coordinates": r["rings"]},
        } for r in results],
    }
    (OUT_DIR / "candidates.geojson").write_text(
        json.dumps(candidates_geojson, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT_DIR / "failures.json").write_text(
        json.dumps(failures, ensure_ascii=False, indent=1), encoding="utf-8")

    existing = []
    for cid, entry in _read_json(POLYGONS_PATH, {}).items():
        if cid == "_meta" or entry.get("source") != "osm":
            continue
        for ring in entry.get("rings", []):
            existing.append(ring)
    key, security = _amap_credentials()
    key_hint = "" if key else '<div class="hint">未读到 NEXT_PUBLIC_GAODE_MAP_KEY,地图空白时请填入下方 __KEY__ 处</div>'
    html = (PREVIEW_TEMPLATE
            .replace("__DATA__", json.dumps({"candidates": results, "existing": existing}, ensure_ascii=False))
            .replace("__KEY__", key or "YOUR_AMAP_KEY")
            .replace("__SECURITY__", security or "")
            .replace("__KEY_HINT__", key_hint))
    (OUT_DIR / "estimate_preview.html").write_text(html, encoding="utf-8")
    print(f"候选 {len(results)} 个 / 失败 {len(failures)} 个 -> {OUT_DIR}")
    print("预览请走 HTTP(高德 SDK 拒绝 file://):")
    print(f'  cd "{OUT_DIR}" && python -m http.server 8917')
    print("  浏览器打开 http://localhost:8917/estimate_preview.html")


# ---------------------------------------------------------------------------
# --apply:经上传接口落盘
# ---------------------------------------------------------------------------

def apply_selection(selection_path, api_base, token):
    selected = json.loads(Path(selection_path).read_text(encoding="utf-8-sig"))
    if not token:
        raise SystemExit("缺少 token:设 HOUSING_ADMIN_TOKEN 环境变量或传 --token")
    accepted, failed = [], []
    for item in selected:
        body = json.dumps({
            "source": "osm-building",
            "boundaries": [{
                "community_id": item["community_id"],
                "coordinate_system": "gcj02",
                "rings": item["rings"],
                "meta": item.get("meta"),
            }],
        }).encode()
        req = urllib.request.Request(
            f"{api_base.rstrip('/')}/api/boundaries/import", data=body,
            headers={"Content-Type": "application/json", "X-Admin-Token": token})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.load(resp)["data"]
            if data["accepted"]:
                accepted.append(item["community_id"])
                print(f"√ {item.get('name', item['community_id'])} 已落盘")
            else:
                reason = data["rejected"][0]["reason"] if data["rejected"] else "unknown"
                failed.append((item["community_id"], reason))
                print(f"× {item.get('name', item['community_id'])}: {reason}")
        except Exception as exc:  # noqa: BLE001 - 上传失败列出清单,接口幂等可重跑
            failed.append((item["community_id"], str(exc)))
            print(f"× {item['community_id']}: {exc}")
    print(f"完成 {len(accepted)} / 失败 {len(failed)};接口幂等,可修正后重跑")


def main(argv=None):
    parser = argparse.ArgumentParser(description="OSM 建筑聚类估算小区轮廓")
    parser.add_argument("--ids", nargs="*", help="仅处理指定 community_id")
    parser.add_argument("--apply", action="store_true", help="上传 selected.json 到后端接口")
    parser.add_argument("--selection", default=str(OUT_DIR / "selected.json"))
    parser.add_argument("--api", default="http://localhost:8096")
    parser.add_argument("--token", default=None)
    parser.add_argument("--interval", type=float, default=REQUEST_INTERVAL, help="Overpass 请求间隔秒")
    parser.add_argument("--online", action="store_true", help="跳过本地快照,强制在线抓取")
    parser.add_argument("--refresh-snapshot", action="store_true", help="全滨江重抓全量楼快照后退出")
    parser.add_argument("--from-api", default=None, help="从线上地图接口派生目标(如 https://host/api/map/communities)")
    args = parser.parse_args(argv)

    if args.apply:
        apply_selection(args.selection, args.api, args.token or __import__("os").environ.get("HOUSING_ADMIN_TOKEN"))
        return
    if args.refresh_snapshot:
        refresh_snapshot(interval=args.interval)
        return
    ids = set(args.ids) if args.ids else None
    results, failures = estimate_all(ids, interval=args.interval, online=args.online, from_api=args.from_api)
    write_outputs(results, failures)
    if failures:
        print("失败清单:")
        for f in failures:
            print(f"  {f['name']} ({f['community_id']}): {f['error']}")


if __name__ == "__main__":
    main()
