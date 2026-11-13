"""夏普榜单历史周回填·扩展版（一次性运维脚本，容器内执行）

目标：补齐 2026-09-07 之前的历史周榜（默认 2025-01-06 ~ 2026-08-31 共 87 周；
2026-09-07 起已由原版脚本 + 定时任务覆盖，complete 周自动跳过）。

与 scripts/backfill_sharpe_board.py（原版）的差异：
1. 周范围参数化：--start-week / --end-week（周一为周键）。
2. 基准 TRI 不读库：库内 fund_benchmark 是滚动 3 年窗口（delete+insert），
   覆盖不到历史窗口且写扩展行会被周六刷新删掉。改为对「库内有 TRI 的
   code」用 fetch_benchmark_tri 现场合成扩展窗口 TRI（start = 最早
   as_of - 3 年），内存缓存复用全部周、不写库 —— 无调度时序竞争，
   合成代码与生产每周用的是同一份（口径等价）。
3. 净值/TRI 缓存可落盘（pickle）：dry-run 与正式跑共享一次网络拉取。
4. 其余口径与原版完全一致：risk-3y-v1、profile v1、rf=0、entry_predicate
   同一份谓词、base 字段用当前值近似（历史快照不存在）、trigger=backfill、
   publish_week_board 冻结语义。

TRI 合成失败的 code（重试后仍失败）：按无基准路径处理（r_b 空 →
has_bench=False → 夏普用基金净值全样本计算，与生产对无基准基金的处理
一致），打 warning 不阻塞。

用法（容器内 /app）：
  python scripts/backfill_sharpe_board_ext.py --nav-cache /tmp/nav_ext.pkl \
      --bench-cache /tmp/bench_ext.pkl          # dry-run，只算不写
  python scripts/backfill_sharpe_board_ext.py --publish --nav-cache ... --bench-cache ...
"""
import argparse
import pickle
import sys
import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import select

from src.data.benchmark_fetcher import clear_index_cache, fetch_benchmark_tri
from src.data.fund_universe import load_fund_codes
from src.data.market_subtype_map import DISCOVERY_STOCK_SUBTYPES
from src.data.nav_fetcher import fetch_nav
from src.utils.config import get_stock_funds_config_path
from src.db.models import Fund, FundBenchmark, FundPerformance, MarketFundRank
from src.db.session import SessionLocal
from src.services import sharpe_board_service as sbs
from src.services.risk_service import compute_risk_metrics
from src.services.sharpe_capture import SharpeRunCapture, freeze_base_row

TZ = ZoneInfo("Asia/Shanghai")
PROFILE_VERSION = "v1"
SOURCES = ("stock", "discovery-stock")
DEFAULT_START_WEEK = date(2025, 1, 6)
DEFAULT_END_WEEK = date(2026, 8, 31)


def build_universe(db, source: str) -> dict[str, dict]:
    """universe codes + base_rows（当前值近似）+ dd_3y 合并。与原版一致。"""
    if source == "stock":
        codes = load_fund_codes(get_stock_funds_config_path())
    else:
        profile = sbs.get_profile(source, PROFILE_VERSION)
        pre = profile["collection_prefilters"]
        subtypes = profile["market_subtypes"]
        rows = db.execute(
            select(Fund.code)
            .join(MarketFundRank, MarketFundRank.code == Fund.code)
            .where(
                Fund.market_subtype.in_(subtypes),
                Fund.size_yi >= pre["min_size_yi"],
                Fund.mgr_experience_years >= pre["min_mgr_exp"],
                MarketFundRank.ret_3y >= pre["min_ret_3y"],
            )
        ).scalars().all()
        codes = list(rows)

    base_rows: dict[str, dict] = {}
    for code in codes:
        frozen = freeze_base_row(db, code)
        if frozen is not None:
            perf = db.get(FundPerformance, code)
            frozen["dd_3y"] = perf.dd_3y if perf is not None else None
            base_rows[code] = frozen
    return base_rows


