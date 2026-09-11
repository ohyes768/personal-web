# FundTable 类型列加 5 粗类别 chip + market_subtype，让筛选正确性一眼可见

## Goal

FundTable 的「类型」列当前展示 `fund_type` 字段（DB 全为空字符串），实际看到的是 "-"。改为展示两层信息：

- **上行**：浅灰底 chip，显示 5 粗类别（股票型 / 混合型 / 指数型 / QDII / REITs / 纯债型 / 指数债 等）
- **下行**：小字灰字，显示精确 `market_subtype`（如 指数型-股票 / 混合型-偏股 / QDII-普通股票）

目标：用户在勾选「基金类型」多选框后，扫一眼表格就能确认每行基金属于哪个粗类别、哪个精确子类——筛选 bug 一眼可见。

## Background

### 数据现状

- DB 里 `funds.fund_type` 字段全为空（`market_universe_fetcher.fetch_market_universe` 没填过）
- DB 里 `funds.market_subtype` 字段有值（akshare 基金类型，27 个精确枚举）
- 后端 `_to_dto` 当前只返回 `fund_type`，**没**返回 `market_subtype`
- 前端 `fund.fund_type` 显示走 `displayFundType()`，对空字符串走 `|| '-'`，结果整列都是 "-"

### 设计决策（已和用户确认）

- 方案 1：浅灰底 chip + 灰字 subtype（中性灰配色，不引入彩色）
- chip 样式：`bg-paper-tint text-ink-strong text-[10px] font-medium px-1.5 py-0.5 rounded`
- subtype 行：`text-ink-soft text-[10px]`
- 5 大类不需要区分，文字本身已能识别——避免多色污染表格视觉

### 反向映射来源

前端 `types.ts` 已有 `COARSE_TO_SUBTYPES_STOCK` / `COARSE_TO_SUBTYPES_BOND`（粗 → 精）。新增反向映射 `SUBTYPE_TO_COARSE_STOCK` / `SUBTYPE_TO_COARSE_BOND`（精 → 粗），由模块初始化时从正向映射 invert 得到。

未知 subtype（如 `QDII-商品` / `商品` / `其他` / 未来新增）→ chip 显示原值（无粗类别前缀）+ subtitle 行也是原值，颜色用 ink-soft。

## Requirements

### 后端改动

1. **[api/models.py:FundListItem](backend/fund-select/src/api/models.py)** Pydantic 同步声明新字段：
   ```python
   market_subtype: Optional[str] = None  # akshare 精确子类（替代 fund_type 显示用）
   ```
   **必须同步**（参考 09-09 踩坑：Pydantic v2 严格序列化会静默 drop 未声明字段）

2. **[services/filter_service.py:_to_dto](backend/fund-select/src/services/filter_service.py)** 返回 dict 加：
   ```python
   "market_subtype": f.market_subtype,
   ```
   （fund_type 字段保留兼容，不删）

### 前端改动

3. **[types.ts](apps/fund-select/src/lib/types.ts)** FundListItem 接口加字段：
   ```typescript
   market_subtype: string;  // akshare 精确子类
   ```

4. **[types.ts](apps/fund-select/src/lib/types.ts)** 加反向映射（紧贴 `COARSE_TO_SUBTYPES_STOCK/BOND` 定义）：
   ```typescript
   export const SUBTYPE_TO_COARSE_STOCK: Record<string, string> = invertCoarseMap(COARSE_TO_SUBTYPES_STOCK);
   export const SUBTYPE_TO_COARSE_BOND: Record<string, string> = invertCoarseMap(COARSE_TO_SUBTYPES_BOND);

   function invertCoarseMap(m: Record<string, string[]>): Record<string, string> {
     const out: Record<string, string> = {};
     for (const [coarse, subs] of Object.entries(m)) {
       for (const s of subs) out[s] = coarse;
     }
     return out;
   }
   ```

5. **[components/FundTable.tsx](apps/fund-select/src/components/FundTable.tsx)** 「类型」列 td 重做：
   ```tsx
   <td className={`${td} leading-tight`}>
     <TypeCell subtype={fund.market_subtype} />
   </td>
   ```
   `TypeCell` 子组件：
   ```tsx
   function TypeCell({ subtype }: { subtype: string | null }) {
     if (!subtype) return <span className="text-ink-soft">-</span>;
     const coarse = SUBTYPE_TO_COARSE_STOCK[subtype] ?? SUBTYPE_TO_COARSE_BOND[subtype];
     if (!coarse) {
       // 未知 subtype（QDII-商品/商品/未来新增）：单行灰字
       return <span className="text-ink-soft text-xs">{subtype}</span>;
     }
     return (
       <div className="flex flex-col gap-0.5">
         <span className="inline-block self-start px-1.5 py-0.5 rounded text-[10px] font-medium bg-paper-tint text-ink-strong">
           {coarse}
         </span>
         <span className="text-[10px] text-ink-soft">{subtype}</span>
       </div>
     );
   }
   ```

