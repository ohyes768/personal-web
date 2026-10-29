# 幸福里租金抽样早停采集

## Goal

幸福里租金采集从"全量抓取"改为"配额抽样"：列表页行内筛整租候选，逐条详情核验，**凑满 10 条合格样本即停**。目的：限速 5 秒/请求下，把大社区（50 套在租、30 套整租）的采集从约 30 个请求 ≈ 3 分钟压到约 11 个请求 ≈ 1 分钟。

## Background（代码证据）

- 现状：`XingfuliClient.crawl()`（backend/housing-map/src/services/xingfuli_rentals.py:157）默认 `max_pages=10, details=True`，所有整租逐条抓详情，翻页由 `has_more` 驱动。
- 列表行自带 `rental_type`（1=整租）、`rent_price`、`sub_title` 面积、`title` 户型与疑似隔断旗（`_sample`，xingfuli_rentals.py:94）——不点详情即可筛候选。
- 统计只消费详情核验通过的样本（`detail_fetched=False`、合租/疑似隔断/疑似重复剔除，statistics.py `_exclusion_reason`），按面积段（`AREA_BANDS = ('lt90','90to144','gte144')`，statistics.py:13）× 户型分组，`MIN_GROUP_SAMPLES = 3` 才出参考值。
- 采集结果按 `SeedRunResult.status` 入库，refresh.py:399 调 crawl；快照整社区替换，无新旧混算。
- 快照级标记 → 租金面板出一条说明，已有先例：`regional_sample`（CommunityRentalReference.tsx:98）。

## Requirements

1. **配额采样（crawl 核心改动）**
   - 候选 = 列表行整租（`rental_type → whole`）且无 `suspected_partition` 标题旗。
   - 候选逐条发详情请求；合格样本（`_enrich` 通过，即 `detail_success`）达 **10 条**停止翻页，状态记 `complete`（配额提前停止不是 `truncated`）。
   - 详情失败的候选不占配额：继续从列表取下一套补位，直到凑满 10 条合格或列表耗尽（`has_more=false` 且当前页候选用尽）。
   - `max_pages=10` 上限仍生效；翻满仍未凑满配额记 `truncated`（同现状语义）。
2. **样本保留口径**：所有行仍进 `samples`（含未核验的非候选），只有详情请求受配额约束——保持"已排除样本"明细视图完整，结构改动最小。
3. **防线不变**：逐行 `neighborhood_id` 校验拒发、末页重复/分页不推进拒发、空列表反查种子详情防误报、冷却熔断中止——全部保留，禁止回退。
4. **快照元数据**：`CommunityBatch.quality` 记录 `sampling = {quota, qualified, sampled}`（字段名实现时定），如实反映"抽了多少、成了几条"。
5. **默认行为**：抽样是幸福里采集的默认且唯一路径，**不加开关、不加配置项**；≤10 条整租的小区行为与全量完全一致。房天下（fang）采集不变。
6. **前端标注**：API 透传抽样标记；小区租金参考面板顶部出一条说明（仿 `regional_sample` 模式），措辞表达"抽样采集：目标 10 条整租合格样本，非小区全部在租房源"。看板/目录表格的"有效样本数"列含义不变，不动。

## Acceptance Criteria

- [ ] 整租 ≤10 条的小区：采集结果与全量一致（样本数、状态、详情数）。
- [ ] 整租 >10 条的小区：详情请求停止于第 10 条合格样本；`status='complete'`、`pages_truncated=False`。
- [ ] 详情失败场景：失败候选标 `detail_fetch_failed` 不占配额，后续候选补位（测试模拟第 2 条候选失败，验证第 11 条整租被补位抓取）。
- [ ] 配额满足时不再翻页（测试验证无多余分页请求），状态 `complete` 可入库——即使存在 detail_failed（失败已被补位吸收；`ADOPTABLE_STATUSES` 不含 `partial_detail`，storage.py:34，此映射不能破坏）。
- [ ] 配额未满足且列表耗尽且存在详情失败：状态 `partial_detail` 不入库，旧快照保留（现状语义）。
- [ ] 防线用例全部保留且通过：混入他区行拒发、空列表反查种子、末页重复拒发、冷却中止。
- [ ] 快照 `quality.sampling` 字段如实记录；API 返回抽样标记；旧快照（无标记）前端不显示说明行。
- [ ] 前端租金面板对抽样快照显示一条口径说明。
- [ ] `python -m pytest tests/ -q` 全绿；前端 lint/build 通过。

## Out of Scope

- 房天下采集策略、幸福里传输层（限速/冷却/白名单）、统计口径（面积段、MIN_GROUP_SAMPLES、排除规则）均不变。
- 不做"面积>50㎡"过滤（已拍板：会系统性抬高 lt90 段中位数，见已拍板 Q1）。
- 不做全量模式的开关或回退配置。

## 已拍板

- Q1（2026-10-29）：只筛整租，不卡面积。统计已按面积段分组并有排除规则，采集端叠 >50㎡ 会让 lt90 段样本只剩 50-90㎡，中位数系统性偏高且可能凑不满每组 3 条。
- Q2（2026-10-29）：补抓到 10 条合格样本，不是候选上限。请求预算不再固定（正常 ≈11 个，失败多则更多），病态情况由现有冷却熔断兜底；统计侧疑似重复剔除发生在统计时，采集端配额不含这层，最终合格数可能略少于 10——快照元数据如实记录。
- Q3（2026-10-29）：默认替换、不加开关（用户全局规则"不做没要求的可配置性"；≤10 条整租小区行为与全量一致，开关无服务对象）。
- Q4（2026-10-29）：快照元数据 + 租金面板一条说明；看板/目录不动。
