# 地点确认与筛选 UI Implementation Plan

**Goal:** 通过候选卡片与分层筛选降低操作成本，保留现有业务契约。
**Architecture:** PositionPanel 管理核对，CatalogFilters 负责受控筛选呈现，DirectoryFlowWorkspace 保留请求状态。
**Tech Stack:** Next.js、React、TypeScript、原生表单/details、现有 CSS、node:test、Playwright。
**执行约束:** 当前仅获准规划；后续用户要求开发后，按 Trellis 执行阶段逐步实施。

## 0. 开始前
- [ ] 检查 git status 与当前任务，保留其他会话改动；阅读 prd.md、design.md、implement/check.jsonl，再激活本任务。
- [ ] 使用 trellis-before-dev；UI 编辑前阅读 impeccable craft-floor，沿用现有视觉风格。
- [ ] 确认测试基线：此前全量前端有 community-management 的旧展示断言、rental-dashboard/rental-sources 缺失组件共3项失败；不将无关问题扩大为本任务。

## 1. 候选卡片与确认顺序（R1–R4 / R7–R8）
文件：PositionPanel.tsx、tests/position-status.test.cjs，均位于 apps/housing-map。
- [ ] 先写失败测试：单候选展开不提交、多候选 radio、名称/地址/末级类型分行、完整类型可展开、参考项默认折叠且不可选。
- [ ] 补充无地址未勾选禁用、有地址无需勾选、缺 ID/坐标/版本禁用、busy 禁用及无主体/错误状态用例。
- [ ] 运行 `node --test tests/position-status.test.cjs`，确认新增用例因旧行为失败，排除装载错误。
- [ ] 实现卡片、类型详情、状态说明及参考折叠；确认按钮移到地图与勾选之后，沿用原确认请求。
- [ ] 使用实际 DOM 交互验证候选和 revision 切换清除核对标记，单候选初始化不能勾选或发送请求；相关测试转绿。

## 2. 筛选组件与状态协同（R5–R6 / R8）
文件：新增 src/components/community/CatalogFilters.tsx；修改同目录 DirectoryFlowWorkspace.tsx 与 tests/catalog-filters.test.cjs。
- [ ] 先写失败测试：三种目录页的常驻/更多条件矩阵、可见标签、更多条件计数、摘要和无结果提示。
- [ ] 验证清空使 q/district/所有专属条件为空且 page=1；单项移除只清对应字段；刷新保留条件。
- [ ] 验证切页签保留 q/district、清理专属条件；隐藏条件不进入请求或摘要，法拍/租金独立页不新增住宅条件。
- [ ] 运行 `node --test tests/catalog-filters.test.cjs` 确认新增用例失败，再实现受控组件及适用范围纯函数，连接原有节流/取消/加载逻辑。
- [ ] 结果数移入筛选结果摘要，加载时标明更新中；测试转绿，并拦截 GET 核对实际参数。

## 3. 样式与可访问性（R7）
文件：apps/housing-map/src/app/globals.css；仅调整本任务组件作用域。
- [ ] 卡片使用原生 radio + label/fieldset，保留键盘箭头选择、焦点样式；筛选和展开项具备可见标签。
- [ ] 桌面 grid 对齐；390px 搜索满行、筛选两列、长文案换行；提交禁用有可读原因。
- [ ] 用假数据浏览器同时检查1440px和390px的溢出、键盘、地图链接、确认 payload、核对重置、筛选参数；不写生产数据。
- [ ] 对改动组件运行 impeccable detect 一次，将问题批量修正后最多再复核一次；关闭自建预览进程。

## 4. 质量门与交付
从 apps/housing-map 执行：
```powershell
node --test tests/position-status.test.cjs tests/catalog-filters.test.cjs tests/use-review.test.cjs
npm run lint
npx tsc --noEmit
npm run build
```
- [ ] 全量 `node --test tests/*.test.cjs` 与基线比较，无新增失败；记录已存在失败。
- [ ] 若需要改变后端契约，先回到设计评审。本任务默认不改后端；定位行为疑点可复跑 test_position_status.py / test_collection_pipeline.py，使用独立 basetemp。
- [ ] trellis-check 对照 AC1–AC8；更新 directory-position.md / collection-pipeline.md 的旧下拉框与筛选呈现说明，补充 validation.md。
- [ ] git diff --check；报告范围、验证结果和未部署状态，仅按用户后续授权提交、推送或部署。

## 回滚点
候选卡片与筛选组件可分别回滚，无接口迁移。样式与对应 JSX 同步回滚，保留既有确认和收录规则。
