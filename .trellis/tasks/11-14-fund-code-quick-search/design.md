# 技术设计：基金代码快速搜索

## 1. 边界

| 层 | 文件 | 改动 |
|---|---|---|
| API | `src/api/routes.py` | 新增 `GET /lookup/{code}` |
| DTO | `src/api/models.py` | 新增 `FundLookupResponse` |
| 服务 | `src/services/lookup_service.py`（新） | 判定逻辑（yaml 优先 + market_type 兜底） |
| 前端 | `src/components/FundCodeSearch.tsx`（新） | 搜索框组件 |
| 前端 | `src/components/FundsHeader.tsx` | 右侧槽位插入搜索框 |
| 前端 | `src/lib/api.ts` 或新 `lookup.ts` | fetch 封装 + 类型 |

### 不变量

1. **不改四个 tab 页的 `?code=` 协议**（是本次依赖的既有能力）。
2. **搜索框不写进筛选状态**（不参与 `?qs` 序列化，避免污染可分享链接）。
3. **跳转用相对路径**（basePath 契约：`/discovery-stock?code=x`，不写 `/funds/...`）。
4. 判定**只读**，不写库、不触发采集。

---

## 2. 路由判定逻辑（核心）

```python
# src/services/lookup_service.py

def resolve_tab(db: Session, code: str) -> dict:
    """6 位基金代码 → 应跳到哪个 tab。

    优先级（yaml 名单优先于 market_type）：
      1. 在 funds.yaml（债基名单）      → bond
      2. 在 funds_stock.yaml（股基名单）→ stock
      3. market_type == 'stock'         → discovery-stock
      4. market_type == 'bond'          → discovery-bond
      5. market_type == 'other'         → discovery-stock（兜底，与现口径一致）
      6. 库内无该 code                  → found=False, tab=None
    """
```

**为什么 yaml 名单优先**：yaml 是「精选名单」，某只基金如果在名单里，用户更可能
是从「雪球三分法」两个 tab 认识的它；market_type 是全市场分类，粒度更粗。
两份名单无交集（31 / 142 / 交集 0），判定无歧义。

**`market_type='other'` 必须再看 `market_subtype`（实测关键发现）**：

生产库里 `other` 有 5115 只，其中：
- **2653 只是 `债券型-*`** ← 如果笼统兜底到股基市场，这 2653 只会跳到错误的 tab
- 969 只货币型 / 1430 只 FOF / 24 只空 → 均不在两个 discovery universe 内

因此 `other` 的规则：

```
other + market_subtype 以「债券型」开头  → discovery-bond
other + 其它                              → discovery-stock（含 FOF/货币，兜底）
```

`DISCOVERY_STOCK_SUBTYPES` 含「混合型-*」4 个子类，`DISCOVERY_BOND_SUBTYPES`
含「债券型-*」8 个子类——用这两个常量做**前缀/枚举匹配**比硬编码字符串更稳。

**注意**：`market_type` 有一个脏值 `'债券型-长债'`（1 行，code=519622），这是
`market_subtype` 的值被误写进了 `market_type`。判定时凡是以「债券」开头的一律
按 `bond` 处理。

---

## 3. API 契约

```python
class FundLookupResponse(BaseModel):
    code: str
    found: bool
    name: Optional[str] = None
    tab: Optional[str] = None          # bond|stock|discovery-bond|discovery-stock
    market_type: Optional[str] = None
    in_yaml: Optional[str] = None      # 'bond'|'stock'|None（命中哪份名单）
    path: Optional[str] = None         # '/bond?code=003547'
```

- **HTTP 一律 200**（包括 found=False）：查不到是正常业务结果，不是错误。
  用 404 会让前端要区分「代码不存在」和「接口挂了」，得不偿失。
- 路径参数校验：`code` 必须 6 位数字，否则 422（FastAPI `pattern`）。
  但为了让前端好处理，也可以统一 200 + `found=false`。**决策：用 422**——
  格式错误是调用方 bug，应明确暴露；`found=false` 只表示「格式对但库里没有」。

