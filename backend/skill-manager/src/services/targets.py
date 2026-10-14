"""Live target configuration with fixed deployment authorization boundaries."""
import hashlib
import os
from pathlib import Path
import re

from src.models import InstallTarget, is_install_target
from src.services.operation_lock import operation_lock


class TargetUnavailable(ValueError):
    pass


class TargetConfigError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class TargetResolver:
    def __init__(self, settings, store=None):
        self.settings = settings
        self.store = store
        self.legacy = {t.id: t for t in settings.hermes_targets}
        self.legacy_roots = {key: value.skills_root.resolve() for key, value in self.legacy.items()}
        self.profiles_root = settings.hermes_profiles_root.resolve() if settings.hermes_profiles_root else None
        if store:
            with operation_lock:
                authorized = []
                for target in settings.hermes_targets:
                    if target.id == 'hermes' or self.profiles_root is None:
                        authorized.append(target.id)
                    else:
                        try:
                            if self.profile_path(target.profile_name).resolve() == target.skills_root.resolve():
                                authorized.append(target.id)
                        except TargetUnavailable:
                            pass
                store.initialize_install_targets(settings.hermes_targets, authorized, settings._legacy_hermes_root)
                default = store.get_install_target('hermes')
                if default and default['managed'] and 'hermes' in self.legacy and default['last_root'] != str(self.legacy_roots['hermes']):
                    raise ValueError('default hermes root changed; restore its original directory')

    def profiles_base(self):
        base = self.settings.hermes_profiles_root
        if not base or self.profiles_root is None:
            raise TargetUnavailable('profiles 父目录尚未配置或挂载')
        if base.resolve() != self.profiles_root or not base.is_dir():
            raise TargetUnavailable('profiles 父目录不可用或已重定向')
        return base

    def profile_path(self, name):
        if not name or name in ('.', '..') or '/' in name or '\\' in name or '\x00' in name:
            raise TargetUnavailable('profile 名称必须是一个目录名')
        base = self.profiles_base()
        profile = base / name
        skills = profile / 'skills'
        # Reject redirection, including links that remain within the parent root.
        if profile.is_symlink() or skills.is_symlink() or skills.resolve() != self.profiles_root / name / 'skills':
            raise TargetUnavailable('profile/skills 目录发生符号链接重定向')
        return skills

    def _row(self, target):
        if self.store:
            return self.store.get_install_target(target)
        config = self.legacy.get(target)
        return dict(id=target,name=config.name,profile_name=config.profile_name,last_root=str(self.legacy_roots[target]),managed=1,removed_at='',config_revision=1) if config else None

    def root(self, target: str) -> Path:
        row = self._row(target)
        if not row or not row['managed'] or row['removed_at']:
            raise TargetUnavailable(f'目标 {target} 未配置或已移除')
        if target == 'hermes':
            item = self.legacy.get(target)
            if not item:
                raise TargetUnavailable('默认目录未配置')
            root = item.skills_root
            expected = self.legacy_roots[target]
        elif self.profiles_root is not None:
            root = self.profile_path(row['profile_name'])
            expected = Path(row['last_root'])
        else:
            # Legacy installations stay usable without the new parent mount;
            # this does not grant UI creation or arbitrary historical roots.
            item = self.legacy.get(target)
            if not item:
                raise TargetUnavailable('旧目标未配置，不能恢复历史路径权限')
            root = item.skills_root
            expected = self.legacy_roots[target]
        if root.resolve() != expected or str(expected) != row['last_root']:
            raise TargetUnavailable(f'目标 {target} 目录已变化，请恢复原目录')
        if not root.is_dir() or not os.access(root, os.R_OK | os.W_OK | os.X_OK):
            raise TargetUnavailable(f'目标 {target} 目录缺失或没有访问权限：{root}')
        return root.resolve()

    def fingerprint(self, target: str, skill_id: str):
        root = self.root(target)
        row = self._row(target)
        stat = root.stat()
        link = root / skill_id
        if link.is_symlink():
            state = ('link', os.readlink(link), link.lstat().st_ino, link.lstat().st_mtime_ns)
        elif link.exists():
            state = ('occupied', link.stat().st_ino, link.stat().st_mtime_ns)
        else:
            state = ('missing',)
        return (row['id'],row['name'],row['profile_name'],row['config_revision'],row['managed'],row['removed_at'],str(root),stat.st_dev,stat.st_ino,state)

    def editable(self, row):
        return bool(self.profiles_root and row['id'] != 'hermes' and row['managed'] and not row['removed_at'] and Path(row['last_root']) == self.profiles_root / row['profile_name'] / 'skills')

    def catalog(self):
        rows = {row['id']: row for row in self.store.list_install_targets()} if self.store else {key:self._row(key) for key in self.legacy}
        active = {}
        if self.store:
            for record in self.store.list_deployments():
                if is_install_target(record.target):
                    if record.status == 'active':
                        active[record.target] = active.get(record.target,0) + 1
                    rows.setdefault(record.target,dict(id=record.target,name=record.target,profile_name=record.target,last_root='',managed=0,removed_at='',config_revision=1))
        result = []
        for key,row in rows.items():
            reason = ''
            try:
                self.root(key)
            except (TargetUnavailable,OSError,RuntimeError) as exc:
                reason = str(exc)
            editable = self.editable(row)
            result.append(InstallTarget(id=key,name=row['name'],profile_name=row['profile_name'],install_path=row['last_root'],configured=bool(row['managed'] and not row['removed_at']),available=not reason,unavailable_reason=reason,editable=editable,deletable=editable and not active.get(key,0),removed=bool(row['removed_at']),active_installation_count=active.get(key,0),config_revision=row['config_revision']))
        return result

    def profiles(self):
        # Inspect only the authorized parent and skills directory metadata.
        base = self.profiles_base()
        rows = self.store.list_install_targets() if self.store else []
        result = []
        for directory in sorted(base.iterdir()):
            if directory.name.startswith('.') or not directory.is_dir():
                continue
            reason = ''
            skills = directory / 'skills'
            try:
                skills = self.profile_path(directory.name)
                self._validate_new_root(skills)
            except (TargetUnavailable,OSError,RuntimeError) as exc:
                reason = str(exc)
            existing = next((r for r in rows if r['profile_name']==directory.name and r['managed'] and not r['removed_at']),None)
            result.append(dict(profile_name=directory.name,skills_path=str(skills),available=not reason,unavailable_reason=reason,existing_target_id=existing['id'] if existing else None))
        return result

    def _validate_new_root(self, root):
        resolved = root.resolve()
        if not root.is_dir() or not os.access(root,os.R_OK|os.W_OK|os.X_OK):
            raise TargetUnavailable('skills 子目录缺失或没有访问权限')
        boundaries = [self.settings.skills_source_root,self.settings.github_skill_cache_root,self.settings.state_dir]
        boundaries += [Path(r['last_root']) for r in self.store.list_install_targets() if r['managed'] and not r['removed_at']] if self.store else []
        for other in boundaries:
            if resolved != other and (resolved.is_relative_to(other) or other.is_relative_to(resolved)):
                raise TargetUnavailable('skills 目录与受控源/缓存/state 或其他目标重叠')
        if any(resolved == p for p in boundaries[:3]):
            raise TargetUnavailable('skills 目录与受控源/缓存/state 重叠')
        return resolved

    def create(self, profile_name, name):
        if not name.strip():
            raise TargetConfigError('invalid_request','显示名称不能为空')
        root = self._validate_new_root(self.profile_path(profile_name))
        slug = re.sub('[^a-z0-9-]+','-',profile_name.lower()).strip('-')[:54] or 'profile'
        target = 'hermes:profile:' + slug
        rows = self.store.list_install_targets()
        collision = next((r for r in rows if r['id']==target and r['profile_name']!=profile_name),None)
        if collision:
            target += '-' + hashlib.sha256(profile_name.encode()).hexdigest()[:8]
        return self.store.create_install_target(target,profile_name,name.strip(),str(root))

    def mutate(self,target,revision,name=None):
        if target=='hermes':
            raise TargetConfigError('reserved_target','默认目录固定，只读且不可删除')
        row = self._row(target)
        if not row or not self.editable(row):
            raise TargetConfigError('target_not_found','目标不存在、已移除或不在网页管理范围')
        if name is not None and not name.strip():
            raise TargetConfigError('invalid_request','显示名称不能为空')
        return self.store.mutate_install_target(target,revision,name.strip() if name is not None else None)
