# 验证记录

- 根因：共用 rental_reference.association.eligible_communities 没有市场类型门槛，新房虽通过住宅准入却仍进入租金流程。
- 修复：目录模式排除 admitted 投影的 new_house；旧模式排除 matched TMSF 有效新房身份；售完通过 existing effective_market_state 恢复二手房规则。
- 红灯：新增用例初跑 6 failed / 2 passed，失败均为新房仍在资格集合。
- 最终相关回归：tests/test_newhouse_rental_skip.py、test_matching_speed.py、test_rental_probe.py、test_rental_association_flow.py、test_rental_split.py、test_rental_xingfuli_sources.py、test_rental_refresh.py，117 passed / 2 dependency deprecation warnings（24.68s）。basetemp=.pytest-tmp-newhouse-rental-final。
- 全量中间快照：1190 passed / 10 failed / 3 warnings（125.94s）。失败全部位于并行任务正在改动的 test_xingfuli_source_api.py，其四请求预期与当时五请求实现不一致。随后并行任务继续修改 probe/discovery 等文件，因此不以这次快照宣称全量通过。
- 隔离进程使用 HEAD 原版 association 复查 API 套件时，因并行实现已更新，52 passed（23.46s）。不能用此结果声称已证明先前失败的基线归因。
- 本次范围 git diff --check 通过；未修改其他并行文件。spec 已同步。
- 本地实现完成；未提交、推送、部署、修改生产数据。保留 in_progress 等待后续集成，不运行会自动提交的归档/会话脚本。
- 提交前复验：test_newhouse_rental_skip.py 10 passed（1.48s）；用户已追加授权提交并推送，仅纳入本次过滤逻辑、回归、spec 与任务记录，排除并行 API 提速文件。
