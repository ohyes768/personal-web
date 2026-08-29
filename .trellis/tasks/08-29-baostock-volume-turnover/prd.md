# BaoStock 实现两市成交额/换手率历史日频数据

## Goal

用 BaoStock 上证指数 + 深证综指日线获取两市成交额与换手率的全量历史日频数据，回补
`volume.csv` / `turnover.csv`，并统一日常增量取数口径（历史与日常同源，避免混口径）。

## 背景

- 调研已验证（demo：`backend/macro/demo_baostock.py`，2026-08-29 执行通过）：
  - BaoStock `query_history_k_data_plus` 指数日线含 `amount`（元）与 `turn`（%）
  - 上证指数 `sh.000001` 覆盖 1990-12-19 至今（8714 行）；深证综指 `sz.399106` 覆盖 1991-04-04 至今
  - 2026-08-28 交叉验证：两市成交额 = 9703.65 + 11313.50 ≈ 21017 亿，量级正确
- 现状：`volume_service` / `turnover_service` 走沪深交易所官方 API 只取**当日点**，
  CSV 各仅 2 天数据（2026-08-25 起），宏观信号 / 日频快照缺少历史序列做分位与趋势。
- 官方 API 历史日期不可查（SSE 仅近一两年、SZSE 返回空），无法用于回补；且近期
  SZSE 成交额解析已出现 0 值，官方口径与通用"两市成交额"也存在偏差（详见调研记录）。

## Requirements

1. 新增 BaoStock 数据源服务（`baostock_service.py`）：
   - 一次登录会话拉取 `sh.000001` 与 `sz.399106` 日线（date, close, volume, amount, turn）
   - 两市成交额 = 沪 amount + 深 amount（元 → 亿元）
   - 两市换手率 = 按两市成交额加权（复用现有加权公式）
2. 历史回补：提供 API 端点一次回补两指标，默认起点 2010-01-01（与融资余额历史起点
   对齐），写入复用 `DataService.save_volume_data / save_turnover_data`（同日覆盖 keep=last）
3. 日常增量切换：现有 `POST /api/macro/update/volume|turnover` 端点内部改调 BaoStock
   （端点路径、请求/响应结构不变，n8n 调度无感知）
4. 口径统一后清理孤儿：删除 `volume_service.py` / `turnover_service.py` 及其测试
   （`test_volume.py` / `test_turnover.py`）
5. 依赖：`baostock>=0.9.0` 加入 `pyproject.toml`（venv 已装 0.9.3）

## 范围外（Out of Scope）

- 融资余额（margin）历史回补 —— akshare 现有接口即全量历史，另开任务
- 前端任何改动 —— 回补后日频快照 / 宏观信号自然受益，无需改 UI
- 数据缺口监控 / 双源兜底 —— 单源 BaoStock，失败靠调度重试

## Acceptance Criteria

- [ ] `volume.csv` / `turnover.csv` 回补后 ≥ 3800 行（2010-01-01 至今），日期序列
      与两指数交易日对齐、无重复、无缺行
- [ ] 回补后 2026-08-28 成交额在 21017 亿 ±1% 内；两市加权换手率落在
      min/max(沪、深单市 turn) 区间内（加权正确性）
- [ ] `POST /api/macro/update/volume|turnover` 走 BaoStock 口径且落库；响应结构不变
- [ ] 回补端点幂等：重复调用不产生重复行
- [ ] `python -m pytest tests/ -v` 全部通过（新增 baostock 单测，mock 外部依赖，
      不真连 BaoStock；旧 volume/turnover 测试随源码删除）
- [ ] `demo_baostock.py` 调研脚本在任务收尾时删除

## Notes

- 回补前备份 `data/volume.csv` / `data/turnover.csv`（CSV 可能不受 git 管理，覆盖不可逆）
- BaoStock 为免费服务，登录会话需显式 login/logout；批量历史拉取一次会话完成
