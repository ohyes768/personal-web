"""Configured roots authorize writes; persisted catalog only preserves identity."""
import os
from pathlib import Path

from src.models import InstallTarget, is_install_target


class TargetUnavailable(ValueError):
    pass


class TargetResolver:
    def __init__(self, settings, store=None):
        self.settings = settings
        self.configured = {t.id: t for t in settings.hermes_targets}
        self.roots = {key: value.skills_root.resolve() for key, value in self.configured.items()}
        self.store = store
        if store:
            store.sync_install_targets(settings.hermes_targets, settings._legacy_hermes_root)

    def root(self, target: str) -> Path:
        item = self.configured.get(target)
        if not item:
            raise TargetUnavailable(f"目标 {target} 未配置，不能操作历史目录")
        root = item.skills_root
        if root.resolve() != self.roots[target]:
            raise TargetUnavailable(f"目标 {target} 目录已重定向，请恢复配置并重启")
        if not root.is_dir() or not os.access(root, os.R_OK | os.W_OK | os.X_OK):
            raise TargetUnavailable(f"目标 {target} 目录缺失或没有访问权限：{root}")
        return root.resolve()

    def fingerprint(self, target: str, skill_id: str):
        root = self.root(target)
        stat = root.stat()
        link = root / skill_id
        if link.is_symlink():
            state = ('link', os.readlink(link), link.lstat().st_ino, link.lstat().st_mtime_ns)
        elif link.exists():
            state = ('occupied', link.stat().st_ino, link.stat().st_mtime_ns)
        else:
            state = ('missing',)
        item = self.configured[target]
        return (item.id, item.name, item.profile_name, str(item.skills_root), str(root), stat.st_dev, stat.st_ino, state)

    def catalog(self):
        rows = {row['id']: row for row in self.store.list_install_targets()} if self.store else {}
        if self.store:
            for record in self.store.list_deployments():
                if is_install_target(record.target) and record.target not in rows:
                    rows[record.target] = dict(id=record.target, name=record.target, profile_name=record.target, last_root='')
        for key, item in self.configured.items():
            rows[key] = dict(id=key, name=item.name, profile_name=item.profile_name, last_root=str(item.skills_root))
        result = []
        for key, row in rows.items():
            reason = ''
            try:
                self.root(key)
            except TargetUnavailable as exc:
                reason = str(exc)
            result.append(InstallTarget(id=key, name=row['name'], profile_name=row['profile_name'], install_path=row['last_root'], configured=key in self.configured, available=not reason, unavailable_reason=reason))
        return result
