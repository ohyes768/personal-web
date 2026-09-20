"""RegistrySkill 与枚举契约测试（models.py 是唯一 Pydantic 契约来源）。"""

import pytest
from pydantic import ValidationError

from src.models import RegistrySkill, SkillSource, TargetKey


def test_enum_values_match_design():
    assert SkillSource.LOCAL == "local"
    assert SkillSource.GITHUB == "github"
    assert TargetKey.OPENCLAW == "openclaw"
    assert TargetKey.HERMES == "hermes"


def test_registry_skill_accepts_valid_local_skill():
    skill = RegistrySkill(id="dividend-report", name="高股息报告", source=SkillSource.LOCAL, path="skills/dividend-report")
    assert skill.repository is None
    assert skill.status == "active"
    assert skill.tags == []


def test_registry_skill_accepts_valid_github_skill():
    skill = RegistrySkill(
        id="github-research",
        name="Research",
        source=SkillSource.GITHUB,
        path=".",
        repository="https://github.com/example/research",
    )
    assert skill.source == SkillSource.GITHUB
    assert str(skill.repository).startswith("https://github.com/")


def test_registry_skill_rejects_invalid_ids():
    for bad_id in ("Uppercase", "with_underscore", "-leading-dash", "has space", "a" * 64):
        with pytest.raises(ValidationError):
            RegistrySkill(id=bad_id, name="x", source=SkillSource.LOCAL, path="p")


def test_registry_skill_rejects_empty_path():
    with pytest.raises(ValidationError):
        RegistrySkill(id="ok-id", name="x", source=SkillSource.LOCAL, path="")


def test_registry_skill_path_is_required():
    with pytest.raises(ValidationError):
        RegistrySkill(id="ok-id", name="x", source=SkillSource.LOCAL)


def test_registry_skill_requires_repository_for_github():
    with pytest.raises(ValidationError, match="repository"):
        RegistrySkill(id="gh-skill", name="x", source=SkillSource.GITHUB, path=".")


def test_registry_skill_rejects_repository_for_local():
    with pytest.raises(ValidationError, match="repository"):
        RegistrySkill(
            id="local-skill",
            name="x",
            source=SkillSource.LOCAL,
            path="p",
            repository="https://github.com/example/repo",
        )


def test_registry_skill_rejects_bad_tags():
    with pytest.raises(ValidationError):
        RegistrySkill(id="ok-id", name="x", source=SkillSource.LOCAL, path="p", tags=[""])
    with pytest.raises(ValidationError):
        RegistrySkill(id="ok-id", name="x", source=SkillSource.LOCAL, path="p", tags=["t" * 41])


def test_registry_skill_rejects_unknown_status():
    with pytest.raises(ValidationError):
        RegistrySkill(id="ok-id", name="x", source=SkillSource.LOCAL, path="p", status="draft")
