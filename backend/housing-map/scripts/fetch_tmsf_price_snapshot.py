"""透明售房网价格采集的命令行入口。

实际传输、解析和快照构建都在 ``src.services.tmsf_fetcher``，HTTP refresh
与此脚本共用同一逻辑；保留本文件仅供人工批量执行。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.tmsf_fetcher import (
    BASE_URL,
    PriceSnapshot,
    TmsfClient,
    build_snapshots,
    decode_response_bytes,
    fetch_community_snapshots,
    input_value_by_id,
    parse_index_page,
    parse_tendency_page,
    strip_tags,
    write_outputs,
)


def fetch_html(url: str, timeout: int) -> str:
    """供旧维护脚本调用的兼容入口。"""
    return TmsfClient().fetch_text(url, timeout)


def fetch_html_with_curl(url: str, timeout: int) -> str:
    """历史名称兼容；不再降级到无浏览器指纹的系统 curl。"""
    return fetch_html(url, timeout)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch low-frequency TMSF community price snapshots.")
    parser.add_argument("--community-id", action="append", required=True, help="TMSF community id, e.g. 10001734")
    parser.add_argument("--output-dir", default="data", help="Output directory, default: data")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout seconds")
    parser.add_argument("--sleep", type=float, default=2.0, help="Delay between communities")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    snapshots: list[PriceSnapshot] = []
    for index, raw_community_id in enumerate(args.community_id):
        community_id = raw_community_id.strip()
        result = fetch_community_snapshots(community_id, timeout=args.timeout)
        if result.snapshots:
            snapshots.extend(result.snapshots)
            suffix = f" (partial: {'; '.join(result.errors)})" if result.errors else ""
            print(f"[ok] {community_id}: {len(result.snapshots)} snapshots{suffix}")
        else:
            print(f"[error] {community_id}: {'; '.join(result.errors) or 'no verified price'}")
        if index < len(args.community_id) - 1:
            time.sleep(args.sleep)

    write_outputs(snapshots, Path(args.output_dir))
    print(f"[done] wrote {len(snapshots)} snapshots to {args.output_dir}")
    return 0 if snapshots else 1


if __name__ == "__main__":
    raise SystemExit(main())
