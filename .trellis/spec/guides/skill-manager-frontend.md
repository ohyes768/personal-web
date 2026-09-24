# Skill Manager 前端契约

> 维护 `apps/skill-manager/` 前端时的硬约束与已知环境限制。

## 两级导航（2026-09-23 重构）

- 一级按职责：`管理看板`（默认）/ `部署看板`；二级管理切来源（自研/GitHub）、看板切 agent（Hermes 在前且为默认，OpenClaw 在后）
- URL 是唯一真源：`?view=manage&tab=local|github` / `?view=board&agent=hermes|openclaw`；
  `useSearchParams` 派生 + `router.replace` 写；非法值逐级回退（view→manage，tab→local，agent→hermes）；需 `<Suspense>` 包裹（Next 15 静态渲染要求）
- 视图常驻挂载（Tailwind `hidden` 切换显隐），队列/筛选状态跨切换保留
- 下架唯一入口在部署看板；回滚已全面移除（后端 rollback 对核心场景无效，修复见独立任务）

## Next.js basePath 陷阱（实测踩过）

`basePath: '/skills'` 下，**`router.push/replace` 的路径不含 basePath**——
写 `router.replace('/skills?x=1')` 会双拼成 `/skills/skills?x=1`（404）。
正确写法：`router.replace('/?x=1')`，浏览器 URL 自动呈现为 `/skills?x=1`。

## 本机 dev 环境限制（Windows）

- **无 symlink 特权**（WinError 1314）：后端发布/下架的原子链接替换无法端到端运行，
  `pnpm build` 的 standalone 输出阶段同样失败（编译与 `tsc --noEmit` 不受影响）。
  发布链路的完整验证需在 Linux 容器（docker compose）内进行。
- launch.json 的 `skill-manager-api` 需把 `~/.local/bin` 加进 PATH 才能找到 `uv`（bash 环境）。
