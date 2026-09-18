"""手动刷新价格快照

移植自源项目 web/src/app/api/refresh/route.ts。
POST   后台启动 scripts/fetch_tmsf_price_snapshot.py (全量小区 id, ?limit=N 为测试用)
GET    轮询任务进度
DELETE 终止当前任务

数据安全: 脚本只在全部抓完后一次性覆盖 price_snapshots.jsonl,
因此启动前先备份旧文件; 退出码 0 时把新记录与备份合并(新优先,
未抓到的小区保留旧价), 失败/中止时原文件未动。
"""

import asyncio
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.services.data_loader import DATA_DIR, load_communities

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # backend/housing-map
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "fetch_tmsf_price_snapshot.py"
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

_child: asyncio.subprocess.Process | None = None
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


def merge_snapshots(snapshot_path: Path, backup_path: Path) -> dict:
    """合并: 新记录在前, 按 community_id+price_type 去重, 未刷新到的小区保留旧价"""
    fresh = _read_jsonl(snapshot_path)
    old = _read_jsonl(backup_path)

    def key_of(r: dict) -> str:
        return f"{r.get('community_id')}|{r.get('price_type')}"

    seen = {key_of(r) for r in fresh}
    kept = [r for r in old if key_of(r) not in seen]
    rows = fresh + kept
    # JSON.stringify 输出原始 UTF-8 字符 (非 ASCII 不转义)
    snapshot_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    return {"fetched": len(fresh), "keptOld": len(kept), "rows": rows}


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


async def _watch_process(
    proc: asyncio.subprocess.Process,
    snapshot_path: Path,
    backup_path: Path,
    data_path: Path,
) -> None:
    """消费子进程输出并按退出码落盘 (对应 TS child.stdout/stderr/exit 回调)"""
    global _child, _cancel_requested
    assert proc.stdout is not None and proc.stderr is not None

    stderr_tail = ""

    async def pump_stderr() -> None:
        nonlocal stderr_tail
        # 脚本 stderr 仅在异常时输出, 保留最后一段用于排错
        async for chunk in proc.stderr:
            stderr_tail += chunk.decode("utf-8", errors="replace")

    async def pump_stdout() -> None:
        # 行前缀 [ok]/[error] 计数
        async for chunk in proc.stdout:
            for line in chunk.decode("utf-8", errors="replace").split("\n"):
                if line.startswith("[ok]"):
                    job["processed"] += 1
                    job["okCount"] += 1
                elif line.startswith("[error]"):
                    job["processed"] += 1
                    job["errorCount"] += 1

    await asyncio.gather(pump_stdout(), pump_stderr())
    code = await proc.wait()

    _child = None
    job["finishedAt"] = _now_iso()
    if code == 0:
        job["phase"] = "merging"
        try:
            merged = merge_snapshots(snapshot_path, backup_path)
            rewrite_csv(data_path, merged["rows"])
            job["result"] = {
                "fetched": merged["fetched"],
                "keptOld": merged["keptOld"],
                "total": len(merged["rows"]),
            }
            job["phase"] = "done"
        except (OSError, ValueError) as exc:
            job["phase"] = "error"
            job["error"] = f"合并快照失败: {exc}"
    elif _cancel_requested:
        job["phase"] = "cancelled"
        job["error"] = "任务已被终止(数据未改动)"
    else:
        job["phase"] = "error"
        job["error"] = f"采集脚本退出码 {code}(数据未改动, 备份 {backup_path.name})"
    if stderr_tail:
        job["error"] = stderr_tail[-500:]
    job["running"] = False


async def start_refresh(limit: int) -> tuple[bool, int, dict]:
    """启动刷新任务。返回 (ok, http_status, body)"""
    global _child, _cancel_requested
    if job["running"]:
        return False, 409, {"success": False, "error": "已有刷新任务在运行"}

    limit = min(max(limit, 0), 500)

    ids = [c.get("community_id") for c in load_communities()]
    ids = [cid for cid in ids if cid]  # TS filter(Boolean)
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

    args: list[str] = []
    for cid in targets:
        args.extend(["--community-id", cid])
    args.extend(["--output-dir", str(data_path), "--sleep", "1.2"])

    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    try:
        _cancel_requested = False
        _child = await asyncio.create_subprocess_exec(
            sys.executable, str(SCRIPT_PATH), *args,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except (OSError, ValueError) as exc:
        _child = None
        job["running"] = False
        job["phase"] = "error"
        job["finishedAt"] = _now_iso()
        job["error"] = f"无法启动采集进程: {exc}"
        return False, 500, {"success": False, "error": job["error"]}

    asyncio.create_task(
        _watch_process(_child, snapshot_path, backup_path, data_path)
    )

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
    if not job["running"] or _child is None:
        return False, 409, {"success": False, "error": "没有运行中的刷新任务"}
    _cancel_requested = True
    _child.kill()
    return True, 200, {"success": True, "data": {"message": "终止信号已发送"}}
