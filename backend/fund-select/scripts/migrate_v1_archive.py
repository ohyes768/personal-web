"""v1 夏普榜单历史导出存档 → 验证 → 删除（11-13-sharpe-board-v2-rules 阶段 6）

背景：v2 上线后不再发布 v1 周榜，历史 96 周（157 只 / 9264 条观测）不再影响
榜单视图。用户确认「先导出存档，再删除」。本脚本只动 v1 的两张表，其它表零影响。

三阶段：
  1. 导出：weeks（全 status）+ 关联 observations → JSON + SQL + manifest(sha256)
  2. 验证：重读比对行数/哈希；临时 SQLite 库重放 SQL 比对行数
  3. 删除：**仅 `--apply` 执行**；单事务，先删 observations 再删 weeks

默认 dry-run，不带 --apply 绝不做破坏性操作。

用法（容器内，cwd=backend/fund-select）：
    python scripts/migrate_v1_archive.py                 # dry-run：导出+验证+打印将删行数
    python scripts/migrate_v1_archive.py --apply         # 人工确认后执行删除
    python scripts/migrate_v1_archive.py --db /path.db  # 指定库（测试用）

存档目录：data/archive/（不入 git），文件名带时间戳，多次执行不覆盖。
恢复：sqlite3 /path/funds.db < data/archive/sharpe_board_v1_<ts>.sql
"""
import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from src.db.models import SharpeBoardObservation, SharpeBoardWeek  # noqa: E402
from src.db.session import SessionLocal  # noqa: E402
from src.utils.config import DATA_DIR, get_database_url  # noqa: E402

V1 = "v1"
ARCHIVE_DIR = DATA_DIR / "archive"


def _now_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _row_to_dict(row) -> dict:
    """SQLAlchemy ORM 行 → 可 JSON 序列化 dict（日期转 ISO）。"""
    out = {}
    for col in row.__table__.columns:
        v = getattr(row, col.name)
        if isinstance(v, datetime):
            out[col.name] = v.isoformat()
        elif hasattr(v, "isoformat"):
            out[col.name] = v.isoformat()
        else:
            out[col.name] = v
    return out


def _sql_literal(v) -> str:
    """Python 值 → SQLite INSERT 字面量。"""
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return repr(v)
    return "'" + str(v).replace("'", "''") + "'"


def _insert_sql(table: str, row: dict) -> str:
    cols = ", ".join(row)
    vals = ", ".join(_sql_literal(v) for v in row.values())
    return f"INSERT INTO {table} ({cols}) VALUES ({vals});"


def export_v1(db: Session, stamp: str, *, archive_dir: Path | None = None) -> dict:
    """阶段 1：导出 v1 周批次与观测，写 JSON + SQL + manifest。

    archive_dir 可注入（测试用 tmp_path），默认 DATA_DIR/archive。
    """
    out_dir = archive_dir or ARCHIVE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    weeks = db.execute(
        select(SharpeBoardWeek).where(SharpeBoardWeek.profile_version == V1)
        .order_by(SharpeBoardWeek.id.asc())
    ).scalars().all()
    week_dicts = [_row_to_dict(w) for w in weeks]
    week_ids = [w["id"] for w in week_dicts]
    obs: list[dict] = []
    if week_ids:
        obs_rows = db.execute(
            select(SharpeBoardObservation)
            .where(SharpeBoardObservation.week_id.in_(week_ids))
            .order_by(SharpeBoardObservation.id.asc())
        ).scalars().all()
        obs = [_row_to_dict(o) for o in obs_rows]

    payload = {"weeks": week_dicts, "observations": obs}
    json_bytes = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":")).encode("utf-8")
    sha256 = hashlib.sha256(json_bytes).hexdigest()

    json_path = out_dir / f"sharpe_board_v1_{stamp}.json"
    sql_path = out_dir / f"sharpe_board_v1_{stamp}.sql"
    manifest_path = out_dir / f"sharpe_board_v1_{stamp}.manifest.json"
    json_path.write_bytes(json_bytes)
    sql_lines = ["BEGIN;"]
    sql_lines += [_insert_sql("sharpe_board_weeks", w) for w in week_dicts]
    sql_lines += [_insert_sql("sharpe_board_observations", o) for o in obs]
    sql_lines.append("COMMIT;")
    sql_path.write_text("\n".join(sql_lines) + "\n", encoding="utf-8")
    manifest = {
        "exported_at": datetime.now(UTC).isoformat(),
        "database_url": get_database_url(),
        "profile_version": V1,
        "weeks": len(week_dicts),
        "observations": len(obs),
        "sha256_payload": sha256,
        "json_file": json_path.name,
        "sql_file": sql_path.name,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"manifest": manifest, "json_path": json_path,
            "sql_path": sql_path, "manifest_path": manifest_path,
            "payload": payload}


