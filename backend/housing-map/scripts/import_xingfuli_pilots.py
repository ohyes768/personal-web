"""Preview by default; --apply registers only proven, currently admitted pilots."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.community_registry import CommunityRegistry
from src.services.rental_reference.storage import RentalPublishLock
from src.services.xingfuli_pilots import ReadOnlyRegistry, apply, preview


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--apply', action='store_true', help='显式写入试点关联；默认只读预览')
    parser.add_argument('--maintenance', action='store_true', help='确认后台服务和其他目录写入者已停止')
    args = parser.parse_args()
    path = args.data_dir / 'community_registry.sqlite3'
    readonly = ReadOnlyRegistry(path)
    if args.apply:
        if not args.maintenance:
            raise ValueError('写入前请停止后台服务及其他目录写入者，并传入 --maintenance')
        # The live web worker does not hold this lock during network collection.
        # Refuse its persisted running state as well as concurrent publishers.
        with RentalPublishLock(args.data_dir / 'rentals' / 'rental_publish'):
            job_path = args.data_dir / 'rentals' / 'refresh_job.json'
            if job_path.exists() and json.loads(job_path.read_text(encoding='utf-8')).get('running'):
                raise ValueError('请先停止租金采集，再导入试点关联')
            report = apply(CommunityRegistry(path))
    else:
        report = preview(readonly)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
