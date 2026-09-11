# market_size_fetcher 雪球优先 + 东财 fallback

## 大白话

东财移动端 msm 接口在连续大批量请求时严重限流（5 月份雪球接口 schema broken 换过去的），
实测 1155 只从预估 7.7 分钟变成 41.7 分钟（每只 ~2.4 秒）。

雪球接口 `ak.fund_individual_basic_info_xq` **现已恢复正常**，8 只样本测 7 只 OK（87.5% 成功率）。
失败的（007130 / 007234 / 007294 / 016537 等）都是 KeyError 'data'（雪球没数据字段）。

**改用雪球优先 + 失败 fallback 东财**：
- 雪球能拿的：1.3 秒/只（含网络），无累计限流
- 雪球失败的：fallback 东财 msm 兜底（0.4 秒/只 + 限流）
- 两者都失败：返回 None（不抛）

## 需求

### R1 fetcher 改动

`src/data/market_size_fetcher.py`：
1. **新增 `fetch_size_xq(code)`**：调 `ak.fund_individual_basic_info_xq(symbol=code)`
   - 字段映射：
     - `最新规模` → `size_yi`（已是"亿"单位；带"万"要 ÷10000 转亿）
     - `成立时间` → `established_date`（`YYYY-MM-DD` 直接 fromisoformat）
     - `基金管理人` → `mgr_company`（兜底字段，原 L2 没用到但顺手填）
   - 失败（KeyError 'data' / 网络错）→ 返回 None
2. **改 `fetch_size(code)`**：先调雪球，失败 fallback 东财 fetch_size_eastmoney
   - 拆分原 fetch_size 为 fetch_size_eastmoney（保留）
   - `fetch_size` 入口：新逻辑 = 雪球 → 失败 → 东财 → None
3. **`fetch_market_size(codes)`**：调用 `fetch_size`，对外接口不变

### R2 测试

`tests/test_market_size_fetcher.py` 新增：
- `test_xueqiu_parses_size_and_estabdate`：mock `ak.fund_individual_basic_info_xq` 返回完整字段
- `test_xueqiu_size_in_wan_converts_to_yi`：最新规模=2250.45万 → size_yi=0.0225（注意实际"亿"单位转换）
- `test_xueqiu_key_error_returns_none`：mock 抛 KeyError 'data' → None
- `test_fallback_to_eastmoney_on_xueqiu_failure`：雪球失败 → 自动调东财 → 返回东财结果
- `test_fallback_chain_returns_none_when_both_fail`：雪球+东财都失败 → None

现有 20 个测试保持不变（验证东财单测仍过）。

### R3 验证

- 实测 L2 size：1155 只时间从 41.7 分钟降到 5-7 分钟
- 失败率：< 5%（雪球失败那只 fallback 东财兜底）

## 字段映射细节

雪球返回 DataFrame columns = ['item', 'value']，典型值：

```
item             value
基金代码          000001
基金名称          华夏成长混合
基金全称          ...
成立时间          2001-12-18
最新规模          39.38亿         ← 已是"亿"单位；如带"万"要 ÷10000
基金管理人        华夏基金管理有限公司  ← 可选，兜底
```

`最新规模` 解析：
- `"39.38亿"` → 直接 float = 39.38
- `"2250.45万"` → 2250.45 / 10000 = 0.2250

## Acceptance Criteria

- [ ] AC1 `fetch_size_xq(code)` 单函数存在，能解析雪球 DataFrame 三个字段（size_yi / established_date / mgr_company）
- [ ] AC2 `fetch_size(code)` 主路径走雪球，雪球失败自动 fallback 东财
- [ ] AC3 两都失败返回 None（不抛）
- [ ] AC4 单元测试覆盖：雪球成功 / 雪球失败 fallback / 两都失败 三场景
- [ ] AC5 现有 20 个东财 fetcher 测试 0 regression
- [ ] AC6 实测 L2 size：1155 只耗时 < 10 分钟

## Out of Scope

- ❌ 改其他阶段（L3/L4/L5 mini_racer 问题另外处理）
- ❌ 改 pipeline 行为（只改 fetcher 内部）
- ❌ 改 fund_basic 老路径（已删除）
- ❌ mgr_company 写入 funds 表（虽然 fetch 拿到但 refresh 不消费）

## Notes

- 雪球限频：之前测试 ~1-3 秒/只，比东财稳定（东财 0.4s 设计 + 限流变 2.4s）
- 雪球 KeyError 'data'：监控日志里 `WARNING fund-select.market_size: fetch_size_xq %s 失败: 'data'`
- 测试要做数据驱动：007130 / 016537 真实失败样本
