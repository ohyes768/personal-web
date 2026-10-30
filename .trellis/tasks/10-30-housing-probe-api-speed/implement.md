# 实施计划

- [x] 先增真实适配器3/4请求、列表混归属/无归属/空列表/种子替换、预算和前端进度测试，确认失败。
- [x] 提取 xingfuli_rentals.py 列表URL，xingfuli_discovery.py 新增白名单与核验方法，discovery_checkpoint.py 接入未缓存步骤，probe.py 使用核验后种子。
- [x] 更新 rental-probe.ts / XingfuliProbe.tsx 运行态进度，清除新操作遗留步骤。
- [x] 运行后端source_api/probe/matching/discovery/collector及相关回归，独立F盘basetemp；前端node测试、lint、tsc、build。
- [x] 更新发现契约和验证记录；改动留工作区，不影响其他任务。
