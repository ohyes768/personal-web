"""分类退役迁移：category 的值并进 tags，然后删掉这一列。

迁移不可逆（值此后只以标签形式存在），顺序必须是先转标签、后删列；
两步都在同一事务里，失败整笔回滚。
"""

from __future__ import annotations

import json
import sqlite3

from src.backup import export_payload, preview, restore
from src.db import Store
from src.models import ServiceCreate
from src.registry import Registry


def make_legacy_db(path) -> None:
    """造一个「旧版」库：services 表带 category 列，没有 ownership 列。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE services (id TEXT PRIMARY KEY, name TEXT NOT NULL,"
        " description TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT '',"
        " tags TEXT NOT NULL DEFAULT '[]', notes TEXT NOT NULL DEFAULT '',"
        " revision INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,"
        " updated_at TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO services(id, name, description, category, tags, notes,"
        " revision, created_at, updated_at) VALUES"
        " ('s1', '股息率分析', 'A股高股息', '金融', '[\"public\",\"stock\"]', '', 1,"
        " '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'),"
        " ('s2', 'RSS中转', '', '内容', '[\"rss\"]', '', 1,"
        " '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'),"
        " ('s3', '无分类的', '', '', '[]', '', 1,"
        " '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()


def test_migration_moves_category_into_tags(settings) -> None:
    make_legacy_db(settings.db_path)
    store = Store.from_settings(settings)
    registry = Registry(store)

    result = registry.migrate_category_to_tags()
    assert result["migrated"] == 2
    assert result["column_removed"] == 1

    with store.read() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(services)")}
        assert "category" not in columns
        rows = {
            row["id"]: json.loads(row["tags"])
            for row in conn.execute("SELECT id, tags FROM services")
        }
    # 分类值并进标签，且整体按字典序
    assert rows["s1"] == ["public", "stock", "金融"]
    assert rows["s2"] == ["rss", "内容"]
    # 本来就没有分类的行不受影响
    assert rows["s3"] == []


def test_migration_is_idempotent(settings) -> None:
    make_legacy_db(settings.db_path)
    store = Store.from_settings(settings)
    registry = Registry(store)

    first = registry.migrate_category_to_tags()
    second = registry.migrate_category_to_tags()
    assert first["migrated"] == 2
    assert second == {"migrated": 0, "column_removed": 0}

    with store.read() as conn:
        tags = json.loads(
            conn.execute("SELECT tags FROM services WHERE id = 's1'").fetchone()["tags"]
        )
    assert tags == ["public", "stock", "金融"]


def test_fresh_database_has_no_category_column(settings) -> None:
    store = Store.from_settings(settings)
    registry = Registry(store)
    assert registry.migrate_category_to_tags() == {"migrated": 0, "column_removed": 0}
    with store.read() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(services)")}
    assert "category" not in columns


def test_export_has_no_category_key(registry: Registry, store) -> None:
    registry.create_service(ServiceCreate(name="股息率", tags=["public"]))
    payload = export_payload(store)
    assert "category" not in payload["services"][0]


def test_restore_old_backup_ignores_category(
    registry: Registry, store, settings
) -> None:
    """老备份里有 category 键：恢复时忽略，不能报错也不能把分类写回去。"""
    registry.create_service(ServiceCreate(name="股息率", tags=["public"]))
    payload = export_payload(store)
    for item in payload["services"]:
        item["category"] = "金融"

    registry.delete_service(payload["services"][0]["id"])
    raw = json.dumps(payload).encode()
    meta = preview(store, raw)
    restore(
        store,
        payload=meta.payload,
        expected_digest=meta.digest,
        expected_revision=meta.registry_revision,
        raw=raw,
        confirm=True,
        data_dir=settings.data_dir,
    )
    detail = registry.get_service(payload["services"][0]["id"])
    assert detail.tags == ["public"]
