# 技术设计:宏观信号按月过滤

## 改动边界

| 层 | 文件 | 改动 |
|----|------|------|
| 后端 | `src/services/macro_signal_service.py` | 兜底路径按月过滤 + 占位指标生成 |
| 前端 | `apps/macro/src/lib/modules/macro-signal/types.ts` | 无(现有字段够用) |
| 前端 | `apps/macro/src/app/modules/economic/components/macro-signal/GroupCard.tsx` | IndicatorRow 暂未获取态 |
| 前端 | `apps/macro/src/app/modules/economic/components/MacroSignalTab.tsx` | months ∪ 当前自然月 |
| 测试 | `backend/macro/tests/test_macro_signal_month_filter.py`(新建) | 过滤与占位逻辑 |

不动:release_rules.py 规则表(能力已有)、models.py(字段已有)、
归档路径读取逻辑。

> 注:前端发布日历(ReleaseCalendar.tsx + 前端 release-rules.ts)与维度
> total_score 徽章已于本任务之外先行移除(用户决策:日历无意义、分数已有
> 档位刻度替代),与上述后端 release_rules.py 无关,后者继续服务
> 「暂未获取 + 预期发布时间」。

## 后端设计

### 数据流(兜底路径,月频)

```
读平铺最新 macro_signal.json
  → details 里出现过的 key = 该维度全量指标清单(不含本次未输出的)
  → 逐指标判定:
      data_date 前 7 位 == 请求月 → 正常输出(value + 三时间)
      否则                        → 占位(value=null, data_date=null,
                                    next_release_at=规则推算, frequency=规则表)
  → 全部指标都不在请求月 → 该维度保留占位清单(不返回 null)
```

### 关键函数改动(`macro_signal_service.py`)

1. `_convert_dimension_from_macro_signal(raw, file_mtime)` 增加参数
   `month: Optional[str]`。None = 不过滤(归档路径语义);非 None = 兜底路径
   按月过滤 + 生成占位。指标级逻辑:
   - `in_month = ind_date and ind_date.startswith(month)`
   - `in_month` → 原样输出
   - 非 in_month 但 key 在 `INDICATOR_RELEASE_RULES` → 占位 MacroIndicator
   - key 不在规则表(如 skill 新增指标)→ 剔除(无规则可推预期,不造数)
   - value 本身是 None/字符串的跳过逻辑维持(不进清单)
2. `_convert_risk_appetite` 同样加 `month` 参数。risk 三个子块全是日频,
   逻辑与 macro_signal 一致(日频不落请求月也会推「下一工作日」预期,
   `frequency='daily'` 前端不渲染下次段,占位仍会显示「暂未获取」)。
3. `get_snapshot`:
   - 兜底分支 `_read_latest_groups()` 调用改为 `_read_latest_groups(month)`。
   - `any_match` 判定放宽:`any(ind.value is not None and ind.updated_at...)`
     → 保留任一**有值**指标落在请求月即算该月有数据;全占位(无任何有值
     指标落请求月)时返回 None?**否**——R4 要求当前自然月可切,若返回 None
     前端显示「数据缺失」整页,没有占位指标可见。决定:兜底路径**只要有
     任一 key 在请求月或全占位时仍返回 groups**(即把 `any_match` 判定改为
     `any(ind.data_date and ind.data_date.startswith(month))`,有值指标判定
     不变),只是无值。前端 emptySnapshot 兜底不再触发。

     → 再推敲:全占位场景=该月连日频指标都没有(极端:8 月完全没推送过,
     平铺文件全是 7 月)。此时前端切到 8 月应显示六组「全暂未获取」占位。
     这正是 R4 的诉求(8 月数据还没出来,显示暂未获取+预期发布时间)。
     所以 `any_match` 直接删除?不行,验收标准 3 要求无数据月(2026-06)
     返回 null。区分:请求月 < 最新数据月(历史空洞月)→ null;
     请求月 >= 最新数据月(当前月/未来月)→ 全占位返回。

### 归档月与兜底路径的语义区分(核心判定)

```
latest_month = 平铺文件里所有指标 data_date 的最大 YYYY-MM
请求 month:
  - archive/<month>/ 存在        → 归档全量(现状)
  - month > latest_month          → 兜底+全占位(R4:未来月/当前月切得进去)
  - month == latest_month         → 兜底+按月过滤(R1:8 月视图里 7 月指标变占位)
  - month < latest_month 且无归档 → null(验收 3:历史空洞月)
```

`month > latest_month` 场景占位指标的 `next_release_at` 推算:ref 取
`date.today()`(规则函数已有「基准日=max(数据时间, 今天)」语义,数据时间
为 null 时自然落到今天,正好推算出「8 月数据」的发布日,如 CPI → 09-09)。

### 占位 MacroIndicator 字段

```python
MacroIndicator(
    key=key, value=None, updated_at=None, data_date=None,
    analyzed_at=None,
    next_release_at=<规则推算>, next_release_note=<规则 note>,
    frequency=<'daily'|'monthly'>,
)
```

### 超出本次范围(设计上预留、实现不做)

- 归档月也可能有「skill 当时漏输出」的指标 → 不补占位(归档即真源)。
- `month == latest_month` 但部分指标已跨到下月的混合场景 → 过滤规则天然覆盖。

## 前端设计

### GroupCard.tsx / IndicatorRow

```
value === null && frequency === 'monthly'
  → 数值显示 '—'(现有 formatValue 已处理 null)
  → 时间行渲染:
      <span title="预期 2026-09-09 · CPI/PPI 约每月9日发布">
        暂未获取 · 预计 ≈09-09 发布
      </span>
```

判断入口在 IndicatorRow:新增分支优先于现有「本月无数据」分支
(现有分支条件 `!dataDate`,占位指标 data_date=null 也会落到那里,需区分:
占位指标带 next_release_at,旧「本月无数据」针对的是「skill 输出了 key 但
连日期都没有」的边缘态,保留给无 next_release_at 的行)。

日频占位(frequency='daily')同渲染「暂未获取」,不渲染「预计」
(下一工作日无信息量)。

### MacroSignalTab.tsx

```ts
const currentYM = currentYearMonth();
const monthsWithNow = useMemo(
  () => Array.from(new Set([...availableMonths, currentYM])).sort(),
  [availableMonths, currentYM],
);
// MonthSwitcher 与 selectedMonth 默认值均用 monthsWithNow
```

defaultMonth 逻辑不变(`sorted[sorted.length-1]`,当前自然月排序最大,
首次进入即落在当前月——符合「最新」直觉)。

## 兼容与回滚

- API shape 不变(MacroIndicator 字段全 Optional),前端旧版本读到占位指标
  显示 `—` + 「本月无数据」,不炸。
- 回滚 = revert 单 commit,无数据迁移、无存量数据重写。

## 权衡记录

1. **占位 vs 剔除**:选择占位透出(而非静默剔除),因为用户明确要「显示下
   暂未获取,展示下预期发布时间」;剔除会让指标凭空消失,无法感知缺什么。
2. **全占位月返回 groups vs null**:选择返回(R4 切到 8 月必须能看到占位),
   同时保留历史空洞月 null 的语义(验收 3),用 `month vs latest_month` 比较区分。
3. **占位清单来源 = 本次 details keys**:不引入硬编码指标清单(22 个 key
   双份维护),skill 输出什么就占位什么,规则表查不到的 key 剔除。
4. **前端判断用 value==null**:不用新增 is_placeholder 字段——语义上
   「暂未获取」就是「该指标在这个月没有值」,与 data_date 联合判定足够。
