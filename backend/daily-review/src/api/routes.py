"""
API 路由（prefix /api/review）
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from src import db, llm
from src.config import get_dsh_dir, get_ingest_token
from src.parser.session import parse_session_file

from src.parser.usage import parse_usage_ledger

# 杂项桶：家目录 / 默认工作区 / task-board 快照，非真实项目，项目维度直接隐藏
HIDDEN_BUCKETS = {"home-ohyes768", "default-workspace", "task-board"}
from src.parser.taskboard import parse_git_commits, parse_ledger

router = APIRouter(prefix="/api/review")


# ---------- models ----------


class RecordIn(BaseModel):
    """结构化记录（采集器源头脱敏后的摘要，不含原文）。"""

    machine: str = Field(..., description="来源机器标识，如 windows / nas")
    kind: Literal["session", "task_board", "git_commit"]
    project: str = Field("", description="项目/仓库名")
    external_id: str = Field(..., description="来源侧唯一 ID（session uuid / commit sha / ledger rev）")
    session_id: str = ""
    title: str = ""
    summary_text: str = Field("", description="做了什么的要点摘要文本")
    started_at: str = Field("", description="ISO 时间")
    ended_at: str = ""
    payload: dict = Field(default_factory=dict, description="结构化补充信息（计数等，不含原文）")


class RecordsBatch(BaseModel):
    records: list[RecordIn]


class SyncResult(BaseModel):
    sessions_parsed: int
    sessions_skipped: int
    ledger_parsed: bool
    records_inserted: int
    usage_upserted: int = 0
    errors: list[str]


class UsageIn(BaseModel):
    """单机单日单 provider/model 的 LLM 用量日汇总。"""

    machine: str
    date: str = Field(..., description="YYYY-MM-DD")
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    calls: int = 0
    cost: float = 0.0


class UsageBatch(BaseModel):
    usage: list[UsageIn]


class UsageResult(BaseModel):
    received: int
    upserted: int


class ReportGenerateIn(BaseModel):
    report_type: Literal["daily", "weekly"]
    period_start: str | None = Field(None, description="YYYY-MM-DD；daily 默认今天，weekly 默认本周一")
    period_end: str | None = Field(None, description="YYYY-MM-DD；daily 默认同 period_start，weekly 默认本周日")


class BatchResult(BaseModel):
    received: int
    inserted: int
    skipped: int


# ---------- helpers ----------


def _require_ingest_token(x_ingest_token: str | None) -> None:
    """配置了 INGEST_TOKEN 才启用鉴权比对；未配置则 ingest 一律 503（fail closed）。"""
    expected = get_ingest_token()
    if not expected:
        raise HTTPException(status_code=503, detail="ingest disabled: INGEST_TOKEN not configured")
    if x_ingest_token != expected:
        raise HTTPException(status_code=401, detail="invalid X-Ingest-Token")


def _record_to_out(row) -> dict:
    return {
        "id": row["id"],
        "machine": row["machine"],
        "kind": row["kind"],
        "project": row["project"],
        "external_id": row["external_id"],
        "session_id": row["session_id"],
        "title": row["title"],
        "summary_text": row["summary_text"],
        "started_at": row["started_at"],
        "ended_at": row["ended_at"],
        "payload": json.loads(row["payload_json"] or "{}"),
        "ingested_at": row["ingested_at"],
    }


def normalize_project(project: str) -> str:
    """项目名归一化：Windows 会话桶/cwd 会带盘符路径，同一仓库出现多种写法。

    - 路径形态（含 / 或 \\）：取最后一段  f:/personal-projects/personal-web → personal-web
    - 盘符虚线形态（首段是单字母盘符）：剥掉盘符段、虚线当路径分隔、取末段
      F-personal-projects-personal-web → personal-web
      F-personal-projects-esp32-s3 → esp32-s3（仓库名里的连字符不受影响）
    - 其余（本就是纯项目名，如 daily-review / stock-info-dingding）原样保留
    """
    if not project:
        return project
    p = project.replace("\\", "/").strip().strip("/")
    if "/" in p:
        return p.split("/")[-1]
    parts = p.split("-")
    if len(parts) > 1 and len(parts[0]) == 1 and parts[0].isalpha():
        # 剥掉盘符段后，虚线当路径分隔；仓库名里的连字符不可恢复，
        # 但实测取末两段拼回即稳定命中仓库根目录名（esp32-s3 / personal-web / datagen-dev）
        rest = parts[1:]
        tail = rest[-2:] if len(rest) >= 2 else rest
        return "-".join(tail)
    return p


def _insert_record(item: RecordIn, machine: str | None = None) -> bool:
    return db.upsert_record(
        {
            "id": str(uuid.uuid4()),
            "machine": machine or item.machine,
            "kind": item.kind,
            "project": normalize_project(item.project),
            "external_id": item.external_id,
            "session_id": item.session_id,
            "title": item.title,
            "summary_text": item.summary_text,
            "started_at": item.started_at,
            "ended_at": item.ended_at,
            "payload": item.payload,
        }
    )


# ---------- ingest ----------


@router.post("/ingest/records", response_model=BatchResult)
def ingest_records(body: RecordsBatch, x_ingest_token: str | None = Header(default=None)):
    """批量结构化记录 upsert，按 UNIQUE(machine,kind,external_id) 幂等。"""
    _require_ingest_token(x_ingest_token)
    inserted = 0
    for item in body.records:
        if _insert_record(item):
            inserted += 1
    db.log_ingest(
        machine=body.records[0].machine if body.records else "-",
        batch_id=f"http:{body.records[0].external_id if body.records else '-'}",
        record_count=len(body.records),
        status="ok",
    )
    return {"received": len(body.records), "inserted": inserted, "skipped": len(body.records) - inserted}


@router.post("/ingest/usage", response_model=UsageResult)
def ingest_usage(body: UsageBatch, x_ingest_token: str | None = Header(default=None)):
    """批量 LLM 用量日汇总 upsert，按 UNIQUE(machine,date,provider,model) 幂等，重跑覆盖。"""
    _require_ingest_token(x_ingest_token)
    rows = [u.model_dump() for u in body.usage]
    upserted = db.upsert_usage(rows)
    db.log_ingest(
        machine=rows[0]["machine"] if rows else "-",
        batch_id=f"usage:{rows[0]['date'] if rows else '-'}",
        record_count=len(rows),
        status="ok",
    )
    return {"received": len(rows), "upserted": upserted}


@router.post("/ingest/sync-nas", response_model=SyncResult)
def sync_nas():
    """解析 NAS 只读挂载 ~/.dsh 下未处理的会话 / ledger（文件级游标防重复）。"""
    dsh_dir = get_dsh_dir()
    if dsh_dir is None:
        raise HTTPException(status_code=503, detail="DAILY_REVIEW_DSH_DIR not configured; NAS sync skipped")
    if not dsh_dir.is_dir():
        raise HTTPException(status_code=503, detail=f"DSH dir not found: {dsh_dir}")

    errors: list[str] = []
    sessions_parsed = sessions_skipped = 0
    inserted = 0

    sessions_root = dsh_dir / "sessions"
    if sessions_root.is_dir():
        for session_file in sorted(sessions_root.glob("*/*/session.v4.jsonl.zstd")):
            rel = str(session_file.relative_to(dsh_dir))
            if db.file_already_done("nas", rel):
                sessions_skipped += 1
                continue
            rec = parse_session_file(session_file)
            if rec is None:
                errors.append(f"parse failed: {rel}")
                continue
            rec["machine"] = "nas"
            if db.upsert_record(rec):
                inserted += 1
            sessions_parsed += 1
            db.log_ingest("nas", rel, 1, "ok")

    ledger_parsed = False
    ledger_path = dsh_dir / "task-board" / "ledger-v2.json"
    if ledger_path.is_file():
        ledger_key = "task-board/ledger-v2.json"
        try:
            mtime = ledger_path.stat().st_mtime
        except OSError:
            mtime = 0
        cursor = f"{ledger_key}:{int(mtime)}"
        if not db.file_already_done("nas", cursor):
            rec = parse_ledger(ledger_path, machine="nas")
            if rec is None:
                errors.append("ledger parse failed")
            else:
                if db.upsert_record(rec):
                    inserted += 1
                ledger_parsed = True
                db.log_ingest("nas", cursor, 1, "ok")

    usage_upserted = 0
    usage_ledger = dsh_dir / "dsh-usage" / "usage-ledger.json"
    if usage_ledger.is_file():
        usage_rows = parse_usage_ledger(usage_ledger, machine="nas")
        if usage_rows:
            usage_upserted = db.upsert_usage(usage_rows)

    return {
        "sessions_parsed": sessions_parsed,
        "sessions_skipped": sessions_skipped,
        "ledger_parsed": ledger_parsed,
        "records_inserted": inserted,
        "usage_upserted": usage_upserted,
        "errors": errors,
    }


# ---------- 查询 ----------


@router.get("/today")
def today(date: str | None = None):
    """两机活动合并时间线（按 started_at 排序，含 machine 标注）。"""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    rows = db.get_conn().execute(
        """
        SELECT * FROM records
        WHERE substr(started_at, 1, 10) = ?
        ORDER BY started_at ASC
        """,
        (date,),
    ).fetchall()
    return {"date": date, "items": [_record_to_out(r) for r in rows]}


@router.get("/projects")
def projects(days: int = 7):
    """按 project 聚合窗口内活跃度（days=0 表示全部）。

    排序按窗口内活动总量降序；杂项桶（家目录/默认工作区/task-board 快照）直接隐藏。
    每项目附近 14 天逐日活动计数（前端迷你条形图）。
    """
    window_start = ""
    if days > 0:
        window_start = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    where = "WHERE substr(started_at, 1, 10) >= ?" if window_start else ""
    args = (window_start,) if window_start else ()

    rows = db.get_conn().execute(
        f"""
        SELECT project,
               MAX(started_at) AS last_activity,
               SUM(CASE WHEN kind='session' THEN 1 ELSE 0 END) AS session_count,
               SUM(CASE WHEN kind='git_commit' THEN 1 ELSE 0 END) AS commit_count,
               SUM(CASE WHEN kind='task_board' THEN 1 ELSE 0 END) AS task_board_count,
               COUNT(DISTINCT substr(started_at, 1, 10)) AS active_days,
               COUNT(*) AS total_count
        FROM records
        {where}
        GROUP BY project
        ORDER BY total_count DESC
        """,
        args,
    ).fetchall()

    # 近 14 天逐日计数（与窗口无关，固定给迷你条形图）
    bars: dict[str, list[dict]] = {}
    for row in rows:
        day_rows = db.get_conn().execute(
            """
            SELECT substr(started_at, 1, 10) AS day, COUNT(*) AS n FROM records
            WHERE project = ? AND substr(started_at, 1, 10) >= ?
            GROUP BY day ORDER BY day
            """,
            (row["project"], (datetime.now() - timedelta(days=13)).strftime("%Y-%m-%d")),
        ).fetchall()
        by_day = {r["day"]: r["n"] for r in day_rows}
        seq = []
        d = datetime.now() - timedelta(days=13)
        for _ in range(14):
            key = d.strftime("%Y-%m-%d")
            seq.append({"day": key, "count": by_day.get(key, 0)})
            d += timedelta(days=1)
        bars[row["project"]] = seq

    out = []
    for r in rows:
        project = r["project"] or "(unknown)"
        if project in HIDDEN_BUCKETS:
            continue
        summary_sql = """
            SELECT title, summary_text, started_at, kind, machine FROM records
            WHERE project = ?"""
        summary_args = (project,)
        if window_start:
            summary_sql += " AND substr(started_at, 1, 10) >= ?"
            summary_args += (window_start,)
        summaries = db.get_conn().execute(
            summary_sql + " ORDER BY started_at DESC LIMIT 5", summary_args
        ).fetchall()
        out.append(
            {
                "project": project,
                "last_activity": r["last_activity"],
                "session_count": r["session_count"],
                "commit_count": r["commit_count"],
                "task_board_count": r["task_board_count"],
                "active_days": r["active_days"],
                "total_count": r["total_count"],
                "daily_counts": bars.get(project, []),
                "recent_summaries": [dict(s) for s in summaries],
            }
        )
    return {"projects": out, "window_days": days}


# ---------- usage ----------


def _usage_summary_response(rows, start: str, end: str) -> dict:
    fields = ("input_tokens", "output_tokens", "cache_read_tokens",
              "cache_write_tokens", "reasoning_tokens", "calls", "cost")

    def agg(rs):
        out = {f: 0 for f in fields}
        for r in rs:
            for f in fields:
                out[f] += r[f]
        out["cost"] = round(out["cost"], 4)
        return out

    return {
        "start": start,
        "end": end,
        "totals": agg(rows),
        "by_day_machine": [
            {**agg([r for r in rows if r["date"] == d and r["machine"] == m]), "date": d, "machine": m}
            for d, m in sorted({(r["date"], r["machine"]) for r in rows})
        ],
        "by_model": [
            {**agg([r for r in rows if (r["provider"], r["model"], r["machine"]) == k]),
             "provider": k[0], "model": k[1], "machine": k[2]}
            for k in sorted({(r["provider"], r["model"], r["machine"]) for r in rows})
        ],
    }


@router.get("/usage")
def get_usage(
    date: str | None = None,
    start: str | None = None,
    end: str | None = None,
    days: int | None = None,
):
    """LLM token/cost 查询：?date=YYYY-MM-DD 或 ?start=&end=（含首尾）；?days=N 最近 N 天（默认 7）。"""
    try:
        if date:
            datetime.strptime(date, "%Y-%m-%d")
            s = e = date
        elif start and end:
            s = datetime.strptime(start, "%Y-%m-%d").date()
            e = datetime.strptime(end, "%Y-%m-%d").date()
            if e < s:
                raise HTTPException(status_code=400, detail="end earlier than start")
            s, e = s.isoformat(), e.isoformat()
        else:
            e = datetime.now().date()
            s = e - timedelta(days=(days or 7) - 1)
            s, e = s.isoformat(), e.isoformat()
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    rows = db.get_conn().execute(
        "SELECT * FROM usage_daily WHERE date >= ? AND date <= ?", (s, e)
    ).fetchall()
    return _usage_summary_response([dict(r) for r in rows], s, e)


# ---------- reports ----------


@router.get("/reports")
def list_reports(type: str | None = None):
    """报告列表（摘要首段）。"""
    sql = "SELECT * FROM reports"
    params: tuple = ()
    if type in ("daily", "weekly"):
        sql += " WHERE report_type = ?"
        params = (type,)
    sql += " ORDER BY period_start DESC"
    rows = db.get_conn().execute(sql, params).fetchall()
    return {
        "reports": [
            {
                "id": r["id"],
                "report_type": r["report_type"],
                "period_start": r["period_start"],
                "period_end": r["period_end"],
                "generated_at": r["generated_at"],
                "status": r["status"],
                "summary_first_paragraph": (r["summary_md"] or "").split("\n\n")[0],
            }
            for r in rows
        ]
    }


@router.get("/reports/{report_id}")
def report_detail(report_id: str):
    row = db.get_conn().execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="report not found")
    record_ids = json.loads(row["record_ids_json"] or "[]")
    records = []
    if record_ids:
        marks = ",".join("?" for _ in record_ids)
        rec_rows = db.get_conn().execute(
            f"SELECT * FROM records WHERE id IN ({marks}) ORDER BY started_at ASC", record_ids
        ).fetchall()
        records = [_record_to_out(r) for r in rec_rows]
    return {
        "id": row["id"],
        "report_type": row["report_type"],
        "period_start": row["period_start"],
        "period_end": row["period_end"],
        "generated_at": row["generated_at"],
        "status": row["status"],
        "summary_md": row["summary_md"],
        "records": records,
    }


def _period_range(report_type: str, period_start: str | None, period_end: str | None) -> tuple[str, str]:
    """daily/weekly 的起止日（含首尾）。

    默认回顾刚过去的一段：daily=昨天；weekly=上周一~上周日
    （调度在早上生成，回顾的是完整结束的周期，不是进行中的今天/本周）。
    """
    today = datetime.now().date()
    if period_start:
        start = datetime.strptime(period_start, "%Y-%m-%d").date()
    elif report_type == "weekly":
        start = today - timedelta(days=today.weekday()) - timedelta(days=7)
    else:
        start = today - timedelta(days=1)
    if period_end:
        end = datetime.strptime(period_end, "%Y-%m-%d").date()
    elif report_type == "weekly":
        end = start + timedelta(days=6)
    else:
        end = start
    if end < start:
        raise HTTPException(status_code=400, detail="period_end earlier than period_start")
    return start.isoformat(), end.isoformat()


def _usage_prompt_lines(start: str, end: str) -> str:
    """period 内两机 usage 汇总文本；无数据返回空串。"""
    rows = db.get_conn().execute(
        "SELECT * FROM usage_daily WHERE date >= ? AND date <= ?", (start, end)
    ).fetchall()
    if not rows:
        return ""
    resp = _usage_summary_response([dict(r) for r in rows], start, end)
    t = resp["totals"]
    per_machine = "；".join(
        f"{d['machine']} ${d['cost']}（{d['calls']} 次）" for d in resp["by_day_machine"]
    )
    models = "；".join(f"{m['provider']}/{m['model']}" for m in resp["by_model"])
    return (
        f"\n## LLM 用量（{start}~{end}，两机合计）\n"
        f"input {t['input_tokens']}、output {t['output_tokens']}、"
        f"cache_read {t['cache_read_tokens']}、cache_write {t['cache_write_tokens']}、"
        f"reasoning {t['reasoning_tokens']} tokens；调用 {t['calls']} 次；成本 ${t['cost']}。"
        f"分机器：{per_machine}。模型：{models}。"
        "\n请在报告末尾加一节 \"## LLM 消耗\" 概述上述用量与成本。\n"
    )


def _build_prompt(records: list, report_type: str, start: str, end: str) -> str:
    lines = [
        f"以下是 {start} 至 {end} 的结构化工作记录（两台机器合并，已脱敏，仅摘要不含原文）。",
        f"请用中文写一份{'日报' if report_type == 'daily' else '周报'} markdown（不要一级标题）：\n"
        "先一行引用块概览（几个项目、重点）；然后输出一张 markdown 表格：\n"
        "| 项目 | ✅ 完成 | 🔄 进行中 | 📋 待办 |\n|---|---|---|---|\n"
        "| <项目名> | 事项1；事项2 | 事项 | 事项 |\n"
        "硬性规则：\n"
        "1. 极简：每格最多 2 条，每条不超过 20 字（commit 号不计入字数），多条用「；」分隔；"
        "完成项只留该周期最重要的，其余靠记录回溯；\n"
        "2. 每条事项末尾用（win）或（nas）标注来源机器（Windows 记为 win）；两机共同推进的事项才合并，来源标（win+nas）；\n"
        "3. 没有证据的格子留空，禁止推测、禁止编造；\n"
        "4. 同一任务的多次推进合并成一条叙述（合并时保留来源标注）；\n"
        "5. 表格后加一节 \"## 明日建议\"（周报为 \"## 下周建议\"）只基于确凿待办列 1-3 条。\n"
        "记录：",
    ]
    for r in records:
        lines.append(
            f"- [{r['started_at']}] [{r['machine']}] [{r['kind']}] {r['project']}: "
            f"{r['title']} — {r['summary_text'][:300]}"
        )
    if len(records) == 0:
        lines.append("（该时间段无记录）")
    lines.append(_usage_prompt_lines(start, end))
    return "\n".join(lines)


@router.post("/reports/generate")
def generate_report(body: ReportGenerateIn):
    """同步生成 LLM 日报/周报；无 DEEPSEEK_API_KEY 返回明确错误；失败落 failed。"""
    if not llm.get_deepseek_api_key():
        raise HTTPException(status_code=503, detail="DEEPSEEK_API_KEY not configured")
    start, end = _period_range(body.report_type, body.period_start, body.period_end)

    rows = db.get_conn().execute(
        """
        SELECT * FROM records
        WHERE substr(started_at, 1, 10) >= ? AND substr(started_at, 1, 10) <= ?
        ORDER BY started_at ASC
        """,
        (start, end),
    ).fetchall()
    record_ids = [r["id"] for r in rows]

    # 幂等：同一类型同一 period_start 重复生成则覆盖
    existing = db.get_conn().execute(
        "SELECT id FROM reports WHERE report_type=? AND period_start=?", (body.report_type, start)
    ).fetchone()
    report_id = existing["id"] if existing else str(uuid.uuid4())
    db.get_conn().execute(
        """
        INSERT INTO reports (id, report_type, period_start, period_end, generated_at,
                             summary_md, record_ids_json, status)
        VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(report_type, period_start)
        DO UPDATE SET period_end=excluded.period_end, generated_at=excluded.generated_at,
                      summary_md=excluded.summary_md, record_ids_json=excluded.record_ids_json,
                      status=excluded.status
        """,
        (report_id, body.report_type, start, end, db.now_iso(), "", json.dumps(record_ids), "pending"),
    )
    db.get_conn().commit()

    try:
        summary_md = llm.generate_summary(_build_prompt(rows, body.report_type, start, end))
    except Exception as e:  # httpx / runtime 错误统一落 failed
        db.get_conn().execute(
            "UPDATE reports SET status='failed', summary_md=? WHERE id=?",
            (f"生成失败：{e}", report_id),
        )
        db.get_conn().commit()
        raise HTTPException(status_code=502, detail=f"LLM generation failed: {e}")

    db.get_conn().execute(
        "UPDATE reports SET status='done', summary_md=?, generated_at=? WHERE id=?",
        (summary_md, db.now_iso(), report_id),
    )
    db.get_conn().commit()
    return {
        "id": report_id,
        "report_type": body.report_type,
        "period_start": start,
        "period_end": end,
        "status": "done",
        "record_count": len(record_ids),
    }


@router.get("/health")
def health():
    conn_ok = True
    try:
        db.get_conn().execute("SELECT 1")
    except Exception:
        conn_ok = False
    return {"status": "ok" if conn_ok else "degraded", "db": conn_ok}
