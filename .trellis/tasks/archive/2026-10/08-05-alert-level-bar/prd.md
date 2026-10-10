# 挡位监控水平价位条 Tab

## 背景

现有 dividend 页面顶部已有 Tab "全部 / 收藏" 切换两个数据视图。当前 AlertSettingsModal 弹窗是单只股票的挡位设置入口，但缺一个**全局视图**让用户一眼看到所有收藏 + 已设挡位的股票当前状态。

外部草图已确认体验细节：
- 5 段色块（重仓区 / 加仓区 / 持有区 / 减仓区 / 全卖区）
- ▲ 蓝色三角箭头（朝上）指示当前价位置
- 4 档价格下方刻度带 PE/PB（用户设置时输入）
- 当前价 ▲ 旁实时 PE/PB（PEDataService 实时数据）

## 目标

- dividend 主页面顶部 Tab 加第 3 个 "挡位监控"
- 切换到该 Tab 时显示**所有收藏 + 已设置 alerts 的股票**（未设挡位的收藏在该 Tab 不显示）
- 每只股票一行水平价位条，含 5 段色块 + 4 档价格 PE/PB + 当前价 ▲ 三角 + 实时 PE/PB
- 后端 AlertLevel 加 PB 字段（用户设置时输入）
- 前端 Modal 加 PB 输入

## 范围

### In Scope

- 后端 `AlertLevel` Pydantic 模型加 `pb: Optional[float]` 字段
- 后端 `_alert_config_to_dict` 与 AlertStatusItem 构造透传 PB
- 前端 `types.ts` 同步加 `pb` 字段
- 前端 `AlertSettingsModal.tsx` 加 PB 输入框 + 序列化时一并提交
- 前端 `page.tsx` 顶部 Tab 加 "挡位监控" 第三个 Tab
- 新建 `apps/dividend/src/components/AlertLevelBar.tsx` 组件（水平价位条 + 5 段色块 + ▲ 三角 + PE/PB）
- page.tsx 整合：Tab 切换到 alerts 时筛选 `favorites ∩ alertsMap[code].levels 要有非空配置`，调用 AlertLevelBar 列表展示
- 拉 `getPEData` 拿到所有 favorite codes 的 PE/PB（实时）

### Out of Scope

- 推送统计、月度历史等扩展功能（不在本次）
- 独立路由 `/alerts`（本次走主页面 Tab）
- 重新设计 AlertSettingsModal 布局（仅加 PB 输入）
- 数据导出、报表分析
- 移动端深度适配（桌面优先）

## 需求

### 功能性

| 编号 | 需求 |
|------|------|
| FR-1 | 主页面顶部 Tab 三个："全部 / 收藏 / 挡位监控" |
| FR-2 | URL query `?tab=alerts` 切换到第 3 个 Tab（沿用现有 URL 同步模式） |
| FR-3 | Tab 3 列表内容：所有 `favorites` ∩ `alertsMap[code].levels 至少 1 档非空` 的股票 |
| FR-4 | 每行水平价位条：5 段色块（重仓区 / 加仓区 / 持有区 / 减仓区 / 全卖区），按 4 档价格切分 |
| FR-5 | 4 档价格刻度：每档下方标注 `档位 + 价格 + PE/PB`（用户设置时输入） |
| FR-6 | 当前价 ▲ 三角箭头（蓝色），位置按当前价在 4 档价格区间的归一化百分比 |
| FR-7 | ▲ 旁标注"现价 + 实时 PE/PB"（PEDataService 实时拉取） |
| FR-8 | 命中状态 badge（顶部）：🟢 重仓命中 / 🟡 加仓命中 / 🏠 持有区 / 🟠 减仓命中 / 🔴 全卖命中 / ⏸ 持有观望 |
| FR-9 | 距离行：每档价格偏离现价的百分比（命中绿/接近黄/其余灰） |
| FR-10 | 后端 `AlertLevel` 加 `pb` 字段（用户设置时输入 + 持久化） |
| FR-11 | 前端 Modal 加 PB 输入（选填，与 PE 并列） |
| FR-12 | 点击股票行 → 打开 AlertSettingsModal 编辑（沿用现有弹窗） |
| FR-13 | 空状态：Tab 切到 alerts 时无数据 → 提示"暂无设置挡位的收藏股票" + "去设置"链接 |

### 非功能性

| 编号 | 约束 |
|------|------|
| NFR-1 | 不引入新依赖（UI 组件沿用 Tailwind / 现有 Modal / Button） |
| NFR-2 | 性能：≤ 30 只股票时滚动流畅 |
| NFR-3 | 数据复用：favorites/alertsMap/technicalData 复用现有拉取，不重复请求 |
| NFR-4 | 现有 PE/PB 数据流：后端 `read_pe_data()` 已有 `pe`/`pb` 字段，前端可批量获取 |
| NFR-5 | 改动范围：后端 2 文件 + 前端 4 文件 + 新建 1 组件 |

## 验收标准

### 后端
- [ ] `AlertLevel` 模型字段：`price` / `pe` / `pb`
- [ ] `_alert_config_to_dict` 序列化时透传 `pb`
- [ ] AlertStatusItem 状态接口构造时透传 `pb`
- [ ] `favorites.json` 旧数据（无 PB）兼容读取：`dict.get('pb')` 返回 None
- [ ] 后端 import 改后 `python -c "from src.api.models import AlertLevel"` OK

### 前端
- [ ] `types.ts` AlertLevel 增 `pb?: number | null`
- [ ] 弹窗 Modal 加 PB 输入框（与 PE 并列）
- [ ] 提交时把 PB 字段 submit
- [ ] Tab 3 切换：URL `?tab=alerts` 同步
- [ ] 列表只在 favorites + 已设 alerts 时显示
- [ ] 每行 5 段色块按当前价定位渲染
- [ ] ▲ 三角位置精确（在 4 档价格区间内的归一化百分比）
- [ ] ▲ 标签：现价 + 实时 PE/PB（来自 PEDataService）
- [ ] 4 档价格刻度下方 PE/PB 标注
- [ ] tsc 0 错误，next build 0 错误

### 部署
- [ ] 子模块 + 主仓库 commit + push
- [ ] NAS 重新 build + 部署

## 风险

| 风险 | 应对 |
|------|------|
| PE/PB 批量接口性能 | 后端 `/pe` 已支持 `codes` 查询，前端按 favorites codes 一次性拿 |
| PE/PB 缺失（akshare 拉不到） | 显示 `-`，不报错 |
| 历史 favorites.json 无 PB 字段 | 读时默认 None；本次保存时自动写入 |
| 5 段色块宽度（价格量级差异大） | 用归一化百分比，不按价格绝对值 |
| Modal 改 + 水平条组件联动 | AlertLevelBar 复用 Modal 现有 props |

## 备注

- 草图：`apps/dividend/public/alerts-preview.html`（开发参考）
- 设计文档：`design.md`
- 执行计划：`implement.md`