def verify_export(art: dict) -> None:
    """阶段 2：重读 JSON 比对哈希；临时库重放 SQL 比对行数。"""
    m = art["manifest"]
    raw = art["json_path"].read_bytes()
    assert hashlib.sha256(raw).hexdigest() == m["sha256_payload"], "JSON 哈希不一致"
    payload = json.loads(raw)
    assert len(payload["weeks"]) == m["weeks"], "weeks 行数不一致"
    assert len(payload["observations"]) == m["observations"], "observations 行数不一致"

    tmp = sqlite3.connect(":memory:")
    try:
        # 建最小表结构供 INSERT 重放（只声明被导出的列，SQLite 宽松类型）
        cols_w = list(payload["weeks"][0]) if payload["weeks"] else []
        cols_o = list(payload["observations"][0]) if payload["observations"] else []
        # 空存档也建占位表，让 INSERT 为空的 SQL 重放不至于因表不存在报错
        tmp.execute(f"CREATE TABLE sharpe_board_weeks ({', '.join(cols_w) or 'id INTEGER'})")
        tmp.execute(f"CREATE TABLE sharpe_board_observations ({', '.join(cols_o) or 'id INTEGER'})")
        tmp.executescript(art["sql_path"].read_text(encoding="utf-8"))
        n_w = tmp.execute("SELECT COUNT(*) FROM sharpe_board_weeks").fetchone()[0]
        n_o = tmp.execute("SELECT COUNT(*) FROM sharpe_board_observations").fetchone()[0]
        assert n_w == m["weeks"], f"SQL 重放 weeks {n_w} != {m['weeks']}"
        assert n_o == m["observations"], f"SQL 重放 observations {n_o} != {m['observations']}"
    finally:
        tmp.close()


def delete_v1(db: Session) -> dict:
    """阶段 3：单事务删除 v1 观测与周批次（先子后父）。"""
    weeks = db.execute(
        select(SharpeBoardWeek).where(SharpeBoardWeek.profile_version == V1)
    ).scalars().all()
    ids = [w.id for w in weeks]
    n_obs = 0
    try:
        if ids:
            n_obs = db.query(SharpeBoardObservation).filter(
                SharpeBoardObservation.week_id.in_(ids)
            ).delete(synchronize_session=False)
        n_weeks = db.query(SharpeBoardWeek).filter(
            SharpeBoardWeek.profile_version == V1
        ).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"deleted_weeks": n_weeks, "deleted_observations": n_obs}


def main() -> int:
    ap = argparse.ArgumentParser(description="导出存档并删除 v1 夏普榜单历史")
    ap.add_argument("--apply", action="store_true",
                    help="真正执行删除（默认 dry-run 只导出+验证）")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        stamp = _now_stamp()
        art = export_v1(db, stamp)
        verify_export(art)
        m = art["manifest"]
        print(f"[导出] {art['json_path']}")
        print(f"[导出] {art['sql_path']}")
        print(f"[验证] weeks={m['weeks']} observations={m['observations']} "
              f"sha256={m['sha256_payload'][:16]}… OK")
        if not args.apply:
            print(f"[dry-run] 将删除 v1 weeks={m['weeks']} "
                  f"observations={m['observations']}；确认后加 --apply 执行。")
            print("[dry-run] 未做任何破坏性操作。")
            return 0
        result = delete_v1(db)
        print(f"[删除] weeks={result['deleted_weeks']} "
              f"observations={result['deleted_observations']}（单事务已提交）")
        # 删后再查一次确认
        left = db.execute(
            select(SharpeBoardWeek).where(SharpeBoardWeek.profile_version == V1)
        ).scalars().all()
        print(f"[确认] 剩余 v1 周批次: {len(left)}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
