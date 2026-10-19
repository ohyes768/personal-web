"""Run `python -m src.tag_audio --help` for the conservative tag repair CLI."""
import argparse
import json
from collections import Counter
from pathlib import Path

from src.audio_tags import scan
from src.tag_files import apply_rows, restore


def run(root: Path, *, album: str | None = None, apply: bool = False,
        backup_dir: Path | None = None) -> dict:
    root = Path(root).resolve(strict=True)
    if apply and backup_dir is None:
        raise ValueError('--apply 必须指定扫描目录外的 --backup-dir')
    rows = scan(root, album)
    run_dir = apply_rows(root, rows, Path(backup_dir)) if apply else None
    return {'mode': 'apply' if apply else 'preview', 'root': str(root),
            'run_dir': run_dir, 'summary': dict(Counter(r['status'] for r in rows)), 'files': rows}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='为已下载 MP3/M4A 只补缺失标签；默认只读预览，冲突跳过')
    parser.add_argument('--root', required=True, type=Path, help='音频根目录，直接子目录为合集')
    parser.add_argument('--album', help='只处理一个直属合集目录（精确名称）')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true', help='备份后补标签')
    mode.add_argument('--restore', type=Path, help='从 tag-run-* 目录恢复原始文件')
    parser.add_argument('--backup-dir', type=Path, help='备份父目录，必须在扫描根目录之外')
    args = parser.parse_args(argv)
    if args.restore and (args.album or args.backup_dir):
        parser.error('--restore 不能与 --album/--backup-dir 同用')
    try:
        if args.restore:
            rows = restore(args.root, args.restore)
            report = {'mode': 'restore', 'files': rows,
                      'summary': dict(Counter(r['status'] for r in rows))}
        else:
            report = run(args.root, album=args.album, apply=args.apply, backup_dir=args.backup_dir)
    except (OSError, ValueError) as exc:
        parser.exit(1, str(exc) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report['summary'].get('error'):
        return 1
    if report['summary'].get('conflict') or report['summary'].get('skipped'):
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
