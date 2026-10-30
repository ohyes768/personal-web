# 实施计划

## 名称包含补充
- [x] 补充近距离包含名成功及竞争/截断/位置缺失/范围冲突/实时复核负例，先验证失败。
- [x] 通过显式策略让ProbeService所有身份复核使用同一包含名规则，旧发现入口保持原条件。
- [x] 运行相关回归并同步规范及验证记录。

- [x] 先增真实适配器3/4请求、列表混归属/无归属/空列表/种子替换、预算和前端进度测试，确认失败。
- [x] 提取 xingfuli_rentals.py 列表URL，xingfuli_discovery.py 新增白名单与核验方法，discovery_checkpoint.py 接入未缓存步骤，probe.py 使用核验后种子。
- [x] 更新 rental-probe.ts / XingfuliProbe.tsx 运行态进度，清除新操作遗留步骤。
- [x] 运行后端source_api/probe/matching/discovery/collector及相关回归，独立F盘basetemp；前端node测试、lint、tsc、build。
- [x] 更新发现契约和验证记录；改动留工作区，不影响其他任务。

## 同名唯一补充
- [x] 新增缺少位置证据的唯一候选自动绑定测试，以及多候选、截断、远距离、恢复后资料变化保护。
- [x] evaluate提供显式同名策略，ProbeService搜索、恢复和落库复核一致使用。
- [x] 跑幸福里相关回归并同步发现契约与验证记录。
