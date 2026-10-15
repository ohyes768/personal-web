# Skill Manager 前端契约

> 维护 `apps/skill-manager/` 前端时的硬约束与已知环境限制。

## 两级导航（2026-09-23 重构）

- 一级按职责：`管理看板`（默认）/ `部署看板` / `导出目标`；二级管理切来源（自研/GitHub），部署看板仅 Hermes。
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
- GitHub 安装直接软链到仓库登记目录；不再提供随行共享资源拷贝选项。旧 shared_paths 字段保留兼容但不参与安装。
- `TaskProgressDialog`：done 且 `results.length > 0`（批量任务）停留展示
  逐项清单，"完成"按钮才触发 `onDone(task)` 关框+刷新；无 results 的单任务
  保持 done 自动关。部分成功时通知用 err 样式引导复查。

## GitHub 扫描等待状态（2026-10-13）

- `POST /github/scan` 返回 202 前可能做缓存检查与远端预检；loading 必须在请求发出前开启，不能只依赖返回的 task_id。
- 请求提交和后台任务运行期间显示 spinner、阶段与已用时；提交阶段用独立 state，并用 ref 防止重渲染前重复点击。
- 新一轮扫描先清除旧 task_id 与候选选择；请求失败或轮询失败退出 loading，保留错误提示并允许重试。
- 关闭弹窗只停止前端展示/轮询，服务端任务仍按原契约继续执行。

## 本机 dev 环境限制（Windows）

- **无 symlink 特权**（WinError 1314）：后端发布/下架的原子链接替换无法端到端运行，
  `pnpm build` 的 standalone 输出阶段同样失败（编译与 `tsc --noEmit` 不受影响）。
  发布链路的完整验证需在 Linux 容器（docker compose）内进行。
- launch.json 的 `skill-manager-api` 需把 `~/.local/bin` 加进 PATH 才能找到 `uv`（bash 环境）。

## GitHub 仓库合集（2026-10-13）

- 管理/部署视图按规范化完整 owner/repo 派生合集；不创建合集表，逐 Skill 直链仓库缓存登记目录。GitHub Tab 计数为仓库组数，合集卡片标明已登记成员数量。
- URL .git 后缀、末尾斜线与大小写归一；不同 owner 不合并；异常仓库地址各自独立显示，不能静默丢失条目。
- 先用完整成员形成合集，再用筛选匹配集合控制成员展示；“全部发布/下架”按钮标明完整数量，操作不受搜索过滤裁剪。
- 全部发布只加入原发布队列；重复加入幂等，仍需计划预览与密码确认。队列改变后旧计划失效，计划请求期间改队列也必须拒绝旧响应。
- 已发布计数排除 link_missing；异常/成功/失败仍以成员为准，不保存合集状态。
- 每轮扫描结束默认全选候选并折叠详情；用户清空/调整后不能被同轮快照重新初始化；单候选预填名称与简介。不再配置共享资源拷贝。
- 检查更新继续只读；恢复缓存每合集一次 Clone，不声称已部署。远端新增成员需重新扫描登记。
- 下架沿用部署看板入口，批量逐项展示结果；成功项不重试。发布后失败/阻止项留队，成功/unchanged 项退出，原计划中的 blocked/unchanged 明细保留。
- 验证在 Windows 本机运行；本任务不安排 WSL/NAS 写操作。模拟 API 浏览器验证与真实软链部署验证需明确区分。

## Hermes 安装与一键安装（2026-10-13）

