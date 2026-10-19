# Skill Manager — Profile Switcher 重设计方案

## 现状问题（截图 + 代码 + DOM 三方共同确认）

参考截图：
- `screenshots/skill-manager-current-manage.png`（manage 视图，picker 占 header 下方整行）
- `screenshots/skill-manager-current-install-targets.png`（install-targets 视图，picker 消失）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ← 返回首页    Skill 发布管理台    [管理看板][部署看板][安装目标][导出目标]    │
├─────────────────────────────────────────────────────────────────────────────┤
│ Hermes profile [Default dev ▾]  F:\personal-projects\personal-web\.skill-…  │
│                                  管理安装目标                                │
├─────────────────────────────────────────────────────────────────────────────┤
│ [自研 Skill 21] [GitHub Skill 3]              自研 Skill 由源库目录自动同步… │
│ ┌─────┐ ┌─────┐ ┌─────┐                                                        │
│ │卡片1│ │卡片2│ │卡片3│  ← skill 卡片网格                                      │
│ └─────┘ └─────┘ └─────┘                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

代码位置：`apps/skill-manager/src/app/page.tsx:281-290`

**核心问题：**
1. 切换器在 header **下方**单独占一行，挤压主区
2. 裸 `<select>` + `install_path` 长字符串 + "管理安装目标" 链接挤在同 row，视觉竞争
3. **install-targets 视图下 picker 完全消失**——用户改完 profile 配置后切回 manage 才看到状态变化
4. Label "Hermes profile" 误导：target id 不一定是 Hermes
5. 当前选中的 profile 没有视觉强化（色点/边框/状态指示）
6. install_path 没换行也没折叠，撑爆 row

---

## 推荐方案：应用级 scope bar（header 右上角常驻）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ← 返回首页          [管理看板][部署看板][安装目标][导出目标]    ● Hermes · Default dev ▾ │
│ Skill 发布管理台                                          ⌄                  │
│                                                                          安装路径  │
│                                                                          ⌄ /tar…/hermes │
├─────────────────────────────────────────────────────────────────────────────┤
│ [自研 Skill 21] [GitHub Skill 3]              自研 Skill 由源库目录自动同步… │
```

要点：
1. **顶部常驻**：移入 header 右上角；与四个 view tab 同一行右侧
2. **当前状态显形**：绿色圆点 + `Hermes · Default dev` provider/profile_name + chevron
3. **install_path 收纳**：放在 popover 里以 monospace chip 显示，主区不再被路径撑爆
4. **状态色点**：可用=绿、不可用=琥珀、已移除=灰；不可用时按钮整体琥珀边框
5. **popover 内容**：
   ```
   ┌─────────────────────────────────────┐
   │ 切换发布目标                  [刷新] │
   ├─────────────────────────────────────┤
   │ ● Hermes · Default dev        ✓     │
   │   /targets/hermes  · 0 安装         │
   │                                     │
   │ ● Hermes · ohyes768 dev      ✓     │
   │   /targets/profiles/ohyes768/skills │
   │   · 12 安装                         │
   │                                     │
   │ ● Hermes · archive           ⚠     │
   │   目录不可用：路径未挂载             │
   ├─────────────────────────────────────┤
   │ 管理安装目标 →                       │
   └─────────────────────────────────────┘
   ```
6. **切换 toast**：切完顶部短暂滑出 `已切换到 profile 'ohyes768'`，3 秒淡出
7. **label 改名**：`当前发布目标`（或 `操作目标`），不再写 "Hermes profile"
8. **跨视图常驻**：manage / board / install-targets / targets 全部显示；切到 install-targets 后还能看到当前 scope

---

## 跟现状的差异对照

| 维度 | 现状 | 推荐 |
|---|---|---|
| 位置 | header 下方独立 row | header 右上角，与 view tab 同 row |
| 组件 | 裸 `<select>` | button + popover |
| 当前状态可视化 | 下拉文字 | 色点 + 边框 + provider·profile_name |
| install_path | 占主区一行宽度 | popover 内 monospace chip |
| install-targets 视图下可见性 | ❌ 消失 | ✅ 常驻 |
| 不可用态指示 | 选项尾巴"（不可用）"文字 | 按钮琥珀边框 + popover 内显形说明 |
| 切换反馈 | 无 | toast + 安装数变化 |
| Label 文案 | "Hermes profile"（不准） | "当前发布目标" |
| 切换破坏性操作确认 | 无 | （二期）二次确认 |

---

## 不选 sidebar 的核心理由

1. **Profile 不是导航，是 scope**——它定义后续所有操作作用在哪个发布目标
2. **顶栏是 operate-mode scope switcher 的行业标准**（GitHub org、Vercel team、AWS account/region、Slack workspace、Linear workspace）
3. **当前已有顶部 tab bar，没有 sidebar**——为这一个功能引入 sidebar = over-engineering
4. **Sidebar 列表化会污染视图分组**——把"视图"和"目标"两个不同维度混在一个 list

---

## 实施分两期

**一期（建议先做）**
- 把 `<select>` 升级成 button + popover
- 搬到 header 右上角
- 跨视图常驻
- 色点 + 不可用态视觉强化
- label 改名
- install_path 折进 popover chip

**二期（看一期反馈再做）**
- 切换 toast
- 切换时破坏性操作二次确认
- 移动端 popover → bottom sheet

---

## 是否进入 shape 流程？

如果方向认可，我可以：
1. 起 PRODUCT.md / DESIGN.md（impeccable 要求的 artifacts）
2. 写 surface brief "profile-scope-switcher"
3. 拆任务 + TDD 推进

如果你只想讨论视觉方向、不想现在就动手，告诉我画 wireframe 的某几个细节要调整。
