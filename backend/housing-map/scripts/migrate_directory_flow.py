"""Preview by default. Apply/rollback only in an explicit offline maintenance window."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.services.directory_migration import preview, apply, rollback

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--data-dir', type=Path, required=True)
parser.add_argument('--plan', type=Path, required=True, help='Preview output / reviewed apply input')
parser.add_argument('--backup-dir', type=Path)
parser.add_argument('--action', choices=['preview', 'apply', 'rollback'], default='preview')
parser.add_argument('--maintenance', action='store_true', help='Backend and CLI writers have been stopped')
args = parser.parse_args()
if args.data_dir.resolve() in args.plan.resolve().parents:
    parser.error('--plan must be outside data-dir to keep the snapshot stable')
if args.action == 'preview':
    report = preview(args.data_dir)
    args.plan.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({'snapshot_id': report['snapshot_id'], **report['totals']}, ensure_ascii=False))
else:
    if not args.backup_dir:
        parser.error('--backup-dir is required')
    if args.action == 'apply':
        report = apply(args.data_dir, json.loads(args.plan.read_text()), args.backup_dir, maintenance=args.maintenance)
    else:
        report = rollback(args.data_dir, args.backup_dir, maintenance=args.maintenance)
    print(json.dumps(report, ensure_ascii=False))
