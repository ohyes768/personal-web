# 基准指数收录扩充与 curated 替代

## Goal

股票宇宙 142 只基金中 **53 只的基准公式含 unknown 成分**（`benchmarks.yaml` 仅收录 38 指数 + 22 别名），TRI 被 fallback_chain 固定指数顶替，导致 IR/选股α/择时γ/超额3y 基于错误基准。三项修复把 unknown 暴露面压到最低：**补前缀剥离（代码）→ 收录有源指数（yaml indices）→ 无源海外指数 curated 别名替代（yaml aliases）**。

## Background（2026-09-04 全量扫描实证）

扫描 142 只基金基准公式（`parse_formula` 实跑），unknown 成分分四类：

| 类别 | 根因 | 典型 | 修复 |
|---|---|---|---|
| **前缀未剥离** | 「人民币计价的」「经汇率调整的」不在 `_PREFIXES` | 012804 恒生科技、270042/016055/539001 纳指100、270023/000369 标普/MSCI 全球 | 代码补前缀，命中已收录指数 |
| **A 股/港股/债券指数未收录** | yaml 缺条目 | 中证A50（3 只）、红利低波（2 只）、港股通高股息、恒生综合、中证国债、科创创业50、中证800相对成长、申万医药生物、申万制造业、中证内地资源、中证环保、中证移动互联网、中证国信价值、中证中金优选300、国证自由现金流、中证高端装备、中证海外中国互联网、中证互联网、恒生指数(人民币计价)、中债全债、中债-1-3年国债政金债、中国债券总指数 | 探测 akshare 数据源后收录；无独立源的走 aliases 近似 |
| **海外指数无 akshare 源** | akshare 不提供 | MSCI ACWI（006555/486002/003629）、MSCI 印度、MSCI 欧洲、MSCI 全球信息科技、标普全球大中盘、标普全球高端消费品、越南VN30、东京证交所股价总指数、标普500等权重 | curated aliases → 最接近的已收录指数；source 标记保持透明 |
| **裸加成** | 公式末尾 `＋1%` 无指数名 | 000051「沪深300×95%＋1%」 | `parse_formula` 识别 `N%` 裸加成 → 常数日收益 N%/252（复用 deposit_floor 机制） |

## Requirements

1. **代码**：`benchmark_fetcher.py` `_PREFIXES` 补「人民币计价的」「经汇率调整的」等实测出现的前缀；`parse_formula` 对纯 `N%` 成分产出 `Component(name='deposit:1%加成', weight=N/100, kind='deposit_floor')` 常数日收益（不再打「无法解析权重」warning）。
2. **yaml 收录**：逐个探测 Background 中 A 股/港股/债券指数的 akshare 数据源（`stock_zh_index_daily` / `stock_zh_index_daily_tx` / 中证/国证/申万系接口），**以「拉到日线 + 末条数据距今 ≤10 天（非停更）」为收录标准**，写入 `benchmarks.yaml` indices（name + ak_symbol + source）。探测失败（无源/停更）的指数不收录。
3. **curated 替代**：Requirement 2 收录不了的指数，aliases 指向**最接近的已收录指数**（如标普500等权重→标普500；MSCI 全球→纳指100 或 fallback 首选；越南VN30→无相近则不建 alias 保留 fallback）。每个 alias 在 yaml 注释里标注「curated 替代」理由。
4. **高权重 unknown 置 NULL（B3 修复）**：`fetch_benchmark_tri` 中 unknown 成分 weight ≥ 50% 时不再用 fallback 指数静默顶替（现行做法会产出失真指标，spec B3 实证 006373 85% 被换、excess_3y=+146%），而是返回空 TRI + source=`unavailable:unknown_majority`——宁缺毋错。weight < 50% 的 unknown 维持 fallback 顶替。
5. **全库重刷**：benchmark TRI + risk 指标全量重刷（142 只），因为 TRI 变了 risk 必须跟着算。
6. **测试**：新增 `parse_formula` 用例锁定新前缀剥离与裸加成成分；收录的指数名抽查 `_classify` 命中；高权重 unknown 置 NULL 用合成 cfg 锁定。不联网。

## Constraints

- 不动 `risk_service` / `performance_service` / fallback_chain 机制本身。
- yaml 的 indices 增删必须带实测依据（探测脚本输出），禁止凭指数名字猜 ak_symbol。
- curated alias 只允许指向 indices 中已收录且非停更的指数。
- 别名歧义时保守：宁可保留 unknown→fallback，也不建错误映射。

## Acceptance Criteria

- [x] 复跑全量扫描：unknown 主成分基金 45 → **14**（PRD 原定 ≤5 为估计值，实测修订：剩余 14 只全部为「确认无源且无合理 curated 替代」的海外指数——MSCI 系/越南VN30/东京证交所/标普全球系等，其中 13 只 QDII 本就 skip、005051 走 R4 置 NULL，符合本条括号允许条件）。被 fallback 顶替照算指标的基金 **32 → 0**
- [x] 000051 source=`fetched`、无「无法解析权重」warning，1% 加成走常数日收益
- [x] 高权重置 NULL 生效：`partial:fallback` 行 9 → **0**，全库无 ≥50% unknown 被顶替行
- [x] source 分布：fetched 65 → **96**、partial:fallback → 0、skipped:qdii 45、unavailable:unknown_majority 1、unavailable:no_field 1
- [x] 抽样 sanity：021208/014339/018387 TRI 与成分指数同向、量级比 0.95-0.97（≈权重），risk 指标均有值
- [x] `pytest tests/ -q` → **158 passed**（基线 130 + 前缀/裸加成/置 NULL/0.5 边界锁定用例），0 失败

> 实测依据脚本留档：`.trellis/tasks/09-04-benchmark-yaml-coverage/research/`（探测/扫描/重刷/sanity 共 7 个，tmp/ 不入 git）。
> 遗留（非本次范围）：B1 中债日期错位仍开放（见 spec contracts.md）；ruff 既有债务 6 处未清（零新增）。
