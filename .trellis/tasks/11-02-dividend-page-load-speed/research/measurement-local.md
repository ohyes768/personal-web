# 本地验证与测量记录（2026-11-04）

## 环境

Windows 开发机 + 本地 fixture 数据（`backend/dividend-select/data/`，gitignored）：
主 CSV 2 只（601088/600900）、股东户数/财务指标/M120 上周快照/实时价格、
favorites 601088（配 4 档挡位）+ 600900（仅收藏）。数据池远小于 NAS 生产（202 只），
本地数字不能替代 NAS p95，只做行为与方向验证。

## 请求模式验证（R1，Browser network 面板）

`/?tab=alerts` 深链接（对应生产 `/dividend/?tab=alerts`）：

- 发出：favorites、favorites/alerts/status、`/stocks?min_yield=0&codes=601088,600900`
  （精确收藏资料）、`/prices?codes=…`（精确挡位现价）、m120/dividend/aux status、refresh/jobs。
- 不再发出：`/stocks?min_yield=3.5`（全量主列表）、全量 `/m120`、`/stats`。
- AlertLevelBar 完整渲染：4 档价格、现价 39.50、PE/PB、距挡位百分比、价格文件真实 mtime。
- `/`（全部 Tab）：主列表 + stats + 全量 m120 + codes 精确收藏资料 + prices，全部 200。

## 并发阻塞对照（R3 本地近似，2 只池）

8 并发混合读 + 2 路 health 探针（`bench_concurrent.py`，各 30 样本内 20 探针）：

| 版本 | health p50 | health p95 | 总墙钟 |
|---|---:|---:|---:|
| 改造前（stash 对照） | 164.5 ms | 373.5 ms | 2.0 s |
| 改造后 | 125.4 ms | 226.1 ms | 1.7 s |

本地池小，同步计算本就便宜，仍有 -40% p95；NAS 上基线混合并发 health 已到
1037 ms（见 baseline.md），隔离+快照收益会显著更大，部署后需按 baseline.md
方法复测 30 次（R5 的 NAS 部分留待部署授权后执行）。

## 单请求热态对照（本地，30 次采样）

改造前后单请求 p50 基本持平（health 10.1→5.9 ms、stocks_full 40.1→39.9 ms、
m120_full 22.3→26.0 ms）：本地 2 只池 + SSD 下重复解析本就便宜，与设计预期一致。
真实收益来自 202 只池上的重复组装消除与跨请求数（M120 每请求 3 次全量读 → 1 次构建）。

## 发现的既有问题（非本次引入，已留档不修）

- `filter_by_3y_dividend` 对空 DataFrame 抛 KeyError（m120/status、financial/status
  在主 CSV 缺失时 500）——本地数据缺失时暴露，生产有当月文件不触发。
- `/stats` 空数据分支缺 `yield_distribution` 等 3 个字段，pydantic 校验 500。
- `apps/dividend` 有并行任务 11-04-dividend-eslint-setup 正在接入 ESLint，
  `npx next build` 的 lint 阶段被 api-client.ts 存量 any error 阻塞（属该任务范围）；
  本任务验证用 `npx next build --no-lint` 确认编译与静态生成通过（tsc --noEmit 零错误）。
- `test_quality_service.py::TestQueueControls::test_append_and_reorder_keep_one_waiting_order`
  在改动前即失败（stash 对照 3/3），并发时序 flaky，与本任务无关。

## 前端测试说明

未新增 Playwright 用例：请求模式已由 network 面板人工验证并留档；ScreeningTab 挂载
分支未改动。`screening.spec.ts` 存在 3 个已知 stale 基线失败（frontend spec 记录）。
