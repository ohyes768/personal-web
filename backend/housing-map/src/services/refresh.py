"""价格快照采集刷新（11-04 批次 B: 采集范围与结果透明化）

POST   /api/refresh?mode=all|missing&limit=N   后台启动服务内采集任务
GET    /api/refresh                            轮询任务进度 + eligible/missing 数量
DELETE /api/refresh                            终止当前任务

采集资格（R5）: 只有已收录小区才采集——community_views 有效 admitted、覆盖内
坐标、真实小区、有效 matched 的 TMSF community 来源, 排除新房/项目; 无台账
不猜测已收录, 返回空计划。补齐(mode=missing)只选两种当前可用价格都没有的
已收录小区。定时任务复用默认 mode=all; 所有入口共用 running 互斥。

结果透明（R3）: 每轮报告 updated/noData/failed/skipped（互斥, 合计=小区总数）
与 retained（保留原价的小区数, 可与前三类重叠）; 部分页失败标记 partial 不吞
errors; 网络失败(fetch_failed)、解析失败(parse_failed)与正常无价(no_price_data)、
仅过期价(expired_only)分别记录原因。每小区结果持久化到 price_refresh_status.json;
套数与价格独立记录采集时间, 套数更新不表述为价格更新。

数据安全（R4）: 主快照通过目标目录内临时文件 + fsync + os.replace 原子发布,
失败清理临时文件并保留旧主快照; CSV 是可重建导出, 失败只报警告并说明主快照
已发布; 任务取消不发布快照、不写状态, 仅在 job 上记录取消尝试。
"""

import asyncio
from dataclasses import asdict
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from src.services.data_loader import DATA_DIR, load_price_snapshots
from src.services.price_policy import PRICE_KIND_DEAL, PRICE_KIND_LISTING, deal_month_is_current
from src.services.tmsf_fetcher import CommunityFetchResult, fetch_community_snapshots

DEFAULT_FETCH_TIMEOUT = 20
REFRESH_STATUS_FILE = "price_refresh_status.json"
CSV_FIELDS = [
    "community_id", "community_name", "snapshot_date", "source", "price_type",
    "avg_price", "listing_count", "deal_count", "trend_point_count",
    "min_price", "max_price", "source_url", "raw_payload", "crawled_at",
]

# 模块级单例: 本地/容器单进程部署足够
job: dict = {
    "running": False,
    "phase": "idle",  # idle | fetching | merging | done | error | cancelled
    "mode": None,     # all | missing
    "total": 0,
    "processed": 0,
    "okCount": 0,     # 兼容字段 = updated 小区数
    "errorCount": 0,  # 兼容字段 = failed 小区数
    "updated": 0,
    "noData": 0,
    "failed": 0,
    "skipped": 0,
    "retained": 0,
    "startedAt": None,
    "finishedAt": None,
    "error": None,
    "result": None,
}

_task: asyncio.Task | None = None
_cancel_requested = False


def _now_iso() -> str:
    """UTC ISO 时间戳, 与 JS new Date().toISOString() 同格式 (毫秒 + Z)"""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").split("\n"):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if parsed is not None:  # TS filter(Boolean): "null" 行解析结果也被滤掉
            rows.append(parsed)
    return rows


def merge_snapshot_rows(fresh: list[dict], old: list[dict]) -> list[dict]:
    """新记录优先，未刷新到的小区继续保留旧记录。"""

    def key_of(r: dict) -> str:
        return f"{r.get('community_id')}|{r.get('price_type')}"

    seen = {key_of(r) for r in fresh}
    kept = [r for r in old if key_of(r) not in seen]
    return fresh + kept


