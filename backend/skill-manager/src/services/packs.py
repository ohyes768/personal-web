"""Repository packs: a shared mutable checkout and one link per Agent."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from src.db import DeploymentRecord
import os
import re
import uuid
from tempfile import TemporaryDirectory
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from src.models import GithubPack, PackDeployment, PackInventoryItem, PackPlan, PackPlanItem, PackInstallResult, PackInstallItem, TargetKey
from src.services.git_cache import GitCacheError, GitTimeoutError, _remove_workspace, _SCAN_EXCLUDED_DIRS
from src.services.publisher import Publisher, force_remove_tree


class PackError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


class PackService:
    def __init__(self, settings, store, git_cache):
        self.settings, self.store, self.git_cache = settings, store, git_cache
        self.publisher = Publisher(settings, store)

    def _canonical(self, repository):
        try:
            return self.git_cache.normalize_repository(str(repository)).lower()
        except GitCacheError as exc:
            raise PackError('invalid_repository', str(exc)) from exc

    def _id(self, repository):
        base = re.sub('[^a-z0-9-]', '-', 'github-' + repository.removeprefix('https://github.com/').replace('/', '-'))
        return base[:50] + '-' + hashlib.sha256(repository.encode()).hexdigest()[:12]

    @contextmanager
    def _lock(self, repository):
        root = self.settings.github_skill_cache_root / '.locks'
        root.mkdir(exist_ok=True)
        path = root / (hashlib.sha256(repository.encode()).hexdigest() + '.lock')
        with path.open('a+b') as handle:
            handle.seek(0); handle.write(b'0'); handle.flush(); handle.seek(0)
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise PackError('repo_busy', '仓库正在执行其他操作，请稍后重试', 409) from exc
            try:
                yield
            finally:
                if os.name == 'nt':
                    import msvcrt
                    handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _git(self, *args, cwd=None):
        try:
            return self.git_cache._run_git(list(args), cwd=cwd).strip()
        except GitTimeoutError as exc:
            raise PackError('download_timeout', str(exc)) from exc
        except GitCacheError as exc:
            raise PackError('update_failed', str(exc)) from exc

    def _repo_dir(self, repository: str) -> Path:
        # GitHub names are case-insensitive; preserve an existing Linux directory's
        # spelling so legacy links and the shared checkout path remain stable.
        expected = self.git_cache.repo_cache_dir(repository)
        root = expected.parent
        if root.exists():
            if not root.is_dir() or not root.resolve().is_relative_to(self.settings.github_skill_cache_root.resolve()):
                raise PackError('cache_missing', '仓库缓存根目录超出受控范围')
            matches = [entry for entry in root.iterdir() if entry.name.casefold() == expected.name.casefold()]
            if len(matches) > 1:
                raise PackError('cache_ambiguous', '发现多个大小写等价缓存，请先人工确认保留哪一份', 409)
            if matches:
                return matches[0]
        return expected

    def _source(self, pack):
        path = self._repo_dir(pack.repository)
        if path.is_symlink() or not path.resolve().is_relative_to((self.settings.github_skill_cache_root / 'repos').resolve()):
            raise PackError('cache_missing', '仓库缓存路径超出受控目录')
        if not (path / '.git').exists():
            raise PackError('cache_missing', '仓库缓存缺失')
        return path.resolve()

    def _head(self, path):
        return self._git('rev-parse', 'HEAD', cwd=path)

    def _clean(self, path):
        if self._git('status', '--porcelain', '--untracked-files=all', cwd=path):
            raise PackError('dirty_worktree', '仓库存在本地修改，请处理后重试', 409)

    def _remote_head(self, repository):
        output = self._git('ls-remote', '--symref', self.git_cache._remote_for(repository), 'HEAD')
        branch, revision = '', ''
        for line in output.splitlines():
            if line.startswith('ref: refs/heads/'):
                branch = line.split('\t')[0].removeprefix('ref: refs/heads/')
            elif line.endswith('\tHEAD'):
                revision = line.split('\t')[0]
        if not branch or not revision:
            raise PackError('unreachable', '无法读取远端默认分支')
        return branch, revision

    def _inventory(self, path):
        inventory = []
        for candidate in self.git_cache._discover(path).candidates:
            md = path / candidate.path / 'SKILL.md'
            if md.is_symlink() or not md.resolve().is_relative_to(path.resolve()):
                continue
            inventory.append(PackInventoryItem(path=candidate.path, name=candidate.name, description=candidate.description))
        if not inventory:
            raise PackError('no_skills', '仓库中没有有效技能')
        diagnostics = []
        names = [item.name for item in inventory]
        if len(names) != len(set(names)):
            diagnostics.append('仓库内部存在重复技能名')
        paths = [item.path for item in inventory]
        if '.' in paths and len(paths) > 1:
            diagnostics.append('根技能与子技能重叠，无法保证 Agent 完整发现')
        if any(len(PurePosixPath(item.path).parts) > 5 for item in inventory):
            diagnostics.append('技能嵌套超过 Agent 支持深度')
        return inventory, diagnostics

    def add(self, repository: str, name: str = '', tags: list[str] | None = None, summary: str = '', on_progress=None) -> GithubPack:
        repository = self._canonical(repository)
        with self._lock(repository):
            return self._add_locked(repository, name, tags, summary, on_progress)

    def _add_locked(self, repository: str, name: str = '', tags: list[str] | None = None, summary: str = '', on_progress=None) -> GithubPack:
        existing = next((p for p in self.store.list_packs() if p.repository == repository), None)
        if existing:
            self._require_no_pending(existing.id)
        path = self._repo_dir(repository)
        if not (path / '.git').exists():
            if path.exists():
                raise PackError('cache_missing', '缓存目录不完整，请先修复再重试')
            if existing and existing.deployments.get('openclaw', PackDeployment()).status == 'active':
                try:
                    self._adapter().check()
                except ValueError as exc:
                    raise PackError('target_incompatible', str(exc)) from exc
            temp_root = self.settings.github_skill_cache_root / '.tmp'
            temp_root.mkdir(exist_ok=True)
            temporary = temp_root / uuid.uuid4().hex
            try:
                self.git_cache._run_git_streaming(['clone', '--progress', self.git_cache._remote_for(repository), str(temporary)], on_progress or (lambda frame: None))
                candidate_inventory, candidate_diagnostics = self._inventory(temporary)
                if existing:
                    if candidate_diagnostics:
                        raise PackError('target_incompatible', '; '.join(candidate_diagnostics), 409)
                    for target, deployment in existing.deployments.items():
                        if deployment.status == 'active':
                            try:
                                self._check_name_conflicts(existing, target, candidate_inventory)
                            except PackError as exc:
                                raise PackError('target_incompatible', str(exc), 409) from exc
                path.parent.mkdir(exist_ok=True)
                temporary.replace(path)
            except GitCacheError as exc:
                raise PackError('download_timeout' if isinstance(exc, GitTimeoutError) else 'unreachable', str(exc)) from exc
            finally:
                if temporary.exists():
                    _remove_workspace(temporary)
        inventory, diagnostics = self._inventory(self._source(GithubPack(id=self._id(repository), name='pack', repository=repository)))
        branch = self._git('symbolic-ref', '--short', 'refs/remotes/origin/HEAD', cwd=path).removeprefix('origin/') if (path / '.git/refs/remotes/origin/HEAD').exists() else ''
        if not branch:
            branch, _ = self._remote_head(repository)
        pack = existing or GithubPack(id=self._id(repository), name=name or repository.rsplit('/', 1)[-1], repository=repository, summary=summary, tags=sorted(set(tags or [])))
        pack.inventory, pack.skill_count, pack.diagnostics = inventory, len(inventory), diagnostics
        pack.current_revision = self._head(path)
        pack.tracking_branch = pack.tracking_branch or branch
        pack.source_missing = False
        if pack.deployments.get('openclaw', PackDeployment()).status == 'active':
            self._adapter().sync(pack.id, self._target('openclaw') / pack.id, [item.path for item in pack.inventory])
        self.store.upsert_pack(pack)
        self.store.append_pack_history(pack.id, 'add', 'success')
        return self.get(pack.id)


    def list(self) -> list[GithubPack]:
        return [self.get(pack.id) for pack in self.store.list_packs()]

    def _pack_repository(self, pack_id: str) -> str:
        pack = self.store.get_pack(pack_id)
        if pack is None:
            raise PackError('pack_not_found', '仓库包不存在', 404)
        return pack.repository

    def get(self, pack_id: str) -> GithubPack:
        pack = self.store.get_pack(pack_id)
        if pack is None:
            raise PackError('pack_not_found', '仓库包不存在', 404)
        try:
            source = self._repo_dir(pack.repository)
        except PackError as exc:
            pack.source_missing = True
            pack.diagnostics = [str(exc)]
            for deployment in pack.deployments.values():
                if deployment.status == 'active':
                    deployment.link_missing = True
            return pack
        pack.source_missing = not (source / '.git').exists()
        if not pack.source_missing:
            try:
                path = self._source(pack)
                pack.current_revision = self._head(path)
                pack.inventory, pack.diagnostics = self._inventory(path)
                pack.skill_count = len(pack.inventory)
            except PackError as exc:
                pack.diagnostics = [str(exc)]
        for target, deployment in pack.deployments.items():
            if deployment.status == 'active':
                link = self._target(target) / pack.id
                deployment.link_missing = not link.is_symlink() or link.resolve() != source.resolve()
        if self._pending_conversions(pack.id):
            pack.diagnostics.append('存在未完成转换，请恢复转换记录后再操作；未知链接不会被覆盖')
        pack.has_update = bool(pack.last_checked_revision and pack.last_checked_revision != pack.current_revision)
        return pack

    def check_update(self, pack_id: str) -> GithubPack:
        repository = self._pack_repository(pack_id)
        with self._lock(repository):
            pack = self.get(pack_id)
            branch, revision = self._remote_head(pack.repository)
            if pack.tracking_branch and branch != pack.tracking_branch:
                raise PackError('branch_changed', '远端默认分支发生变化，请确认跟踪分支', 409)
            pack.last_checked_revision = revision
            self.store.upsert_pack(pack)
        return self.get(pack_id)

    def update(self, pack_id: str, on_progress=None) -> GithubPack:
        repository = self._pack_repository(pack_id)
        with self._lock(repository):
            pack = self.get(pack_id)
            self._require_no_pending(pack.id)
            if pack.source_missing:
                return self._add_locked(pack.repository, on_progress=on_progress)
            path = self._source(pack); self._clean(path)
            if pack.deployments.get('openclaw', PackDeployment()).status == 'active':
                self._adapter().check()
            branch, revision = self._remote_head(pack.repository)
            if pack.tracking_branch and branch != pack.tracking_branch:
                raise PackError('branch_changed', '远端默认分支发生变化', 409)
            self._git('fetch', 'origin', 'refs/heads/' + branch, cwd=path)
            ahead = int(self._git('rev-list', '--count', 'FETCH_HEAD..HEAD', cwd=path))
            if ahead:
                raise PackError('branch_diverged', '存在本地提交，无法快进更新', 409)
            inventory, diagnostics = self._candidate_inventory(path)
            if diagnostics:
                raise PackError('target_incompatible', '; '.join(diagnostics), 409)
            for target, deployment in pack.deployments.items():
                if deployment.status == 'active':
                    try:
                        self._check_name_conflicts(pack, target, inventory)
                    except PackError as exc:
                        raise PackError('target_incompatible', str(exc), 409) from exc
            # Preserve existing branch commits; a clean legacy detached HEAD may rejoin
            # its tracking branch only when both heads are ancestors of the candidate.
            branches = self._git('for-each-ref', '--format=%(refname:short)', 'refs/heads', cwd=path).splitlines()
            if branch in branches:
                if int(self._git('rev-list', '--count', 'FETCH_HEAD..refs/heads/' + branch, cwd=path)):
                    raise PackError('branch_diverged', '跟踪分支存在本地提交，无法快进更新', 409)
                self._git('checkout', branch, cwd=path)
            else:
                self._git('checkout', '-b', branch, cwd=path)
            self._git('merge', '--ff-only', 'FETCH_HEAD', cwd=path)
            pack.current_revision = self._head(path)
            pack.tracking_branch, pack.last_checked_revision = branch, revision
            pack.inventory, pack.diagnostics = self._inventory(path)
            pack.skill_count = len(pack.inventory)
            self.store.upsert_pack(pack)
            if pack.deployments.get('openclaw', PackDeployment()).status == 'active':
                self._adapter().sync(pack.id, self._target('openclaw') / pack.id, [item.path for item in pack.inventory])
            self.store.append_pack_history(pack.id, 'update', 'success', pack.current_revision)
        return self.get(pack_id)

    def _candidate_inventory(self, checkout: Path) -> tuple[list[PackInventoryItem], list[str]]:
        # Only ephemeral SKILL.md text is materialized for the shared parser.
        # Resources and Git checkout files never move; installation keeps the root link.
        tree = self._git('ls-tree', '-r', '-z', 'FETCH_HEAD', cwd=checkout)
        candidates = []
        for entry in tree.split('\0'):
            if not entry:
                continue
            metadata, filename = entry.split('\t', 1)
            parts = PurePosixPath(filename).parts
            if metadata.split()[0] not in {'100644', '100755'} or parts[-1] != 'SKILL.md':
                continue
            if any(part.startswith('.') or part in _SCAN_EXCLUDED_DIRS for part in parts[:-1]):
                continue
            if any(part in {'.', '..'} for part in parts) or PurePosixPath(filename).is_absolute():
                raise PackError('target_incompatible', '候选技能路径不合法')
            candidates.append(filename)
        if not candidates:
            raise PackError('no_skills', '更新后的仓库不含技能')
        root = self.settings.state_dir / 'pack-checks'
        root.mkdir(exist_ok=True)
        with TemporaryDirectory(prefix='inventory-', dir=root) as temporary:
            workspace = Path(temporary)
            for filename in candidates:
                destination = workspace.joinpath(*PurePosixPath(filename).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(self._git('show', 'FETCH_HEAD:' + filename, cwd=checkout), encoding='utf-8')
            return self._inventory(workspace)

    def _check_name_conflicts(self, pack: GithubPack, target: str, inventory: list[PackInventoryItem]) -> None:
        names = {item.name for item in inventory}
        ignored = {pack.id, *(record.skill_id for record in self._legacy(pack, target))}
        for entry in self._target(target).iterdir():
            if entry.name in ignored or entry.name.startswith('.') or not entry.is_dir():
                continue
            found = self.git_cache._discover(entry).candidates
            if names & {candidate.name for candidate in found}:
                raise PackError('target_conflict', '目标目录存在同名技能：' + entry.name)
        for other in self.list():
            if other.id != pack.id and other.deployments.get(target, PackDeployment()).status == 'active' and names & {item.name for item in other.inventory}:
                raise PackError('target_conflict', '其他已安装仓库包存在同名技能')

    def _require_no_pending(self, pack_id: str) -> None:
        if self._pending_conversions(pack_id):
            raise PackError('conversion_failed', '存在未完成转换，请先处理恢复记录', 409)

    def _pending_conversions(self, pack_id: str) -> list[Path]:
        root = self.settings.state_dir / 'pack-conversions'
        return [root / (pack_id + '-' + target + '.json') for target in ('hermes', 'openclaw')
                if (root / (pack_id + '-' + target + '.json')).exists()]

    def _target(self, target):
        if str(target) not in {'hermes', 'openclaw'}:
            raise PackError('invalid_target', '安装目标仅支持 Hermes 和 OpenClaw')
        return getattr(self.settings, str(target) + '_skills_root')

    def _adapter(self):
        from src.services.openclaw_pack_discovery import OpenClawPackDiscovery
        path = getattr(self.settings, 'openclaw_config_path', None)
        if path is None:
            raise PackError('target_incompatible', 'OpenClaw 整包发现配置不可用')
        return OpenClawPackDiscovery(path, self.settings.state_dir)

    def _legacy(self, pack, target):
        return [record for record in self.store.list_deployments() if record.skill_id in self.store.list_pack_members(pack.id) and record.target == target and record.status == 'active']

    def plan(self, pack_id: str, targets: list[str]) -> PackPlan:
        pack = self.get(pack_id); items = []
        for target in dict.fromkeys(str(t) for t in targets):
            root = self._target(target); link = root / pack.id
            legacy = self._legacy(pack, target)
            message, action = '将安装仓库中的全部技能', 'convert' if legacy else 'install'
            try:
                self._source(pack)
                if pack.diagnostics:
                    raise PackError('target_incompatible', '; '.join(pack.diagnostics))
                if target == 'openclaw':
                    self._adapter().check()
                if link.is_symlink():
                    deployment = pack.deployments.get(target)
                    if not deployment or deployment.status != 'active' or link.resolve() != self._repo_dir(pack.repository).resolve():
                        raise PackError('target_conflict', '现有链接不属于此仓库包')
                    action = 'none'
                elif link.exists():
                    raise PackError('target_conflict', '包安装路径被普通目录或文件占用')
                for record in legacy:
                    old = root / record.skill_id
                    if not old.is_symlink() or old.resolve() != Path(record.current_link_target).resolve():
                        raise PackError('target_conflict', '旧安装链接被修改或缺失：' + record.skill_id)
                self._check_name_conflicts(pack, target, pack.inventory)
            except (PackError, ValueError) as exc:
                action, message = 'blocked', str(exc)
            items.append(PackPlanItem(target=target, action=action, message=message, legacy_skill_ids=[r.skill_id for r in legacy]))
        return PackPlan(items=items)

    def install(self, pack_id: str, targets: list[str]) -> PackInstallResult:
        repository = self._pack_repository(pack_id); results = []
        with self._lock(repository):
            pack = self.get(pack_id)
            self._require_no_pending(pack.id)
            for item in self.plan(pack_id, targets).items:
                if item.action == 'blocked':
                    results.append(PackInstallItem(target=item.target,status='blocked',message=item.message)); continue
                removed = []; adapter = None; snapshot = None; journal = None; link = self._target(item.target) / pack.id
                was_link = link.is_symlink()
                try:
                    source = self._source(pack); self._clean(source)
                    legacy = self._legacy(pack, item.target)
                    if item.target == 'openclaw':
                        adapter = self._adapter(); snapshot = adapter.snapshot(pack.id)
                    journal = self._write_conversion_journal(pack, item.target, legacy, snapshot, was_link)
                    if not was_link:
                        self.publisher._atomic_swap(pack.id, TargetKey(item.target), source)
                    if adapter:
                        adapter.sync(pack.id, link, [entry.path for entry in pack.inventory])
                    for record in legacy:
                        old = self._target(item.target) / record.skill_id
                        removed.append((old, old.readlink())); old.unlink()
                    pack.deployments[item.target] = PackDeployment(status='active', link_target=str(source))
                    self.store.persist_pack_conversion(pack, [replace(record, status='removed') for record in legacy])
                    self.store.append_pack_history(pack.id, 'install', 'success', item.target)
                    journal.unlink()
                    results.append(PackInstallItem(target=item.target,status='success',message='包链接已安装；Agent 识别尚未验证'))
                except Exception as exc:
                    for old, destination in removed:
                        if not old.exists() and not old.is_symlink(): old.symlink_to(destination, target_is_directory=True)
                    if not was_link and link.is_symlink(): link.unlink()
                    if adapter and snapshot is not None: adapter.restore(snapshot)
                    if journal is not None:
                        self._restore_conversion(journal)
                    pack = self.get(pack_id)
                    results.append(PackInstallItem(target=item.target,status='error',message=str(exc)))
        return PackInstallResult(items=results)

    def uninstall(self, pack_id: str, target: str) -> GithubPack:
        repository = self._pack_repository(pack_id)
        with self._lock(repository):
            pack = self.get(pack_id)
            self._require_no_pending(pack.id)
            link = self._target(target) / pack.id
            deployment = pack.deployments.get(str(target))
            if deployment and deployment.status == 'legacy_pending':
                raise PackError('legacy_pending', '请先转换旧安装，再卸载仓库包')
            if link.is_symlink():
                if not deployment or deployment.status != 'active' or link.resolve() != self._repo_dir(pack.repository).resolve():
                    raise PackError('target_conflict', '不能移除未知链接')
                if str(target) == 'openclaw': self._adapter().remove(pack.id)
                link.unlink()
            elif link.exists():
                raise PackError('target_conflict', '不能移除普通目标目录')
            pack.deployments[str(target)] = PackDeployment(status='removed')
            self.store.upsert_pack(pack)
            self.store.append_pack_history(pack.id, 'uninstall', 'success', str(target))
        return self.get(pack_id)

    def delete(self, pack_id: str) -> None:
        repository = self._pack_repository(pack_id)
        with self._lock(repository):
            pack = self.get(pack_id)
            self._require_no_pending(pack.id)
            if any(d.status in {'active','legacy_pending'} for d in pack.deployments.values()):
                raise PackError('pack_in_use', '请先卸载所有目标再删除', 409)
            members = self.store.list_pack_members(pack.id)
            if any(record.skill_id in members and record.status == 'active' for record in self.store.list_deployments()):
                raise PackError('pack_in_use', '仍有旧部署或导出台账引用', 409)
            path = self._repo_dir(pack.repository)
            if path.exists():
                self._source(pack); self._clean(path); force_remove_tree(path)
            self.store.delete_pack(pack.id)

    def _write_conversion_journal(self, pack, target, records, snapshot, was_link):
        root = self.settings.state_dir / 'pack-conversions'
        root.mkdir(exist_ok=True)
        path = root / (pack.id + '-' + target + '.json')
        payload = {'pack': pack.model_dump(), 'target': target, 'records': [asdict(record) for record in records],
                   'adapter': snapshot, 'was_link': was_link,
                   'links': {record.skill_id: str((self._target(target) / record.skill_id).readlink()) for record in records}}
        temporary = path.with_suffix('.tmp')
        with temporary.open('w', encoding='utf-8') as handle:
            json.dump(payload, handle, ensure_ascii=False)
            handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
        return path

    def _restore_conversion(self, journal):
        payload = json.loads(journal.read_text(encoding='utf-8'))
        pack = GithubPack.model_validate(payload['pack'])
        target = payload['target']; root = self._target(target); link = root / pack.id
        source = self._repo_dir(pack.repository).resolve()
        if link.is_symlink() and link.resolve() != source:
            raise PackError('conversion_failed', '转换恢复遇到未知包链接，保留恢复记录')
        if link.exists() and not link.is_symlink():
            raise PackError('conversion_failed', '转换恢复遇到普通目录，保留恢复记录')
        for skill_id, destination in payload['links'].items():
            if self.store.get_pack_for_skill(skill_id) != pack.id:
                raise PackError('conversion_failed', '转换恢复成员映射不匹配')
            old = root / skill_id
            if (old.exists() or old.is_symlink()) and (not old.is_symlink() or str(old.readlink()) != destination):
                raise PackError('conversion_failed', '转换恢复遇到已修改旧链接，保留恢复记录')
        if not payload['was_link'] and link.is_symlink(): link.unlink()
        for skill_id, destination in payload['links'].items():
            old = root / skill_id
            if not old.is_symlink(): old.symlink_to(destination, target_is_directory=True)
        if payload['adapter'] is not None: self._adapter().restore(payload['adapter'])
        self.store.persist_pack_conversion(pack, [DeploymentRecord(**record) for record in payload['records']])
        journal.unlink()

    def recover_conversions(self) -> None:
        root = self.settings.state_dir / 'pack-conversions'
        if not root.exists(): return
        for journal in root.glob('*.json'):
            payload = json.loads(journal.read_text(encoding='utf-8'))
            with self._lock(payload['pack']['repository']):
                self._restore_conversion(journal)

    def migrate_legacy(self) -> None:
        # Pure data migration: no Git commands, network, link writes or snapshots.
        for skill in self.store.list_registry_skills():
            if str(skill.source) != 'github' or self.store.get_pack_for_skill(skill.id):
                continue
            repository = self._canonical(skill.repository)
            with self._lock(repository):
                if self.store.get_pack_for_skill(skill.id):
                    continue
                pack = next((p for p in self.store.list_packs() if p.repository == repository), None)
                if pack is None:
                    pack = GithubPack(id=self._id(repository), name=repository.rsplit('/',1)[-1], repository=repository)
                pack.tags = sorted(set(pack.tags) | set(skill.tags))
                for record in self.store.list_deployments():
                    if record.skill_id == skill.id and record.target in {'hermes','openclaw'} and record.status == 'active' and pack.deployments.get(record.target, PackDeployment()).status != 'active':
                        pack.deployments[record.target] = PackDeployment(status='legacy_pending', link_target=record.current_link_target, diagnostic='旧安装需要转换为整包安装')
                self.store.migrate_pack_member(pack, skill.id)
