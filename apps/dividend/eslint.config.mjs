/**
 * ESLint flat config（apps/dividend）
 *
 * 为什么用 FlatCompat 桥接：`eslint-config-next@15` 只发 eslintrc 风格的配置
 * （`core-web-vitals.js` 是 `module.exports = { extends: [...] }`），flat config
 * 是 v16 才有的。本项目仍在 Next 15.5.19，不能照抄 housing-map / skill-manager
 * 那套（它们在 Next 16 上）。见 .trellis/tasks/11-04-dividend-eslint-setup/design.md。
 *
 * 规则集与仓库其它 app 保持同构：next/core-web-vitals + next/typescript。
 */
import { FlatCompat } from "@eslint/eslintrc";
import { defineConfig, globalIgnores } from "eslint/config";
import { dirname } from "path";
import { fileURLToPath } from "url";

const compat = new FlatCompat({ baseDirectory: dirname(fileURLToPath(import.meta.url)) });

export default defineConfig([
  ...compat.extends("next/core-web-vitals", "next/typescript"),

  // 本项目用 `_` 前缀表达「解构出来只为丢弃」（如 markdown 组件的 `{ node: _node, ...props }`、
  // e2e 里剔除某个 key 的 `const { '000002': _removed, ...rest }`），不该按未使用变量报错。
  {
    rules: {
      "@typescript-eslint/no-unused-vars": [
        "warn",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          ignoreRestSiblings: true,
        },
      ],
    },
  },

  // 这两个文件的 hook 依赖数组刻意不含「每渲染新建的数组/对象」
  //（eligibleCodes / stockCodes / refreshJobs 等），照插件建议加依赖会引发无限重渲染与请求风暴。
  // 逐条判定与证据见 .trellis/tasks/11-04-dividend-eslint-setup/research/hook-deps.md。
  // TODO: 11-02-dividend-page-load-speed 落地后改回逐点处理，恢复该规则在这两个文件里的检查。
  {
    files: ["src/app/page.tsx", "src/lib/hooks.ts"],
    rules: { "react-hooks/exhaustive-deps": "off" },
  },

  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    "test-results/**",
    "playwright-report/**",
  ]),
]);
