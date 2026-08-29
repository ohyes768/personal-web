# 技术设计：BaoStock 两市成交额/换手率

## 边界与不动点

- 不改 CSV 存储结构：`volume.csv(date,total_amount_yi)` / `turnover.csv(date,turnover_rate)`
- 不改读取侧：`DataService.load_volume/load_turnover`、`daily_snapshot_service`、
  `macro_signal_service` 全部无感知
- 不改对外 API 契约：`/update/volume`、`/update/turnover` 路径与响应模型不变

## 新增：`src/services/baostock_service.py`

```
class BaostockService:
    _SH_CODE = "sh.000001"   # 上证指数（全沪市样本）
    _SZ_CODE = "sz.399106"   # 深证综指（全深市样本）

    def fetch_index_daily(code, start, end) -> DataFrame[date, amount, turn]
        # bs.query_history_k_data_plus(code, "date,close,volume,amount,turn",
        #   frequency="d", adjustflag="3")；amount/turn 转 float，空串→NaN

    def fetch_history(start, end) -> dict
        # 一次 login/logout 会话：
        #   sh = fetch_index_daily(SH), sz = fetch_index_daily(SZ)
        #   inner-join on date（只保留两指数都有值的交易日）
        #   volume_df:  date, total_amount_yi = (sh.amount + sz.amount) / 1e8
        #   turnover_df: date, turnover_rate = 加权换手率
        # 返回 {"volume": df, "turnover": df, "status": "ok"|"failed", ...}

    def fetch_today() -> dict
        # 增量入口：start = 今天往前 10 个自然日（覆盖节假日缺口），end = 今天
        # 复用 fetch_history；与现有 fetch_today 语义对齐（返回最新交易日单点或小批量）
```

- 加权公式与现 `turnover_service` 一致：
  `turnover = (sh_amt × sh_turn + sz_amt × sz_turn) / (sh_amt + sz_amt)`
- 模块级单例 `get_baostock_service()`，与项目其他 service 同款模式
- baostock import 放方法内（与 `margin_service` 处理 akshare 的方式一致，避免拖慢启动）

## 路由改动：`src/api/routes.py`

1. `update_volume()` / `update_turnover()`：
   - 内部 `get_volume_service()` → `get_baostock_service()`
   - 结果 dict 结构与旧实现兼容（date / total_amount_yi / turnover_rate 字段名不变），
     落库与响应代码不动
   - 两个端点各自调 `fetch_today()`（同一会话内拉两指标后各取所需；一次登录成本可接受，
     不合并端点，保持调度独立）
2. 新增 `POST /update/volume-turnover/history`（query 参数：`start_date` 默认
   `2010-01-01`、`end_date` 默认昨天）：
   - 调 `fetch_history()` → `save_volume_data` + `save_turnover_data`
   - 响应复用 `UpdateResponse` 风格，data 里带 `{volume_rows, turnover_rows, start, end}`

## 清理（本次改动产生的孤儿）

- 删除 `src/services/volume_service.py`、`src/services/turnover_service.py`
  （引用方仅 routes.py 与彼此，切换后无引用）
- 删除 `tests/test_volume.py`、`tests/test_turnover.py`
- 删除调研脚本 `demo_baostock.py`（收尾时）

## 依赖

- `pyproject.toml` dependencies 增加 `"baostock>=0.9.0"`（venv 已装 0.9.3）

## 测试设计：`tests/test_baostock_service.py`

- monkeypatch `baostock.login/logout/query_history_k_data_plus`（fake rs 对象带
  `error_code/error_msg/next()/get_row_data()/fields`），不真连
- 用例：
  1. 两指数合成：amount 求和/1e8、turn 成交额加权正确（手算 fixture）
  2. 交易日对齐：某日仅一指数有值 → 该日被 inner-join 剔除
  3. 空串/异常值 → NaN 行被 dropna
  4. login 失败 / error_code != 0 → status=failed 不抛异常
  5. 回补端点幂等：同数据重复 save 无重复行（依赖 `_save_market_sentiment_data`
     keep=last，已被现有行为覆盖，路由层断言调用参数即可）

## 风险与回滚

- BaoStock 免费服务不稳定 → 失败返回 failed，靠 n8n 调度次日自然补上；
  `fetch_today` 取近 10 日窗口可自动补节假日缺口
- 回补覆盖 CSV 不可逆（data/ 大概率不入 git）→ 回补前复制备份两份 CSV
- 回滚：git revert 代码；CSV 从备份恢复
