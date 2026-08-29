# 融资余额历史回补 — 执行清单

## 顺序

1. **单测先写合并逻辑**  
   `tests/test_margin.py`：outer join、缺侧 0、单位、失败路径。mock 两个 akshare DataFrame，不真连。

2. **`margin_service.py`**  
   - 抽出 `_merge_margin_history(sh_df, sz_df) -> DataFrame`（date + margin_balance_yi）。  
   - `fetch_today` 继续用 `_extract_latest_margin`。  
   - 新增 `fetch_history()`。  
   - 注释「万元→亿元」改为「元→亿元」（与测试一致）。

3. **`models.py` + `routes.py`**  
   - `MarginHistoryData` / `MarginHistoryUpdateData`。  
   - `POST /fetch/margin/history` 按 9 步骨架，落盘 `save_margin_data`。  
   - 不改 `update/margin`。

4. **前端**  
   `apps/macro/src/lib/modules/economic/api.ts`：`initMarketSentimentHistory` 串行 volume-turnover history → margin history。  
   `MarketSentimentTab` 注释改成两条 history；按钮绑定不用动。

5. **文档**  
   - `backend/macro/docs/数据更新端点规范.md` 清单补 `/fetch/margin/history`。  
   - `.trellis/spec/backend/global-macro-fin/backend/data-sources.md`：融资余额 history 契约 + 初始化串行两条；删掉「暂无 history」句。

6. **验证**  
   见下方命令。手动补数步骤见 `prd.md` Notes（三份 CSV + localStorage）。

## 验证

```bash
cd backend/macro
python -m pytest tests/test_margin.py -v
```

前端：市场情绪 Tab 点「初始化历史数据」，网络里先 `volume-turnover/history` 再 `margin/history`，两步 200 后图表出现融资余额长序列。

## 风险文件

- `backend/macro/src/api/routes.py` — 文件大，只在 `update/margin` 附近追加 history，不动其它端点。
- `backend/macro/data/margin.csv` — 回补覆盖同日点；操作前可备份。
- `apps/macro/src/lib/modules/economic/api.ts` — 只改 `initMarketSentimentHistory`。

## 回滚点

- 步骤 1–3 可整段还原三个后端文件。  
- 步骤 4 单独还原 `api.ts` 一行函数。  
- 已写入的 CSV 不能靠 git 回滚（通常未跟踪），从备份拷回或再打一次 history。
