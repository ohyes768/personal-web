# skill-manager 控件语言契约

来源：2026-10-15 UI 统一评审（`.impeccable/critique/2026-10-15T09-48-03Z__*.md`，27/40）与任务 10-15-unify-target-managers-ui。

## 共享常量（`apps/skill-manager/src/lib/ui.ts`）

所有卡片 / 弹窗 / 表单 / 工具栏 / 导航必须引用 `lib/ui.ts` 导出的 className 常量，禁止在组件内新写局部按钮/输入框 class：

- 按钮（卡内 py-1.5）：`ghostButton` / `ghostDangerButton`（rose 文字危险入口）/ `primaryButton`（sky-700）/ `solidSecondaryButton`（slate-700，语义=新建/启动流程）
- 弹窗按钮（py-2）：`dialogGhostButton` / `dialogPrimaryButton` / `dialogDangerButton`
- 块：`cardClass` / `errorBlockClass` / `okBlockClass` / `emptyStateClass`
- 输入：`inputClass`（表单）/ `toolbarInput` / `toolbarSelect`（工具栏紧凑）
- 导航：`navTabClass`（顶栏 tab，data-active 驱动）/ `segButtonClass`（来源 segmented）

## 危险色语义（全 app 一条规则）

- rose 文字（`ghostDangerButton` 或紧凑变体 border-slate-300 + text-rose-700）= 卡内危险动作入口
- rose-600 实心（`dialogDangerButton`，ConfirmActionDialog `danger`）= 确认弹窗内不可逆动作
- sky 实心 = 普通确认；slate-700 实心 = 新建/启动流程类动作（如「新增 GitHub Skill」「扫描」）

## 对比度（AA，页面级检测验证 44→0）

- 主按钮底色 sky-**700**（白字 ~5.1:1；sky-600 白字仅 4.0:1 不达标）
- 辅助文字：白底用 `text-slate-500`（4.76:1）；slate-50/slate-100 底（chip、页面底说明、徽章）用 `text-slate-600`；**全 app 禁用 `text-slate-400`**（2.9:1）
- placeholder 显式着色：输入类常量含 `placeholder:text-slate-500`（UA 默认色 2.6:1 不达标）

## 确认弹窗

写操作确认一律用 `ConfirmActionDialog`：
- `requirePassword`（默认 true）：写 NAS 真实目录的操作必须保留密码框；本地台账 CRUD（导出目标）传 false
- `danger`：删除类动作必传
- `confirmLabel`：动词（「删除」「保存」「确认安装」），不用「确认执行」
- `completed` 展示态（被拦截/已完成）：关闭钮文案 `completedLabel` 默认「知道了」，不渲染确认钮
- 被拦截时必须在弹窗内给跳转出路按钮（「进入该目标部署看板」/「到管理看板清除记录」模式）

## 目标卡三层语法

层1 头部（名称 + 状态徽章 + 卡头右侧操作组）→ 层2 事实（`安装目录：` + font-mono 路径，单列完整宽度）→ 层3 状态（计数 · 不可用原因 amber · 备注）。列表一律单列 `space-y-3`。

## 刻意保留的差异（勿"顺手统一"）

- NAS 密码两步确认 + `config_revision` 乐观锁：仅安装目标侧（写 NAS 真实目录、Git 提交全局生效）
- profile 发现流（置灰已登记项、写入目录预览、目录身份固定）：仅安装目标侧
- `enabled` 启停开关：仅导出目标侧

## 质量检查

- `cd apps/skill-manager && pnpm lint && pnpm test`（vitest，91 用例）
- `npx tsc --noEmit`
- **dev server 运行期间禁止 `pnpm build`**——build 会覆写 `.next` 导致 dev 静态资源 404（2026-10-15 两次实测）；build 前先停 dev server
- 启动脚本 `start-skill-manager-dev.bat` 的 taskkill 不带 `/T`，重启后需手动清理 8097 上的双监听旧进程
