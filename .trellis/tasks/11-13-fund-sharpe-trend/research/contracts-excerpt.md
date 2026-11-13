# fund-select 后端契约摘录（夏普走势任务适用部分）

> 从 `contracts.md`（67KB，超注入上限会被截断）摘出本任务真正用到的条款。
> 权威原文见 `.trellis/spec/backend/fund-select/backend/contracts.md`，改契约时同步回去。

## §3a Pydantic response_model 静默砍字段（最高频陷阱）

`response_model` 序列化会**静默丢弃未显式声明的字段**。新增 DTO 时：

1. 每个返回给前端的字段都必须在 Pydantic 模型里声明
2. 后端 DTO 加字段要**三处同步**：`src/api/models.py` ↔ 前端 `src/lib/*.ts` 接口 ↔ 页面消费
3. 枚举值（如 `range`、`source`）两端字面必须完全一致

历史教训：`SharpeBoardResponse` 曾因顶层字段未声明而静默返回空值，排查很久才定位。

## §4 basePath 陷阱

```
浏览器 http://localhost:3005/funds  (Next.js, basePath=/funds)
  → /funds/api/funds/*              (app/api/funds/[...path]/route.ts 代理)
  → http://localhost:8095/api/funds/* (FastAPI)
```

- 页面放 `app/<name>/page.tsx`（不要 `app/funds/...`，会双前缀）
- `<Link href>` / `router.push` 用**相对 basePath 的路径**：`/sharpe-trend?code=xxx` ✓，`/funds/sharpe-trend` ✗（变 `/funds/funds/sharpe-trend`）
- 原生 `fetch` **必须写全路径** `/funds/api/funds/...`（fetch 不吃 basePath）
- 同步筛选 URL 只拼 `?qs`，不要拼 `location.pathname`

## §13 夏普算法口径（走势页必须与之对齐）

**公式**：`sharpe = mean(excess_p) / std(excess_p, ddof=1) × √252`

- `excess_p = R_p − R_f_daily`
- `R_p` = 东财「日增长率」(%) / 100 —— **分红已除息调整的复权日收益**
- 勿用「累计净值」pct_change：累计净值 = 单位净值 + 历史分红简单加总（非复权），有分红的基金会稀释整条序列
- `R_f` 年化小数 / 252 折日频
- 常量：`MIN_SAMPLE_DAYS=250`、`TRADING_DAYS=252`、`WINDOW_YEARS=3`
- `std==0` 或 NaN → 指标无定义（返回 None，不出点）

**多指标共用同一 join 样本**：`compute_risk_metrics` 里 `r_p` 与 `r_b` inner join 后算所有指标。这意味着 **benchmark 缺失会截断夏普的样本窗口** —— 走势页因此改用纯净值口径（不 join 基准），详见 research/data-basis.md。

## §13 周键惯例（走势页周点对齐参考）

周榜用「任务 started_at 转 Asia/Shanghai 所在周周一」作为周键。走势页的周点用**该自然周最后一个交易日**（不是周一），因为夏普需要实际有交易的日期。两者语义不同但都基于自然周，前端展示时注意不要混用。

## 路由注册顺序铁律

静态路由必须注册在通用 `/{code}` 详情路由**之前**（`src/main.py`）：

```python
app.include_router(scheduler_router, prefix="/api/funds")
app.include_router(sharpe_board_router, prefix="/api/funds")   # 静态
app.include_router(router_managers, prefix="/api/funds")       # 静态
app.include_router(router, prefix="/api/funds")                # ← 通用 /{code}
```

否则 `/api/funds/sharpe-trend/000628` 会被 `/{code}` 吞掉，报「基金不存在: sharpe-trend」。

## 刷新与采集边界

走势页是**纯只读 + 现算**页面：
- 不写任何表
- 不进调度
- 不影响周榜发布
- 外部依赖只有 `fetch_nav(code)`（akshare 东财净值）

## 测试基线

`backend/fund-select` 当前 **597 passed**（`/tmp/fsvenv/bin/python -m pytest tests/ -q`）。新增测试必须在同一 venv 下跑通。
