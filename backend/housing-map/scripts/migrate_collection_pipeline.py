"""Explicit full re-review rollout. Default preview never writes business data."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.services.collection_pipeline_migration import preview, apply, rollback


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--backup-dir', type=Path)
    parser.add_argument('--action', choices=['preview', 'apply', 'rollback'], default='preview')
    parser.add_argument('--maintenance', action='store_true')
    args = parser.parse_args()
    if args.data_dir.resolve() == args.plan.resolve() or args.data_dir.resolve() in args.plan.resolve().parents:
        parser.error('--plan 必须位于 data-dir 之外')
    if args.action == 'preview':
        report = preview(args.data_dir)
        args.plan.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report['totals'], ensure_ascii=False))
    else:
        if not args.backup_dir:
            parser.error('apply/rollback 需要 --backup-dir')
        result = (apply(args.data_dir, json.loads(args.plan.read_text(encoding='utf-8')),
                        args.backup_dir, maintenance=args.maintenance) if args.action == 'apply'
                  else rollback(args.data_dir, args.backup_dir, maintenance=args.maintenance))
        print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
