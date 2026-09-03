"""
风险/超额指标计算（phase2-B）

compute_risk_metrics: 纯函数（日频序列 → 6 指标），无 IO 依赖。
refresh_fund_risks:  编排（nav 累计净值 + DB benchmark/risk_free → upsert）。

口径：近 3 年窗口；R_p 基于累计净值（分红再投），R_b 基于 benchmark TRI（财富口径）；
R_f 年化小数 / 252 折日频。√252 年化。
"""
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from src.data.nav_fetcher import fetch_nav_accumulated
from src.db.models import FundBenchmark, FundRiskMetrics, RiskFreeRate
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.risk_service")

MIN_SAMPLE_DAYS = 250
TRADING_DAYS = 252
WINDOW_YEARS = 3


@dataclass(frozen=True)
class MetricsResult:
    sharpe: float | None
    ir: float | None
    alpha: float | None      # 年化
    gamma: float | None      # 日频二次项
    alpha_ir: float | None
    excess_3y: float | None
    sample_days: int


def compute_risk_metrics(
    r_p: pd.Series | None,
    r_b: pd.Series | None,
    r_f: pd.Series | None,
) -> MetricsResult:
    """日频收益序列 → 6 指标。任何输入缺失 / 样本不足 / 退化 → 对应指标 None。

    r_p 与 r_b 按日期 inner join 对齐；r_f reindex 对齐日 ffill。
    """
    if r_p is None or r_f is None or len(r_p) == 0:
        return MetricsResult(None, None, None, None, None, None, 0)

    r_p = r_p.dropna()
    if len(r_p) < MIN_SAMPLE_DAYS:
        return MetricsResult(None, None, None, None, None, None, len(r_p))

    # R_f 对齐（年化小数 → 日频）
    rf_daily = (r_f / TRADING_DAYS).reindex(r_p.index).ffill().fillna(0.0)

    has_bench = r_b is not None and len(r_b.dropna()) >= MIN_SAMPLE_DAYS
    if has_bench:
        joined = pd.concat([r_p.rename("p"), r_b.rename("b")], axis=1, join="inner").dropna()
    else:
        joined = pd.concat([r_p.rename("p")], axis=1)
    if len(joined) < MIN_SAMPLE_DAYS:
        has_bench = False

    excess_p = joined["p"] - (rf_daily.reindex(joined.index).ffill().fillna(0.0))

    # ---- sharpe ----
    sharpe = _ratio_annualized(excess_p)

    # ---- 基准相关指标 ----
    ir: float | None = None
    excess_3y: float | None = None
    alpha: float | None = None
    gamma: float | None = None
    alpha_ir: float | None = None
    sample_days = len(joined)

    if has_bench:
        excess_b = joined["b"] - (rf_daily.reindex(joined.index).ffill().fillna(0.0))
        diff = joined["p"] - joined["b"]
        ir = _ratio_annualized(diff)
        cum_p = float(np.prod(1 + joined["p"]) - 1)
        cum_b = float(np.prod(1 + joined["b"]) - 1)
        excess_3y = cum_p - cum_b

        # ---- T-M 回归：y = α + β·x + γ·x² ----
        x = excess_b.to_numpy()
        if np.std(x) > 0:
            y = excess_p.to_numpy()
            X = np.column_stack([np.ones_like(x), x, x ** 2])
            coef, *_ = np.linalg.lstsq(X, y, rcond=None)
            resid = y - X @ coef
            sigma_e = float(resid.std(ddof=1)) if len(resid) > 1 else 0.0
            alpha_d = float(coef[0])
            gamma = float(coef[2])
            if not math.isnan(alpha_d):
                alpha = alpha_d * TRADING_DAYS
            if sigma_e > 0 and not math.isnan(alpha_d):
                alpha_ir = alpha_d / sigma_e * math.sqrt(TRADING_DAYS)
        # x 恒定（std=0）→ 回归退化，alpha/gamma/alpha_ir 保持 None

    return MetricsResult(sharpe, ir, alpha, gamma, alpha_ir, excess_3y, sample_days)


def _ratio_annualized(s: pd.Series) -> float | None:
    """mean/std × √252；std=0 → None（无分散，比率无定义）"""
    arr = s.to_numpy()
    std = float(arr.std(ddof=1)) if len(arr) > 1 else 0.0
    if std == 0 or math.isnan(std):
        return None
    v = float(arr.mean()) / std * math.sqrt(TRADING_DAYS)
    return None if math.isnan(v) else v


def refresh_fund_risks(db: Session, codes: list[str]) -> list[str]:
    """全量刷新 fund_risk_metrics。单只失败记 errors 不阻塞。"""
    end = date.today()
    start = end - timedelta(days=365 * WINDOW_YEARS)
    as_of = end

    rf_df = db.query(RiskFreeRate).filter(
        RiskFreeRate.date >= start - timedelta(days=30),
    ).order_by(RiskFreeRate.date).all()
    r_f = pd.Series(
        {d.date: d.rate for d in rf_df},
        index=pd.DatetimeIndex([d.date for d in rf_df]),
    ) if rf_df else pd.Series(dtype=float)

    errors: list[str] = []
    for i, code in enumerate(codes, 1):
        try:
            bench_rows = (
                db.query(FundBenchmark)
                .filter(FundBenchmark.code == code, FundBenchmark.tri.isnot(None))
                .order_by(FundBenchmark.date)
                .all()
            )
            r_b = (
                pd.Series(
                    [row.tri for row in bench_rows],
                    index=pd.DatetimeIndex([row.date for row in bench_rows]),
                ).pct_change().dropna()
                if bench_rows else pd.Series(dtype=float)
            )

            nav = _safe_fetch_nav(code)
            if nav.empty:
                r_p = pd.Series(dtype=float)
            else:
                nav = nav[nav["净值日期"] >= pd.Timestamp(start)]
                r_p = (
                    nav.set_index("净值日期")["累计净值"].pct_change().dropna()
                )

            m = compute_risk_metrics(r_p, r_b, r_f)
            _upsert(db, code, m, as_of)
            db.commit()
            if i % 20 == 0:
                logger.info("[risk %d/%d] 进度", i, len(codes))
        except Exception as e:  # noqa: BLE001
            db.rollback()
            errors.append(f"risk:{code}: {str(e)[:120]}")
            logger.warning("[risk %d/%d] %s 失败: %s", i, len(codes), code, str(e)[:120])
    return errors


def _safe_fetch_nav(code: str) -> pd.DataFrame:
    """拉累计净值；无数据源（互认基金返回 HTML 等）→ 空 DataFrame，指标全 NULL。"""
    try:
        return fetch_nav_accumulated(code)
    except Exception as e:  # noqa: BLE001
        logger.warning("累计净值 %s 不可用: %s", code, str(e)[:100])
        return pd.DataFrame()


def _upsert(db: Session, code: str, m: MetricsResult, as_of: date) -> None:
    row = db.get(FundRiskMetrics, code)
    if row is None:
        db.add(FundRiskMetrics(
            code=code, sharpe=m.sharpe, ir=m.ir, alpha=m.alpha, gamma=m.gamma,
            alpha_ir=m.alpha_ir, excess_3y=m.excess_3y, sample_days=m.sample_days,
            as_of_date=as_of,
        ))
    else:
        row.sharpe = m.sharpe
        row.ir = m.ir
        row.alpha = m.alpha
        row.gamma = m.gamma
        row.alpha_ir = m.alpha_ir
        row.excess_3y = m.excess_3y
        row.sample_days = m.sample_days
        row.as_of_date = as_of
        row.updated_at = datetime.now(UTC)
