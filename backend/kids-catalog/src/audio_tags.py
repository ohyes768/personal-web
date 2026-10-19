"""Conservative metadata plans for the existing flat /kids album layout."""
import re
from collections import Counter
from pathlib import Path

import mutagen
from mutagen.easymp4 import EasyMP4
from mutagen.mp3 import EasyMP3

FIELDS = ('album', 'title', 'tracknumber', 'artist', 'albumartist')
NUMBERED = re.compile(r'^(\d+)-(.+)$')
DEFAULT_ARTIST = '哆咪音频'


def open_audio(path: Path):
    audio = mutagen.File(path, easy=True)
    if not isinstance(audio, (EasyMP3, EasyMP4)):
        raise ValueError('不是可识别的 MP3/M4A 音频')
    return audio


def read_tags(path: Path) -> dict:
    audio = open_audio(path)
    return {k: [str(v) for v in audio.get(k, []) if str(v).strip()] for k in FIELDS}


def write_missing(path: Path, changes: dict) -> None:
    audio = open_audio(path)
    if audio.tags is None:
        audio.add_tags()
    for key, value in changes.items():
        audio[key] = value
    audio.save()
    actual = read_tags(path)
    if any(actual[key] != value for key, value in changes.items()):
        raise ValueError('标签写入后读回校验失败')


def safe_child(base: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or '..' in rel.parts or not rel.parts:
        raise ValueError('路径必须位于指定目录内')
    target = base / rel
    if not target.resolve().is_relative_to(base.resolve()):
        raise ValueError('路径越界')
    cursor = target
    while cursor != base:
        if cursor.is_symlink() or cursor.is_junction():
            raise ValueError('不跟随符号链接或 junction')
        cursor = cursor.parent
    return target


def scan(root: Path, album: str | None = None) -> list[dict]:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError('root 必须是音频根目录')
    if album is not None:
        if Path(album).name != album or album in ('.', '..'):
            raise ValueError('album 必须是直属合集目录名')
        folder = safe_child(root, album)
        if not folder.is_dir():
            raise ValueError('合集目录不存在')
        folders = [folder]
    else:
        folders = sorted(root.iterdir())
    result = []
    for folder in folders:
        if folder.is_symlink() or folder.is_junction():
            result.append({'path': folder.name, 'status': 'skipped', 'error': '跳过链接'})
            continue
        if not folder.is_dir():
            if folder.suffix.lower() in ('.mp3', '.m4a'):
                result.append({'path': folder.name, 'status': 'skipped', 'error': '根目录文件没有合集目录'})
            continue
        rows = []
        for path in sorted(folder.iterdir()):
            if path.suffix.lower() not in ('.mp3', '.m4a'):
                continue
            row = {'path': path.relative_to(root).as_posix(), 'status': 'skipped',
                   'current': {}, 'proposed': {}, 'changes': {}, 'conflicts': {}}
            rows.append(row)
            try:
                safe_child(root, row['path'])
                if not path.is_file():
                    raise ValueError('不是普通文件')
                match = NUMBERED.fullmatch(path.stem)
                if match and 1 <= int(match[1]) <= 65535 and match[2].strip():
                    row['proposed'] = {'album': [folder.name], 'title': [match[2].strip()],
                                       'tracknumber': [str(int(match[1]))]}
                # Even corrupt files retain their filename-derived number for
                # duplicate detection; unnumbered readable files supply artists.
                row['current'] = read_tags(path)
                if not row['proposed']:
                    row['error'] = '无法从 NNN-标题 文件名推导有效曲序和标题'
                    continue
                row['status'] = 'pending'
            except Exception as exc:
                row.update(status='error', error=str(exc))
        numbers = Counter(r['proposed'].get('tracknumber', [''])[0] for r in rows if r['proposed'])
        duplicate = any(n and count > 1 for n, count in numbers.items())
        album_artists = {tuple(r['current'].get('albumartist', [])) for r in rows
                         if r['current'].get('albumartist')}
        artists = {tuple(r['current'].get('artist', [])) for r in rows if r['current'].get('artist')}
        selected = next(iter(album_artists)) if len(album_artists) == 1 else (
            next(iter(artists)) if len(artists) == 1 else (DEFAULT_ARTIST,))
        for row in rows:
            if row['status'] != 'pending':
                continue
            current, proposed = row['current'], row['proposed']
            proposed['albumartist'] = list(selected)
            proposed['artist'] = current['artist'] or list(selected)
            if duplicate or len(album_artists) > 1:
                row['conflicts']['folder'] = '合集曲序重复' if duplicate else '合集存在多个专辑艺术家'
            for key in ('album', 'title', 'tracknumber'):
                if current[key]:
                    if key == 'tracknumber':
                        raw = current[key][0].split('/')[0]
                        matches = raw.isdigit() and int(raw) == int(proposed[key][0]) and len(current[key]) == 1
                    else:
                        matches = current[key] == proposed[key]
                    if not matches:
                        row['conflicts'][key] = {'current': current[key], 'proposed': proposed[key]}
            row['changes'] = {k: v for k, v in proposed.items() if not current[k]}
            row['status'] = ('conflict' if row['conflicts'] else
                             'needs_change' if row['changes'] else 'unchanged')
        result.extend(rows)
    return result
