"""OpenClaw old grouped-discovery compatibility, using only isolated config."""
import json
from pathlib import Path

import pytest


def test_nested_pack_adds_group_roots_and_preserves_user_config(tmp_path):
    from src.services.openclaw_pack_discovery import OpenClawPackDiscovery
    config = tmp_path / "openclaw.json"
    config.write_text(json.dumps({"gateway": {"port": 1234}, "skills": {"load": {"extraDirs": ["/user/skills"]}}}))
    adapter = OpenClawPackDiscovery(config, tmp_path / "state")
    link = tmp_path / "skills/pack"
    adapter.sync("pack", link, ["codex-skills/alpha", "codex-skills/beta"])
    updated = json.loads(config.read_text())
    assert updated["gateway"] == {"port": 1234}
    assert updated["skills"]["load"]["extraDirs"] == ["/user/skills", str(link / "codex-skills")]
    adapter.sync("pack", link, ["codex-skills/alpha"])
    assert json.loads(config.read_text()) == updated
    adapter.remove("pack")
    assert json.loads(config.read_text())["skills"]["load"]["extraDirs"] == ["/user/skills"]


def test_preexisting_discovery_root_not_removed_on_uninstall(tmp_path):
    from src.services.openclaw_pack_discovery import OpenClawPackDiscovery
    config = tmp_path / "openclaw.json"
    link = tmp_path / "skills/pack"
    config.write_text(json.dumps({"skills": {"load": {"extraDirs": [str(link / "skills")]}}}))
    adapter = OpenClawPackDiscovery(config, tmp_path / "state")
    adapter.sync("pack", link, ["skills/a"])
    adapter.remove("pack")
    assert json.loads(config.read_text())["skills"]["load"]["extraDirs"] == [str(link / "skills")]


def test_group_change_replaces_only_owned_entries(tmp_path):
    from src.services.openclaw_pack_discovery import OpenClawPackDiscovery
    config = tmp_path / "openclaw.json"
    config.write_text("{}")
    adapter = OpenClawPackDiscovery(config, tmp_path / "state")
    link = tmp_path / "skills/pack"
    adapter.sync("pack", link, ["skills/a"])
    adapter.sync("pack", link, ["codex-skills/a", "other/group/b"])
    assert json.loads(config.read_text())["skills"]["load"]["extraDirs"] == [
        str(link / "codex-skills"), str(link / "other/group")
    ]


@pytest.mark.parametrize("bad", ["../escape", "/absolute", "skills/../../escape"])
def test_invalid_inventory_path_cannot_change_config(tmp_path, bad):
    from src.services.openclaw_pack_discovery import OpenClawPackDiscovery
    config = tmp_path / "openclaw.json"
    config.write_text("{}")
    adapter = OpenClawPackDiscovery(config, tmp_path / "state")
    with pytest.raises(ValueError):
        adapter.sync("pack", tmp_path / "pack", [bad])
    assert config.read_text() == "{}"


def test_missing_or_invalid_config_does_not_get_overwritten(tmp_path):
    from src.services.openclaw_pack_discovery import OpenClawPackDiscovery
    config = tmp_path / "openclaw.json"
    adapter = OpenClawPackDiscovery(config, tmp_path / "state")
    with pytest.raises(ValueError):
        adapter.sync("pack", tmp_path / "pack", ["skills/a"])
    assert not config.exists()
    config.write_text("invalid json")
    with pytest.raises(ValueError):
        adapter.sync("pack", tmp_path / "pack", ["skills/a"])
    assert config.read_text() == "invalid json"


def test_conversion_restore_preserves_another_pack_config_change(tmp_path):
    from src.services.openclaw_pack_discovery import OpenClawPackDiscovery
    config = tmp_path / "openclaw.json"
    config.write_text("{}")
    adapter = OpenClawPackDiscovery(config, tmp_path / "state")
    snapshot = adapter.snapshot("a")
    adapter.sync("a", tmp_path / "a", ["skills/x"])
    adapter.sync("b", tmp_path / "b", ["skills/y"])
    adapter.restore(snapshot)
    assert json.loads(config.read_text())["skills"]["load"]["extraDirs"] == [str(tmp_path / "b/skills")]
