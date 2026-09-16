# DR001改为定时落库(对齐DR007设计)

## Goal

把 DR001 从「prr-md.json 请求时实时拉取、不落库」的旁路，改造成与 DR007 完全同款的定时落库链路：同一数据源 `prr-chrt.csv`、独立 `/update/dr001` 更新端点、`dr001.csv` 存储、scheduler `a_share_daily` 接入。改造后 DR001 获得与 DR007 相同的 asof 回退能力（外部拉取失败时显示最近可得值，不再整行「—」）。

## 背景

- 2026-09-15 排查确认（任务 archive/2026-09/09-15-fix-dr001-json-path）：`prr-chrt.csv` 实测同时含 DR001/DR007/DR014 三列（如 `2026-09-15,,,,,,1.4266,1.4244,1.4169`，index 6=DR001、7=DR007、8=DR014，已与 `prr-md.json` 当日值交叉验证），但 `dr007_service.parse_csv` 只取 index 7，DR001 列被丢弃，另走了实时旁路——结构上容易误解（用户指出）。
- 实时旁路的脆弱点：拉取失败整行消失、无历史回退、每次页面请求都打货币网。
- 用户决策：DR001 按 DR007 的设计补齐（定时落库），不做两套并存的混合说明。

## Requirements

1. `dr001_service.py` 改为 GET 同一 `prr-chrt.csv`，`parse_csv` 取 index 6 列（DR001 加权利率），提供与 `DR007Service` 同形态的 `fetch_history` / `fetch_latest`；prr-md.json/POST/`extract_dr001`/`fetch_today` 实时链路整体删除（生产无调用方后不留死代码）。
2. `data_service.py`：`files["dr001"]`、`save_dr001_data`（合并去重升序，镜像 `save_dr007_data`）、`load_dr001` 改为读 `dr001.csv`（同 `load_dr007` 形态）。
3. `routes.py` 新增 `POST /update/dr001`（镜像 `/update/dr007`：更新锁、`_compute_incremental_start`、增量拉取、落库、`UpdateResponse`）；`/update/dr007` docstring 补一句同源说明消除误解。
4. `models.py` 新增 `DR001Data` / `DR001UpdateData`（镜像 DR007 版）。
5. `scheduler.json` 的 `a_share_daily.targets` 增加 `/update/dr001`，同步更新组 description。
6. `daily_snapshot_service.py` 零改动（`("dr001","load_dr001","dr001")` 不变，取数实现内部切换）。
7. 文档同步：`docs/api.md` 接口清单加 `/update/dr001`；spec `macro-daily-snapshot.md` §2.1/§4 更新取数契约（由主会话在 spec 阶段处理，实施子代理不改 spec）。

## Acceptance Criteria

- [ ] `POST /update/dr001`：dr001.csv 为空时从 `historical_start_date` 全量回补（受 prr-chrt.csv 滚动窗口限制，与 DR007 行为一致）；已有数据时从 last_date+1 增量；数据源无新数据时返回「已是最新」不报错。
- [ ] `/daily-snapshot` 的 dr001 改读 dr001.csv；CSV 落库后显示最近可得值并带 `data_date`（asof 回退），外部源故障不再导致整行为 null。
- [ ] 代码中不再存在 prr-md.json / `extract_dr001` / `fetch_today` 的生产调用（grep 可验证）。
- [ ] scheduler 配置含 `/update/dr001` 且 description 准确。
- [ ] `tests/test_dr001.py` 重写后全绿（parse_csv 用真实 9 列格式样本；8 列老格式行、短行、空输入、去重排序等边界）；全量 `pytest tests/` 回归通过。
- [ ] `docs/api.md` 已更新。

## Notes

- 部署后需在 NAS 手动触发一次 `POST /api/update/dr001` 做首次全量回补（或等 16:30 定时任务自动补），此为部署动作，不在代码验收内。
- 当日值入库时点与 DR007 一致（货币网晚间发布当日行 → 次日 16:30 任务入库），页面行级 asof 回退标注——这正是与 DR007 对齐的语义。
- 不动 query_data_by_tab / 对比页 rates tab（DR001 不进对比页，超出本任务范围）。
