# 技术设计：安装/导出目标 UI 统一

## 改动文件

| 文件 | 改动 |
|---|---|
| `apps/skill-manager/src/lib/ui.ts` | 新建：共享 className 常量 |
| `apps/skill-manager/src/components/ConfirmActionDialog.tsx` | 泛化 props |
| `apps/skill-manager/src/components/ExportTargetManager.tsx` | 改用共享常量 + ConfirmActionDialog + onNotify/onManage |
| `apps/skill-manager/src/components/InstallTargetManager.tsx` | 对齐重写（结构不变，样式/弹窗/反馈统一）+ prettier |
| `apps/skill-manager/src/app/page.tsx` | 给两个 Manager 传 onNotify / onManage |

## lib/ui.ts 常量契约

```ts
// 卡内小按钮（py-1.5）
export const ghostButton  = 'rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50';
export const primaryButton = 'rounded bg-sky-600 px-3 py-1.5 text-sm text-white hover:bg-sky-700 disabled:opacity-50';
// 弹窗按钮（py-2）
export const dialogGhostButton = 'rounded border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50';
export const dialogPrimaryButton = 'rounded bg-sky-600 px-4 py-2 text-sm text-white hover:bg-sky-700 disabled:opacity-50';
export const dialogDangerButton = 'rounded bg-rose-600 px-4 py-2 text-sm text-white hover:bg-rose-700 disabled:opacity-50';
// 块
export const cardClass  = 'rounded-lg border border-slate-200 bg-white p-4';
export const errorBlockClass = 'rounded bg-rose-50 p-3 text-sm text-rose-700';
export const emptyStateClass = 'rounded-lg border border-dashed border-slate-300 p-8 text-center';
export const inputClass = 'mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-sky-500 focus:outline-none';
```

危险入口（卡内删除按钮）= `${ghostButton} text-rose-700`。

## ConfirmActionDialog 新 props

```ts
interface ConfirmActionDialogProps {
  title: string;
  description?: ReactNode;
  confirmLabel?: string;       // 默认 '确认执行'
  danger?: boolean;            // 确认按钮 dialogDangerButton
  requirePassword?: boolean;   // 默认 true；false 时无密码框，onConfirm('')
  busy?: boolean;
  error?: string;
  completed?: boolean;         // 阻断展示态（无确认按钮）
  completedLabel?: string;     // completed 时关闭钮文案，默认 '知道了'（原 '完成'，语义误导）
  onConfirm: (password: string) => void;
  onCancel: () => void;
}
```

- submit 禁用条件：`busy || (requirePassword && password.length === 0)`
- 密码安全注释与 state 生命周期保持不变（R5）

## 目标卡三层语法（两页同构）

```
层1 头部：名称 + 状态徽章 | 操作按钮组（卡头右侧）
层2 事实：font-mono 路径（break-all，单列完整宽度）
层3 状态：计数行 · 不可用原因(amber) · 备注
```

安装目标徽章映射：可用→emerald「可用」；不可用→amber「不可用」；removed→slate「已移除」；默认只读保留 `默认 · 只读` 文字标注。
导出目标徽章保持 emerald「已启用」/ slate「已停用」。

## ExportTargetManager 关键点

- `deleting` 弹窗替换为 `<ConfirmActionDialog requirePassword={false} danger confirmLabel="删除" completed={blocked}>`；
  blocked = `deleting.deployment_count > 0`；description 内 blocked 时渲染死文案 + `到管理看板清除记录` 按钮（新 prop `onManage: () => void`）。
- 页面级 `error` 块加内联「重试」按钮（吸收安装侧优点）。
- 新 prop `onNotify`：save→`已保存目标「X」`；toggle→`已停用/已启用目标「X」`；remove→`已删除目标「X」`。

## InstallTargetManager 关键点

- 全文件 prettier 化；页头/列表/卡/空态/loading/错误对齐导出侧基准。
- 表单弹窗：shadow-xl + inputClass + dialogGhostButton/dialogPrimaryButton。
- 删除确认：ConfirmActionDialog 传 `danger confirmLabel="删除"`（替换默认 sky「确认执行」）。
- 保存确认：ConfirmActionDialog 默认样式（sky + 密码）。
- 新 prop `onNotify`：save→`已保存安装目标「X」`；remove→`已删除安装目标「X」`。
- 保留：profile 发现流、置灰已登记 option、写入目录预览、乐观锁、blocked「进入部署看板」引导（completed 态）。

## page.tsx

```tsx
<InstallTargetManager ... onNotify={setNotice} />
<ExportTargetManager ... onNotify={setNotice} onManage={() => navigate({ view: 'manage' })} />
```

## 保留差异（防止误统一，代码注释标注）

- NAS 密码 + config_revision 乐观锁：仅安装侧（写 NAS 真实目录，Git 提交全局生效）。
- profile 发现流（select 置灰/写入目录预览/目录身份固定）：仅安装侧。
- enabled 开关：仅导出侧（本地台账无破坏面）。
