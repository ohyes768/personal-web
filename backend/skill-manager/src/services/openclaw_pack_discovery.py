"""Keep one repository symlink while registering its group roots with OpenClaw.

Ownership is kept outside openclaw.json. Never remove a discovery root that
existed before this service added it. Config writes preserve its inode so a
single-file Docker bind mount continues to see updates.
"""
from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Iterator

_THREAD_LOCK = threading.RLock()


class OpenClawPackDiscovery:
    def __init__(self, config_path: Path | None, state_dir: Path) -> None:
        self.config_path = Path(config_path) if config_path else None
        self.state_dir = Path(state_dir)
        self.manifest = self.state_dir / "openclaw-pack-discovery.json"
        self.journal = self.state_dir / "openclaw-pack-discovery-pending.json"

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with _THREAD_LOCK, (self.state_dir / "openclaw-pack-discovery.lock").open("a+b") as lock:
            lock.seek(0)
            if os.name == "nt":
                import msvcrt
                if lock.read(1) == b"":
                    lock.write(b"0")
                    lock.flush()
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                self._recover()
                yield
            finally:
                lock.seek(0)
                if os.name == "nt":
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def check(self) -> None:
        with self._locked():
            self._config()

    def snapshot(self, pack_id: str | None = None) -> dict:
        with self._locked():
            self._config()
            return {"pack_id": pack_id,
                    "config": self.config_path.read_text(encoding="utf-8"),
                    "manifest": self._ownership()}

    def restore(self, snapshot: dict) -> None:
        with self._locked():
            pack_id = snapshot.get("pack_id")
            if pack_id is None:
                self._commit(snapshot["config"], snapshot["manifest"])
                return
            # A different pack may have updated this shared config meanwhile.
            # Undo only this pack's managed additions, preserving other writers.
            state = self._ownership()
            previous = state["packs"].pop(pack_id, [])
            old_groups = snapshot["manifest"]["packs"].get(pack_id)
            if old_groups is not None:
                state["packs"][pack_id] = old_groups
            self._apply(self._config(), state, previous)

    def sync(self, pack_id: str, link_path: Path, inventory_paths: list[str]) -> None:
        groups = []
        for raw in inventory_paths:
            rel = PurePosixPath(raw)
            if not raw or rel.is_absolute() or ".." in rel.parts or "\\" in raw or ":" in raw:
                raise ValueError("技能库存路径不合法")
            # A skill's directory is rel; OpenClaw scans its parent group.
            parent = rel.parent if rel.parts else PurePosixPath(".")
            group = str(Path(link_path).joinpath(*parent.parts))
            if group not in groups:
                groups.append(group)
        with self._locked():
            config = self._config()
            owned = self._ownership()
            previous = owned["packs"].get(pack_id, [])
            owned["packs"][pack_id] = groups
            self._apply(config, owned, previous)

    def remove(self, pack_id: str) -> None:
        with self._locked():
            owned = self._ownership()
            if pack_id not in owned["packs"]:
                return
            config = self._config()
            previous = owned["packs"].pop(pack_id)
            self._apply(config, owned, previous)

    def _config(self) -> dict:
        if self.config_path is None or not self.config_path.is_file():
            raise ValueError("OpenClaw 整包安装需要配置 OPENCLAW_CONFIG_PATH 并挂载实际 openclaw.json")
        try:
            config = json.loads(self.config_path.read_text(encoding="utf-8"))
            if not isinstance(config, dict):
                raise ValueError()
            skills = config.get("skills", {})
            if not isinstance(skills, dict):
                raise ValueError()
            load = skills.get("load", {})
            if not isinstance(load, dict):
                raise ValueError()
            dirs = load.get("extraDirs", [])
            if not isinstance(dirs, list) or any(not isinstance(item, str) for item in dirs):
                raise ValueError()
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError("OpenClaw 配置不是有效 JSON，未修改；请先修复配置") from exc
        if not os.access(self.config_path, os.W_OK):
            raise ValueError("OpenClaw 配置不可写，无法登记整包搜索目录")
        return config

    def _ownership(self) -> dict:
        if not self.manifest.exists():
            return {"packs": {}, "added": []}
        try:
            state = json.loads(self.manifest.read_text(encoding="utf-8"))
            if not isinstance(state["packs"], dict) or not isinstance(state["added"], list):
                raise ValueError()
            return state
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ValueError("OpenClaw 搜索目录台账损坏，请恢复台账后重试") from exc

    def _apply(self, config: dict, state: dict, previous: list[str]) -> None:
        load = config.setdefault("skills", {}).setdefault("load", {})
        dirs = list(load.get("extraDirs", []))
        required = {item for groups in state["packs"].values() for item in groups}
        for item in previous:
            if item in state["added"] and item not in required:
                dirs = [entry for entry in dirs if entry != item]
                state["added"].remove(item)
        for groups in state["packs"].values():
            for item in groups:
                if item not in dirs:
                    dirs.append(item)
                    if item not in state["added"]:
                        state["added"].append(item)
        load["extraDirs"] = dirs
        self._commit(json.dumps(config, ensure_ascii=False, indent=2) + "\n", state)

    def _commit(self, content: str, state: dict) -> None:
        old = self.config_path.read_text(encoding="utf-8")
        old_state = self._ownership()
        if content == old and state == old_state:
            return
        self._write_state(self.journal, {"before": old, "after": content,
                                      "before_state": old_state, "after_state": state})
        try:
            self._write_config(content)
            self._write_state(self.manifest, state)
        except Exception:
            # Keep the journal if rollback fails; the next operation recovers.
            self._write_config(old)
            self._write_state(self.manifest, old_state)
            self.journal.unlink()
            raise
        self.journal.unlink()

    def _recover(self) -> None:
        if not self.journal.exists():
            return
        if self.config_path is None or not self.config_path.is_file():
            raise ValueError("OpenClaw 配置变更待恢复，但配置文件不可用")
        pending = json.loads(self.journal.read_text(encoding="utf-8"))
        current = self.config_path.read_text(encoding="utf-8")
        if current == pending["after"]:
            self._write_state(self.manifest, pending["after_state"])
        elif current == pending["before"]:
            self._write_state(self.manifest, pending["before_state"])
        else:
            try:
                json.loads(current)
            except ValueError:
                self._write_config(pending["before"])
                self._write_state(self.manifest, pending["before_state"])
            else:
                raise ValueError("OpenClaw 配置在中断后被其他操作修改，请核对恢复台账")
        self.journal.unlink()

    def _write_config(self, content: str) -> None:
        # Do not os.replace a bind-mounted config file.
        with self.config_path.open("r+", encoding="utf-8") as handle:
            handle.seek(0)
            handle.write(content)
            handle.truncate()
            handle.flush()
            os.fsync(handle.fileno())

    @staticmethod
    def _write_state(path: Path, state: dict) -> None:
        temp = path.with_suffix(".next")
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
