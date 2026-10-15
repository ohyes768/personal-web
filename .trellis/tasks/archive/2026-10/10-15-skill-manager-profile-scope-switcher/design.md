# Design — Skill Manager profile scope switcher

## 1. 组件结构

新增一个客户端组件 `ProfileScopePicker`，文件位置 `apps/skill-manager/src/components/ProfileScopePicker.tsx`。

```tsx
'use client';

interface ProfileScopePickerProps {
  current: string;              // 当前 target id（来自 URL search params）
  targets: InstallTarget[];     // installTargets 列表（已过滤掉 removed）
  loading: boolean;
  error: string;
  onSelect: (id: string) => void;            // 切换 scope，调用 navigate({ agent })
  onManage: () => void;                       // 跳 view=install-targets
  onRefresh: () => void;                      // 复用 page.tsx 的 refreshInstallTargets
}
```

内部状态：
- `const [open, setOpen] = useState(false)` 控制 popover 开关
- `const popRef = useRef<HTMLDivElement>(null)` 用于外点击关闭
- `const triggerRef = useRef<HTMLButtonElement>(null)`

外点击 / Esc 关闭：
```tsx
useEffect(() => {
  if (!open) return;
  function onDoc(e: MouseEvent) {
    if (popRef.current?.contains(e.target as Node)) return;
    if (triggerRef.current?.contains(e.target as Node)) return;
    setOpen(false);
  }
  function onKey(e: KeyboardEvent) {
    if (e.key === 'Escape') setOpen(false);
  }
  document.addEventListener('mousedown', onDoc);
  document.addEventListener('keydown', onKey);
  return () => {
    document.removeEventListener('mousedown', onDoc);
    document.removeEventListener('keydown', onKey);
  };
}, [open]);
```

## 2. 颜色 / 状态映射

| target 状态 | 色点 class | button 边框 | button 文字 |
|---|---|---|---|
| `available && !removed` | `bg-emerald-500` | 默认 `border-slate-300` | `Hermes · <name>` |
| `!available && !removed` | `bg-amber-500` | `border-amber-400` | `目标不可用：<reason>` |
| `removed` | `bg-slate-300` | `border-slate-200` | `<name>（已移除）` |
| `loading` | `bg-slate-300 animate-pulse` | `border-slate-200` | `加载中…` |
| `error` | `bg-rose-500` | `border-rose-400` | `目标加载失败` |

色点尺寸：`h-2 w-2 rounded-full inline-block mr-2`

不可用态 `<reason>`：取 `target.unavailable_reason` 的第一行（按 `.split('\n')[0]` 截断，避免一行太长炸 button）。

## 3. popover 布局

绝对定位：相对 button 右对齐向下展开。
```tsx
<div className="relative">
  <button ref={triggerRef} ...>{trigger}</button>
  {open && (
    <div
      ref={popRef}
      role="dialog"
      aria-label="切换发布目标"
      className="absolute right-0 top-full mt-1 z-30 w-[360px] rounded-md border border-slate-200 bg-white shadow-lg"
    >
      {/* 标题 + 刷新 */}
      <header className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
        <h3 className="text-sm font-medium text-slate-700">切换发布目标</h3>
        <button onClick={onRefresh} disabled={loading} className="text-xs text-sky-700 underline disabled:opacity-50">
          {loading ? '刷新中…' : '刷新'}
        </button>
      </header>
      {/* 列表 */}
      <ul className="max-h-72 overflow-y-auto py-1">
        {targets.map(t => (
          <li key={t.id}>
            <button
              type="button"
              onClick={() => { onSelect(t.id); setOpen(false); }}
              data-active={t.id === current}
              className="flex w-full items-start gap-2 px-3 py-2 text-left hover:bg-slate-50 data-[active=true]:bg-sky-50 data-[active=true]:border-l-2 data-[active=true]:border-sky-500"
            >
              <span className={`mt-1 h-2 w-2 rounded-full ${dotClass(t)}`} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm text-slate-800">
                    {t.provider} · {t.profile_name}
                  </span>
                  {t.available ? <span className="text-xs text-slate-400">✓</span> : <span className="text-xs text-amber-600">⚠</span>}
                </div>
                <code className="mt-0.5 block truncate rounded bg-slate-50 px-1.5 py-0.5 font-mono text-[11px] text-slate-500" title={t.install_path}>
                  {t.install_path}
                </code>
                {!t.available && t.unavailable_reason && (
                  <p className="mt-0.5 text-[11px] text-amber-700">{t.unavailable_reason.split('\n')[0]}</p>
                )}
                <p className="mt-0.5 text-[11px] text-slate-400">已安装 {t.active_installation_count ?? 0} 个 Skill</p>
              </div>
            </button>
          </li>
        ))}
        {targets.length === 0 && (
          <li className="px-3 py-4 text-center text-sm text-slate-400">暂无 profile</li>
        )}
      </ul>
      {/* 底部 */}
      <footer className="border-t border-slate-100 px-3 py-2">
        <button onClick={() => { onManage(); setOpen(false); }} className="text-xs text-sky-700 underline">
          管理安装目标 →
        </button>
      </footer>
    </div>
  )}
</div>
```

## 4. page.tsx 改造点

`apps/skill-manager/src/app/page.tsx` 改动：

