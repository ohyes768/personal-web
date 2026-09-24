"""手动刷新价格快照

移植自源项目 web/src/app/api/refresh/route.ts。
POST   后台启动服务内采集任务 (仅住宅小区 id, ?limit=N 为测试用)
GET    轮询任务进度
DELETE 终止当前任务

数据安全: 任务只在全部抓完后一次性覆盖 price_snapshots.jsonl，
因此启动前先备份旧文件; 成功时把新记录与备份合并(新优先,
未抓到的小区保留旧价), 失败/中止时原文件未动。
"""

import asyncio
from dataclasses import asdict
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from src.services.community_filters import is_real_community
from src.services.data_loader import DATA_DIR, load_communities
from src.services.tmsf_fetcher import CommunityFetchResult, fetch_community_snapshots

DEFAULT_FETCH_TIMEOUT = 20
CSV_FIELDS = [
    "community_id", "community_name", "snapshot_date", "source", "price_type",
    "avg_price", "listing_count", "deal_count", "sample_count",
    "min_price", "max_price", "source_url", "confidence_score", "raw_payload", "crawled_at",
]

# 模块级单例: 本地/容器单进程部署足够
job: dict = {
    "running": False,
    "phase": "idle",  # idle | fetching | merging | done | error | cancelled
    "total": 0,
    "processed": 0,
    "okCount": 0,
    "errorCount": 0,
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


def write_jsonl(snapshot_path: Path, rows: list[dict]) -> None:
    snapshot_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )


def rewrite_csv(data_path: Path, rows: list[dict]) -> None:
    """与脚本 write_outputs 保持同字段/utf-8-sig, 供人工查看"""
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


def select_refresh_targets(communities: list[dict]) -> list[str]:
    return [
        str(community["community_id"])
        for community in communities
        if community.get("community_id") and is_real_community(community)
    ]


async def run_refresh_once(
    targets: list[str],
    snapshot_path: Path,
    backup_path: Path,
    data_path: Path,
    *,
    fetcher: Callable[..., CommunityFetchResult] = fetch_community_snapshots,
    sleep_seconds: float = 1.2,
) -> dict:
    """在服务进程内采集并在完整循环后写盘；中断前绝不改原快照。"""
    fresh: list[dict] = []
    failed = 0
    for index, community_id in enumerate(targets):
        if _cancel_requested:
            raise asyncio.CancelledError
        result = await asyncio.to_thread(fetcher, community_id, timeout=DEFAULT_FETCH_TIMEOUT)
        job["processed"] += 1
        if result.snapshots:
            fresh.extend(asdict(snapshot) for snapshot in result.snapshots)
            job["okCount"] += 1
        else:
            failed += 1
            job["errorCount"] += 1
        if index < len(targets) - 1 and sleep_seconds:
            await asyncio.sleep(sleep_seconds)

    if not fresh:
        raise RuntimeError("no verified price collected from TMSF")

    job["phase"] = "merging"
    old = _read_jsonl(backup_path)
    rows = merge_snapshot_rows(fresh, old)
    write_jsonl(snapshot_path, rows)
    rewrite_csv(data_path, rows)
    return {"fetched": len(fresh), "keptOld": len(rows) - len(fresh), "total": len(rows), "failed": failed}


async def _watch_refresh(
    targets: list[str], snapshot_path: Path, backup_path: Path, data_path: Path
) -> None:
    global _task
    try:
        job["result"] = await run_refresh_once(targets, snapshot_path, backup_path, data_path)
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


async def start_refresh(limit: int) -> tuple[bool, int, dict]:
    """启动刷新任务。返回 (ok, http_status, body)"""
    global _task, _cancel_requested
    if job["running"]:
        return False, 409, {"success": False, "error": "已有刷新任务在运行"}

    limit = min(max(limit, 0), 500)

    ids = select_refresh_targets(load_communities())
    if len(ids) == 0:
        return False, 500, {"success": False, "error": "小区清单为空, 无法刷新"}
    targets = ids[:limit] if limit > 0 else ids

    data_path = DATA_DIR
    snapshot_path = data_path / "price_snapshots.jsonl"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    backup_path = Path(str(snapshot_path).replace(".jsonl", f"_{stamp}.bak.jsonl"))
    if snapshot_path.exists():
        shutil.copyfile(snapshot_path, backup_path)

    job["running"] = True
    job["phase"] = "fetching"
    job["total"] = len(targets)
    job["processed"] = 0
    job["okCount"] = 0
    job["errorCount"] = 0
    job["startedAt"] = _now_iso()
    job["finishedAt"] = None
    job["error"] = None
    job["result"] = None

    _cancel_requested = False
    _task = asyncio.create_task(_watch_refresh(targets, snapshot_path, backup_path, data_path))

    return True, 200, {
        "success": True,
        "data": {
            "total": len(targets),
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