- Hermes 默认环境及配置登记的 profiles 是软链接安装目标；OpenClaw 标识、配置和 UI 已完全移除，二级导航不再有 agent 切换。
- GitHub 与自研 Skill 走同一 `InstallDialog`：自动取计划 → 一次密码确认 → 后台安装。正常流程不再需要独立登记、队列或计划预览步骤。
- 新增 GitHub Skill 与补充合集成员均提供「仅登记 / 登记并安装到 Hermes」两个入口。「仅登记」复用单条/批量登记 API，密码确认后显示登记任务进度，不调用安装 API、不创建 Hermes 链接；登记后可管理和导出。另一入口继续使用统一 `InstallDialog`。请求失败保留确认弹窗允许重试，重复确认需 ref 锁拦截。
- 多选安装/合集一键安装复用同一个对话框和 request_id 幂等；部分成功明确标出"已登记/未安装"，重复点击 409，错误密码无副作用。
- 注册与安装分开记账：GitHub 仓库同一身份不重复登记；安装失败不删除已登记条目。
- 部署看板按当前 Hermes profile 展示；下架操作保留，密码验证仍在。静态导出目标独立视图不受影响。

## 管理列表安装筛选（2026-10-14）

- GitHub 合集头部提供「＋ 添加成员」，复用登记弹窗并预填规范仓库 URL；数量标为「已登记」，不声称是仓库总数。扫描后按规范化仓库身份与相对路径标记已登记项并禁选，默认/全选只选择未登记候选。沿用缓存优先扫描；远端新增成员需要先更新缓存。

- 安装状态提供「全部 / 已安装 / 未安装」三项，默认全部；全部不限制安装状态，仍应用搜索、标签和更新筛选。
- 已安装要求 Hermes 部署记录为 `active` 且 `link_missing` 为 false；无记录、下架或链接缺失均归入未安装。外部导出记录不影响安装筛选。
- 自研 Skill 独立卡片只提供单卡安装，不显示成员选择框或批量选择栏；多选和批量安装仅用于 GitHub 合集成员。
- 已安装且链接正常的自研 Skill 不显示更新按钮：软链直接读取源目录，文件修改自动生效；未安装或链接缺失时保留安装入口。GitHub 保留更新缓存入口，缓存更新会同步作用于同仓库已安装的直链成员。
- GitHub 已安装且没有待更新内容时，更新按钮使用中性描边；仅未安装或存在 `update.has_update` / Hermes `stale` 时突出主操作，仓库缓存 HEAD 更新后同步刷新所有成员的更新提示。
- 卡片安装徽章与合集安装计数省略单目标 Hermes 前缀，使用「已安装 / 未安装」；下架显示未安装，链接缺失显示「未安装 · 链接缺失」。
- 安装徽章统一为 24px 高圆角胶囊：绿色勾号表示已安装、灰色圆点表示未安装、橙色感叹号表示链接缺失；版本号放入已安装徽章的悬停提示。
- 安装徽章紧邻标题，窄卡片允许换行；无外部导出记录时不保留独立状态行。底部安装/更新用文字主按钮，下架用同高度的红色文字按钮；导出、编辑、删除用带提示的图标。
- 自研卡片列表与 GitHub 合集成员详情复用同一网格样式：小屏一列、md 两列、lg 三列，间距和卡片拉伸方式一致。
- 管理列表的检索与筛选固定在卡片滚动区上方；仅卡片列表使用 `min-h-0 flex-1 overflow-y-auto`，筛选区不随列表滚动。
- GitHub 勾选、全选、清空与安装所选仅作用于所在合集，页面顶部不提供跨合集批量栏。全选只选当前可见且源/缓存可用的成员；安装所选排除不可用成员，隐藏的已选成员明确显示数量。不提供「安装整个合集」入口，批量安装统一通过显式选择完成。
- 合集默认折叠为概览卡片，展示「合集 · N 项」图层图标、仓库名、owner/repo、安装比例与成员名称预览；展开后才显示仓库操作与合集选择栏。成员卡片省略重复仓库和 GitHub 来源徽章，复选框与名称同一行，保留状态和单卡操作。
- GitHub Tab 命名为「GitHub Skill」，不新增 Tab。按仓库完整登记成员数展示：单项直接显示「独立 Skill」文档图标卡片与 owner/repo，无合集外框、折叠和多选；多项折叠时与独立卡片同宽，展开后跨整行展示成员。两者共用三列响应式网格；筛选仅剩一个可见成员时不把多项合集降成单项。Tab 计数仍为仓库组数。

## Hermes 多 profile（2026-10-14）