1. 删除 `{view === 'manage' || view === 'board') && <div className="flex flex-wrap items-center gap-2 text-sm">...</div>}` 整块（第 281-290 行）
2. header `<div className="flex flex-wrap items-end gap-x-6 gap-y-1">` 容器改为 `flex items-center justify-between gap-3`，并把 `<nav>` 和 `<ProfileScopePicker>` 放进右侧 flex
3. 新增 `<ProfileScopePicker>` 渲染位置：
```tsx
<div className="flex items-center gap-3">
  <nav className="flex gap-1" aria-label="视图切换">…</nav>
  <ProfileScopePicker
    current={agent}
    targets={installTargets.filter(t => !t.removed)}
    loading={installTargetsLoading}
    error={installTargetsError}
    onSelect={(id) => navigate({ agent: id as TargetKey })}
    onManage={() => navigate({ view: 'install-targets' })}
    onRefresh={() => void refreshInstallTargets()}
  />
</div>
```

注意：当 `view === 'targets'` 时 `installTargets` 仍然加载（因为 page 顶部已经统一 `refreshInstallTargets()`），所以 picker 数据一直就绪，无需额外请求。

## 5. 数据流（不引新 store）

- picker **不**引入新的 context / store / zustand
- 数据完全复用现有 `installTargets` state（`page.tsx` 第 71 行）和 `InstallTargetsContext`
- 切换 scope 仍然走 `navigate({ agent })` → URL `?target=<id>` 变化 → 整个组件树因 search params 变化重新计算（Next.js useSearchParams 触发 re-render）
- `InstallTargetsContext.Provider` 已在 `<main>` 外层包裹，`InstallTarget` 类型已定义在 `apps/skill-manager/src/lib/installTargets.tsx`

## 6. 边界 / 错误处理

| 场景 | 行为 |
|---|---|
| `targets.length === 0` | button 显示 `● — · 暂无 profile ▾`；popover 显示空态 `暂无 profile` |
| `loading=true && error=''` | button 显示 `● … 加载中… ▾`；popover 不显示列表或显示骨架（沿用简单 `loading` 文案） |
| `error !== ''` | button 边框 rose 色 + 文字 `加载失败，点击重试`；点击触发 `onRefresh` |
| popover 内 `刷新` 按钮 | 触发 `onRefresh`；刷新期间 disable 列表项 |
| 当前选中 target 已 removed | button 仍显示但色点灰 + 文字带「已移除」；popover 默认列表过滤掉（沿用 `!removed`） |
| URL `?target` 是非法值 | 沿用现有 `selectedTarget = installTargets.find(t => t.id === agent && !t.removed)` 逻辑；非法值 button 显示 `<id>（不可用）`，色点琥珀（与不可用态共用） |

## 7. Tradeoff

| 决策 | 替代 | 选这个的理由 |
|---|---|---|
| 自写 popover（绝对定位） | Headless UI Popover / Radix | 减少依赖；当前页面其他 dialog 都是自写（ConfirmActionDialog、RegisterGithubDialog 等），保持一致；样式可 100% 用 Tailwind 控制 |
| 数据完全复用 `installTargets` state | 引入 store / context 单独管 picker state | 单一数据源；picker 始终反映后端最新状态；无 stale 数据风险 |
| 不加切换 toast | 加 toast | toast 是二期 backlog；URL 变化已经够明确；主区列表会因 target 变化重新加载（视觉反馈已经够强） |
| 跨视图常驻 | 仅 manage / board 视图显示 | 解决 install-targets 视图下用户改完配置后看不到当前 scope 的核心痛点 |
| install_path 折进 popover | header 仍显示但用折叠 | 视觉更干净；header 不被路径撑宽；折叠交互进 popover 一次解决 |
| 用 `provider · profile_name` 不用 `name` | 直接用 `name` | `name` 是用户起的显示名（如 "Default dev"），`profile_name` 是真实身份（如 "default"）；显示完整身份让用户知道操作的真实目标；未来 provider 扩展也兼容 |

## 8. 兼容性 / 回归风险

- ✅ URL 格式 `?target=<id>` 不变 → 书签、分享链接可继续工作
- ✅ `InstallTargetsContext.current` 仍是 `agent`（来自 URL search params）→ 所有依赖 context 的子组件（SourceWorkspace、DeployBoard 等）行为不变
- ✅ `navigate({ agent })` 调用不变 → 安装/下架/部署等所有 R1-R5 行为不变
- ⚠️ 旧 `selectedTarget` 计算逻辑（第 75 行）仍在使用，保留
- ⚠️ `InstallTarget` 类型加字段需兼容：当前类型 `InstallTarget` 已包含 `available` / `unavailable_reason` / `active_installation_count` / `provider` / `profile_name` 等字段，无需新增

## 9. 实施顺序（与 implement.md 对齐）

1. 新增 `apps/skill-manager/src/components/ProfileScopePicker.tsx`
2. 加 vitest 单测 `apps/skill-manager/src/components/ProfileScopePicker.test.ts`
3. 改 `apps/skill-manager/src/app/page.tsx` 替换 header 区块
4. 跑 `pnpm lint` / `pnpm typecheck` / `pnpm build`
5. 起 dev server 跑 live 验证，截图存证
6. 跑 `ProfileViews.test.ts` 确认既有行为不破

## 10. 回滚形状

- 改动范围小、文件少：仅 `page.tsx` 头部 ~10 行 + 新增 `ProfileScopePicker.tsx` 一个文件
- 回滚方式：`git revert` 单 commit；或临时把 header 改回旧结构 + 删新组件
- 不涉及数据迁移、不涉及后端、无数据库 schema 改动
- 即使实施中途发现问题，可保留 `ProfileScopePicker` 组件 + 不挂载到 header（零风险回滚到现状）
