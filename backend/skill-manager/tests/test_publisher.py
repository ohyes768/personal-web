"""安全发布、下架与回滚测试（design 6.1/6.2）。"""

import os
from types import SimpleNamespace

import pytest

from src.config import Settings
from src.db import SkillStateStore
from src.models import PublishItem, TargetKey
from src.services.publisher import (
    InvalidSourceError,
    PublishBlockedError,
    Publisher,
    PublisherError,
    RollbackUnavailableError,
)


def _make_skill(root, name, marker="demo"):
    """在 root 下创建含 SKILL.md 的候选 Skill 目录。"""
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\n---\n{marker}\n", encoding="utf-8"
    )
    return skill_dir


@pytest.fixture()
def roots(tmp_path):
    source_root = tmp_path / "source"
    github_cache = tmp_path / "cache"
    state = tmp_path / "state"
    targets = tmp_path / "targets"
    openclaw = targets / "openclaw"
    hermes = targets / "hermes"
    for directory in (source_root, github_cache, state, openclaw, hermes):
        directory.mkdir(parents=True)
    return SimpleNamespace(
        source_root=source_root,
        github_cache=github_cache,
        state=state,
        targets=targets,
        openclaw=openclaw,
        hermes=hermes,
    )


@pytest.fixture()
def settings(roots):
    return Settings(
        skills_source_root=roots.source_root,
        github_skill_cache_root=roots.github_cache,
        openclaw_skills_root=roots.openclaw,
        hermes_skills_root=roots.hermes,
        state_dir=roots.state,
        admin_password="test-password",
        targets_mount_root=roots.targets,
    )


@pytest.fixture()
def store(settings):
    return SkillStateStore(settings.state_dir / "skill-manager.sqlite3")


@pytest.fixture()
def publisher(settings, store):
    return Publisher(settings, store)


@pytest.fixture()
def openclaw_root(roots):
    return roots.openclaw


@pytest.fixture()
def source_dir(roots):
    return _make_skill(roots.source_root, "research-skill").resolve()


# ---------- 发布 ----------


# 以下标记见 conftest.py：无 symlink 特权的 Windows 环境显式跳过
@pytest.mark.requires_symlink
def test_publish_replaces_only_a_managed_symlink(publisher, source_dir, openclaw_root):
    published = publisher.publish(
        "research-skill", TargetKey.OPENCLAW, source_dir, "sha-1"
    )
    link = openclaw_root / "research-skill"
    assert link.is_symlink()
    assert link.resolve() == source_dir
    assert published.action == "add"
    assert published.status == "success"


def test_publish_refuses_to_overwrite_a_real_directory(
    publisher, source_dir, openclaw_root
):
    (openclaw_root / "research-skill").mkdir()
    with pytest.raises(PublishBlockedError, match="ordinary directory"):
        publisher.publish("research-skill", TargetKey.OPENCLAW, source_dir, "sha-1")


@pytest.mark.requires_symlink
def test_rollback_restores_the_previous_link(publisher, roots):
    source_v1 = _make_skill(roots.source_root, "v1").resolve()
    source_v2 = _make_skill(roots.source_root, "v2").resolve()
    publisher.publish("research-skill", TargetKey.OPENCLAW, source_v1, "sha-1")
    publisher.publish("research-skill", TargetKey.OPENCLAW, source_v2, "sha-2")

    publisher.rollback("research-skill", TargetKey.OPENCLAW)

    assert (roots.openclaw / "research-skill").resolve() == source_v1


@pytest.mark.requires_symlink
def test_batch_keeps_successful_item_when_another_target_is_blocked(
    publisher, source_dir, roots
):
    (roots.hermes / "blocked-skill").mkdir()
    result = publisher.publish_many(
        [
            PublishItem(
                skill_id="good-skill", target=TargetKey.OPENCLAW, source=source_dir
            ),
            PublishItem(
                skill_id="blocked-skill", target=TargetKey.HERMES, source=source_dir
            ),
        ]
    )
    assert [item.status for item in result.items] == ["success", "blocked"]
    assert (roots.openclaw / "good-skill").is_symlink()


def test_publish_rejects_source_without_skill_md(publisher, roots):
    empty = roots.source_root / "empty"
    empty.mkdir()

    with pytest.raises(InvalidSourceError, match="SKILL.md"):
        publisher.publish("empty-skill", TargetKey.OPENCLAW, empty)


