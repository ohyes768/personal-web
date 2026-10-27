"""Preview first. Explicit apply/disable require stopped writers and maintenance."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.services.address_policy_migration import preview, apply, disable


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-dir', type=Path, required=True)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--backup-dir', type=Path)
    p.add_argument('--action', choices=['preview', 'apply', 'disable'], default='preview')
    p.add_argument('--maintenance', action='store_true')
    args = p.parse_args()
    if args.data_dir.resolve() == args.plan.resolve() or args.data_dir.resolve() in args.plan.resolve().parents:
        p.error('--plan 必须位于 data-dir 之外')
    if args.action == 'preview':
        report = preview(args.data_dir)
        args.plan.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report['totals'], ensure_ascii=False))
    elif args.action == 'apply':
        if not args.backup_dir:
            p.error('apply 需要 --backup-dir')
        print(json.dumps(apply(args.data_dir, json.loads(args.plan.read_text(encoding='utf-8')),
                               args.backup_dir, maintenance=args.maintenance), ensure_ascii=False))
    else:
        print(json.dumps(disable(args.data_dir, maintenance=args.maintenance), ensure_ascii=False))


if __name__ == '__main__':
    main()
