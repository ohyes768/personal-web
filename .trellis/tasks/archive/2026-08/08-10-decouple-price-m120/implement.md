# Implement — 行情价与M120解耦

> 执行顺序：后端 → 后端验证 → 前端 → 前端验证 → 手动场景验证。
> 每阶段末尾的 verify 必须通过再进入下一阶段。

## 阶段 0 · 基线

- [ ] 跑后端既有测试，记录基线结果(区分既有失败 vs 本次回归)。
  ```bash
  cd backend/dividend-select && python -m pytest tests/ -v 2>&1 | tail -40
  ```
  > 注：若基线已有失败，用 `git stash` 对照确认本次零回归(参见 memory 通用教训)。

## 阶段 1 · 后端 service：`read_prices_only`

文件：`backend/dividend-select/src/services/m120_service.py`

- [ ] 抽取 `_read_price_csv()`：把 `read_m120_with_deviation()` 中读实时价格 CSV 的段(line ~432-466，含新旧列名兼容、pe/pb 解析)搬入私有方法，返回 `{code: {close, realtime, pe, pb}}`。
- [ ] `read_m120_with_deviation()` 改调 `self._read_price_csv()`(行为不变)。
- [ ] 新增 `read_prices_only() -> dict[str, dict]`：`return self._read_price_csv()`。
- [ ] 新增单测 `tests/test_m120_service.py::test_read_prices_only*`(构造临时实时价格 CSV，断言返回；文件缺失返回 `{}`；M120 CSV 不存在不影响)。
- [ ] verify：
  ```bash
  cd backend/dividend-select && python -m pytest tests/test_m120_service.py -v
  ```

## 阶段 2 · 后端接口：`GET /api/dividend/prices`

文件：`backend/dividend-select/src/api/models.py`、`routes.py`

- [ ] `models.py` 新增 `PriceItem` / `PriceListResponse`。
- [ ] `routes.py` 抽 `_compute_yield_ttm(row, realtime_price, calculator)` helper；m120 endpoint 改调它(行为不变)。
- [ ] `routes.py` 新增 `GET /prices` endpoint：`read_prices_only()` → codes 过滤 → 对请求 code 算 yield_ttm → 组装 `PriceListResponse`；`last_updated` 取实时价格 CSV mtime(`get_realtime_price_file_mtime`)。
- [ ] verify：启服务，curl 验证。
  ```bash
  # 启动(后台)后：
  curl -s "http://127.0.0.1:8092/api/dividend/prices?codes=000922,000015" | python -m json.tool
  curl -s "http://127.0.0.1:8092/api/dividend/m120" | python -m json.tool | head   # 行为不变对照
  ```

## 阶段 3 · 前端：取数能力

文件：`apps/dividend/src/lib/types.ts`、`lib/api.ts`、`lib/hooks/useRealtimePrices.ts`

- [ ] `types.ts` 新增 `PriceItem`。
- [ ] `api.ts` 新增 `getPrices(codes?)`。
- [ ] 新建 `hooks/useRealtimePrices.ts`(codes→priceMap，空 codes→空 Map，`useMemo(JSON.stringify)` 防循环)。
- [ ] verify：
  ```bash
  cd apps/dividend && pnpm lint
  ```

## 阶段 4 · 前端：挡位监控接线

文件：`apps/dividend/src/app/page.tsx`

- [ ] 派生 `alertCodes`；调 `useRealtimePrices(alertCodes)`。
- [ ] 挡位监控渲染段(1068-1087)：`currentPrice/pe/pb/yield_ttm` 改读 `priceMap`，移除该段对 `technicalData.get` 的引用。
- [ ] verify：
  ```bash
  cd apps/dividend && pnpm lint && pnpm build
  ```

## 阶段 5 · 手动场景验证(核心验收)

- [ ] 正常：实时价格 CSV + M120 CSV 均在 → 挡位监控 bar 正常，值与改造前一致。
- [ ] **核心**：临时移走/改名当周 M120 CSV → 挡位监控 bar 仍渲染；全部 tab 的 M120 列可空(符合预期)。
  ```bash
  # 在后端 data 目录找到当周 M120均线_*.csv，临时改名
  # 刷新前端挡位监控 tab，确认 bar 仍在
  # 验完改回
  ```
- [ ] `GET /api/dividend/prices` 在 M120 CSV 缺失时仍返回数据。

## 阶段 6 · 提交(子模块)

- [ ] 子模块内：`git add -A && git commit -m "feat(api): 新增 /prices 现价接口，挡位监控与M120解耦" && git push origin main`
- [ ] 主仓库：`git add backend/dividend-select && git commit -m "chore: bump dividend-select pointer"` → 前端改动一并 commit → push。
  > 规则：子模块先 push，主仓库再 push gitlink。

## Review Gates

- 阶段 1 后：`read_prices_only` 单测绿 + m120 既有行为未变。
- 阶段 4 后：lint/build 通过。
- 阶段 5 后：核心验收(删 M120 CSV 挡位仍在)必须亲眼确认。

## 回滚点

- 任意阶段失败：后端改动均在子模块，`git checkout -- .` 还原；前端同理。
- 上线后发现回归：还原 `page.tsx` 挡位段读 `technicalData`，新接口保留无害。
