# 实施计划与进度

## 前置门槛
- [x] 用户确认开工及提前结束范围；followup R2归属已同步。
- [x] 已读取开发/来源/名称匹配/Windows测试规范，保护其他会话改动。
- [x] task.py start，状态in_progress。

## 顺序
1. 目标与模式：先补matching及API行为测试，再实现full/incremental、失败重试、增量数量、旧调用/自动恢复兼容。
2. 诊断基线：记录请求等待/HTTP耗时，固定响应保存旧策略请求序列，不改变节流。
3. 缓存/断点：测试TTL、有效空结果、失败不缓存、输入变化、损坏缓存、取消/进程重启及旧任务，再接入search/homepage；保留已有单次去重。
4. 提前结束：完整检查当前通道候选再决定；测试竞争候选、页面失败、预算截断、分期/区域冲突、入口失效、人工否决；详情和列表归属核验不省略。
5. 前端：DirectoryFlowWorkspace.tsx两个按钮发送不同模式，显示数量/范围/诊断，验证空增量禁用、停止、互斥；目录流程回归测试。
6. 集成/契约：隔离数据测试停止→继续、重启、冷却和全量刷新，对照HTTP次数/匹配差异，更新契约。

## 验证
backend/housing-map目录使用已验证可用的本项目Python环境：
```powershell
python -m pytest tests/test_rental_split.py tests/test_rental_probe.py tests/test_xingfuli_discovery.py tests/test_rental_xingfuli_sources.py --basetemp=.pytest-tmp-matching-speed
python -m pytest --basetemp=.pytest-tmp-matching-speed-all
```
apps/housing-map目录：
```powershell
node --test tests/directory-flow.test.cjs tests/rental-probe.test.cjs
npm run lint
npx tsc --noEmit
npm run build
```
- [ ] 桌面及390px浏览器隔离数据验证两个按钮与完整停止/继续链路。
- [ ] Windows构建若有现存symlink限制，保留失败记录并在既有NAS环境验证，不隐去失败。
- [ ] 离线请求数测试用假fetcher/时钟；真实性能报告比较同等目标与冷热条件，记录绑定决定差异。
- [ ] 部署及真实小批次另行进入上线步骤，本次不操作生产。

## 风险与回退
重点检查probe.py、matching.py、xingfuli_transport.py及路由的锁和恢复行为。提前结束改变候选覆盖，出现风险关闭快速路径；缓存问题禁用读取。只回退本任务代码与派生缓存，不整库覆盖来源/人工决定。

## 本轮执行记录
- [x] 两种模式、查询复用、提前结束、HTTP步骤恢复、批次诊断及前端按钮已实现。
- [x] 强候选提前结束/错误竞争候选/缓存过期损坏/失败不缓存/真实进程退出/最新证据重新判断等回归通过。
- [x] 前端点击模式与禁用条件、桌面/390px隔离组件布局和状态验证通过。
- [x] 沙箱外webpack生产打包通过；默认Turbopack沙箱限制记录见research/validation.md。
- [ ] 真实小批性能测量留待上线验证；未部署、未迁移、未启动线上批次。
- [ ] 代码尚未提交，任务保留in_progress，不自动归档。
