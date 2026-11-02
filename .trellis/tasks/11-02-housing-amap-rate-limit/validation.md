# 验证

- AmapClient进程共享锁、2秒间隔、QPS/HTTP429的2/4/8秒有限重试与安全错误码。
- RequestBudgetClient为真实客户端每次HTTP尝试注入预算/取消检查，异常保持原类型；测试替身保持原计数语义。
- 新增test_amap_rate_limit.py：21项，含跨线程/客户端、分页恢复、重试耗尽、永久错误脱敏、预算及取消。
- 后端完整回归：1344 passed，9个本地HTTP服务器fixture因沙箱绑定端口限制报错；允许端口后重跑test_tmsf_browser_protocol.py，33 passed。
- 最后预算/取消调整另跑定位、目录流程、用途核对、资料补全、pipeline及限速全部相关回归，213 passed。
- git diff --check通过。无前端修改；未部署、未更改NAS业务数据。
- 现有未关联改动.trellis/.template-hashes.json和.pnpm-store/保留。
