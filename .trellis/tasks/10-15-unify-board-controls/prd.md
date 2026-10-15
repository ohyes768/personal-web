# PRD：管理/部署看板三块接入控件契约 + 对比度系统性修复

来源：2026-10-15 第二轮评审（29/40，快照 `.impeccable/critique/2026-10-15T10-56-35Z__apps-skill-manager-src-components-skillpool-tsx.md`）。用户选定范围：**仅 P1-3 + P1-4（机械批量）**；两个 P0（合集下架 bug、计数语义）与来源模型重构不在本次。

## 需求

1. `lib/ui.ts` 契约扩展：
   - `primaryButton`/`dialogPrimaryButton` 底色 sky-600 → **sky-700**（白字对比 ~5.1:1 达 AA；检测器证实 sky-600 白字仅 4.0:1）
   - 新增 `solidSecondaryButton`（slate-700，语义=「新建/启动流程」类动作）
   - 新增 `ghostDangerButton`（rose 文字危险入口统一字面量）
   - 新增 `navTabClass`（page.tsx 重复 4 次的长串）、`segButtonClass`（SEG_BUTTON 挪入）、`toolbarInput`/`toolbarSelect`
2. `text-slate-400` 全部 → `text-slate-500`（12+ 处，spec 明令禁用）
3. 卡容器统一 `cardClass`（rounded-lg p-4；GitHub 卡去掉 min-h/shadow-sm/rounded-xl 差异）
4. 空态/加载态统一 `emptyStateClass`；页级错误/notice 统一 `errorBlockClass`
5. 弹窗底部按钮统一 dialog 系（ExportDialog / EditSkillTagsDialog / RegisterGithubDialog）
6. 删除 emerald queued 死状态（`queue={[]}` 恒空）及 `SourceWorkspace` 的 queue 传参（若仅此处使用）
7. amber 实心「Clone 缓存」图标钮降级为 amber 边框 ghost 风格（次要恢复动作不该用实心重量）
8. 「检查更新」→ ghostButton；「新增 GitHub Skill」「扫描」→ solidSecondaryButton
9. spec `skill-manager-ui.md` 同步增补新常量与语义

## 非目标（明确不做）

- P0-1 合集下架功能 bug（含批量下架弹窗换 ConfirmActionDialog——CollectionDialog 408-443 区块本次不动行为，仅 toolbar class 收编）
- P0-2 segmented 计数语义
- P2 aria-current/aria-pressed、跨 view 来源 tab 保留
- emoji → icons.tsx 图标创作（需新 SVG 资产，单独做）
- 来源能力表重构

## 验收标准

- [ ] 页面级检测对比度 findings 从 44 显著下降（sky 按钮组、slate-400 组归零）
- [ ] 三块（manage/board/来源切换区）无手写按钮/输入框/卡容器/空态 class 字面量残留（对照评审差距清单 15 组逐项销号）
- [ ] 90 用例测试全过、lint 干净、tsc 0 错误
- [ ] 浏览器实测：主按钮深蓝、两看板卡片同构、GitHub tab 的 slate-700 按钮与 sky 主按钮并存且语义清晰
