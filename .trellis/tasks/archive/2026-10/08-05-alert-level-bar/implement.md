# Implement — 挡位监控水平价位条 Tab

4 阶段：后端 → 前端 Modal → 前端 Bar 组件 → 前端 page 集成。

## Phase A：后端 AlertLevel 加 pb

### A1. models.py 加 pb 字段

`backend/dividend-select/src/api/models.py`:
```python
class AlertLevel(BaseModel):
    """单档挡位（价格必填，PE/PB 选填仅推送展示）"""
    price: float = Field(..., description="挡位价格（元）", gt=0)
    pe: Optional[float] = Field(None, description="对应挡位 PE（选填）")
    pb: Optional[float] = Field(None, description="对应挡位 PB（选填）")
```

`AlertLevel` 嵌套 AlertConfig / AlertConfigRequest / AlertStatusItem 时 Pydantic 自动带 pb，无需逐处改。

### A2. routes.py 透传 pb

`backend/dividend-select/src/api/routes.py`:
- `_alert_config_to_dict` 函数：levels_dict 的赋值加 `pb` 字段
- AlertStatusItem 构造：传入 `pb=alerts.get('pb') if alerts else None`

### A3. 验证

```bash
cd backend/dividend-select
python -c "from src.api.models import AlertLevel; print(AlertLevel.model_fields.keys())"
# dict_keys(['price', 'pe', 'pb'])
```

**🚦 Review Gate A**：跑后端 import 验证 + python -c 验证。**不通过不进 Phase B**。

**Rollback point A**：git restore models.py + routes.py。业务接口不受影响。

---

## Phase B：前端 types.ts + Modal + useAlertsStatus 同步

### B1. types.ts

`apps/dividend/src/lib/types.ts`:
```ts
export interface AlertLevel {
  price: number;
  pe?: number | null;
  pb?: number | null;  // 新增
}
```

### B2. AlertSettingsModal 加 PB 输入

`apps/dividend/src/components/AlertSettingsModal.tsx`:
- state: `pbStr` per level
- UI: PB 输入框（与 PE 并列）
- updateLevel 加 `pb` 字段
- handleSave 序列化时带 PB

### B3. useAlertsStatus 同步

`apps/dividend/src/lib/hooks/useAlertsStatus.ts`:
- 乐观更新 items 同步 pb 字段（首次落地时也行）

### B4. 验证

```bash
cd apps/dividend
npx tsc --noEmit
```

**🚦 Review Gate B**：tsc 0 错误。**不通过不进 Phase C**。

**Rollback point B**：git restore 3 个前端文件。

---

## Phase C：AlertLevelBar 组件

### C1. 新建组件

`apps/dividend/src/components/AlertLevelBar.tsx`:
- 接收 levels + currentPrice + PE/PB + onClick
- 渲染 5 段色块 + ▲ 三角 + 4 档价格 PE/PB 刻度
- 命中状态 badge
- 距离行

实现细节见 `design.md` 组件设计章节。

### C2. 单元验证（手动）

- 跑 next dev → 临时 import AlertLevelBar + 假数据 → 看效果
- 5 段色块宽按归一化% 算
- ▲ 三角位置精确

### C3. 验证

```bash
npx tsc --noEmit
npx next build
```

**🚦 Review Gate C**：构建 0 错误 + 视觉效果 OK。

**Rollback point C**：删 AlertLevelBar.tsx。

---

## Phase D：page.tsx 加 Tab

### D1. Tab 状态

`apps/dividend/src/app/page.tsx`:
- TabKey 类型加 'alerts'
- activeTab 解析 url query
- 顶部 Tab 切换渲染 3 个 button

### D2. PE/PB 拉取

- 新建 `apps/dividend/src/lib/hooks/useAlertsPePb.ts`
- 依赖 favorites 列表 + alertsMap
- 调 `dividendApi.getPEData({ codes: ... })`
- 返回 `pePbMap: Map<string, {pe, pb}>` + loading

### D3. 列表渲染

```tsx
{activeTab === 'alerts' && (
  <div className="space-y-4">
    {filteredAlertStocks.length === 0 ? (
      <div className="bg-paper-card rounded-lg p-12 text-center">
        <span className="text-5xl">📊</span>
        <h2 className="text-xl font-semibold text-ink mt-4">暂无设置挡位的收藏股票</h2>
        <p className="text-ink-muted mt-2">去「收藏」标签页点股票行设置挡位</p>
      </div>
    ) : (
      filteredAlertStocks.map(stock => (
        <AlertLevelBar
          key={stock.code}
          code={stock.code}
          name={stock.name}
          levels={alertsMap.get(stock.code)?.levels ?? { ...EMPTY_LEVELS }}
          currentPrice={technicalData.get(stock.code)?.realtime ?? technicalData.get(stock.code)?.close ?? 0}
          currentPE={pePbMap.get(stock.code)?.pe}
          currentPB={pePbMap.get(stock.code)?.pb}
          onClick={() => handleOpenAlertSettings(stock.code)}
        />
      ))
    )}
  </div>
)}
```

### D4. 验证

```bash
npx tsc --noEmit
npx next build
```

**🚦 Review Gate D**：构建 0 错误 + 端到端测试。

**Rollback point D**：删 Tab 状态改动 + 列表渲染代码。

---

## Phase E：部署

### E1. 子模块 commit + push

```bash
cd backend/dividend-select
git add src/api/models.py src/api/routes.py
git commit -m "feat(alerts): AlertLevel 加 pb 字段（用户设置时输入）"
git push origin main
```

### E2. 主仓库 commit + push

```bash
git add apps/dividend/src/lib/types.ts \
        apps/dividend/src/components/AlertSettingsModal.tsx \
        apps/dividend/src/lib/hooks/useAlertsStatus.ts \
        apps/dividend/src/components/AlertLevelBar.tsx \
        apps/dividend/src/lib/hooks/useAlertsPePb.ts \
        apps/dividend/src/app/page.tsx \
        backend/dividend-select
git commit -m "feat(dividend/ui): 挡位监控 Tab（水平价位条 + 5 段色块 + ▲ 三角 + PE/PB）"
git push origin master
```

### E3. NAS 部署

```bash
git pull
git submodule update --init --recursive backend/dividend-select
docker compose -f docker-compose.nas.yml build --no-cache dividend-backend dividend-frontend
docker compose -f docker-compose.nas.yml up -d --force-recreate dividend-backend dividend-frontend
```

---

## 全局验证清单

- [ ] A 阶段：后端 AlertLevel 字段含 pb
- [ ] B 阶段：tsc 0 错误
- [ ] C 阶段：next build 0 错误
- [ ] D 阶段：端到端测试（手动）
- [ ] E 阶段：commit + push + NAS 部署
- [ ] NAS 上看 Tab 3 渲染效果

## 注意事项

- 4 档价格 span 大时（¥5 vs ¥600），归一化百分比是唯一可行方案
- favourites 没设 alerts 的不进 Tab 3（不动现有逻辑）
- 渲染顺序：成本最小化顺序 = A → B → C → D → E

## 特殊情况

- 所有 favorite 都没设 alerts：Tab 3 显示空状态
- 个别股票 PE/PB 缺失：Bar 仍渲染，PB 字段显示 `-`
- 当前价 4 档外（< 重仓 或 > 全卖）：▲ 定位 0% 或 100%，badge 仍然显示对应命中
