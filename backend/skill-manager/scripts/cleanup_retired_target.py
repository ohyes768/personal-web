"""Dry-run by default; remove only unchanged manager-owned retired links.

Run before removing the old mount, using the migration backup or archived rows.
No source directories, regular files, foreign links or Hermes entries are removed.
"""
import argparse
import json
import os
from pathlib import Path
import sqlite3


def cleanup(db: Path, root: Path, execute: bool = False):
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError('target root must be a directory')
    with sqlite3.connect(f'file:{db.resolve()}?mode=ro', uri=True) as conn:
        table = 'retired_deployment' if conn.execute("SELECT 1 FROM sqlite_master WHERE name='retired_deployment'").fetchone() else 'deployment'
        records = conn.execute(f"SELECT skill_id,current_link_target,status FROM {table} WHERE target='openclaw'").fetchall()
    results = []
    for skill_id, expected, status in records:
        link = root / skill_id
        if not skill_id or Path(skill_id).name != skill_id or skill_id in ('.', '..'):
            results.append({'skill_id': skill_id, 'status': 'invalid_id'}); continue
        if status != 'active' or not link.is_symlink():
            results.append({'skill_id': skill_id, 'status': 'skipped'}); continue
        # Lexical link target comparison: never follow a dangling/foreign link.
        actual = os.readlink(link)
        if os.path.normpath(actual) != os.path.normpath(expected):
            results.append({'skill_id': skill_id, 'status': 'modified_link'}); continue
        if execute:
            link.unlink()
        results.append({'skill_id': skill_id, 'status': 'removed' if execute else 'would_remove', 'target': actual})
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    print(json.dumps(cleanup(args.db, args.root, args.execute), ensure_ascii=False, indent=2))
