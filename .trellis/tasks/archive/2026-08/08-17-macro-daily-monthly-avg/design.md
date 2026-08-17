# 技术设计：日频指标月均透传与分层展示

## 1. 数据流与改动边界

```
macro-fin-skill(仓库外,配套)
  ├─ 日频 skill 输出契约 +month_avg     ← 契约在本文档登记,实现不在本任务
  └─ B 调度:日频 skill 交易日盘后推送   ← 调度脚本/文档在本任务登记
        ↓ POST /api/signal/upload
后端(本任务)
  ├─ models.py: MacroIndicator +month_avg
  ├─ macro_signal_service.py: 两处转换函数读取并透传 month_avg
前端(本任务)
  ├─ types.ts: MacroIndicator +month_avg
  └─ GroupCard.tsx: 历史月日频指标显示月均,当月不变
```

不动的部分：归档逻辑(`save_skill_json` 三步写入)、按月过滤/占位逻辑、
`_resolve_next_release`、缓存、API 路由 shape(字段只增不改)。

## 2. 后端改动

### 2.1 models.py

```python
class MacroIndicator(BaseModel):
    ...
    month_avg: Optional[float] = None  # 日频指标的月均值(skill 计算,透传)
```

### 2.2 macro_signal_service.py

**`_convert_dimension_from_macro_signal`**(macro_signal.json 路径)：

在构造 `MacroIndicator(...)` 处增加一行——月份校验复用现有
`_month_of()` 模式(直接前 7 位对比，不新增解析函数)：

```python
ind_month_avg = m.get("month_avg")
# 仅当月均值属于请求月/数据月时透传,防止跨月旧均值冒充
month_avg = float(ind_month_avg) if isinstance(ind_month_avg, (int, float)) else None
```

校验语义：month_avg 描述的是「该指标 data_date 所在月的月均」，因此
**不做额外的月份匹配**——它跟 value 绑定同一个采样月，value 通过了按月
过滤，month_avg 自然同月。按月过滤占位路径(`_placeholder_indicator`)
month_avg 保持 None，不构造。

**`_convert_risk_appetite`**(risk_data.json 路径)：

三个子块(volume/turnover/margin)同样读 `block.get("month_avg")`，
数值类型检查后透传，逻辑同上。

**边界守住**：后端不计算月均——skill 没算就没有，后端不补。

## 3. 前端改动

### 3.1 types.ts

```typescript
/** 日频指标的月均值(skill 计算);历史月卡片主数值位显示它,当月显示最新值 */
month_avg?: number | null;
```

### 3.2 GroupCard.tsx IndicatorRow

现有结构：主数值位 `formatValue(ind.value)`，时间行有「日频」标签。

分层规则(组件内已有 `selectedMonth` prop，当前自然月由 `new Date()` 取)：

```typescript
const isCurrentMonth = selectedMonth === current YYYY-MM;
// 日频 + 历史月 + 有月均 → 月均展示
const showMonthAvg = ind.frequency === 'daily' && !isCurrentMonth && ind.month_avg != null;
```

- `showMonthAvg=true`：主数值位显示 `formatValue(ind.month_avg)`，
  时间行标签从「日频」换成「月均」(title 说明「本月日频读数均值」)，
  保留 data_date 完整展示(月均的采样终点)。
- `showMonthAvg=false`：现状行为，零变化(当月、或 skill 未输出月均的历史月)。
- isStale 判断仍基于 data_date，不受影响。

## 4. 兼容性

| 场景 | 行为 |
|------|------|
| 旧 skill JSON(无 month_avg) | 后端 month_avg=null → 前端回退现状展示 |
| 新 JSON + 当月卡片 | 显示最新值(月均不干扰) |
| 新 JSON + 历史月 | 显示月均 + 「月均」标注 |
| 占位指标(暂未获取) | month_avg=null,占位逻辑不变 |
| Pydantic 模型新增可选字段 | 旧客户端(不认识 month_avg)反序列化响应不受影响 |

API 契约只增不改，符合按月留存设计 G5。

## 5. 测试策略

后端(pytest,沿用 conftest 的 `make_macro_signal`/`write_skill_json` fixture):

1. `test_month_avg_passthrough`: macro_signal.json 带
   `indicator_meta.dr007.month_avg` → 快照里 dr007.month_avg 正确。
2. `test_month_avg_absent_is_null`: 旧格式无字段 → month_avg=None。
3. `test_risk_data_month_avg`: risk_data.json 的 volume.month_avg →
   total_amount_yi.month_avg。
4. `test_month_avg_not_numeric_ignored`: 字段是字符串 → None(不抛错)。

前端无单测基础设施，验证走 lint + 手动验证(AC3/AC4)。

## 6. 风险

| 风险 | 缓解 |
|------|------|
| skill 侧迟迟不输出 month_avg | 字段可选,前端回退现状,无阻塞依赖 |
| 月均口径歧义(全月 vs 本月至今) | 契约文档明确:历史月=全月均值(终值),当月推送含本月至今均值 |
| 跨月推送时 month_avg 归属错月 | month_avg 与 value 同采样月绑定,跟随 value 的按月过滤 |
