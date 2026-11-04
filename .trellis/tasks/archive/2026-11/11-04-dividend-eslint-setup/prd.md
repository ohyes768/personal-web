# 股息率前端接入 ESLint 并清理存量问题

## 目标与用户价值

`apps/dividend` 的 `npm run lint` 目前**从未真正执行过 lint**：`package.json` 里写的是 `next lint`，而 Next 15.5 已弃用该命令（Next 16 彻底移除），且项目没有 ESLint 配置，跑起来只会弹交互式向导、在脚本/CI 里无法使用。

补上配置后，lint 从「形同虚设」变成**真实的质量门**：以后改这个前端能被自动拦住 `any`、死代码和 hook 依赖问题。

## 已确认的现状（实测，非推测）

| 事实 | 依据 |
|------|------|
| `apps/dividend/package.json` 的 lint 脚本是 `next lint` | 文件内容 |
| 项目无 `.eslintrc*` / `eslint.config.*`；`next lint` 进交互向导 | 实际执行观察 |
| Next 15.5.19 的 `eslint-config-next` **只提供 eslintrc 风格配置**（`core-web-vitals.js` 是 `module.exports = { extends: [...] }`），flat config 是 v16 才有的 | `node_modules/eslint-config-next/package.json` 与文件内容 |
| 仓库已有现成范式：`apps/housing-map`、`apps/skill-manager` 用 flat config + `eslint` CLI；housing-map 当前 lint **零告警** | 两者 `eslint.config.mjs` + `package.json`；实测 `npx eslint .` 输出为空 |
| 装好依赖试跑 `eslint .`：**6 errors + 34 warnings**，分布在 15 个文件 | 实测输出 |
| 6 个 error 全是 `src/lib/api-client.ts` 的 `@typescript-eslint/no-explicit-any` | 实测输出 |
| 34 个 warning = 22 个 `no-unused-vars` + 12 个 `react-hooks/exhaustive-deps` | 实测输出 |
| **12 条 `exhaustive-deps` 全部是误报**，照插件建议加依赖反而会引入无限重渲染 | `research/hook-deps.md` 逐条判定 |
| `ApiResponse` 接口与 `apiClient`（wrapped 模式客户端）全仓无调用方，是死代码 | 全仓 grep |

## 需求

| ID | 需求 |
|---|------|
| R1 | `apps/dividend` 提供 ESLint flat config，`npm run lint` 能真正跑完并**非交互**退出。配置方式与仓库既有的 housing-map / skill-manager 保持同构。 |
| R2 | lint 脚本从 `next lint` 改为 `eslint` CLI（`next lint` 在 Next 16 已移除）。依赖版本与本项目 Next 15.5.19 匹配。 |
| R3 | **0 error**。修掉 `api-client.ts` 的 6 个 `no-explicit-any`，且**不改变任何调用方行为**（`api.ts` 现有 20+ 处 `directClient.get<T>/post<T>` 调用零改动）。 |
| R4 | `react-hooks/exhaustive-deps` 的 12 条按研究结论处理：确属误报的，用**不改变运行时行为**的合法修法消除；无法在不碰并发改动文件的前提下处理的，定向 suppress 并写明理由。 |
| R5 | 存量 `no-unused-vars` 不做批量删除（多数是预存死代码与 Next.js 路由签名约定，删除属超范围改动），改为登记留档；**本次新增文件里的未使用变量必须清理干净**。 |
| R6 | 不因本任务改动任何运行时行为：改完 `tsc --noEmit`、生产构建、全量 Playwright 必须全部通过。 |
| R7 | 与并发任务隔离：`11-02-dividend-page-load-speed` 正在改 `src/app/page.tsx`、`src/lib/hooks.ts`、`src/lib/types.ts`，本任务**不得改动这三个文件**，相关告警登记留档待其落地后单独收尾。 |
| R8 | 文档同步：frontend spec 索引里「next lint 需要初始 ESLint 配置」的说明改为现状描述；测试清单补一条 lint 检查项。 |

## 验收条件

| ID | 对应需求 | 可观察结果 |
|---|---|---|
| AC1 | R1、R2 | `cd apps/dividend && npm run lint` 无人机交互直接结束，exit code 0；`package.json` 的 lint 脚本为 `eslint`；`eslint.config.mjs` 存在且带 `eslint-config-next` 的 core-web-vitals + typescript 规则集 |
| AC2 | R3 | `npx eslint .` 输出 `0 errors`；`api.ts` 的 `directClient.*` 调用点 diff 为空；`npx tsc --noEmit` exit 0 |
| AC3 | R4 | `exhaustive-deps` 告警从 12 条降到 0 条（要么合法修复，要么定向 suppress 并附理由注释）；无 `eslint-disable` 出现在新增代码之外的无关位置 |
| AC4 | R5 | 本次新增/修改的文件里 `no-unused-vars` 为 0；剩余存量未使用变量在任务文档中列明文件与数量 |
| AC5 | R6 | `npx tsc --noEmit` exit 0；`npm run build` exit 0；`npx playwright test` 全量 54 passed / 0 failed |
| AC6 | R7 | `git diff` 不含 `src/app/page.tsx`、`src/lib/hooks.ts`、`src/lib/types.ts`；并发任务 11-02 的未提交改动未被触碰 |
| AC7 | R8 | frontend spec 索引不再声称 lint 不可用；测试清单出现 lint 检查项 |

## 不在本次范围

- 迁移到 Next 16、升级 `eslint-config-next` 到 v16（dividend 仍在 Next 15.5.19）。
- 清理全部 22 个存量 `no-unused-vars`、删除 `ApiResponse`/`apiClient` 死代码、`useStockInfo` 死链。
- 为其它 7 个 app 补 ESLint 配置。
- 修复「卸载只作废序号、没真正 abort 请求」的行为改进（属功能改动，另立任务）。
- 改动 `page.tsx` / `hooks.ts` / `types.ts`（并发任务在改）。
