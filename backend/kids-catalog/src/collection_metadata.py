"""Generation-time, fill-only metadata with audited crash recovery (no audio backup)."""
import hashlib
import json
import os
from contextlib import nullcontext
from pathlib import Path

from src.audio_tags import DEFAULT_ARTIST, NUMBERED, read_tags, safe_child, write_missing
from src.tag_files import sha256, sync_directory, sync_file, temporary_copy


class MetadataError(ValueError):
    pass


def audit_path(audit_dir, folder):
    return Path(audit_dir) / (hashlib.sha256(folder.encode()).hexdigest() + '.jsonl')


def stat_row(path):
    stat = path.stat()
    return [path.name, stat.st_size, stat.st_mtime_ns]


def recover_manifest(root, folder, stored, observed, audit_dir):
    """Only acknowledge exact file revisions prepared by this service itself."""
    if stored == observed:
        return observed
    old = {r[0]: r for r in stored}
    new = {r[0]: r for r in observed}
    if old.keys() != new.keys():
        raise MetadataError('文件已变化，请核对完成情况')
    journal = audit_path(audit_dir, folder)
    entries = {}
    if journal.exists():
        with journal.open(encoding='utf-8') as stream:
            for line in stream:
                try:
                    entry = json.loads(line)
                    if entry.get('folder') == folder:
                        entries[entry['before'][0]] = entry
                except (ValueError, KeyError, TypeError):
                    continue
    for name, row in new.items():
        if row == old[name]:
            continue
        entry = entries.get(name)
        if not entry or entry['before'] != old[name] or entry['after'] != row:
            raise MetadataError('文件已变化，请核对完成情况')
        path = safe_child(Path(root), folder + '/' + name)
        if sha256(path) != entry['after_sha256']:
            raise MetadataError('文件已变化，请核对完成情况')
    return observed


def prepare_collection(root, folder, title, manifest, audit_dir, checkpoint, guard=None):
    root = Path(root)
    expected = [list(r) for r in manifest]
    plans = []
    for row in expected:
        path = safe_child(root, folder + '/' + row[0])
        if stat_row(path) != row:
            raise MetadataError('生成期间音频发生变化，请重新生成')
        current = read_tags(path)
        if current['album'] and current['album'] != [title]:
            raise MetadataError('现有专辑标签与合集名称冲突，请先核对标签')
        number = current['tracknumber']
        match = NUMBERED.fullmatch(path.stem)
        if number:
            raw = number[0].split('/')[0]
            if len(number) != 1 or not raw.isdecimal() or not 1 <= int(raw) <= 65535:
                raise MetadataError('现有曲序标签无效，请先核对标签')
            position = int(raw)
        elif match and 1 <= int(match[1]) <= 65535:
            position = int(match[1])
        else:
            raise MetadataError('缺少曲序且文件名无有效编号，请先整理标签')
        plans.append((path, current, position, match))
    positions = [p[2] for p in plans]
    if len(positions) != len(set(positions)):
        raise MetadataError('合集曲序重复，请先核对标签')
    album_artists = {tuple(c['albumartist']) for _, c, _, _ in plans if c['albumartist']}
    artists = {tuple(c['artist']) for _, c, _, _ in plans if c['artist']}
    if len(album_artists) > 1:
        raise MetadataError('合集存在多个专辑艺术家，请先核对标签')
    selected = list(next(iter(album_artists)) if album_artists else
                    next(iter(artists)) if len(artists) == 1 else (DEFAULT_ARTIST,))
    changes = []
    for path, current, position, match in plans:
        proposed = {'album': [title], 'title': current['title'] or [match[2] if match else path.stem],
                    'tracknumber': [str(position)], 'artist': current['artist'] or selected,
                    'albumartist': selected}
        changes.append({k: v for k, v in proposed.items() if not current[k]})
    updated = 0
    for index, ((path, current, _, _), change) in enumerate(zip(plans, changes, strict=True)):
        if not change:
            continue
        temp = None
        try:
            # The owner holds its generation token/completion transaction across
            # publication + checkpoint, so a superseding worker cannot interleave.
            with guard() if guard else nullcontext():
                if stat_row(path) != expected[index] or read_tags(path) != current:
                    raise MetadataError('生成期间音频发生变化，请重新生成')
                before_hash = sha256(path)
                temp = temporary_copy(path)
                if sha256(temp) != before_hash:
                    raise MetadataError('复制期间音频发生变化，请重试')
                write_missing(temp, change)
                actual = read_tags(temp)
                if any(actual[k] != v for k, v in current.items() if v):
                    raise MetadataError('原有标签校验失败，未覆盖文件')
                sync_file(temp)
                after_row = [path.name, temp.stat().st_size, temp.stat().st_mtime_ns]
                after_hash = sha256(temp)
                if stat_row(path) != expected[index] or sha256(path) != before_hash:
                    raise MetadataError('发布前音频发生变化，请重试')
                journal = audit_path(audit_dir, folder)
                journal.parent.mkdir(parents=True, exist_ok=True)
                with journal.open('a', encoding='utf-8') as log:
                    log.write(json.dumps({'folder': folder, 'before': expected[index],
                        'after': after_row, 'before_sha256': before_hash,
                        'after_sha256': after_hash, 'changes': change}, ensure_ascii=False) + '\n')
                    log.flush()
                    os.fsync(log.fileno())
                sync_directory(journal.parent)
                sync_directory(journal.parent.parent)
                os.replace(temp, path)
                sync_directory(path.parent)
                expected[index] = after_row
                checkpoint([list(r) for r in expected])
                updated += 1
        except (OSError, MetadataError) as exc:
            if isinstance(exc, MetadataError):
                raise
            raise MetadataError('音频标签写入失败，请检查文件权限和磁盘空间') from exc
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)
    return expected, updated
