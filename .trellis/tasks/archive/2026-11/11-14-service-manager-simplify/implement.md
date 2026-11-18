# 实施计划：service-manager 瘦身

> 配套 `prd.md` / `design.md`。每步做完跑对应验证；绿灯再进下一步。

## 步骤 0 · 前置

- [x] 决策已确认（Q1–Q6，见 prd.md）
- [x] 基线绿灯：后端 `pytest` 208 passed；前端 `tsc`/`eslint` 0 问题；e2e 23 passed / 1 skipped
- [x] 工作树盘点：发现另一个会话的「退役归属」改动未提交且与本任务重叠 → 先单独提交收尾，再在本任务基线上做

## 步骤 1 · 删详情页与它的入口

- [x] 删除 `apps/service-manager/app/service/[id]/page.tsx`（整个目录）
- [x] `app/page.tsx`：删服务名到详情页的 Link（服务名改成纯文本）、删「打开」按钮、删「主入口」列
- [x] `app/discovery/page.tsx`：删「查看服务」链接；导入后跳列表页（原来跳详情页）
- [x] 验证：`pnpm exec tsc --noEmit && pnpm lint`；`/service/{id}` 返回 404（e2e 断言）

## 步骤 2 · 列表页收敛与接住新能力

- [x] `app/page.tsx`：
  - [x] 状态维度只留**运行**+**健康**（删 URL/证书/发布徽章）
  - [x] 删「巡检」按钮（巡检的对象是入口，入口已下线）；refresh 只剩 docker 一种
  - [x] **行内编辑名称 + 用途**（input/textarea + 保存/取消，保存后就地更新并覆盖 revision）
  - [x] **移除服务**按钮（confirm 文案沿用原详情页）
  - [x] 「操作」列重排：编辑 + 移除（行加 data-service-id 便于定位）
- [x] 验证：`tsc`/`eslint`；e2e 覆盖改名称 / 改用途 / 保存 / 移除

## 步骤 3 · 资源总览与发现导入收敛

- [x] `app/resources/page.tsx`：删「域名」「证书」tab，只留端口
- [x] 验证：e2e 断言资源总览没有 tab、只有端口列

## 步骤 4 · 清理前端不再用的类型与封装

- [x] `lib/api.ts`：删 endpoints / port_notes / release_sources / releases / markRead / 组件绑定类方法与相关类型（535 行 → 323 行）
- [x] `lib/status.ts`：删只服务被下线维度的常量与函数（URL_STATE / TLS_STATE / RELEASE_STATE / JOB_STATE / describeCheck / tlsTone / tlsTooltip / invalidReasonOf…），保留运行与健康部分
- [x] `components/Widgets.tsx`：删 `SafeLink` 与 `CopyButton`（都只服务已下线的详情页）
- [x] `lib/jobs.ts`：巡检文案随按钮下线（describeJob 保留 docker 分支）
- [x] 验证：`tsc`/`eslint` 0 问题

## 步骤 5 · e2e

- [x] 重写用到详情页的用例：
  - [x] 「台账条目走接口建立后，搜索、加端口、删除都可用」→ 改成「搜索命中、行内改名称与用途、移除」
  - [x] 「归属可逐条改」→ 已由 ownership-retirement 任务改写（列表平铺）
- [ ] 新增：行内编辑名称与用途（保存后列表立即变）
- [ ] 新增：访问 `/service/{id}` 返回 404
- [ ] 「资源总览三个标签可切换」→ 改成只剩端口视图
- [ ] 375px 断言仍要过（表格列变少，风险更低）
- [x] 全量：`pnpm exec playwright test` —— 23 passed / 1 skipped

## 步骤 6 · spec 更新（Phase 3.3）

- [x] `.trellis/spec/apps/service-manager/frontend/index.md`：写明**已下线**的能力清单（详情页、入口/发布维护、组件明细、域名/证书总览、单服务检查），以及「列表页是唯一维护面」
- [x] `.trellis/spec/backend/service-manager/backend/index.md`：新增 §2.10「界面已下线、实现暂留的能力」——后端接口/数据/备份格式不变，**下线的是界面不是检查**
- [x] 原 PRD 的 R3/R4/R5/R6(部分)/R7 口径写进 spec（历史 PRD 原文不动）

## 步骤 7 · 收尾（Phase 3.4）

- [x] 重建前端容器（后端没改，不用重建）
- [ ] `git status --porcelain` 盘点脏文件，区分「本次改的」与「别人的」
- [ ] 拟提交计划 → 用户确认 → 分批提交（**不 push**）
- [ ] 提醒用户跑 `/trellis:finish-work`

## 风险与回滚

| 风险 | 处置 |
|------|------|
| 误删后端接口/数据 | 本任务**只动前端**；后端代码与数据一行不改 |
| 行内编辑漏更新 revision → 下次 PATCH 409 | 保存成功后用后端返回的 `revision` 覆盖本地值 |
| 删了 `status.ts` 里还被别处引用的导出 | `tsc --noEmit` 会报出来；逐个确认再删 |
| 与别人同时改 `apps/service-manager` | 动手前先 `git status` 看脏文件 |
