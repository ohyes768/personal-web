#!/usr/bin/env python3
"""
status.json 数据迁移脚本：v1.0 → v2.0 schema

v1.0 schema:
  {
    "videos": {
      "<aweme_id>": {
        "status": "pending" | "processing" | "completed" | "failed",
        "is_read": true | false,        # 独立布尔字段
        "read_at": "...",
        "error": "...",                # status=failed 时存在
        ...
      }
    }
  }

v2.0 schema:
  {
    "videos": {
      "<aweme_id>": {
        "status": "pending" | "unread" | "read" | "deleted",  # 已读/未读并入 status
        # is_read 字段已废弃，语义由 status 字段表达
        "read_at": "...",
        "error": "...",                # 保留
        "pending_at": "...",
        "processed_at": "...",
        "deleted_at": "...",
        ...
      }
    }
  }

迁移规则：
  status=completed, is_read=true  → status=read
  status=completed, is_read=false → status=unread
  status=processing                → status=unread  (视作已处理)
  status=failed                    → status=deleted (失败记录标删除，保留 error)
  status=pending                   → 保持 pending
  任何带 is_read 字段的           → 删除该字段

用法：
  python scripts/migrate_status.py                 # 迁移 data/status.json（默认）
  python scripts/migrate_status.py path/to/file    # 迁移指定文件
  python scripts/migrate_status.py --dry-run       # 仅预览不写
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# 旧 → 新 status 映射
STATUS_MIGRATION = {
    "completed": "read",        # 默认 completed 视作"已识别"，具体是 read/unread 看 is_read
    "processing": "unread",     # 处理中的视作已处理（用户未读）
    "failed": "deleted",        # 失败记录标删除
    "pending": "pending",       # 保持
}


def migrate_status_file(status_path: Path, dry_run: bool = False) -> dict:
    """迁移单个 status.json 文件

    Args:
        status_path: status.json 路径
        dry_run: 仅预览不写

    Returns:
        迁移统计 {"migrated": int, "skipped": int, "details": list}
    """
    if not status_path.exists():
        print(f"❌ 文件不存在: {status_path}")
        return {"migrated": 0, "skipped": 0, "details": []}

    print(f"📂 读取: {status_path}")
    with open(status_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    videos = data.get("videos", {})
    print(f"📊 共 {len(videos)} 条记录")

    stats = {"migrated": 0, "skipped": 0, "details": []}

    for aweme_id, record in videos.items():
        old_status = record.get("status", "pending")
        is_read = record.get("is_read", False)

        # 判断新 status
        if old_status == "completed":
            # completed 根据 is_read 细分
            new_status = "read" if is_read else "unread"
        elif old_status in STATUS_MIGRATION:
            new_status = STATUS_MIGRATION[old_status]
        else:
            # 已经是 v2.0 状态（read/unread/deleted/pending），跳过
            stats["skipped"] += 1
            continue

        # 应用新 status
        old_status_display = old_status
        record["status"] = new_status

        # 删除 is_read 字段（已并入 status）
        if "is_read" in record:
            del record["is_read"]

        # failed → deleted 时添加 deleted_at
        if old_status == "failed" and "deleted_at" not in record:
            record["deleted_at"] = datetime.now().isoformat()

        # 标记迁移时间（方便回溯）
        if "_migrated_from" not in record:
            record["_migrated_from"] = old_status_display

        stats["migrated"] += 1
        stats["details"].append({
            "aweme_id": aweme_id,
            "old": old_status_display,
            "is_read": is_read,
            "new": new_status,
        })

    # 更新 last_updated
    data["last_updated"] = datetime.now().isoformat()
    data["_schema_version"] = "2.0"

    if dry_run:
        print(f"\n🔍 [DRY-RUN] 预览：")
        for d in stats["details"][:10]:
            is_read_str = f"+is_read={d['is_read']}" if d["old"] == "completed" else ""
            print(f"  {d['aweme_id']}: {d['old']}{is_read_str} → {d['new']}")
        if len(stats["details"]) > 10:
            print(f"  ... 还有 {len(stats['details']) - 10} 条")
        print(f"\n✅ 预览完成: 将迁移 {stats['migrated']} 条, 跳过 {stats['skipped']} 条")
    else:
        # 写回（用临时文件 + rename 原子操作）
        tmp_path = status_path.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp_path.replace(status_path)

        print(f"\n✅ 迁移完成: 迁移 {stats['migrated']} 条, 跳过 {stats['skipped']} 条")
        print(f"📝 写入: {status_path}")
        if stats["migrated"] > 0:
            print(f"💡 建议备份原文件: cp {status_path} {status_path}.bak")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="status.json v1.0 → v2.0 schema 迁移"
    )
    parser.add_argument(
        "file",
        nargs="?",
        default="data/status.json",
        help="status.json 路径（默认: data/status.json）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅预览，不实际修改文件",
    )
    args = parser.parse_args()

    status_path = Path(args.file)
    print("=" * 60)
    print("status.json v1.0 → v2.0 迁移工具")
    print("=" * 60)

    if args.dry_run:
        print("⚠️  DRY-RUN 模式：只显示不修改")
    print()

    result = migrate_status_file(status_path, dry_run=args.dry_run)

    if not args.dry_run and result["migrated"] > 0:
        print()
        print("📋 后续步骤:")
        print("  1. 验证前端能正常显示已迁移数据")
        print("  2. 跑一次清理脚本（如需）：POST /api/aweme/cleanup?days=30")
        print("  3. 删掉备份文件（如不需要回滚）")

    return 0


if __name__ == "__main__":
    sys.exit(main())
