"""侦察：中证全表模糊搜索候选指数代码 + 申万一二级行业信息。输出到 stdout。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "fund-select"))

import akshare as ak  # noqa: E402

KEYWORDS = [
    "中证A50", "红利低波", "港股通高股息", "中金优选300", "东方红优势成长",
    "东方红红利低波动", "港股通央企红利", "科创创业50", "国信价值", "内地资源",
    "高端装备制造", "800相对成长", "沪港深高股息", "移动互联网", "中证互联网",
    "海外中国互联网", "香港银行", "自由现金流", "国债", "恒生综合",
]


def main() -> None:
    df = ak.index_csindex_all()
    print("csindex 全表列:", list(df.columns), "行数:", len(df))
    for kw in KEYWORDS:
        hit = df[df.apply(lambda r: kw in "".join(str(v) for v in r.values), axis=1)]
        cols = [c for c in df.columns if any(k in str(c) for k in ("名称", "代码", "英文"))][:3]
        for _, r in hit.head(6).iterrows():
            print(f"  [{kw}]", " | ".join(f"{c}={r[c]}" for c in cols))
        if hit.empty:
            print(f"  [{kw}] 无命中")

    print("\n=== 申万一级行业 ===")
    l1 = ak.sw_index_first_info()
    print("列:", list(l1.columns))
    print(l1[l1.apply(lambda r: any(k in "".join(str(v) for v in r.values) for k in ("制造", "医药")), axis=1)].to_string())
    print("\n=== 申万二级行业（医药相关）===")
    l2 = ak.sw_index_second_info()
    print(l2[l2.apply(lambda r: any(k in "".join(str(v) for v in r.values) for k in ("医药", "制造")), axis=1)].head(8).to_string())


if __name__ == "__main__":
    main()
