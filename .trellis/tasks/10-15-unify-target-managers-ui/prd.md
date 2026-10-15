# PRD：skill-manager 安装/导出目标 UI 统一

## 背景

设计评审（2026-10-15，27/40，快照 `.impeccable/critique/2026-10-15T09-48-03Z__r-src-components-installtargetmanager-tsx-ddc0613e.md`）发现两个并列的目标管理页是两套控件语言：危险确认色相反（一蓝一红）、错误/空态/loading/表单弹窗/列表布局/按钮组位置全部成对不一致，且导出目标删除被拦时是死文案无出路、写操作成功零反馈。

## 用户已确认的方向

- **形式统一，重量保留**：不合并页面；控件语言、弹窗骨架、反馈、被拦引导统一；NAS 密码两步确认 + 乐观锁（安装侧）、profile 发现流、enabled 开关（导出侧）等交互重量按破坏面保留差异。
- **弹窗全 app 统一**：ConfirmActionDialog 泛化后作为唯一确认弹窗（本任务先覆盖两个 Manager，SkillPool 等后续替换）。
- **保持冷色**（slate/sky/rose/emerald/amber），不接平台暖白 token。

## 需求

1. 以 ExportTargetManager 的控件语言为基准统一两页：单列卡片、卡头操作组、徽章状态、shadow-xl 弹窗、focus 输入样式；吸收安装侧优点（错误块内联重试、被拦跳转引导）。
2. 共享 className 常量收编进 `lib/ui.ts`，消灭两份局部常量漂移。
3. ConfirmActionDialog 泛化：`danger`（rose-600 确认钮）、`confirmLabel`、`requirePassword`（默认 true）、`completed` 态文案改「知道了」。
4. 删除安装目标确认改 `danger`；导出目标删除/表单确认弹窗改用 ConfirmActionDialog（`requirePassword={false}`）。
5. 导出目标删除被拦（有导出记录）时提供「到管理看板清除记录」跳转按钮（对齐安装侧「进入部署看板」模式）。
6. 两个 Manager 接入 `onNotify`：保存/删除/启停成功发 notice（复用 page.tsx 现有通道）。
7. 安装目标页补齐：空态、规范 loading、错误块 rose-50 样式；两页代码统一 prettier 格式。

## 验收标准

- [ ] 同屏切换两个 tab，卡片三层结构（身份+操作 / 路径 / 状态+补充）、页头（标题+说明 / 刷新+主按钮）、列表布局（单列）完全同构。
- [ ] 两页的删除确认弹窗确认按钮均为 rose-600 + 动词 label；安装目标保存确认仍为 sky + 密码框。
- [ ] 删除导出目标被拦时，弹窗内有跳转按钮可直达管理看板。
- [ ] 新增/删除/启停目标成功后顶部出现 notice；失败时弹窗内错误 + 可原地重试。
- [ ] 安装目标页有空态与规范错误/加载样式；所有输入框有一致 focus 样式。
- [ ] 既有测试全部通过；无新增 TS 错误。

## 非目标

- 不合并两个 view/tab；不改后端 API；不接平台 token；不动 InstallDialog 计划明细结构化（后续独立任务）；不加 modal 焦点陷阱/Escape（后续统一弹窗替换时一并做）。
