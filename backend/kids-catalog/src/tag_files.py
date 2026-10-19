"""Backed-up atomic tag updates and guarded byte-for-byte restoration."""
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from src.audio_tags import read_tags, safe_child, write_missing


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def temporary_copy(path: Path) -> Path:
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', suffix='.tagging-tmp', dir=path.parent)
    os.close(fd)
    temp = Path(name)
    try:
        shutil.copy2(path, temp)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    return temp


def sync_file(path: Path) -> None:
    with path.open('rb+') as stream:
        os.fsync(stream.fileno())


def sync_directory(path: Path) -> None:
    # Windows does not expose POSIX directory fsync through os.open.
    if os.name == 'nt':
        return
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def durable_mkdir(path: Path) -> None:
    missing = []
    cursor = path
    while not cursor.exists():
        missing.append(cursor)
        cursor = cursor.parent
    for directory in reversed(missing):
        directory.mkdir(exist_ok=True)
        sync_directory(directory)
        sync_directory(directory.parent)


def apply_rows(root: Path, rows: list[dict], backup_dir: Path) -> str | None:
    root = root.resolve(strict=True)
    backup_dir = backup_dir.resolve()
    if backup_dir == root or backup_dir.is_relative_to(root):
        raise ValueError('备份目录必须位于音频扫描根目录之外')
    run_dir = None
    for row in rows:
        if row['status'] != 'needs_change':
            continue
        temp = None
        try:
            path = safe_child(root, row['path'])
            original_hash = sha256(path)
            if read_tags(path) != row['current']:
                raise ValueError('预览后标签已改变，请重新预览')
            temp = temporary_copy(path)
            if sha256(temp) != original_hash:
                raise ValueError('复制时原文件发生变化')
            write_missing(temp, row['changes'])
            actual = read_tags(temp)
            if any(actual[k] != v for k, v in row['current'].items() if v):
                raise ValueError('原有标签发生变化，拒绝发布')
            sync_file(temp)
            edited_hash = sha256(temp)
            if run_dir is None:
                durable_mkdir(backup_dir)
                run_dir = Path(tempfile.mkdtemp(prefix='tag-run-', dir=backup_dir))
                sync_directory(backup_dir)
            backup_rel = row['path'] + '.bak'
            backup = safe_child(run_dir, backup_rel)
            durable_mkdir(backup.parent)
            shutil.copy2(path, backup)
            sync_file(backup)
            sync_directory(backup.parent)
            if sha256(backup) != original_hash or sha256(path) != original_hash:
                raise ValueError('备份期间原文件发生变化')
            entry = {'root': str(root), 'path': row['path'], 'backup': backup_rel,
                     'original_sha256': original_hash, 'edited_sha256': edited_hash}
            with (run_dir / 'manifest.jsonl').open('a', encoding='utf-8') as manifest:
                manifest.write(json.dumps(entry, ensure_ascii=False) + '\n')
                manifest.flush()
                os.fsync(manifest.fileno())
            sync_directory(run_dir)
            os.replace(temp, path)
            sync_directory(path.parent)
            row['status'] = 'applied'
        except Exception as exc:
            row.update(status='error', error=str(exc))
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)
    return str(run_dir) if run_dir else None


def restore(root: Path, run_dir: Path) -> list[dict]:
    root, run_dir = root.resolve(strict=True), run_dir.resolve(strict=True)
    if run_dir.is_relative_to(root):
        raise ValueError('备份目录不能位于音频扫描根目录内')
    manifest = safe_child(run_dir, 'manifest.jsonl')
    rows = []
    with manifest.open(encoding='utf-8') as stream:
        for line in stream:
            row = {'path': '', 'status': 'error'}
            rows.append(row)
            temp = None
            try:
                entry = json.loads(line)
                row['path'] = entry['path']
                if entry['root'] != str(root):
                    raise ValueError('恢复根目录与记录不一致')
                path = safe_child(root, entry['path'])
                backup = safe_child(run_dir, entry['backup'])
                if sha256(backup) != entry['original_sha256']:
                    raise ValueError('备份校验失败')
                current_hash = sha256(path)
                if current_hash == entry['original_sha256']:
                    row['status'] = 'already_restored'
                    continue
                if current_hash != entry['edited_sha256']:
                    raise ValueError('文件在补标签后又被修改，拒绝覆盖')
                temp = temporary_copy(path)
                shutil.copy2(backup, temp)
                sync_file(temp)
                if sha256(temp) != entry['original_sha256'] or sha256(path) != current_hash:
                    raise ValueError('恢复校验失败或原文件发生变化')
                os.replace(temp, path)
                sync_directory(path.parent)
                row['status'] = 'restored'
            except Exception as exc:
                row['error'] = str(exc)
            finally:
                if temp is not None:
                    temp.unlink(missing_ok=True)
    return rows