def _atomic_write(path: Path, content: str) -> None:
    """目标目录内临时文件 + flush/fsync + os.replace; 失败清理临时文件（R4）。"""
    tmp = path.with_name(path.name + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8", newline="") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def write_jsonl(snapshot_path: Path, rows: list[dict]) -> None:
    _atomic_write(
        snapshot_path,
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + ("\n" if rows else ""),
    )


def rewrite_csv(data_path: Path, rows: list[dict]) -> None:
    """与脚本 write_outputs 保持同字段/utf-8-sig, 供人工查看; 可随时重建的导出。"""
    def escape(v) -> str:
        if v is None:
            return ""
        if isinstance(v, bool):
            s = "true" if v else "false"
        else:
            s = str(v)
        if any(ch in s for ch in ',"\r\n'):
            return '"' + s.replace('"', '""') + '"'
        return s

    lines = [",".join(CSV_FIELDS)]
    for row in rows:
        fields = []
        for f in CSV_FIELDS:
            if f == "raw_payload":
                v = json.dumps(row.get(f), ensure_ascii=False)  # JS: JSON.stringify(row[f] ?? null)
            else:
                v = row.get(f)
            fields.append(escape(v))
        lines.append(",".join(fields))
    (data_path / "price_snapshots.csv").write_text(
        "\r\n".join(lines) + "\r\n", encoding="utf-8-sig"
    )


# ---------------------------------------------------------------------------
# 采集资格（R5）: all 与 missing 共用同一实现
# ---------------------------------------------------------------------------

def collectible_plans(data_path: Path | None = None) -> list[dict]:
    """已收录小区的采集计划: [{"community_id", "community_name", "sources": [来源ID...]}]。

    资格 = community_views 有效 admitted（覆盖内坐标 + 真实小区 + 收录状态,
    与 /communities 展示口径一致; 不依赖地图轮廓, 缺轮廓仍可采）+ 排除
    new_house/项目身份。每个小区的全部有效 community 来源按来源去重采集。
    无台账不猜测已收录, 返回空计划。
    """
    data_path = Path(data_path) if data_path else DATA_DIR
    from src.services.community_admission import community_views
    from src.services.community_registry import existing_registry

    registry = existing_registry(data_path)
    if registry is None:
        return []
    views = community_views(registry, data_path)
    eligible: dict[str, str] = {}
    for view in views:
        if view.get("map_status") != "displayed":
            continue
        if view.get("market_state") == "new_house" or view.get("project"):
            continue
        eligible[view["community_id"]] = view.get("community_name") or ""
    plans: dict[str, dict] = {}
    for record in registry.sources():
        if (record["source"] == "tmsf" and record["source_kind"] == "community"
                and record["status"] == "matched" and record["community_id"] in eligible):
            cid = record["community_id"]
            plan = plans.setdefault(
                cid, {"community_id": cid, "community_name": eligible[cid], "sources": []})
            if record["source_id"] not in plan["sources"]:
                plan["sources"].append(record["source_id"])
    return sorted(plans.values(), key=lambda plan: plan["community_id"])


def missing_plans(plans: list[dict], prices: dict[str, dict]) -> list[dict]:
    """补齐目标: 没有任何有效 deal 且没有任何有效 listing 的已收录小区。

    仅缺一种价格、或超过 30 天未更新但仍有可用价格的不算缺价;
    counts 套数与过期历史价不算可用价格。
    """
    return [
        plan for plan in plans
        if not (prices.get(plan["community_id"]) or {}).get("deal")
        and not (prices.get(plan["community_id"]) or {}).get("listing")
    ]


def eligibility_counts(data_path: Path | None = None) -> dict:
    """GET /api/refresh 附带的数量: 已收录可采集小区数与缺价小区数（去重后）。"""
    data_path = Path(data_path) if data_path else None
    plans = collectible_plans(data_path)
    prices = load_price_snapshots(data_path / "price_snapshots.jsonl" if data_path else None)
    return {"eligible": len(plans), "missing": len(missing_plans(plans, prices))}


def _still_collectible(data_path: Path, community_id: str, source_id: str) -> bool:
    """轮内轻量重查资格与绑定（R5）: 来源仍 matched 指向本小区、小区未删/未合并、
    收录未被撤销。与 collectible_plans 共用 registry 同一资格事实; 轮内
    property/坐标文件不变, registry 三处变化（撤销收录/换绑/删除合并）均能检出。
    """
    from src.services.community_registry import existing_registry

    registry = existing_registry(data_path)
    if registry is None:
        return False
    with registry.db() as db:
        source = db.execute(
            "SELECT cid, status FROM sources WHERE source='tmsf' AND kind='community' AND sid=?",
            (str(source_id),)).fetchone()
        if not source or source["status"] != "matched" or source["cid"] != community_id:
            return False
        community = db.execute(
            "SELECT deleted, merged_to FROM communities WHERE id=?", (community_id,)).fetchone()
        if not community or community["deleted"] or community["merged_to"]:
            return False
        admission = db.execute(
            "SELECT payload FROM community_admission WHERE cid=?", (community_id,)).fetchone()
        if not admission or json.loads(admission["payload"]).get("state") != "admitted":
            return False
    return True


# ---------------------------------------------------------------------------
# 每轮结果分类（R3）
# ---------------------------------------------------------------------------

def _classify_fetch_result(result: CommunityFetchResult, *, today=None) -> dict:
    """单来源抓取结果 → 透明化分类。

    - updated: 抓到任一当前可用价格（有效月份签约价或有效挂牌价）
    - failed:  页面抓取失败(fetch_failed)或首页抓到但完全解析不出(parse_failed)
    - no_data: 正常无价(no_price_data)或仅抓到过期签约价(expired_only, 不计有效更新)
    partial = updated 但部分页面失败; errors 原样保留不吞。
    """
    snapshots = result.snapshots or []
    errors = list(result.errors or [])
    current_kinds: list[str] = []
    expired_deal = False
    has_counts = False
    captured_at = None
    for snap in snapshots:
        captured_at = snap.crawled_at or captured_at
        if snap.listing_count is not None or snap.deal_count is not None:
            has_counts = True
        if snap.avg_price is None or snap.avg_price <= 0:
            continue
        if snap.price_type == PRICE_KIND_LISTING:
            if snap.listing_count:
                current_kinds.append(PRICE_KIND_LISTING)
        elif snap.price_type == PRICE_KIND_DEAL:
            raw = snap.raw_payload if isinstance(snap.raw_payload, dict) else {}
            tendency = raw.get("tendency") if isinstance(raw.get("tendency"), dict) else {}
            month = tendency.get("latest_month")
            if deal_month_is_current(month, today=today):
                current_kinds.append(PRICE_KIND_DEAL)
            elif month is not None:
                expired_deal = True
    if current_kinds:
        outcome, reason = "updated", None
    elif errors:
        outcome, reason = "failed", "fetch_failed"
    elif not snapshots:
        outcome, reason = "failed", "parse_failed"
    elif expired_deal:
        outcome, reason = "no_data", "expired_only"
    else:
        outcome, reason = "no_data", "no_price_data"
    return {
        "outcome": outcome,
        "reason": reason,
        "partial": bool(current_kinds and errors),
        "errors": errors,
        "counts": has_counts,
        "captured_at": captured_at,
        "price_kinds": sorted(set(current_kinds)),
    }


def _summarize_plan(entry: dict) -> None:
    """按主小区汇总来源结果: updated > failed > no_data, 全部 skipped 则 skipped。"""
    source_outcomes = [s["outcome"] for s in entry["sources"].values()]
    if not source_outcomes or all(o == "skipped" for o in source_outcomes):
        entry["outcome"] = "skipped"
        return
    updated = [s for s in entry["sources"].values() if s["outcome"] == "updated"]
    if updated:
        entry["outcome"] = "updated"
        entry["price_updated"] = True
        entry["price_captured_at"] = next(
            (s["captured_at"] for s in updated if s["captured_at"]), None)
        entry["partial"] = any(
            s["outcome"] in {"failed", "no_data"} or s["partial"]
            for s in entry["sources"].values())
        return
    if any(o == "failed" for o in source_outcomes):
        entry["outcome"] = "failed"
    else:
        entry["outcome"] = "no_data"


def _retained_price_dates(plans: list[dict], old_rows: list[dict]) -> dict[str, str]:
    """旧主快照里每个主小区保留的价格记录的最新快照日（套数记录不算价格）。"""
    sid_to_cid = {sid: plan["community_id"] for plan in plans for sid in plan["sources"]}
    dates: dict[str, str] = {}
    for row in old_rows:
        if row.get("price_type") not in (PRICE_KIND_DEAL, PRICE_KIND_LISTING):
            continue
        if row.get("market_state") == "new_house" or "/newhouse/" in (row.get("source_url") or ""):
            continue
        cid = sid_to_cid.get(str(row.get("community_id")), str(row.get("community_id")))
        captured = str(row.get("snapshot_date") or "")
        if captured and captured > dates.get(cid, ""):
            dates[cid] = captured
    return dates


# ---------------------------------------------------------------------------
# 刷新状态持久化（price_refresh_status.json）
# ---------------------------------------------------------------------------

def load_refresh_status(data_path: Path | None = None) -> dict[str, dict]:
    """{community_id: 状态对象}; 缺失/损坏返回空表, 与读取侧归一化规则一致。"""
    from src.services.data_loader import _load_price_refresh_status

    return _load_price_refresh_status(Path(data_path) if data_path else DATA_DIR)


def save_refresh_status(data_path: Path, updates: dict[str, dict]) -> None:
    """合并写入每小区刷新状态; 原子替换, 不因单轮失败丢历史。"""
    data_path = Path(data_path)
    current = load_refresh_status(data_path)
    current.update(updates)
    _atomic_write(
        data_path / REFRESH_STATUS_FILE,
        json.dumps(current, ensure_ascii=False),
    )


# ---------------------------------------------------------------------------
# 服务内采集
# ---------------------------------------------------------------------------

async def run_refresh_once(
    plans: list[dict],
    snapshot_path: Path,
    backup_path: Path,
    data_path: Path,
    *,
    fetcher: Callable[..., CommunityFetchResult] | None = None,
    sleep_seconds: float = 1.2,
    today=None,
    mode: str = "all",
) -> dict:
    """在服务进程内采集并在循环结束后一次性发布; 取消时不发布不写状态。

    - 请求前与返回后各重查一次资格与绑定; 撤销收录/换绑的来源跳过且结果不落盘,
      在进度中计为已处理, 保证 processed 可达 total（R5）。
    - 发出请求且资格未变的来源, 其全部快照落盘（含过期价与 counts-only）;
      无新记录不改主快照（published=false）但仍保存刷新结果。
    """
    fetcher = fetcher or fetch_community_snapshots
    data_path = Path(data_path)
    run_id = job.get("startedAt") or _now_iso()
    outcomes: dict[str, dict] = {}
    fresh: list[dict] = []

    for plan_index, plan in enumerate(plans):
        if _cancel_requested:
            raise asyncio.CancelledError
        cid = plan["community_id"]
        entry: dict = {
            "community_id": cid,
            "outcome": None,
            "partial": False,
            "retained": False,
            "retained_reason": None,
            "retained_price_date": None,
            "price_updated": False,
            "counts_updated": False,
            "price_captured_at": None,
            "counts_captured_at": None,
            "sources": {},
        }
        outcomes[cid] = entry
        for source_index, sid in enumerate(plan["sources"]):
            if _cancel_requested:
                raise asyncio.CancelledError
            if not _still_collectible(data_path, cid, sid):
                entry["sources"][sid] = {
                    "outcome": "skipped", "reason": "ineligible",
                    "partial": False, "errors": []}
                continue
            result = await asyncio.to_thread(fetcher, sid, timeout=DEFAULT_FETCH_TIMEOUT)
            if _cancel_requested:
                raise asyncio.CancelledError
            if not _still_collectible(data_path, cid, sid):
                # 撤销收录或换绑: 本轮结果不落盘（R5）
                entry["sources"][sid] = {
                    "outcome": "skipped", "reason": "ineligible",
                    "partial": False, "errors": []}
                continue
            classification = _classify_fetch_result(result, today=today)
            entry["sources"][sid] = classification
            fresh.extend(asdict(snapshot) for snapshot in result.snapshots)
            if classification["counts"]:
                entry["counts_updated"] = True
                entry["counts_captured_at"] = classification["captured_at"]
            if (plan_index < len(plans) - 1 or source_index < len(plan["sources"]) - 1) and sleep_seconds:
                await asyncio.sleep(sleep_seconds)
        # 进度按主小区计（total=小区数, UI/统计按主小区去重）, 多来源小区不超总数
        job["processed"] += 1
        _summarize_plan(entry)

    # 合并发布: 主快照只在有新记录时原子替换一次; CSV 失败只警告（R4）
    old = _read_jsonl(backup_path)
    published = False
    warnings: list[str] = []
    total_rows = len(old)
    if fresh:
        job["phase"] = "merging"
        rows = merge_snapshot_rows(fresh, old)
        write_jsonl(snapshot_path, rows)
        published = True
        total_rows = len(rows)
        try:
            rewrite_csv(data_path, rows)
        except (OSError, ValueError) as exc:
            warnings.append(f"price_snapshots.csv 导出失败（主快照已发布）: {exc}")

    # retained: 未更新价格但主快照里保留了旧价格记录的小区（可与前三类重叠）
    retained_dates = _retained_price_dates(plans, old)
    for entry in outcomes.values():
        if entry["outcome"] == "skipped":
            continue
        retained_date = retained_dates.get(entry["community_id"])
        if retained_date:
            entry["retained"] = True
            entry["retained_price_date"] = retained_date
            if entry["outcome"] != "updated":
                entry["retained_reason"] = next(
                    (s["reason"] for s in entry["sources"].values() if s["reason"]),
                    entry["outcome"],
                )

    counts = {
        "updated": sum(1 for e in outcomes.values() if e["outcome"] == "updated"),
        "noData": sum(1 for e in outcomes.values() if e["outcome"] == "no_data"),
        "failed": sum(1 for e in outcomes.values() if e["outcome"] == "failed"),
        "skipped": sum(1 for e in outcomes.values() if e["outcome"] == "skipped"),
        "retained": sum(1 for e in outcomes.values() if e["retained"]),
    }
    job["okCount"] = counts["updated"]
    job["errorCount"] = counts["failed"]
    job["updated"] = counts["updated"]
    job["noData"] = counts["noData"]
    job["failed"] = counts["failed"]
    job["skipped"] = counts["skipped"]
    job["retained"] = counts["retained"]

    # 轮级终态（R3）: 全部成功 / 部分成功（有失败小区或小区内部分页失败）/
    # 全部失败 / 全部跳过（资格在轮内全部丢失）/ 无任何可用数据
    any_partial = any(e["partial"] for e in outcomes.values())
    if counts["updated"] and not counts["failed"] and not any_partial:
        round_outcome = "succeeded"
    elif counts["updated"]:
        round_outcome = "partial"
    elif counts["failed"]:
        round_outcome = "failed"
    elif counts["skipped"] and not counts["noData"]:
        round_outcome = "skipped"
    else:
        round_outcome = "no_data"

    # 刷新结果持久化（取消路径不会走到这里; R3: 页面重启后仍可看旧价保留原因）
    now_iso = _now_iso()
    save_refresh_status(data_path, {
        cid: {**entry, "mode": mode, "run_id": run_id, "updated_at": now_iso}
        for cid, entry in outcomes.items()
    })

    return {
        "outcome": round_outcome,
        "published": published,
        "fetched": len(fresh),
        "keptOld": (total_rows - len(fresh)) if published else 0,
        "total": total_rows,
        **counts,
        "warnings": warnings,
        "outcomes": outcomes,
    }


async def _watch_refresh(
    plans: list[dict], snapshot_path: Path, backup_path: Path, data_path: Path,
    *, mode: str,
) -> None:
    global _task
    try:
        job["result"] = await run_refresh_once(
            plans, snapshot_path, backup_path, data_path, mode=mode)
        job["phase"] = "done"
    except asyncio.CancelledError:
        job["phase"] = "cancelled"
        job["error"] = "任务已被终止(数据未改动)"
    except (OSError, ValueError, RuntimeError) as error:
        job["phase"] = "error"
        job["error"] = f"采集或合并快照失败: {error}"
    finally:
        _task = None
        job["running"] = False
        job["finishedAt"] = _now_iso()


async def start_refresh(limit: int = 0, mode: str = "all") -> tuple[bool, int, dict]:
    """启动刷新任务。mode=all 全量已收录小区, mode=missing 只补齐缺价小区。
    返回 (ok, http_status, body)。"""
    global _task, _cancel_requested
    if job["running"]:
        return False, 409, {"success": False, "error": "已有刷新任务在运行"}
    if mode not in ("all", "missing"):
        return False, 422, {"success": False, "error": "mode 必须是 all 或 missing"}

    limit = min(max(limit, 0), 500)

    plans = collectible_plans()
    if mode == "missing":
        plans = missing_plans(plans, load_price_snapshots())
    if not plans:
        message = "没有缺少价格的小区" if mode == "missing" else "没有可采集的已收录小区"
        return False, 409, {"success": False, "error": message}
    plans = plans[:limit] if limit > 0 else plans

    data_path = DATA_DIR
    snapshot_path = data_path / "price_snapshots.jsonl"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    backup_path = Path(str(snapshot_path).replace(".jsonl", f"_{stamp}.bak.jsonl"))
    if snapshot_path.exists():
        shutil.copyfile(snapshot_path, backup_path)

    job["running"] = True
    job["phase"] = "fetching"
    job["mode"] = mode
    job["total"] = len(plans)
    job["processed"] = 0
    job["okCount"] = 0
    job["errorCount"] = 0
    job["updated"] = 0
    job["noData"] = 0
    job["failed"] = 0
    job["skipped"] = 0
    job["retained"] = 0
    job["startedAt"] = _now_iso()
    job["finishedAt"] = None
    job["error"] = None
    job["result"] = None

    _cancel_requested = False
    _task = asyncio.create_task(
        _watch_refresh(plans, snapshot_path, backup_path, data_path, mode=mode))

    return True, 200, {
        "success": True,
        "data": {
            "total": len(plans),
            "mode": mode,
            "backupFile": backup_path.name if backup_path.exists() else None,
        },
    }


async def stop_refresh() -> tuple[bool, int, dict]:
    """终止当前任务 (数据不动)。返回 (ok, http_status, body)"""
    global _cancel_requested
    if not job["running"] or _task is None:
        return False, 409, {"success": False, "error": "没有运行中的刷新任务"}
    _cancel_requested = True
    _task.cancel()
    return True, 200, {"success": True, "data": {"message": "终止信号已发送"}}
