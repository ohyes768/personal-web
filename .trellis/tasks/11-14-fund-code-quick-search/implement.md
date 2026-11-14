# 执行计划：基金代码快速搜索

## 前置阅读

- `.trellis/spec/backend/fund-select/backend/contracts.md` §4（basePath 陷阱）、
  §13（路由注册顺序陷阱）
- 本任务 `prd.md` / `design.md`
- 现有能力：四个 tab 页的 `?code=` → `RowDetailDrawer` stub 模式

## 测试环境

```bash
cd backend/fund-select
/tmp/fsvenv/bin/python -m pytest tests/ -q        # 710 passed 基线
cd apps/fund-select
node --experimental-strip-types --test src/lib/*.test.ts   # 38 passed 基线
npx tsc --noEmit && pnpm build
```

---

## 阶段 0：基线

- [ ] 0.1 后端全量测试确认 710 passed
- [ ] 0.2 前端 node --test + tsc 确认 38 passed
- [ ] 0.3 记录四个 tab 现有 `?code=` 行为可用（浏览器点一下确认）

---

## 阶段 1：后端判定服务（纯逻辑优先）

### 1.1 `src/services/lookup_service.py`

- [ ] `resolve_tab(db, code) -> dict` 实现 design §2 的优先级
- [ ] yaml 名单判定用 `load_fund_codes(get_funds_config_path()/get_stock_funds_config_path())`
- [ ] `market_subtype` 前缀匹配用 `DISCOVERY_BOND_SUBTYPES` / `DISCOVERY_STOCK_SUBTYPES`
- [ ] `market_type` 以「债券」开头 → bond（脏值防御）
- [ ] `path` 拼接为相对路径 `/{tab}?code={code}`（**不带 `/funds` 前缀**）

**测试**（`tests/test_lookup_service.py`）：
- [ ] yaml 债基代码 → bond
- [ ] yaml 股基代码 → stock
- [ ] 非名单 stock → discovery-stock
- [ ] 非名单 bond → discovery-bond
- [ ] **非名单 other + 债券型子类 → discovery-bond**（2653 只的场景）
- [ ] 非名单 other + 混合型/FOF → discovery-stock
- [ ] 脏值 `market_type='债券型-长债'` → bond
- [ ] 不存在 code → found=False
- [ ] `path` 不含 `/funds` 前缀

### 1.2 API + DTO

- [ ] `FundLookupResponse` 加到 `models.py`（**所有字段显式声明**，§3a 静默砍字段）
- [ ] `@router.get("/lookup/{code}")` 注册在 `/{code}` **之前**
- [ ] `code` 参数 `pattern=r"^\d{6}$"`（格式错 → 422）

**测试**（`tests/test_lookup_api.py`）：
- [ ] `/lookup/002910` → 200，tab=discovery-stock，path 正确
- [ ] `/lookup/999999` → 200 + found=false（不是 404）
- [ ] `/lookup/abc` / `/lookup/12345` → 422
- [ ] **路由顺序**：响应结构是 lookup 不是详情（防被 `/{code}` 吞）
- [ ] 响应含全部 7 个字段

---

## 阶段 2：前端搜索组件

### 2.1 `src/lib/lookup.ts`

- [ ] `FundLookup` 类型对齐后端 7 字段
- [ ] `normalizeCode(input)`：trim + 全角转半角 + 只留数字 + 校验 6 位
- [ ] `fetchFundLookup(code)`：全路径 `/funds/api/funds/lookup/{code}`

**测试**（`src/lib/lookup.test.ts`）：
- [ ] `'002910'` / `' 002910 '` / 全角 `'００２９１０'` 都归一为 `'002910'`
- [ ] `'12345'` / `'abc'` / `''` 返回 null
- [ ] 错误分类

### 2.2 `src/components/FundCodeSearch.tsx`

- [ ] `inputMode="numeric"` + `maxLength={6}`
- [ ] 回车与按钮共用一个 submit handler
- [ ] `loading` 时禁用输入与按钮
- [ ] 成功 → `router.push(path)`
- [ ] 失败 → 就地提示，不清空
- [ ] 移动端：`<640px` 收成图标，点击展开覆盖式输入框

### 2.3 接入 `FundsHeader`

- [ ] 新增可选 prop `showCodeSearch?: boolean`（默认 false）
- [ ] 右侧槽位插入位置：刷新按钮之后、「共 N 只」之前
- [ ] 四个 tab 页传 `showCodeSearch`；经理/榜单/走势不传

---

## 阶段 3：验证

- [ ] 3.1 后端全量 `pytest`（710 + 新增）
- [ ] 3.2 前端 `node --test` + `tsc --noEmit` + `pnpm build`
- [ ] 3.3 浏览器：
  - 四 tab 有搜索框 / 经理·榜单·走势无
  - 输入 002910 → 跳 discovery-stock + 抽屉打开
  - 输入 yaml 内代码 → 跳雪球 tab
  - 输入不存在代码 → 提示
  - 390px 无横溢出
  - `/bond?code=003547` 直达仍可用（回归）

---

## 阶段 4：收尾

- [ ] 契约新增 §20（lookup 路由判定契约）
- [ ] 前端契约补搜索框
- [ ] 部署（前后端）
- [ ] journal + 归档

---

## 回滚点

| 阶段 | 回滚 |
|---|---|
| 1-2 | `git revert`；未改任何现有协议 |
| 3 发现判定错 | 只改 `lookup_service.py` 的优先级 |
| 部署后 | 搜索框是纯新增 UI，前端回滚即消失 |

---

## 验收命令

```bash
cd backend/fund-select
/tmp/fsvenv/bin/python -m pytest tests/test_lookup_service.py tests/test_lookup_api.py -q
/tmp/fsvenv/bin/python -m pytest tests/ -q

cd apps/fund-select
node --experimental-strip-types --test src/lib/lookup.test.ts
npx tsc --noEmit && pnpm build
```
