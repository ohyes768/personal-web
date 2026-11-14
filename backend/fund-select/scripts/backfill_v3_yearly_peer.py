"""夏普榜单 v3 历史周回填（年度同类排名口径，容器内执行）

与 backfill_sharpe_board_ext.py（v1 口径）的差异：

1. **profile v3**：入选规则是「v1 五条件 + IR≥0.5 + 样本≥700 +
   近3个完整年度中至少2年同类排名前25%」。ext 脚本用的 v1 五条件不适用。
2. **risk_rows 补 ir / sample_days**：v3 需要这两项。ext 脚本只存 sharpe，
   因为 v1 不卡它们。IR 需要基准，故 `r_b` 必须参与 `compute_risk_metrics`。
3. **peer 数据（年度排名）一次冻结、全周共享**：年度排名是「某自然年的
   最终排名」历史固定值，不随周变化（实测库内 as_of=2026-09-09 的值与
   2026-11-14 实时接口逐字一致）。这与净值「必须按周算」形成对比。
4. **完全可回溯的根据**：v2 用滚动分位（「截至今天」），历史不存在，只能
   从上线周积累；v3 用年度排名，每周判定都能用同一份数据复现，故能补历史。

口径真实性：
  - 夏普 / IR / 样本天数：按「当周往前 3 年」的净值+基准窗口算，绝不用今天的值
  - 年度排名：历史固定事实，全周共享不构成前视偏差

用法（容器内 /app）：
  python scripts/backfill_v3_yearly_peer.py --nav-cache /tmp/nav_v3.pkl \
      --bench-cache /tmp/bench_v3.pkl                    # dry-run，只算不写
  python scripts/backfill_v3_yearly_peer.py --publish --nav-cache ... --bench-cache ...

幂等：已存在 complete 周的 (source, v3, week) 会被 publish_week_board 跳过。
重跑前若想重建，先 `DELETE FROM sharpe_board_* WHERE profile_version='v3'`。
"""
import argparse
import pickle
import sys
import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import select

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from src.data.benchmark_fetcher import clear_index_cache, fetch_benchmark_tri  # noqa: E402
from src.data.fund_universe import load_fund_codes  # noqa: E402
from src.data.market_subtype_map import DISCOVERY_STOCK_SUBTYPES  # noqa: E402
from src.data.nav_fetcher import fetch_nav  # noqa: E402
from src.db.models import Fund, FundBenchmark, FundPerformance, MarketFundRank  # noqa: E402
from src.db.session import SessionLocal  # noqa: E402
from src.services import sharpe_board_service as sbs  # noqa: E402
from src.services.filter_service import entry_predicate  # noqa: E402
from src.services.risk_service import compute_risk_metrics  # noqa: E402
from src.services.sharpe_capture import (  # noqa: E402
    SharpeRunCapture, freeze_base_row, freeze_yearly_peer_rows,
)
from src.utils.config import get_stock_funds_config_path  # noqa: E402

TZ = ZoneInfo("Asia/Shanghai")
PROFILE_VERSION = "v3"
SOURCES = ("stock", "discovery-stock")
DEFAULT_START_WEEK = date(2025, 1, 6)
DEFAULT_END_WEEK = date(2026, 11, 2)   # 最新已发布周的前一周；v3 自己的周由任务产出


