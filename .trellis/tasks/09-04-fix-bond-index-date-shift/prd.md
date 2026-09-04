# 中债源日期错位修复（B1）+ ruff 债务清理

## Goal

修复 spec contracts.md 登记的 B1 问题：`bond_composite_index_cbond`（中债财富指数源）返回日期**整体 −1 天**（真实周一标成周日、周五标成周四，3 年分布 Fri=9/Sat=11/Sun=142 实证）。错位后果：与基金净值/其他指数 inner join 时**中债周五收益永久丢失**（周五被标成周六），含中债成分基金的基准 TRI 周五收益系统性缺失。顺带清理 ruff 既有债务 6 处（零新增基线上）。

## Requirements

1. **定位与实证**：先复现错位（拉 `ak.bond_composite_index_cbond` 近 3 年，统计星期分布 + 与交易日历对照），确认「−1 天」假说仍然成立（数据源行为可能已变）。
2. **修复**：若错位确认，在 `benchmark_fetcher._fetch_index_daily` 的 `bond_composite_index_cbond` 分支将日期 **+1 天**（`df["date"] + pd.Timedelta(days=1)`），注释说明为什么；探测是否有更优替代源（有则换源并在 yaml 注释标注，无则 shift）。若错位不成立（源已修复），只更新 spec 记录并跳过修复。
3. **重刷**：含中债/存款成分的基金 TRI + risk 全量重刷（受影响基金 = 公式含中债成分或走 deposit 加成混合的；简单起见全量 142 只重刷亦可，成本可接受）。
4. **ruff 清理**：`ruff check src/ tests/` 现存 6 处告警清零（models.py `date` 未用 import、tests 的 `Component` 未用 import、B017/SIM117/RUF059/F841 具体位置跑出来逐个修）；不引入新告警，不改行为。
5. **测试**：中债日期 shift 用例锁定（mock 源数据，断言 shift 后与交易日历对齐）；ruff 清理无需新测试，全量 pytest 回归。

## Constraints

- 不动 `_fetch_index_daily` 其他 source 分支；不动价格对齐算法（09-04-benchmark-price-align 已锁定）。
- B1 修复只影响中债成分基金的 TRI；风险指标变化方向应为「周五收益补回」，数值变化属数据修正。
- ruff 清理禁止顺手改无关代码/格式。

## Acceptance Criteria

- [x] 实证：旧源 Sun=142/Sat=11/Fri=9（周五被标成周六）→ 新源 Mon142/Fri142 齐、与沪深300 日历重叠 579→725/746；保留 Sat9/Sun11 为**真实债市调休交易日**（银行间开市），非错位伪影
- [x] 42 只中债成分基金 TRI 全部非 NULL；001323 修复前后 3 年累计 42.4339% → 42.4541%（+0.02pp），库值与独立复算逐日 |diff|=0；周五行补回（库内 Fri 142 个 vs 旧标签 9 个）；risk 001323 sample_days=726 满窗
- [x] ruff 0 告警（实际 24 处点位 / 5 类，PRD 写「6 处」为类别数；pyproject 钉 select 基线并注释 121 处默认集既有告警的取舍）
- [x] `pytest tests/ -q` → 160 passed（基线 158 + 中债换源/日历透传 2 用例）
