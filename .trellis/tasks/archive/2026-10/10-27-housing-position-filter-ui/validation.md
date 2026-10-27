# 地点确认与分层筛选实现验证（2026-10-27）

## 已实现

仅改前端 `apps/housing-map`：新增 `src/components/community/CatalogFilters.tsx`，重写 `PositionPanel.tsx` 的候选呈现与确认顺序，收敛 `DirectoryFlowWorkspace.tsx` 的筛选状态为单一 `filters` 对象并接入新筛选组件，补充 `globals.css` 的候选卡片与筛选栏样式。删除已被取代的 `CatalogClassificationFilter`。

没有修改后端接口、收录规则、定位证据契约或生产数据库。确认请求体仍为 `{revision, poi_id}`，仅在无地址候选通过地图核对时附加 `coordinates_verified:true`；空的高德地址保持为空，不用来源地址替代。

## 离线检查

- 全量前端测试：`cd apps/housing-map && node --test tests/*.test.cjs` → **93 项中 90 通过，3 项失败**。3 项失败均为本任务开始前就存在的既有失败：`community-management` 的旧展示断言、`rental-dashboard` 与 `rental-sources` 缺组件，与本次改动无关，基线一致。
- 新增/改写测试：`tests/position-status.test.cjs`（候选卡片分行、完整类型折叠、单候选预选但不提交不预勾、核对标记绑定 revision+POI ID、状态行区分警示与错误、参考项折叠且不可选）、`tests/catalog-filters.test.cjs`（三页签条件矩阵、适用范围同时约束请求与摘要、可见标签与明确缺省项、更多筛选计数、生效摘要与单项移除、切页签保留搜索与区域）。
- `npm run lint` 无告警；`npx tsc --noEmit` 通过；`npm run build` 成功（Next 16.2.6 / Turbopack）。
- `git diff --check` 通过。

## 浏览器实测

生产构建 + `next start -p 3017`，Playwright 拦截 `/api/map/**` 喂假数据，不连真实后端、不写生产数据。脚本存于本任务目录 `browser-check.cjs`（Playwright 只装在 `apps/dividend/node_modules`，按绝对路径 require）。

1440px 与 390px 各一轮：

- 筛选栏按页签分层：已收录常驻 搜索/区域/房源类型/定位状态，更多折叠 用途核对/法拍/租金；待处理常驻 搜索/区域/来源用途/定位状态；不收录常驻 搜索/区域/来源用途。请求参数只含当前页适用条件——不收录页实测 `?state=excluded&workflow=excluded&page=1&district=滨江`，不含房源类型与定位状态。
- 切页签保留搜索与区域，页签专属条件清空并回到第一页。
- 候选卡片：名称与单选同行，地址与末级类型分行，完整分级类型在「完整类型」折叠内；参考地点在「相关地点，仅供参考（1）」内折叠且不可选。
- 选中候选后顶部状态行随之改写（`已选候选「鸿雁苑南门商业街」，核对地图后即可确认。`），不再停留在「需要你选择」。
- 无地址候选需勾选「已核对地图位置」，勾选前按钮禁用并显示 `请先查看地图并勾选已核对位置。`；勾选后确认，POST 实测载荷 `{"revision":"rev-1","poi_id":"B1","coordinates_verified":true}`。
- 390px 实测 `documentElement.scrollWidth === clientWidth === 390`，无横向溢出；搜索独占一行（366px），其余筛选两列（177px），候选卡片无溢出，确认按钮纵向铺满。

本轮修正了两处实机才发现的问题：`.directory-filter-field` 与 `.directory-filter-search` 同权重导致手机端搜索未独占一行；弹窗通用 `.directory-detail label` 规则把候选卡片的单选框撑成整行。

## 已知边界

- 并行会话同期在改后端定位批量补全（`41b8450` 及其后续未提交改动），涉及 `directory_position.py`、`collection_pipeline.py`、`directory_workflow_routes.py` 与 `directory-flow.test.cjs`。改动区域与本任务不重叠，两侧测试同跑通过（93 项中同样只有 3 项既有失败），前端筛选与确认契约未受影响。
- 未跑后端 pytest：本任务未改后端。若后续要改后端契约，需先回到设计评审。
- 未部署、未提交、未推送，等待用户后续授权。