def load_nav_histories(codes: list[str], cache_path: str | None) -> dict[str, pd.DataFrame]:
    """每只拉一次全历史净值（日增长率）；--nav-cache 落盘复用。"""
    if cache_path:
        try:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
            if isinstance(cached, dict) and cached:
                print(f"nav 缓存命中 {cache_path}: {len(cached)} 只（跳过在线拉取）", flush=True)
                return cached
        except Exception as e:  # noqa: BLE001
            print(f"nav 缓存读取失败({str(e)[:80]})，改为在线拉取", flush=True)

    out: dict[str, pd.DataFrame] = {}
    failed: list[str] = []
    for i, code in enumerate(codes, 1):
        df = None
        for attempt in range(2):
            try:
                df = fetch_nav(code)
                break
            except Exception as e:  # noqa: BLE001
                if attempt == 1:
                    failed.append(code)
                    print(f"  nav 失败 {code}: {str(e)[:80]}", flush=True)
        if df is not None and not df.empty:
            out[code] = df
        if i % 50 == 0:
            print(f"  nav 进度 {i}/{len(codes)}", flush=True)
    print(f"nav 拉取：{len(out)} 成功 / {len(failed)} 失败", flush=True)

    if cache_path:
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(out, f, protocol=pickle.HIGHEST_PROTOCOL)
            print(f"nav 缓存已写入 {cache_path}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"nav 缓存写入失败: {str(e)[:80]}", flush=True)
    return out


def tri_codes(db) -> set[str]:
    """库内有 TRI 行的 code 集合。

    这些基金在生产/已发布周的夏普样本 = 净值 × 基准 join；无 TRI 的 code
    走净值全样本路径（has_bench=False）。扩展合成只对集合内且在 universe
    的 code 做，保持样本定义与已发布周一致。
    """
    rows = db.execute(
        select(FundBenchmark.code).where(FundBenchmark.tri.is_not(None)).distinct()
    ).scalars().all()
    return set(rows)


def synthesize_bench_returns(code: str, start: date, end: date, retries: int = 3) -> pd.Series:
    """现场合成扩展窗口 TRI → 日收益（pct_change）。失败重试后返回空序列。"""
    for attempt in range(1, retries + 1):
        try:
            df, source = fetch_benchmark_tri(code, start, end)
            if df.empty:
                print(f"  bench 无数据 {code}（source={source}）→ 按无基准路径", flush=True)
                return pd.Series(dtype=float)
            s = pd.Series(
                df["tri"].astype(float).values,
                index=pd.DatetimeIndex(df["date"].values),
            )
            return s.pct_change().dropna()
        except Exception as e:  # noqa: BLE001
            print(f"  bench 合成失败 {code} 第{attempt}次: {str(e)[:80]}", flush=True)
    return pd.Series(dtype=float)


def load_bench_returns(codes: list[str], ext_start: date, cache_path: str | None) -> dict[str, pd.Series]:
    """扩展 TRI 日收益缓存（仅 universe 内且库里有 TRI 的 code）。"""
    if cache_path:
        try:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
            if isinstance(cached, dict) and cached:
                print(f"bench 缓存命中 {cache_path}: {len(cached)} 只（跳过合成）", flush=True)
                return cached
        except Exception as e:  # noqa: BLE001
            print(f"bench 缓存读取失败({str(e)[:80]})，改为在线合成", flush=True)

    print(f"== 现场合成扩展基准 TRI（窗口 {ext_start} ~ 今天）==", flush=True)
    clear_index_cache()
    out: dict[str, pd.Series] = {}
    for i, code in enumerate(codes, 1):
        out[code] = synthesize_bench_returns(code, ext_start, date.today())
        if i % 50 == 0:
            print(f"  bench 进度 {i}/{len(codes)}", flush=True)
    ok = sum(1 for v in out.values() if not v.empty)
    print(f"bench 合成：{ok} 成功 / {len(codes) - ok} 无基准路径", flush=True)

    if cache_path:
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(out, f, protocol=pickle.HIGHEST_PROTOCOL)
            print(f"bench 缓存已写入 {cache_path}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"bench 缓存写入失败: {str(e)[:80]}", flush=True)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-week", type=str, default=DEFAULT_START_WEEK.isoformat(),
                        help="起始周（周一，含）")
    parser.add_argument("--end-week", type=str, default=DEFAULT_END_WEEK.isoformat(),
                        help="结束周（周一，含）")
    parser.add_argument("--publish", action="store_true", help="真正写库发布（缺省 dry-run 只算不写）")
    parser.add_argument("--nav-cache", type=str, default=None, help="净值缓存 pickle 路径")
    parser.add_argument("--bench-cache", type=str, default=None, help="扩展 TRI 日收益缓存 pickle 路径")
    args = parser.parse_args()

    start_week = date.fromisoformat(args.start_week)
    end_week = date.fromisoformat(args.end_week)
    week_starts: list[date] = []
    w = start_week
    while w <= end_week:
        week_starts.append(w)
        w += timedelta(days=7)
    mode = "PUBLISH" if args.publish else "DRY-RUN"
    print(f"回填 {len(week_starts)} 周（{start_week} ~ {end_week}）mode={mode}", flush=True)

    db = SessionLocal()
    total_written = 0
    try:
        universes: dict[str, dict[str, dict]] = {}
        for source in SOURCES:
            base_rows = build_universe(db, source)
            universes[source] = base_rows
            print(f"== {source}：universe={len(base_rows)} ==", flush=True)

        all_codes = sorted({c for br in universes.values() for c in br})
        print(f"== 拉取净值历史（{len(all_codes)} 只，一次性）==", flush=True)
        nav_shared = load_nav_histories(all_codes, args.nav_cache)

        # 扩展 TRI：最早 as_of - 3 年 起，覆盖所有目标周的 3 年窗口
        first_as_of = week_starts[0] + timedelta(days=4)
        ext_start = first_as_of - timedelta(days=365 * 3)
        codes_with_tri = sorted(set(all_codes) & tri_codes(db))
        print(f"扩展 TRI 目标 {len(codes_with_tri)} 只（universe 内且库里有 TRI）", flush=True)
        bench_shared = load_bench_returns(codes_with_tri, ext_start, args.bench_cache)

        from src.services.filter_service import entry_predicate
        from src.services.sharpe_board_service import publish_week_board

        for source in SOURCES:
            base_rows = universes[source]
            codes = list(base_rows)
            profile = sbs.get_profile(source, PROFILE_VERSION)
            pred = entry_predicate(**profile["filters"])
            subtype_set = set(profile["market_subtypes"]) if profile.get("market_subtypes") else None
            print(f"== {source}：逐周回填 {len(week_starts)} 周 ==", flush=True)

            for week in week_starts:
                as_of = week + timedelta(days=4)  # 该周周五
                started_at = datetime(as_of.year, as_of.month, as_of.day, 10, 5, tzinfo=TZ)
                assert sbs.recording_week(started_at) == week  # 周键自检
                window_start = pd.Timestamp(as_of) - pd.Timedelta(days=365 * 3)

                risk_rows: dict[str, dict] = {}
                for code in codes:
                    nav_df = nav_shared.get(code)
                    if nav_df is None or nav_df.empty:
                        continue
                    nav = nav_df[(nav_df["净值日期"] >= window_start)
                                 & (nav_df["净值日期"] <= pd.Timestamp(as_of))]
                    r_p = nav.set_index("净值日期")["日增长率"].astype(float).div(100).dropna()
                    r_b = bench_shared.get(code, pd.Series(dtype=float))
                    if not r_b.empty:
                        r_b = r_b[(r_b.index >= window_start - pd.Timedelta(days=30))
                                  & (r_b.index <= pd.Timestamp(as_of))]
                    m = compute_risk_metrics(r_p, r_b, pd.Series(dtype=float))
                    if m.sharpe is None:
                        continue
                    risk_rows[code] = {
                        "sharpe": m.sharpe,
                        "returns_end_date": m.returns_end_date,
                        "sample_days": m.sample_days,
                        "calculated_at": started_at,
                        "benchmark_source": None,
                    }

                capture = SharpeRunCapture(
                    run_id=f"backfill-ext-{source}-{week.isoformat()}-{uuid.uuid4().hex[:8]}",
                    filters=profile["filters"],
                    collection_prefilters=profile["collection_prefilters"],
                    universe_codes=codes,
                    base_rows=base_rows,
                    risk_rows=risk_rows,
                )
                # 预演入选数（与 publish 同一谓词）
                sel = 0
                for code in dict.fromkeys(codes):
                    r = risk_rows.get(code)
                    if r is None:
                        continue
                    if subtype_set is not None and base_rows[code].get("market_subtype") not in subtype_set:
                        continue
                    if pred({**base_rows[code], "sharpe": r["sharpe"]}):
                        sel += 1

                if not args.publish:
                    print(f"  [dry] {source} week={week} as_of={as_of}: 有风险值={len(risk_rows)} 预计入选={sel}", flush=True)
                    continue

                row, written = publish_week_board(
                    db, source=source, profile_version=PROFILE_VERSION, capture=capture,
                    trigger="backfill", started_at=started_at, finished_at=started_at,
                )
                total_written += int(written)
                print(f"  {source} week={week}: status={row.status} selected={row.selected_count} written={written}", flush=True)

        print(f"完成。新写入周行数={total_written}", flush=True)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
