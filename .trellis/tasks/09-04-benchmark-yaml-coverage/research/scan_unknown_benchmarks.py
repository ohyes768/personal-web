"""09-04-benchmark-yaml-coverage：全量扫描股票宇宙基金基准公式的 unknown 成分。

产出：
- tmp/benchmark_formulas.json（code -> 公式缓存，离线复用）
- stdout：unknown 主成分基金数 / unknown 成分明细（按类别分组）
用法：.venv python tmp/scan_unknown_benchmarks.py [--offline]
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "fund-select"))

from src.data.benchmark_fetcher import parse_formula  # noqa: E402
from src.data.fund_basic_fetcher import fetch_basic  # noqa: E402
from src.data.fund_universe import resolve_universe_codes  # noqa: E402

FORMULAS_PATH = ROOT / "tmp" / "benchmark_formulas.json"


def load_formulas(codes: list[str], offline: bool) -> dict[str, str]:
    cache: dict[str, str] = {}
    if FORMULAS_PATH.exists():
        cache = json.loads(FORMULAS_PATH.read_text(encoding="utf-8"))
    if offline:
        return {c: cache.get(c, "") for c in codes}
    missing = [c for c in codes if c not in cache]
    for i, code in enumerate(missing, 1):
        try:
            info = fetch_basic(code)
            raw = str(info.get("业绩比较基准") or "").strip()
        except Exception as e:  # noqa: BLE001
            raw = ""
            print(f"  [{i}/{len(missing)}] {code} fetch 失败: {str(e)[:80]}")
        cache[code] = raw
        print(f"  [{i}/{len(missing)}] {code} ok")
        FORMULAS_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    return {c: cache.get(c, "") for c in codes}


def main() -> None:
    offline = "--offline" in sys.argv
    codes = resolve_universe_codes("stock")
    print(f"股票宇宙 {len(codes)} 只")
    formulas = load_formulas(codes, offline)

    n_unknown_major = 0
    unknown_rows: list[tuple[str, str, float]] = []  # code, name, weight
    for code in codes:
        comps = parse_formula(formulas.get(code, ""))
        unknowns = [c for c in comps if c.kind == "unknown"]
        if not unknowns:
            continue
        for c in unknowns:
            unknown_rows.append((code, c.name, c.weight))
        if max(c.weight for c in unknowns) >= 0.5:
            n_unknown_major += 1

    print(f"\n=== 含 unknown 成分基金: {len({r[0] for r in unknown_rows})} / {len(codes)}")
    print(f"=== unknown 主成分(weight>=50%)基金: {n_unknown_major}")
    print("\n=== unknown 成分明细（name -> 出现次数, 最大权重, 基金）===")
    by_name: dict[str, list] = {}
    for code, name, w in unknown_rows:
        by_name.setdefault(name, []).append((code, w))
    for name, rows in sorted(by_name.items(), key=lambda kv: -max(w for _, w in kv[1])):
        codes_str = ",".join(sorted(c for c, _ in rows))
        print(f"  {name} | n={len(rows)} maxw={max(w for _, w in rows):.0%} | {codes_str}")
    print(f"\n=== name 种类: {len(by_name)}")
    print("=== 前缀形态抽样（unknown 名字首 8 字）===")
    print(Counter(n[:8] for n in by_name))


if __name__ == "__main__":
    main()