def build_universe(db, source: str) -> dict[str, dict]:
    """universe codes + base_rows（当前值近似）+ dd_3y 合并。"""
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
                print(f"nav 缓存命中 {cache_path}: {len(cached)} 只", flush=True)
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
    """库内有 TRI 行的 code（决定哪些基金走「有基准」路径）。"""
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
                print(f"bench 缓存命中 {cache_path}: {len(cached)} 只", flush=True)
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
    parser.add_argument("--start-week", type=str, default=DEFAULT_START_WEEK.isoformat())
    parser.add_argument("--end-week", type=str, default=DEFAULT_END_WEEK.isoformat())
    parser.add_argument("--publish", action="store_true", help="真正写库（缺省 dry-run）")
    parser.add_argument("--nav-cache", type=str, default=None)
    parser.add_argument("--bench-cache", type=str, default=None)
    parser.add_argument("--ref-year", type=int, default=None,
                        help="年度窗口基准年（默认今天所在年）")
    args = parser.parse_args()

    start_week = date.fromisoformat(args.start_week)
    end_week = date.fromisoformat(args.end_week)
    week_starts: list[date] = []
    w = start_week
    while w <= end_week:
        week_starts.append(w)
        w += timedelta(days=7)
    mode = "PUBLISH" if args.publish else "DRY-RUN"
    ref_year = args.ref_year or date.today().year
    print(f"回填 {len(week_starts)} 周（{start_week} ~ {end_week}）"
          f"profile={PROFILE_VERSION} 年度窗口={ref_year - 3}~{ref_year - 1} mode={mode}",
          flush=True)

    db = SessionLocal()
    total_written = 0
    try:
        # 年度排名：一次冻结、全周共享（历史固定值，不随周变化）
        universes: dict[str, dict[str, dict]] = {}
        for source in SOURCES:
            base_rows = build_universe(db, source)
            universes[source] = base_rows
            print(f"== {source}：universe={len(base_rows)} ==", flush=True)

        all_codes = sorted({c for br in universes.values() for c in br})
        peer_shared = freeze_yearly_peer_rows(db, all_codes, ref_year=ref_year)
        qualified = sum(1 for v in peer_shared.values() if v["qualified"])
        print(f"年度排名冻结：{len(peer_shared)} 只有数据，其中 {qualified} 只达标"
              f"（窗口 {peer_shared[next(iter(peer_shared))]['window'] if peer_shared else []}）",
              flush=True)

        print(f"== 拉取净值历史（{len(all_codes)} 只，一次性）==", flush=True)
        nav_shared = load_nav_histories(all_codes, args.nav_cache)

        first_as_of = week_starts[0] + timedelta(days=4)
        ext_start = first_as_of - timedelta(days=365 * 3)
        codes_with_tri = sorted(set(all_codes) & tri_codes(db))
        print(f"扩展 TRI 目标 {len(codes_with_tri)} 只", flush=True)
        bench_shared = load_bench_returns(codes_with_tri, ext_start, args.bench_cache)

        for source in SOURCES:
            base_rows = universes[source]
            codes = list(base_rows)
            profile = sbs.get_profile(source, PROFILE_VERSION)
            # min_yearly_top_pct 不是谓词参数（冻结阶段用），过滤掉
            pred_kwargs = {k: v for k, v in profile["filters"].items()
                           if k != "min_yearly_top_pct"}
            pred = entry_predicate(**pred_kwargs)
            subtype_set = (set(profile["market_subtypes"])
                           if profile.get("market_subtypes") else None)
            source_peer = {c: peer_shared[c] for c in codes if c in peer_shared}
            print(f"== {source}：逐周回填 {len(week_starts)} 周 ==", flush=True)

            for week in week_starts:
                as_of = week + timedelta(days=4)  # 该周周五
                started_at = datetime(as_of.year, as_of.month, as_of.day, 10, 5, tzinfo=TZ)
                assert sbs.recording_week(started_at) == week  # 周键自检
                window_start = pd.Timestamp(as_of) - pd.Timedelta(days=365 * 3)
                rf_series = pd.Series(dtype=float)

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
                        # 基准早 30 天起（供 pct_change / 对齐缓冲）
                        r_b = r_b[(r_b.index >= window_start - pd.Timedelta(days=30))
                                  & (r_b.index <= pd.Timestamp(as_of))]
                    m = compute_risk_metrics(r_p, r_b, rf_series)
                    if m.sharpe is None:
                        continue
                    risk_rows[code] = {
                        "sharpe": m.sharpe,
                        "ir": m.ir,                    # v3 需要（v1 脚本不存）
                        "sample_days": m.sample_days,  # v3 需要
                        "returns_end_date": m.returns_end_date,
                        "calculated_at": started_at,
                        "benchmark_source": None,
                    }

                capture = SharpeRunCapture(
                    run_id=f"backfill-v3-{source}-{week.isoformat()}-{uuid.uuid4().hex[:8]}",
                    filters=profile["filters"],
                    collection_prefilters=profile["collection_prefilters"],
                    universe_codes=codes,
                    base_rows=base_rows,
                    risk_rows=risk_rows,
                    peer_rows=source_peer,   # 年度数据全周共享
                )

                # 预演入选数（与 publish 同一谓词 + 同一 peer 合并逻辑）
                sel = 0
                for code in dict.fromkeys(codes):
                    r = risk_rows.get(code)
                    if r is None:
                        continue
                    if subtype_set is not None and base_rows[code].get("market_subtype") not in subtype_set:
                        continue
                    peer = source_peer.get(code) or {}
                    if pred({**base_rows[code], "sharpe": r["sharpe"], "ir": r["ir"],
                             "sample_days": r["sample_days"],
                             "qualified_years": peer.get("qualified_years")}):
                        sel += 1

                if not args.publish:
                    print(f"  [dry] {source} week={week} as_of={as_of}: "
                          f"有风险值={len(risk_rows)} 预计入选={sel}", flush=True)
                    continue

                row, written = sbs.publish_week_board(
                    db, source=source, profile_version=PROFILE_VERSION, capture=capture,
                    trigger="backfill", started_at=started_at, finished_at=started_at,
                )
                total_written += int(written)
                print(f"  {source} week={week}: status={row.status} "
                      f"selected={row.selected_count} written={written}", flush=True)

        print(f"完成。新写入周行数={total_written}", flush=True)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
