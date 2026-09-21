"""SQLite 状态库表结构与读写测试（design 3.2）。"""

import sqlite3
from contextlib import closing

from src.db import (
    DeploymentRecord,
    GithubCheckRecord,
    HistoryEntry,
    RollbackSnapshot,
    SkillStateStore,
)


def _deployment(**overrides) -> DeploymentRecord:
    values = dict(
        skill_id="macro",
        target="openclaw",
        source_revision="sha-1",
        source_path="/mnt/skills-source/macro",
        current_link_target="/mnt/skills-source/macro",
        status="active",
        published_at="2026-09-20T08:00:00+00:00",
    )
    values.update(overrides)
    return DeploymentRecord(**values)


def _history(**overrides) -> HistoryEntry:
    values = dict(
        skill_id="macro",
        target="openclaw",
        action="publish",
        result="success",
        previous_link_target=None,
        new_link_target="/mnt/skills-source/macro",
        source_revision="sha-1",
        error=None,
        created_at="2026-09-20T08:00:00+00:00",
    )
    values.update(overrides)
    return HistoryEntry(**values)


def test_creates_expected_tables(tmp_path):
    db_path = tmp_path / "state" / "skills.sqlite3"

    SkillStateStore(db_path)

    with closing(sqlite3.connect(db_path)) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    assert {"deployment", "deployment_history", "rollback_snapshot"} <= {
        row[0] for row in rows
    }


def test_upsert_and_get_deployment(tmp_path):
    store = SkillStateStore(tmp_path / "state" / "skills.sqlite3")
    record = _deployment()

    store.upsert_deployment(record)

    assert store.get_deployment("macro", "openclaw") == record


def test_get_deployment_returns_none_for_unknown_pair(tmp_path):
    store = SkillStateStore(tmp_path / "state" / "skills.sqlite3")

    assert store.get_deployment("nope", "openclaw") is None


def test_upsert_deployment_replaces_same_primary_key(tmp_path):
    store = SkillStateStore(tmp_path / "state" / "skills.sqlite3")
    store.upsert_deployment(_deployment(source_revision="sha-1"))
    updated = _deployment(
        source_revision="sha-2", published_at="2026-09-21T08:00:00+00:00"
    )

    store.upsert_deployment(updated)

    assert store.get_deployment("macro", "openclaw") == updated
    assert store.list_deployments() == [updated]


def test_list_deployments_covers_all_targets(tmp_path):
    store = SkillStateStore(tmp_path / "state" / "skills.sqlite3")
    store.upsert_deployment(_deployment(target="openclaw"))
    store.upsert_deployment(_deployment(target="hermes", source_revision="sha-9"))

    records = store.list_deployments()

    assert {record.target for record in records} == {"openclaw", "hermes"}


def test_append_history_and_list_with_filter(tmp_path):
    store = SkillStateStore(tmp_path / "state" / "skills.sqlite3")
    first = _history(created_at="2026-09-20T08:00:00+00:00")
    second = _history(action="unpublish", created_at="2026-09-20T09:00:00+00:00")
    other = _history(skill_id="other", target="hermes")

    store.append_history(first)
    store.append_history(second)
    store.append_history(other)

    assert store.list_history(skill_id="macro", target="openclaw") == [first, second]


def test_snapshot_set_get_delete(tmp_path):
    store = SkillStateStore(tmp_path / "state" / "skills.sqlite3")
    snapshot = RollbackSnapshot(
        skill_id="macro",
        target="openclaw",
        previous_link_target="/mnt/skills-source/macro-old",
        previous_revision="sha-0",
        updated_at="2026-09-20T08:00:00+00:00",
    )

    assert store.get_rollback_snapshot("macro", "openclaw") is None

    store.set_rollback_snapshot(snapshot)
    assert store.get_rollback_snapshot("macro", "openclaw") == snapshot

    store.set_rollback_snapshot(
        RollbackSnapshot(
            skill_id="macro",
            target="openclaw",
            previous_link_target="/mnt/skills-source/macro-new",
            previous_revision="sha-1",
            updated_at="2026-09-20T09:00:00+00:00",
        )
    )
    assert (
        store.get_rollback_snapshot("macro", "openclaw").previous_link_target
        == "/mnt/skills-source/macro-new"
    )

    store.delete_rollback_snapshot("macro", "openclaw")
    assert store.get_rollback_snapshot("macro", "openclaw") is None


def test_delete_rollback_snapshots_removes_all_targets_for_skill(tmp_path):
    store = SkillStateStore(tmp_path / "state" / "skills.sqlite3")
    store.set_rollback_snapshot(
        RollbackSnapshot(
            skill_id="macro",
            target="openclaw",
            previous_link_target="/mnt/old-openclaw",
            previous_revision="sha-1",
            updated_at="2026-09-21T08:00:00+00:00",
        )
    )
    store.set_rollback_snapshot(
        RollbackSnapshot(
            skill_id="macro",
            target="hermes",
            previous_link_target="/mnt/old-hermes",
            previous_revision="sha-2",
            updated_at="2026-09-21T09:00:00+00:00",
        )
    )
    store.set_rollback_snapshot(
        RollbackSnapshot(
            skill_id="other",
            target="openclaw",
            previous_link_target="/mnt/other",
            previous_revision="sha-3",
            updated_at="2026-09-21T10:00:00+00:00",
        )
    )

    store.delete_rollback_snapshots("macro")

    assert store.get_rollback_snapshot("macro", "openclaw") is None
    assert store.get_rollback_snapshot("macro", "hermes") is None
    assert store.get_rollback_snapshot("other", "openclaw") is not None


def test_delete_github_check(tmp_path):
    store = SkillStateStore(tmp_path / "state" / "skills.sqlite3")
    store.upsert_github_check(
        GithubCheckRecord(
            skill_id="macro",
            repository="https://github.com/a/macro",
            remote_revision="sha-1",
            remote_tags="",
            cached_revision="sha-1",
            result="ok",
            error=None,
            checked_at="2026-09-21T08:00:00+00:00",
        )
    )

    store.delete_github_check("macro")

    assert store.get_github_check("macro") is None
