# 修复DR001解析JSON路径错误

## Goal

修复日频流动性卡片 DR001 指标恒为空的 bug：`extract_dr001` 在 `payload["data"]["records"]` 找记录，但中国货币网 `prr-md.json` 真实响应的 `records` 在顶层，导致解析永远失败、被失败隔离静默降级为 null。

## 背景与根因（2026-09-15 线上排查结论）

- 线上 `/api/macro/daily-snapshot` 返回 `dr001: {value: null, prev_value: null, data_date: null}`，同组 DR007 正常。
- 数据源正常：用代码同款请求方式（POST + Referer/X-Requested-With 头）拉 `prr-md.json` 成功，当日 DR001 有值。
- 真实响应结构（本机实测 + akshare `bond_china_money.py` 同源解析佐证）：
  `{"head": {...}, "data": {"showDateCN", "showDateEN"}, "records": [{"date", "productCode", "weightedRate", ...}]}`
  —— `records` 在**顶层**，`data` 下只有 showDate 字段。
- 错误代码：`backend/macro/src/services/dr001_service.py` `extract_dr001` 第 82-87 行 `data = payload.get("data"); records = data.get("records")`。
- 测试同样按错误结构 mock（`test_dr001.py` `_make_payload` 构造 `{"data": {"records": [...]}}`），所以测试全绿但从未对过真实接口。该功能自 2026-09-01 上线起从未真正显示过。

## Requirements

1. `extract_dr001` 优先从顶层 `payload["records"]` 抽取（真实结构）；若顶层无 `records`，回退兼容 `payload["data"]["records"]`（防接口结构回摆/与历史认知一致）。两处都没有 → 返回 None（维持现有失败隔离语义）。
2. `test_dr001.py` 的全部 mock payload 改为真实顶层结构；原有用例语义不变（取 DR001、跳过其他产品、字段缺失/类型错误返回 None 等）。
3. 补一条用例：顶层 `records` 正常解析（真实结构）；`test_extract_dr001_returns_none_for_malformed_payload` 等边界用例同步适配双路径。
4. 不改 `fetch_json`/`fetch_today`/请求头/重试逻辑，不改其他文件。

## Acceptance Criteria

- [ ] `extract_dr001` 对真实顶层结构返回 `{"value": float, "data_date": "YYYY-MM-DD"}`；对旧 `data.records` 结构仍可解析；两者皆无返回 None。
- [ ] `cd backend/macro && ./.venv/Scripts/python.exe -m pytest tests/test_dr001.py -v` 全绿。
- [ ] 端到端验证：本机跑 `PYTHONPATH=. ./.venv/Scripts/python.exe -c "...fetch_today()..."` 返回单行 DataFrame（index=当日日期，dr001 有值）。
- [ ] `git diff` 仅涉及 `dr001_service.py` 与 `test_dr001.py` 两个文件。

## Notes

- 部署到 NAS（`./scripts/deploy-nas.sh macro backend`）由用户执行或后续单独确认，本任务验收以本地代码 + 测试 + 端到端复现为准。