- URL `target=<ID>` 是管理/部署看板共同目标，缺省回到 legacy hermes。未知/不可用目标提示并保留，不静默转到其他目标。名单来自 `/api/skills/install-targets`，ZIP 配置仍独立。
- InstallTargetsContext 提供当前目标、catalog 和加载/错误状态。SourceWorkspace 筛选、SkillPool 徽章/合集计数和 DeployBoard 下架均消费当前 ID；外部导出分类用 isInstallTarget，不能把未选中 profile 当导出。
- InstallDialog 捕获打开时当前目标，固定沿用标题旁的环境选择；仅只读显示该目标名称、profile 和安装路径，不提供环境复选框。首次预览的 target_ids 固定为该目标，不采用调用方传入的其他默认目标。输入变化立即清旧计划，cleanup 忽略旧响应；结果按 skill_id/target 组合显示。catalog 加载失败不得确认安装。
- 已登记失败项重试发送 items 精确组合；扫描候选失败项保留 scan_task_id/path，并附 candidate.targets 精确失败组合，已登记候选由服务端复用身份。成功组合不重试。
- 共享更新影响列表含本次未选 profile；Clone 同样展示已安装的共享成员/目标。安装成功仅验证链接，真实 Hermes 发现另做部署验收。

## 网页安装目标管理

`view=install-targets` 与原 ZIP `view=targets` 分开。默认行只读，named profile新增/改名/删除由密码确认，active删除只提示并跳当前target部署看板。候选选择不输入任意路径。catalog removed行保留管理页历史摘要，选择器和安装弹窗排除removed；当前URL被删后保留未知提示，不自动换目标。CRUD成功刷新catalog，异步候选发现使用generation/mounted避免旧响应；revision冲突需刷新/重新打开确认，不保留密码。

## Profile scope picker（2026-10-15）

UI 形态由 header 下方裸 `<select>` 升级为**应用级 scope bar**（`ProfileScopePicker` 组件），跨视图常驻在 `<header>` 右侧。这是所有多 profile 工具应遵循的模式，未来若新增 provider（OpenClaw 之外）也走同一组件。

### 跨视图常驻：scope picker 是 scope 不是 navigation

- `ProfileScopePicker` 必须挂在 `<header>` 内、四个视图（`view ∈ {manage, board, install-targets, targets}`）外层共享。
- **绝不要**把 picker 包在 `{view === 'manage' || view === 'board' && ...}` 这种视图条件里——install-targets 视图下用户改完 profile 配置后必须能立刻看到当前 scope。
- 这是 operate-mode 工具的标配模式（GitHub org、Vercel team、AWS region、Slack workspace、Linear workspace）。
- **位置选择**：放在 `<h1>` 同行右侧（`flex items-baseline gap-3`），不放在 header 右侧跟 tabs 挤一行；tabs 自己占独立一行。理由：title + picker 是"identity 块"，tabs 是"navigation 块"，两个语义层级不该共用一行。GitHub/Vercel/Linear 都把 team/workspace 切换器紧贴 logo/title 放左侧，不放远端右侧。

### Provider · profile_name 渲染格式

- 触发器 button 与 popover 列表项统一显示 `<provider_label> · <profile_name>`（如 `Hermes · ohyes768`）。
- 数据 `provider` 字段是小写 `hermes`；通过组件内 `PROVIDER_LABEL` map 渲染大写 `Hermes`。新增 provider 时只需扩 map，无需改其它逻辑。
- **不要直接用 `name` 字段**——`name` 是用户起的显示名（如 "Default dev"），`profile_name` 是真实身份（如 "default"）；显示真实身份让用户知道操作的目标。

### install_path 永远不进 header

- header 中**不渲染** `install_path`——路径会撑宽 row、视觉上压过 picker 本身。
- `install_path` 只在 popover 列表项里以 `font-mono` chip + `title` attr 显示完整路径。
- header 唯一允许的信息是 `provider · profile_name` + 色点状态指示 + chevron。

### 状态色点映射

