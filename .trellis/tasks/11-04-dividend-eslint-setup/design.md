# 股息率前端 ESLint 接入 · 技术设计

## 边界

只改 `apps/dividend` 的 lint 配置、`package.json`、`src/lib/api-client.ts`、3 个 hook 相关源文件，以及相关文档。不改 nginx、basePath、后端，不改其它 app，不升级 Next。

## 配置形态：为什么是 FlatCompat

仓库里 `apps/housing-map`、`apps/skill-manager` 用的是 flat config：

```js
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
```

**但那只在 `eslint-config-next` v16 成立。** dividend 停在 Next 15.5.19，其 `eslint-config-next@15.5.19` 只发 eslintrc 风格的配置：

```js
// node_modules/eslint-config-next/core-web-vitals.js
module.exports = { extends: [require.resolve('.'), 'plugin:@next/next/core-web-vitals'] };
```

直接照抄 housing-map 会 `ERR_MODULE_NOT_FOUND`（且 v15 没有 `exports` 字段，ESM 还得带 `.js` 后缀）。

**方案**：用 Next 15 官方迁移路径 `@eslint/eslintrc` 的 `FlatCompat` 把 eslintrc 配置桥接进 flat config：

```js
import { FlatCompat } from "@eslint/eslintrc";
import { defineConfig, globalIgnores } from "eslint/config";
import { dirname } from "path";
import { fileURLToPath } from "url";

const compat = new FlatCompat({ baseDirectory: dirname(fileURLToPath(import.meta.url)) });

export default defineConfig([
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts", "test-results/**", "playwright-report/**"]),
]);
```

`@eslint/eslintrc` 是 `eslint` 自带依赖，但需在 devDependencies 里显式声明（flat config 模式下不自动可用）。

**备选与否决理由**：把 dividend 升到 `eslint-config-next@16` 与 Next 15.5.19 版本错配，且属于「升级框架」级别改动，超出本任务范围。

## 依赖与脚本

```jsonc
"scripts": { "lint": "eslint" },          // 原 "next lint"
"devDependencies": {
  "eslint": "^9",                          // eslint 9 才支持 flat config
  "eslint-config-next": "15.5.19"          // 与 Next 版本对齐（housing-map 用 16.2.6，因为它在 Next 16）
}
```

包管理器沿用仓库统一的 pnpm（`pnpm add -D`）。

## 规则调整

`next/typescript` 把 `@typescript-eslint/no-unused-vars` 设为 warn（默认参数）。加两条本项目需要的约定：

```js
{
  rules: {
    "@typescript-eslint/no-unused-vars": ["warn", {
      argsIgnorePattern: "^_",
      varsIgnorePattern: "^_",
      ignoreRestSiblings: true,
    }],
  },
}
```

- `^_` 前缀：本项目用 `_node` 表达「解构出来只为丢弃」的写法（`QualityReportContent.tsx` 的 markdown `table` 组件），以及 e2e 里 `const { '000002': _removed, ...rest }` 的剔除写法。
- `ignoreRestSiblings`：与解构剔除写法同源，避免逐处 disable。

## api-client.ts 的 6 个 error

现状：

```ts
export interface ApiResponse<T = any> { ... }                                  // L4
async get<T>(endpoint: string, params?: Record<string, any>): Promise<T>         // L67
async post<T>(endpoint: string, data?: any): Promise<T>                          // L94
async put<T>(endpoint: string, data?: any): Promise<T>                           // L99
async patch<T>(endpoint: string, data?: any): Promise<T>                         // L104
async delete<T>(endpoint: string, params?: Record<string, any>): Promise<T>      // L109
```

**坑**：把 `Record<string, any>` 直接换成 `Record<string, unknown>` 会在调用点炸一片——TS 的隐式索引签名只对 type alias 生效，`DividendQueryParams`、`BoardInfoRequest` 这些 **interface** 不满足 `Record<string, unknown>`。

**方案**（研究已验证：typecheck exit 0、调用方零改动）：

```ts
export interface ApiResponse<T = unknown> { ... }

async get<T, P extends object = object>(endpoint: string, params?: P): Promise<T>
async post<T>(endpoint: string, data?: unknown): Promise<T>
async put<T>(endpoint: string, data?: unknown): Promise<T>
async patch<T>(endpoint: string, data?: unknown): Promise<T>
async delete<T, P extends object = object>(endpoint: string, params?: P): Promise<T>
```

