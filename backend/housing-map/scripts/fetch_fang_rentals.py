"""Collect Fang Hangzhou asking-rent samples; see scripts/FANG_RENTALS.md."""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.fang_rentals import BASE_URL, FangClient, crawl, validate_url, write_run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--community-id', action='append', default=[], help='Fang community ID (not TMSF ID)')
    parser.add_argument('--url', action='append', default=[], help='Hangzhou Fang rental listing URL')
    parser.add_argument('--max-pages', type=int, default=3, help='Maximum pages per seed')
    parser.add_argument('--sleep', type=float, default=2, help='Seconds between all requests')
    parser.add_argument('--timeout', type=int, default=20)
    parser.add_argument('--details', action='store_true', help='Fetch detail pages for address and property type')
    parser.add_argument('--output-dir', type=Path, required=True, help='Dedicated output directory; files are replaced each run')
    args = parser.parse_args()
    if (args.max_pages < 1 or args.timeout < 1 or not math.isfinite(args.sleep) or args.sleep < 0
            or any(not cid.isascii() or not cid.isdigit() for cid in args.community_id)):
        parser.error('Invalid community ID or request limits')
    seeds = list(dict.fromkeys(args.url + [f'{BASE_URL}/hz/house-xm{cid}/' for cid in args.community_id]))
    if not seeds:
        parser.error('Supply --community-id or --url')
    for url in seeds:
        try:
            validate_url(url)
        except ValueError as error:
            parser.error(str(error))
    client = FangClient(args.timeout)
    try:
        rows, report = crawl(seeds, fetch=client.fetch, max_pages=args.max_pages,
                             delay=args.sleep, details=args.details)
    finally:
        client.close()
    write_run(rows, report, args.output_dir)
    print(f"[done] {len(rows)} listings; {report['pages_succeeded']} pages; "
          f"{report['duplicate_ids']} duplicates; {len(report['errors'])} errors; output={args.output_dir}")
    for error in report['errors']:
        print(f"[error] {error['stage']} {error['url']}: {error['error']}", file=sys.stderr)
    return 1 if report['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
