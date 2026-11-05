# 实施计划

## 阶段门槛

2026-11-02 用户批准实施，已执行 `task.py start`（status=planning → in_progress）。本轮按 inline 方式在主会话实施，不派发子代理。

## 顺序与文件边界

- [x] 开发前运行get_context.py --mode phase --step 2.1 --platform codex，加载trellis-before-dev；阅读frontend/index.md、frontend/index-trends-echarts.md及共享跨层/复用指南。index-trends目前无独立后端spec目录，参考现有服务和测试，不套用其他业务包规则。
- [x] 固化供应商响应fixture：参考官方成功、空数据、权限失败示例，明确标注合成数据，真实联调fixture脱敏后才能提交。先验证平铺字段与ratio单位。
- [x] src/config.py和新增src/data/lixinger.py：Token配置、固定请求、超时、错误脱敏与严格解析；不引入AKShare。
- [x] src/services/store.py追加005迁移与估值事务读写，新增valuation_service.py统一日期、状态、缓存及重试冷却。
- [x] src/main.py接入生命周期、每日/手动刷新和现有锁；src/api/routes.py为status增加只读valuation并为refresh补充估值结果，不改变原行情成功/失败契约。
- [x] src/services/report_service.py注入估值服务，在原幂等检查后刷新并保存估值快照，增加正常/滞后/失败文案，保留休市和错误报告分支。
- [x] apps/index-trends/lib/types.ts、components/CurrentTab.tsx增加类型和独立估值区域。必要时仅修改app/globals.css中的对应样式，历史图与TrendChart不改。
- [x] docker-compose.nas.yml透传INDEX_TRENDS_LIXINGER_TOKEN；补充backend/index-trends的配置说明文件，使用占位值，不写入真实密钥。
- [x] 完成下述验证并进行trellis-check；新增跨层契约落到 `.trellis/spec/backend/index-trends/backend/`（新增 index.md / weekly-pipeline.md / valuation-contract.md）并扩展前端规范。提交与部署仍需用户单独授权。

## 验证清单

新增tests/test_lixinger_provider.py、test_valuation_service.py、test_valuation_store.py，必要时扩充test_api.py、test_weekly_report.py和生命周期相关现有测试。

- 0、1及0.565952...转换为0%、100%、56.5952...%；缺失、bool、负数、>1、NaN拒绝，空值不填零。
- HTTP超时/非JSON/非成功code/权限错误/空data不影响趋势刷新和周报投递；错误不含Token。
- stockCode不符、未来日期、乱序/重复记录，时区日期规范化；日期选择不偷看未来。
- 周一、周五盘前/收盘后、周五假日、整周休市、日历失败；周报取本报告周，页面取最近完整周。
- 同目标缓存命中无请求，失败冷却、跨目标切换可请求；更新失败保留好数据但状态不能ok。
- 迁移在空库、旧库重复打开均安全，不改变行情/模型/既有报告；估值快照随报告固定，已sent不重发。
- /status提供同单位类型，缺Token正常启动，/refresh估值失败不改行情成功结果，旧后端响应可被前端兼容。
- 页面375px及1440px查看ok/stale/empty/error/disabled；切换两个模型、刷新、缺模型状态，不影响主图。

运行命令（按现有依赖环境执行）：

```bash
cd backend/index-trends
uv run pytest
cd ../../apps/index-trends
pnpm exec tsc --noEmit
pnpm build
```

无既有前端单测框架，不为格式化函数引入新的测试框架；通过类型检查、构建及浏览器状态验证覆盖。前端没有lint脚本，不虚报lint通过。

## 真实联调（需要用户本地配置凭据）

- [ ] 确认账号具备指数基本面与10年统计指标权限，费用由用户确认，不自动购买。
- [ ] 用户通过本地环境配置Token，调用已有手动刷新路径，核对000300、目标日期、PE、分位与理杏仁同口径页面。
- [ ] 确认实际返回ratio、请求时间与数据更新时间；尤其记录周五19:00是否有当日数据。若没有，按既定stale文案发送，不擅改调度。
- [ ] 无Token时标记“离线检查通过，真实供应商联调待完成”，不能勾选PRD真实接入验收。

## 回滚点

Provider、表迁移、服务编排、展示分别可review。任何单步失败先修复该层，不扩大改动。上线异常清空Token停用新源；如需回滚应用保留新增SQLite表，旧版本忽略即可。不得删库、覆写旧报告或通过取消幂等保护重发验证。