| 状态 | 色点 class | trigger 边框 | trigger 文字 |
|---|---|---|---|
| `available && !removed` | `bg-emerald-500` | 默认 | `Hermes · <name>` |
| `!available && !removed` | `bg-amber-500` | `border-amber-400` | `目标不可用：<reason>` |
| `removed`（仅当前选中） | `bg-slate-300` | `border-slate-200` | `<name>（已移除）` |
| `loading` | `bg-slate-300 animate-pulse` | `border-slate-200` | `加载中…` |
| `error` | `bg-rose-500` | `border-rose-400` | `加载失败` |
| URL `target` 不在 catalog | 同 unavailable | `border-amber-400` | `<id>（不可用）` |

- 不可用态 `unavailable_reason` 取第一行（`.split('\n')[0]`），避免 button 内文字过长。
- 已移除态：trigger 仍显示当前已移除的 target（色点灰），但 popover 默认列表过滤掉——用户可通过 `管理安装目标 →` 跳到 install-targets 页恢复。

### popover 自写约定

- 不引入 Headless UI / Radix 等 popover 库——单点使用不值得加依赖；当前页面其它 dialog（`ConfirmActionDialog` / `RegisterGithubDialog` / `TaskProgressDialog`）都是自写，保持一致。
- 触发器 button 加 `aria-haspopup="dialog"` `aria-expanded`；popover 加 `role="dialog"` `aria-label`。
- 外点击 / Esc 关闭用 `useEffect` 挂 `mousedown` + `keydown` listener，cleanup 移除；SSR/测试环境必须有 `typeof document === 'undefined'` 守卫，否则 server render / `renderToStaticMarkup` 会炸。
- popover 绝对定位：`absolute right-0 top-full mt-1 z-30 w-[360px]`，列表 `max-h-72 overflow-y-auto`，列表项 `data-active="true"` 用 sky 背景 + 左侧 2px sky border。

### 数据复用：不要为 picker 单独建 store/context

- picker 完全消费 `InstallTargetsContext` 已有的 `targets` / `current` / `loading` / `error`——单一数据源，picker 永远反映后端最新 catalog。
- 切换 scope 仍走 `navigate({ agent: id })` → URL `?target=<id>` 变化 → useSearchParams 触发 re-render → 子组件（SourceWorkspace / DeployBoard）行为不变。
- picker 的 `targets` prop 应传**完整 catalog（含 removed）**，让 picker 内部按需过滤——这样 trigger 能显示当前已移除 target 的灰态，popover 列表过滤掉。

### `pnpm build` 与 dev server 共存陷阱

- 同目录同时跑 `pnpm dev` 和 `pnpm build` 会冲突：`pnpm build` 改写 `.next/` 产物（特别是 `.next/server/app/<id>.js`），正在跑的 `pnpm dev` 下一次请求会 `Cannot find module './<id>.js'`。
- 验证流程 `pnpm build` 后**必须 kill dev server 再重启**（同端口，因为 `pnpm dev` 锁 3008）；不要并行起第二个 dev server（CLAUDE.md 硬规则）。
- Windows + pnpm standalone trace copy 报 `EPERM: symlink`（react / client-only / @swc/helpers / @next/env）是已知环境限制，**只影响 `.next/standalone`，不影响 dev 与常规 build**——验证时跳过 standalone 步骤即可。

### 单测覆盖矩阵（`ProfileScopePicker.test.ts`，15 项）

T1-T5 状态矩阵：available / unavailable / loading / error / invalid-id
T6-T9 交互矩阵：开 popover / 选 item + 关 / 点管理 + 关 / 点刷新
T10 popover 内容：path chip + active count
T11 unavailable_reason 第一行展示
T12 已移除态：trigger 显示 + popover 过滤
T13 toggle：再次点 trigger 关闭
T14 空 catalog：`暂无 profile` 空态
T15 active 列表项：`data-active` + sky class

测试用 `renderToStaticMarkup` + `InstallTargetsContext.Provider`（参考 `ProfileViews.test.ts`），不引入 jsdom。

