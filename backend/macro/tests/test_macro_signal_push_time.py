"""宏观信号分组推送时间测试。"""
from datetime import datetime, timezone
import os

from tests.conftest import make_macro_signal, write_skill_json


def test_group_push_time_uses_uploaded_file_mtime(skill_dir, service):
    """卡片推送时间取线上收到并写入该分组文件的时间，而非 skill 自报分析时间。"""
    write_skill_json(
        skill_dir,
        "monetary-policy-skill",
        "macro_signal.json",
        make_macro_signal(
            "2026-08-20",
            conclusion="偏宽松",
            details={"lpr_1y": 3.0},
            generated_at="2026-08-20T01:00:00Z",
        ),
    )
    path = skill_dir / "monetary-policy-skill" / "macro_signal.json"
    pushed_at = datetime(2026, 9, 15, 6, 30, tzinfo=timezone.utc)
    os.utime(path, (pushed_at.timestamp(), pushed_at.timestamp()))

    snapshot = service.get_snapshot("2026-08")

    assert snapshot is not None
    assert snapshot.groups["monetary_policy"].pushed_at == "2026-09-15T06:30:00Z"