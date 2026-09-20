"""Settings 受限路径与挂载校验测试。"""

import pytest

from src.config import Settings


def _prepare_roots(tmp_path):
    """按 Settings 校验要求创建全部挂载目录（design 2.2：要求目录存在）。"""
    source = tmp_path / "source"
    cache = tmp_path / "cache"
    state = tmp_path / "state"
    targets = tmp_path / "targets"
    for directory in (source, cache, state, targets / "openclaw", targets / "hermes"):
        directory.mkdir(parents=True, exist_ok=True)
    return source, cache, state, targets


def _set_base_env(monkeypatch, tmp_path, source, cache, state, targets):
    monkeypatch.setenv("SKILLS_SOURCE_ROOT", str(source))
    monkeypatch.setenv("GITHUB_SKILL_CACHE_ROOT", str(cache))
    monkeypatch.setenv("SKILL_MANAGER_STATE_DIR", str(state))
    monkeypatch.setenv("HERMES_SKILLS_ROOT", str(targets / "hermes"))
    monkeypatch.setenv("SKILL_MANAGER_ADMIN_PASSWORD", "test-password")


def test_settings_rejects_target_outside_its_mount(monkeypatch, tmp_path):
    source, cache, state, targets = _prepare_roots(tmp_path)
    _set_base_env(monkeypatch, tmp_path, source, cache, state, targets)
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setenv("OPENCLAW_SKILLS_ROOT", str(outside))

    with pytest.raises(ValueError, match="target root"):
        Settings(targets_mount_root=targets)


def test_settings_rejects_missing_root_directory(monkeypatch, tmp_path):
    source, cache, state, targets = _prepare_roots(tmp_path)
    _set_base_env(monkeypatch, tmp_path, source, cache, state, targets)
    monkeypatch.setenv("OPENCLAW_SKILLS_ROOT", str(targets / "openclaw"))
    monkeypatch.setenv("GITHUB_SKILL_CACHE_ROOT", str(tmp_path / "not-created"))

    with pytest.raises(ValueError, match="must exist"):
        Settings(targets_mount_root=targets)


def test_settings_accepts_valid_configuration(monkeypatch, tmp_path):
    source, cache, state, targets = _prepare_roots(tmp_path)
    _set_base_env(monkeypatch, tmp_path, source, cache, state, targets)
    monkeypatch.setenv("OPENCLAW_SKILLS_ROOT", str(targets / "openclaw"))

    settings = Settings(targets_mount_root=targets)

    assert settings.skills_source_root == source.resolve()
    assert settings.github_skill_cache_root == cache.resolve()
    assert settings.state_dir == state.resolve()
    assert settings.openclaw_skills_root == (targets / "openclaw").resolve()
    assert settings.hermes_skills_root == (targets / "hermes").resolve()
    assert settings.admin_password.get_secret_value() == "test-password"
    assert settings.service_port == 8097


def test_settings_resolves_relative_roots(monkeypatch, tmp_path):
    source, cache, state, targets = _prepare_roots(tmp_path)
    _set_base_env(monkeypatch, tmp_path, source, cache, state, targets)
    monkeypatch.setenv("OPENCLAW_SKILLS_ROOT", str(targets / "openclaw"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SKILLS_SOURCE_ROOT", "source")

    settings = Settings(targets_mount_root=targets)

    assert settings.skills_source_root.is_absolute()
    assert settings.skills_source_root == source.resolve()