### 不变更

- 不删 `fund_type` 字段（DB 后续可能填值，保留向后兼容）
- 不动 5 粗类别选项本身（MARKET_TYPE_OPTIONS / STOCK_MARKET_TYPE_OPTIONS / BOND_MARKET_TYPE_OPTIONS）
- 不动筛选逻辑 / 后端 SQL
- 不动表格其它列（名称 / 业绩 / 排名 / 回撤等）
- 不引入彩色（保持项目中性灰主题）

## Acceptance Criteria

- [ ] [api/models.py:FundListItem](backend/fund-select/src/api/models.py) 声明 `market_subtype: Optional[str] = None`
- [ ] [filter_service.py:_to_dto](backend/fund-select/src/services/filter_service.py) 返回 dict 含 `"market_subtype": f.market_subtype`
- [ ] [types.ts](apps/fund-select/src/lib/types.ts) `FundListItem` 接口加 `market_subtype: string`
- [ ] [types.ts](apps/fund-select/src/lib/types.ts) 导出 `SUBTYPE_TO_COARSE_STOCK` 与 `SUBTYPE_TO_COARSE_BOND`，且：
  - `SUBTYPE_TO_COARSE_STOCK['指数型-股票'] === '指数型'`
  - `SUBTYPE_TO_COARSE_STOCK['混合型-偏股'] === '混合型'`
  - `SUBTYPE_TO_COARSE_STOCK['QDII-REITs'] === 'QDII'`
  - `SUBTYPE_TO_COARSE_BOND['混合型-偏债'] === '混合型'`
  - `SUBTYPE_TO_COARSE_STOCK['QDII-商品'] === undefined`（保持 other）
- [ ] [components/FundTable.tsx](apps/fund-select/src/components/FundTable.tsx) 「类型」列渲染两行结构：上行 chip 显示粗类别，下行小字显示精确 subtype
- [ ] 老 bond tab / stock tab / discovery-stock / discovery-bond 四个页面表格都更新（FundTable 共享组件，自动生效）
- [ ] DB 里 `market_subtype='QDII-商品'` 或 `'商品'` 的基金在表格里 chip 不显示（走「未知 subtype」分支，灰色单行）
- [ ] 现有 325 条后端单测不回归
- [ ] 表格行高调整后视觉可接受（每屏少 2-3 行，但能完整看到两层信息）

## Verification Plan

1. **后端单测**：跑现有 `test_discovery_filter_service.py` + `test_api.py` 等用例，新增一条 case 验证 `_to_dto` 返回 `market_subtype` 字段：
   ```python
   def test_to_dto_includes_market_subtype(db_db_session):
       f = _mk_fund("000001", market_subtype="指数型-股票")
       db_db_session.add(f); db_db_session.commit()
       items = FilterService(db_db_session).screen_discovery_stock()["items"]
       assert items[0]["market_subtype"] == "指数型-股票"
   ```

2. **DB 实证**：
   ```bash
   sqlite3 data/funds.db "SELECT code, name, market_subtype FROM funds WHERE is_active=1 AND code='000008';"
   ```
   000008 嘉实中证 500ETF 联接A → market_subtype='指数型-股票' → chip 应显示「指数型」，subtitle「指数型-股票」。

3. **前端构建**：在 apps/fund-select 跑 `pnpm build` 确认 TS 接口一致（不报错即过）。

5. **人工 UI 验证**（部署后）：
   - 打开 /discovery-stock，只勾「指数型」
   - 表格「类型」列全部应显示 chip「指数型」+ subtitle 三选一（指数型-股票 / 指数型-海外股票 / 指数型-其他）
   - 没有任何行 chip 显示「QDII / REITs / 混合型 / 股票型」

## Risks

- **表格行高**：每行从 ~28px 增加到 ~46px。每屏少 3-4 行可见记录。可接受（当前 limit=50，本来就要滚动）。
- **Pydantic 字段遗漏**：参考 09-09 踩坑记录——`_to_dto` 加字段时必须同步 `models.py`。本次已在 Acceptance Criteria 第 1 条约束。
- **未知 subtype**：QDII-商品 / 商品 / 其他 当前不在 universe，理论上 UI 不会展示（被 stock/bond universe 排除）。若 universe 后续扩大，需重新评估 fallback 展示。
- **chip 颜色一致性**：所有 5 大类统一浅灰底，不区分。如果未来需要按 tab 区分粗类别（股基侧 vs 债基侧），要重新设计——本次不做。

## Out of Scope

- 不重做 chip 颜色为彩色分类
- 不动排序 / 筛选 / 分页逻辑
- 不动 FundDetail 详情抽屉
- 不引入「未分类 / unknown」第 6 粗类别 UI
- 不动 DB 数据（market_subtype 已经填好）