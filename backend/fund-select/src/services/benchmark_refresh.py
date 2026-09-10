"""
业绩比较基准（fund_benchmark）刷新公共 service。

stock tab（refresh_stock_funds_sync）和 market tab（market_risk_refresh.refresh）
都依赖此模块写入基准行，避免 IR 公式因 no fund_benchmark row 失败
（PRD 09-10-market-tab-l4-benchmark-prefetch）。

QDII/互认基金基准公式（MSCI/标普全球等）无免费数据源 → 跳过合成写
tri=NULL source=skipped:qdii（与 filter_service.exclude_qdii 口径一致）。

fetch_benchmark_tri / clear_index_cache 在函数内 lazy import：
与 tasks.py._refresh_fund_benchmarks 原实现一致，让 tests/conftest 风格
monkeypatch.setattr("src.data.benchmark_fetcher.*") 在调用点生效。
"""
from sqlalchemy import or_
from sqlalchemy.orm import Session

from src.db.models import Fund, FundBenchmark
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.benchmark_refresh")


def refresh(db: Session, codes: list[str]) -> list[str]:
    """全量刷新 fund_benchmark（delete + insert，仿 _replace_achievement 模式）。

    窗口近 3 年（与 dd_3y 口径一致）；指数级缓存让 143 只只拉 ~35 次指数日线。
    无基准字段的基金写一行 tri=NULL（phase2-B 读到即跳过该基金指标计算）。
    QDII/互认基金基准公式多无免费数据源（MSCI/标普全球等），fallback 出的中证800
    是错误口径 → 跳过合成直接写 tri=NULL（PRD 09-03-qdii-skip-benchmark）；
    判定口径同 filter_service 的 exclude_qdii。
    """
    from datetime import date, timedelta

    from src.data.benchmark_fetcher import clear_index_cache, fetch_benchmark_tri

    skip_codes = {
        code for (code,) in db.query(Fund.code).filter(
            Fund.code.in_(codes),
            # 用 market_subtype 判定 QDII（funds.fund_type 字段从 fetch_market_universe 没填过，
            # 全为空字符串；market_subtype 是 akshare 原始 27 个枚举值，准确）
            or_(Fund.market_subtype.like("QDII%"),
                Fund.market_subtype == "互认基金"),
        ).all()
    }
    if skip_codes:
        logger.info("[benchmark] 跳过 %d 只 QDII/互认基金基准合成", len(skip_codes))

    clear_index_cache()
    end = date.today()
    start = end - timedelta(days=365 * 3)
    bench_errors: list[str] = []
    for i, code in enumerate(codes, 1):
        try:
            db.query(FundBenchmark).filter(FundBenchmark.code == code).delete()
            if code in skip_codes:
                db.add(FundBenchmark(code=code, date=end, tri=None, source="skipped:qdii"))
                db.commit()
                continue
            df, source = fetch_benchmark_tri(code, start, end)
            if df.empty:
                db.add(FundBenchmark(code=code, date=end, tri=None, source=source))
            else:
                db.add_all([
                    FundBenchmark(code=code, date=r["date"].date(), tri=float(r["tri"]), source=source)
                    for _, r in df.iterrows()
                ])
            db.commit()
            if i % 20 == 0:
                logger.info("[benchmark %d/%d] 缓存进度", i, len(codes))
        except Exception as e:  # noqa: BLE001  单只失败不阻塞
            db.rollback()
            bench_errors.append(f"benchmark:{code}: {str(e)[:120]}")
            logger.warning("[benchmark %d/%d] %s 失败: %s", i, len(codes), code, str(e)[:120])
    return bench_errors
