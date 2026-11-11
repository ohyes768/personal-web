"""P2 真实数据冒烟：采集张坤一人，验证 PRD 锚点。只写内存 SQLite，不动 funds.db。

验证点（对应 prd.md 验收标准）：
- 档案页可采，含已离任记录（张坤应 ≥5 只）
- 加权年化 vs 最长任期年化显著不同
- 复权风险指标非空，且 161005 全历史复权收益 ≈1500%
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.data.manager_profile_fetcher import (
    fetch_adjusted_series,
    fetch_manager_tenures,
)
from src.db.models import Base, Manager
from src.services.manager_metrics import annualize, compute_risk, weighted_annual

ZK = "30189744"

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                       poolclass=StaticPool)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
db = Session()

tenures = fetch_manager_tenures(ZK)
print(f"张坤历任基金 {len(tenures)} 只（含离任 {sum(1 for t in tenures if not t['is_current'])} 只）")
for t in sorted(tenures, key=lambda x: -(x["tenure_days"] or 0)):
    ann = annualize(t["tenure_return_pct"], t["tenure_days"])
    print(f"  {t['fund_code']} {t['fund_name'][:16]:20} {t['fund_type'][:9]:10}"
          f" {t['start_date']}~{t['end_date'] or '至今':11} {t['tenure_days']:>5}天"
          f" 回报{t['tenure_return_pct']:>8.2f}% 年化{ann if ann is not None else float('nan'):>7.2f}%")

weighted = weighted_annual([{**t, "annual_return": annualize(t["tenure_return_pct"], t["tenure_days"])}
                            for t in tenures])
rep = max(tenures, key=lambda x: x["tenure_days"])
print(f"\n加权年化={weighted:.2f}%  最长任期年化={annualize(rep['tenure_return_pct'], rep['tenure_days']):.2f}%")

series = fetch_adjusted_series("161005")
risk = compute_risk(series)
total = risk["total_return_pct"]
print(f"\n161005 复权全历史: {len(series)} 点, 累计 {total:.1f}% (锚点 ≈1500%)")
print(f"回撤 {risk['max_drawdown_pct']:.1f}%  夏普 {risk['sharpe']:.2f}  卡玛 {risk['calmar']:.2f}")

# 张坤代表基金 110011：必须切到任职窗口（2012-09-28 起），全历史会把前任算进来
series_zk = fetch_adjusted_series("110011")
zk_start = rep["start_date"]
from src.services.manager_metrics import slice_series
risk_zk = compute_risk(slice_series(series_zk, start=zk_start))
print(f"110011(张坤代表) 任职窗口[{zk_start}~]: 累计 {risk_zk['total_return_pct']:.1f}% (页面任职回报 {rep['tenure_return_pct']:.1f}%)")

ok = True
if not (5 <= len(tenures) <= 20):
    print("!! 任期数量异常"); ok = False
if sum(1 for t in tenures if not t["is_current"]) == 0:
    print("!! 缺已离任记录"); ok = False
if not (weighted < annualize(rep["tenure_return_pct"], rep["tenure_days"])):
    print("!! 加权应低于最长任期"); ok = False
if not (1400 <= total <= 1600):
    print("!! 复权锚点偏离（161005 应为 ≈1500%）"); ok = False
zk_total = risk_zk["total_return_pct"]
page_ret = rep["tenure_return_pct"]
if not (page_ret * 0.8 <= zk_total <= page_ret * 1.25):
    print(f"!! 110011 任职窗口复权 ({zk_total:.1f}%) 偏离页面任职回报 ({page_ret:.1f}%)")
    ok = False
print("\nSMOKE " + ("PASS" if ok else "FAIL"))
