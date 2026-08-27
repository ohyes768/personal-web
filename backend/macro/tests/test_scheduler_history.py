"""scheduler 历史 JSONLReaderWriter 单元测试

验证：
- append + read_tail roundtrip（含组任务 items 子明细完整保留）
- 按 job_id 过滤 + 倒序返回（最新在前）+ n 条数限制
- 解析失败的行跳过不炸
"""
from __future__ import annotations

import asyncio
import json

import pytest

from src.scheduler.history import JSONLReaderWriter, build_record


@pytest.mark.unit
def test_append_and_read_tail_roundtrip_with_items(tmp_path):
    """写入带 items 的组任务记录 → 读回字段完整一致（子明细是页面核心展示）"""
    rw = JSONLReaderWriter(tmp_path / "history.jsonl")
    items = [
        {"path": "/update/vix", "status": "success", "count": None, "ms": 120, "error": None},
        {"path": "/update/tga", "status": "failed", "count": None, "ms": 300, "error": "HTTP 500: boom"},
    ]
    record = build_record(
        job_id="global_daily",
        target="run_group",
        start="2026-08-26T07:30:00",
        end="2026-08-26T07:31:00",
        status="partial",
        count=1,
    )
    record["items"] = items
    asyncio.run(rw.append(record))

    runs = rw.read_tail(job_id="global_daily", n=10)
    assert len(runs) == 1
    got = runs[0]
    assert got["status"] == "partial"
    assert got["count"] == 1
    assert got["items"] == items
    assert got["job_id"] == "global_daily"
    assert got["target"] == "run_group"


@pytest.mark.unit
def test_read_tail_filters_by_job_and_returns_newest_first(tmp_path):
    """按 job_id 过滤 + 倒序（最新在前）+ 条数限制"""
    rw = JSONLReaderWriter(tmp_path / "history.jsonl")

    async def write_all() -> None:
        for i in range(4):
            await rw.append(build_record(
                job_id="a_share_daily" if i % 2 == 0 else "global_daily",
                target="run_group",
                start=f"2026-08-2{i}T16:10:00",
                end=f"2026-08-2{i}T16:11:00",
                status="success",
                count=i,
            ))

    asyncio.run(write_all())

    # a_share_daily 只有 i=0/2 两条，最新（i=2）在前
    a_runs = rw.read_tail(job_id="a_share_daily", n=10)
    assert [r["count"] for r in a_runs] == [2, 0]

    # 不过滤：全量 4 条，最新（i=3）在前
    all_runs = rw.read_tail(n=10)
    assert [r["count"] for r in all_runs] == [3, 2, 1, 0]

    # n=2 截断
    top2 = rw.read_tail(n=2)
    assert [r["count"] for r in top2] == [3, 2]


@pytest.mark.unit
def test_read_tail_skips_corrupt_lines(tmp_path):
    """损坏行（非法 JSON）跳过，不抛异常"""
    path = tmp_path / "history.jsonl"
    path.write_text(
        '{"job_id": "j", "status": "success"}\n'
        "{corrupt line\n"
        '{"job_id": "j", "status": "failed"}\n',
        encoding="utf-8",
    )
    rw = JSONLReaderWriter(path)
    runs = rw.read_tail(job_id="j", n=10)
    assert [r["status"] for r in runs] == ["failed", "success"]