def test_publish_rejects_path_traversal_and_outside_sources(publisher, roots):
    escape = roots.source_root.parent / "escape"
    escape.mkdir()
    (escape / "SKILL.md").write_text("---\nname: escape\n---", encoding="utf-8")

    with pytest.raises(InvalidSourceError, match="controlled"):
        publisher.publish("escape-skill", TargetKey.OPENCLAW, escape)
    # 相对路径穿越形式 resolve 后同样落在受控根之外
    with pytest.raises(InvalidSourceError, match="controlled"):
        publisher.publish(
            "escape-skill", TargetKey.OPENCLAW, roots.source_root / ".." / "escape"
        )


def test_publish_rejects_invalid_skill_id(publisher, source_dir):
    with pytest.raises(InvalidSourceError, match="skill id"):
        publisher.publish("Bad_Skill", TargetKey.OPENCLAW, source_dir)


@pytest.mark.requires_symlink
def test_publish_cleans_up_temp_link_when_replace_fails(
    publisher, source_dir, roots, monkeypatch
):
    publisher.publish("research-skill", TargetKey.OPENCLAW, source_dir, "sha-1")
    source_v2 = _make_skill(roots.source_root, "v2").resolve()

    def broken_replace(src, dst, **kwargs):
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", broken_replace)

    with pytest.raises(PublisherError, match="replace failed"):
        publisher.publish("research-skill", TargetKey.OPENCLAW, source_v2, "sha-2")

    leftovers = [
        path.name for path in roots.openclaw.iterdir() if path.name != "research-skill"
    ]
    assert leftovers == []
    # 替换失败后旧链接保持可用
    assert (roots.openclaw / "research-skill").resolve() == source_dir


@pytest.mark.requires_symlink
def test_publish_persists_deployment_snapshot_and_history(
    publisher, store, source_dir, roots
):
    source_v2 = _make_skill(roots.source_root, "v2").resolve()
    publisher.publish("research-skill", TargetKey.OPENCLAW, source_dir, "sha-1")
    publisher.publish("research-skill", TargetKey.OPENCLAW, source_v2, "sha-2")

    record = store.get_deployment("research-skill", "openclaw")
    assert record.status == "active"
    assert record.source_revision == "sha-2"
    assert record.current_link_target == str(source_v2)

    snapshot = store.get_rollback_snapshot("research-skill", "openclaw")
    assert snapshot.previous_link_target == str(source_dir)

    history = store.list_history(skill_id="research-skill", target="openclaw")
    assert [entry.action for entry in history] == ["publish", "publish"]
    assert history[-1].previous_link_target == str(source_dir)


# ---------- 下架 ----------


@pytest.mark.requires_symlink
def test_unpublish_removes_only_managed_link(publisher, source_dir, openclaw_root):
    publisher.publish("research-skill", TargetKey.OPENCLAW, source_dir, "sha-1")

    publisher.unpublish("research-skill", TargetKey.OPENCLAW)

    link = openclaw_root / "research-skill"
    assert not link.is_symlink()
    assert not link.exists()
    assert source_dir.is_dir()  # 只删链接本身，绝不递归删除源目录


def test_unpublish_refuses_ordinary_directory(publisher, openclaw_root):
    ordinary = openclaw_root / "research-skill"
    ordinary.mkdir()

    with pytest.raises(PublishBlockedError, match="ordinary directory"):
        publisher.unpublish("research-skill", TargetKey.OPENCLAW)
    assert ordinary.is_dir()


# ---------- 回滚 ----------


def test_rollback_without_snapshot_raises(publisher):
    with pytest.raises(RollbackUnavailableError):
        publisher.rollback("research-skill", TargetKey.OPENCLAW)


@pytest.mark.requires_symlink
def test_rollback_refuses_snapshot_target_that_vanished(publisher, roots):
    source_v1 = _make_skill(roots.source_root, "v1")
    source_v2 = _make_skill(roots.source_root, "v2").resolve()
    publisher.publish("research-skill", TargetKey.OPENCLAW, source_v1.resolve(), "sha-1")
    publisher.publish("research-skill", TargetKey.OPENCLAW, source_v2, "sha-2")
    # 快照指向的 v1 目录随后被移除
    import shutil

    shutil.rmtree(source_v1)

    with pytest.raises(RollbackUnavailableError, match="unavailable"):
        publisher.rollback("research-skill", TargetKey.OPENCLAW)
