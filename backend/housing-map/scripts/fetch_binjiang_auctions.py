"""用法：python scripts/fetch_binjiang_auctions.py --max-pages 3 --limit 2"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.services.auction_refresh import collect_auctions
from src.services.auction_store import AUCTION_PATH


def main():
    parser = argparse.ArgumentParser(description="采集来拍公开滨江住宅法拍记录（非阿里直接来源）")
    parser.add_argument("--max-pages", type=int, default=100)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--output", type=Path, default=AUCTION_PATH)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        result = collect_auctions(args.output, max_pages=args.max_pages, limit=args.limit, dry_run=args.dry_run)
    except (Exception, KeyboardInterrupt) as exc:
        print(f"collection failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