### 注册顺序

`/lookup/{code}` **必须注册在通用 `/{code}` 详情路由之前**，否则被
`/{code}` 吞掉当基金代码查（契约 §13 同类陷阱，现状 `main.py` 已有先例）。

---

## 4. 前端组件

```tsx
// src/components/FundCodeSearch.tsx
'use client';

export function FundCodeSearch() {
  // 状态：code / loading / error
  // 提交：fetch /funds/api/funds/lookup/{code}
  // 成功：router.push(res.path)   ← 相对路径已由后端给好
  // 失败：就地显示轻提示，不清空输入
}
```

- `inputMode="numeric"` + `maxLength={6}` + 正则 `^\d{6}$` 才允许提交。
- 回车提交（`onKeyDown` 判断 `Enter`）与按钮点击共用同一个 handler。
- **不写 URL 参数**：跳转由 `router.push(path)` 完成，搜索框自身状态不持久化。

### 移动端（390px）

header 右侧槽位已经很满（刷新 / 全量刷新 / 共 N 只 / 筛选）。方案：
- `hidden sm:flex` 常规输入框（≥640px）
- `<640px` 显示一个放大镜图标按钮，点击展开为覆盖式输入框（`absolute` 定位在 header 下方）
- 展开后 `Escape` 或失焦收起

**不要**在 390px 直接塞输入框——会挤压「共 N 只」导致换行，破坏 header 布局。

---

## 5. 兼容性

| 关注点 | 处置 |
|---|---|
| 现有 `?code=` 协议 | 完全兼容，搜索只是新增入口 |
| 四个 tab 的筛选 URL | 搜索框不写筛选参数，互不干扰 |
| 榜单页/经理页/走势页 | 不渲染搜索框（按 `FundsHeader` 新增 prop 控制） |
| 后端旧路由 | 新接口只增不改 |
| 部署 | 前后端都要发（后端提供 lookup，前端提供搜索框） |

### 如何控制只加在四个基金 tab

`FundsHeader` 新增可选 prop `showCodeSearch?: boolean`：

```tsx
// 四个 tab 页传 true；managers / sharpe-board 不传（默认 false）
<FundsHeader active="bond" showCodeSearch ... />
```

默认 `false`，避免经理页/榜单页误显示——它们复用同一个 header 组件。

---

## 6. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| `/lookup/{code}` 被 `/{code}` 吞掉 | 查到基金详情而非路由 | 注册顺序 + 路由冒烟测试 |
| yaml 名单变更后判定漂移 | 某基金跳错 tab | 名单是配置，改名单即改判定，符合预期 |
| `market_type` 脏值（'债券型-长债'） | 误判到股基市场 | 以「债券」前缀额外判 bond |
| 输入框挤压 header | 390px 溢出 | 小屏走图标展开式，不塞行内 |
| 用户输入带空格/全角 | 查不到 | 提交前 `trim()` + 只保留数字 |

---

## 7. Tests Required

**后端**（`tests/test_lookup_api.py`）：
- yaml 债基名单代码 → `bond`；yaml 股基名单代码 → `stock`
- 非名单 + stock → `discovery-stock`；+ bond → `discovery-bond`；+ other → `discovery-stock`
- `market_type='债券型-长债'` 脏值 → `bond`
- 不存在 code → 200 + `found=false` + `path=null`
- 非 6 位 / 含字母 → 422
- **路由顺序**：`/lookup/002910` 不被 `/{code}` 吞掉（响应结构是 lookup 而非详情）
- `path` 字段格式正确且是相对路径（不含 `/funds` 前缀）

**前端**（`src/lib/lookup.test.ts`）：
- 6 位数字校验、trim、全角数字归一化
- `path` 拼接（若前端自己拼）或直接消费后端 path
- 错误分类（not-found / network）

**浏览器**：
- 四 tab 都有搜索框；经理/榜单/走势没有
- 输入 002910 回车 → 跳 discovery-stock 且抽屉打开
- 输入 yaml 内代码 → 跳到雪球 tab
- 390px 无横溢出