- `P extends object = object` 的默认值不能省：否则 `directClient.get<QualityJob>(url)` 这类**只显式给 T** 的调用会报 TS2558（缺少类型参数）。`P extends object` 保证 interface 类型也能传入，`Object.entries(params)` 内部照常工作。
- `data?: unknown`：请求体只喂给 `JSON.stringify`，`unknown` 完全够用；调用方传对象字面量不受影响。
- `ApiResponse` 与 `apiClient`（wrapped 模式）全仓无调用方，但**本任务不删**（删死代码属超范围，见 PRD），只把 `any` 换成 `unknown`。

## 12 条 exhaustive-deps 的处理

研究结论（`research/hook-deps.md`）：**全部是误报**，根因是依赖数组刻意不含「每次渲染新建的数组/对象」。**照插件建议加依赖会引入无限重渲染 + 请求风暴**——例如 `ScreeningTab.tsx:85` 的 `eligibleCodes` 是 render 内联表达式，每渲染都是新数组，加进 `useRealtimePrices` 的 memo 依赖会让 effect 每渲染重跑。

因此分两类处理：

**A. 合法修复（不改变运行时行为）——3 个不在并发改动范围的文件**

| 文件 | 修法 |
|---|---|
| `src/lib/hooks/useQualityAnalysis.ts` | `stopPolling` 是 `useCallback([])`，引用终身稳定 → 直接加进依赖数组，effect 不会多跑 |
| `src/lib/hooks/useRealtimePrices.ts` | 抽 `codesKey = JSON.stringify(codes)`，memo 依赖改用 `codesKey`（内容相同→引用稳定，内容变→引用变，与原语义一致） |
| `src/components/ScreeningTab.tsx` | 把 `requestId.current++` 抽成稳定的 `useCallback` 包装器，`++` 语义等价 |

**B. 配置级临时桥接——2 个正在被并发任务改动的文件**

`src/app/page.tsx`（1 条）与 `src/lib/hooks.ts`（7 条）正在被 `11-02-dividend-page-load-speed` 重写，**不能插入行内 `eslint-disable` 注释**（会与并发编辑打架）。改为在配置里按文件范围关规则：

```js
// 这两个文件的依赖数组刻意不含每渲染新建的数组/对象（见 research/hook-deps.md），
// 照插件建议加依赖会引发无限重渲染。11-02 落地后改回逐点处理。
{ files: ["src/app/page.tsx", "src/lib/hooks.ts"], rules: { "react-hooks/exhaustive-deps": "off" } },
```

代价与回收：这两文件内**新增**的真实依赖缺失不再被 lint 捕获。已在任务文档登记，`11-02` 落地后应改回逐点 `eslint-disable` + 理由注释。

## 剩余 warning 的处理

22 个 `no-unused-vars` 中：

- 2 个（`_removed`、`_node`）由 `varsIgnorePattern: "^_"` 覆盖 → 归零；
- 其余 20 个是**预存死代码**（未使用的 import/函数/变量，以及 `route.ts` 里 Next.js 路由签名自带的 `params`）。按 PRD R5 **只登记不删**——批量删死代码是超范围改动，且 `params` 属框架签名约定。

最终 lint 结果：**0 error，20 个 unused-vars warning，exit 0**。

## 与并发任务的隔离

`11-02-dividend-page-load-speed` 正在改：`src/app/page.tsx`、`src/lib/hooks.ts`、`src/lib/types.ts`，以及 `backend/dividend-select/**`。

本任务的硬边界：

- 不写这三个 dividend 文件；
- 不写 `backend/**`；
- `package.json` / `pnpm-lock.yaml` 本轮只有本任务改动（`11-02` 目前未碰它们，但提交时需重新核对 diff）；
- 提交前必须 `git diff` 确认只含本任务文件。

## 兼容与回滚

- 无数据迁移、无接口变更、无新增运行时依赖（eslint 仅为 devDependency，不进生产包）。
- `eslint` 不参与 `next build`，不影响生产构建产物。
- 回滚：删除 `eslint.config.mjs`、`package.json`/`pnpm-lock.yaml` 回退、`api-client.ts` 与 3 个 hook 文件回退、文档回退。
- 不加 ESLint 前，`next build` 内建的类型检查是唯一防线；加上后 lint 与类型检查互补，但**不能替代**类型检查与 E2E。
