# 实施计划（未启动）

任务保持planning，本轮仅编写规划；实施须在用户要求实施后按Trellis进入执行阶段。

1. [ ] 核对前置幸福里试点交付和共享git diff；阅读租金来源、幸福里、目录、名称匹配及Windows测试契约，枚举Fang-only/滨江限制和现有锁。
2. [ ] 搜索可行性实测：正负例、别名/分期、同名异区、试点及其他已收录区域；记录请求预算、关键词生效、候选身份、种子获取与归属至research/search-validation.md。成功后进入自动适配，失败明确降级与未完成范围。
3. [ ] 先补行为测试：HTTP200全市推荐拒绝、不同来源同ID、ID/种子分离、缺地址及分期不误绑、人工保护。
4. [ ] 实现provider discovery边界、review兼容和确认事务；统一admitted全范围，不重复实现采集器。
5. [ ] 接入refresh，旧关联先采，新关联下轮采；补真实请求预算、deferred公平性、负缓存、独立冷却、取消、重启、过期响应及发布前校验。
6. [ ] 更新管理页原因/进度/候选审核与继续采集，搜索不可用显式提示；人工链接仍需核验确认。
7. [ ] 隔离多轮全量扫描与端到端，桌面/390px验收；有界公网烟测不改生产。
8. [ ] 逐项验证PRD A1–A8，记录verification.md并更新契约，输出只读覆盖报告；生产导入和部署单独执行。

## 实施阶段验证

在backend/housing-map先检查解释器与测试名，再用独立Windows临时目录：

```powershell
.venv/Scripts/python.exe -m pytest tests/test_rental_association_flow.py tests/test_rental_providers.py tests/test_xingfuli_rentals.py tests/test_rental_refresh.py tests/test_rental_api.py tests/test_directory_flow.py --basetemp=.pytest-tmp-rental-discovery
```

加入本任务新增discovery及实际受影响的sources/storage/statistics用例。在apps/housing-map执行：

```powershell
node --test tests/rental-xingfuli.test.cjs tests/rental-sources.test.cjs tests/directory-flow.test.cjs
npx tsc --noEmit
npm run lint
npm run build
```

旧失败须对照本次最新基线，不沿用前置历史数字宣称通过，不删断言制造成功。规划阶段仅校验任务文档/元数据，不运行业务测试。

## 必查风险

- candidates_for/decide/fingerprint/ingest/active_sources/coverage及前端类型的provider隔离。
- 实际HTTP计数、源独立冷却、全量遍历不饥饿；用户解绑后不得自动搜索恢复。
- 新关联未采集不同于零房源，种子变化/身份变化不得使用旧确认。
- 回退停发现不删关联/历史/人工保护；已有Fang映射不被自动切换。
