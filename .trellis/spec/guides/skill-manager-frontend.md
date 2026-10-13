# Skill Manager 前端契约

## GitHub 整包入口（2026-10-13）

- GitHub tab 用 PackWorkspace，一仓库一卡片；库存只读，无子技能/资源勾选。
- 包 API 与共用任务弹窗负责整包添加、安装、更新、转换和卸载。
- 部署看板 GitHub 按包显示；自研继续原单技能工作区。
- 更新不进旧发布队列，不需要再次发布；已链接目标共用新版。
- 旧 ZIP API/台账保留，包卡片不显示尚未实现的整包导出。
- 完整协议：../backend/skill-manager/backend/repo-packs.md。
- 下文批量勾选描述属于历史兼容代码，不是当前产品入口。

> 维护 `apps/skill-manager/` 前端时的硬约束与已知环境限制。

## 两级导航（2026-09-23 重构）

- 一级按职责：`管理看板`（默认）/ `部署看板` / `导出目标`；二级管理切来源（自研/GitHub）、看板切 agent（Hermes 在前且为默认，OpenClaw 在后）
- URL 是唯一真源：`?view=manage&tab=local|github` / `?view=board&agent=hermes|openclaw` / `?view=targets`；
  `useSearchParams` 派生 + `router.replace` 写；非法值逐级回退（view→manage，tab→local，agent→hermes）；需 `<Suspense>` 包裹（Next 15 静态渲染要求）
- 视图常驻挂载（Tailwind `hidden` 切换显隐），队列/筛选状态跨切换保留
- 下架唯一入口在部署看板；回滚已全面移除（后端 rollback 对核心场景无效，修复见独立任务）

## Next.js basePath 陷阱（实测踩过）

`basePath: '/skills'` 下，**`router.push/replace` 的路径不含 basePath**——
写 `router.replace('/skills?x=1')` 会双拼成 `/skills/skills?x=1`（404）。
正确写法：`router.replace('/?x=1')`，浏览器 URL 自动呈现为 `/skills?x=1`。

## GitHub 登记对话框的批量交互（2026-09-30）

`RegisterGithubDialog` 候选目录支持 checkbox 多选（>1 候选时有全选/清空）：

- **恰 1 项勾选** → 手填表单（名称/标签/简介，与单条登记一致）；
  **≥2 项** → 只读预填列表，按各候选 SKILL.md 的 `name` 批量登记
  （`POST /skills/github/batch`），名称/简介登记后逐个补充；
- 随行共享资源（shared_paths）默认预选扫描发现的 `referenced_paths`，但
  **排除候选目录的祖先目录**——勾上 `codex-skills/` 这类祖先会把整棵
  候选树拷进发布快照；
- `TaskProgressDialog`：done 且 `results.length > 0`（批量任务）停留展示
  逐项清单，"完成"按钮才触发 `onDone(task)` 关框+刷新；无 results 的单任务
  保持 done 自动关。部分成功时通知用 err 样式引导复查。

## GitHub 扫描等待状态（2026-10-13）

- `POST /github/scan` 返回 202 前可能做缓存检查与远端预检；loading 必须在请求发出前开启，不能只依赖返回的 task_id。
- 请求提交和后台任务运行期间显示 spinner、阶段与已用时；提交阶段用独立 state，并用 ref 防止重渲染前重复点击。
- 新一轮扫描先清除旧 task_id、候选选择与共享资源；请求失败或轮询失败退出 loading，保留错误提示并允许重试。
- 关闭弹窗只停止前端展示/轮询，服务端任务仍按原契约继续执行。

## 本机 dev 环境限制（Windows）

- **无 symlink 特权**（WinError 1314）：后端发布/下架的原子链接替换无法端到端运行，
  `pnpm build` 的 standalone 输出阶段同样失败（编译与 `tsc --noEmit` 不受影响）。
  发布链路的完整验证需在 Linux 容器（docker compose）内进行。
- launch.json 的 `skill-manager-api` 需把 `~/.local/bin` 加进 PATH 才能找到 `uv`（bash 环境）。
