# skill-manager 控件语言契约

来源：2026-10-15 UI 统一评审（`.impeccable/critique/2026-10-15T09-48-03Z__*.md`，27/40）与任务 10-15-unify-target-managers-ui。

## 共享常量（`apps/skill-manager/src/lib/ui.ts`）

所有目标卡 / 弹窗 / 表单必须引用 `lib/ui.ts` 导出的 className 常量，禁止在组件内新写局部按钮/输入框 class：

- `ghostButton` / `primaryButton`：卡内小按钮（py-1.5）
- `dialogGhostButton` / `dialogPrimaryButton` / `dialogDangerButton`：弹窗按钮（py-2）
- `cardClass` / `errorBlockClass` / `emptyStateClass` / `inputClass`

## 危险色语义（全 app 一条规则）

- rose 文字（`ghostButton + text-rose-700`）= 卡内危险动作入口
- rose-600 实心（`dialogDangerButton`，ConfirmActionDialog `danger`）= 确认弹窗内不可逆动作
- sky 实心 = 普通确认

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

- `cd apps/skill-manager && pnpm lint && pnpm test`（vitest，90 用例）
- `npx tsc --noEmit`（本机 `pnpm build` 在 `.next/standalone` symlink 阶段 EPERM，属 Windows 权限环境问题，不代表类型错误）
- 辅助文本对比度：用 `text-slate-500`（白底 4.76:1 过 AA），禁用 `text-slate-400`（2.9:1）
