# Hermes run 会话记录打包下载——排查估值/评级慢跑

## 背景

估值（valuation）与评级（quality）任务逐股提交 Hermes run，有的股票跑几分钟、有的跑半个多小时，目前只能看到最终 output 和 job 计数，无法知道慢在哪一步（补查轮数太多？terminal 工具慢？token 爆量？），也就没法针对性调整 skill。

调研结论（2026-11-12 实测确认）：

- Hermes 网关自带会话持久化与查询接口，**不需要改 skill、不需要改 Hermes**：
  - `GET /api/sessions/{session_id}` → 会话元数据（message_count / tool_call_count / api_call_count / input/output/cache token 数 / 起止时间）
  - `GET /api/sessions/{session_id}/messages` → 完整逐条消息（role / content / tool_name / timestamp）
  - **`session_id` 就是 `run_id`**（`run_<hex>`），Bearer 鉴权与现有 hermes_client 相同
- `GET /v1/runs/{run_id}` 终态只保留 1 小时且不含会话，不能用
- skill 侧拿不到自身完整 transcript，此路不通

## 需求

1. dividend-select 后端新增代理下载端点（quality / valuation 各一）：
   - `GET /api/dividend/valuation/runs/{run_id}/session`、`GET /api/dividend/quality/runs/{run_id}/session`
   - 后端用现有 HermesConfig 鉴权调上述两个 Hermes 接口，组装为一份可读记录（会话摘要 + 逐条消息，每条带与上条的耗时差），以 attachment 下载
   - 输出 markdown（排查友好）；404 当 Hermes 无此 session
2. run_id 持久化：`_save_one`（valuation）与 `_save_one`（quality）把 `run_id` 写进落盘记录，历史报告也能下载会话；内存 items 里的 run_id 已有（取消功能引入），直接用
3. 前端：
   - `ValuationReportModal` 加「下载会话记录」按钮（有 run_id 时显示）
   - `QualityReportModal` 同样处理
   - 下载失败（404/网络）行内提示，不弹全局错误
4. 运行中的 run 也可以下载（messages 接口对进行中的 session 同样有效），队列面板不加按钮、只在报告弹窗加，避免面板过挤

## 非目标

- 不做会话列表 / 服务端聚合分析界面
- 不改 Hermes 网关与 skill
- 不做 token 用量统计图表

## 验收标准

- [x] 已落盘的历史报告（有 run_id）点击「下载会话记录」得到 markdown 文件，含会话摘要（消息数/工具数/token）与逐条消息及耗时差
- [x] run 不存在 / Hermes 未配置时按钮行内报错，不影响弹窗其它功能（404 / 503 / 502 分别处理）
- [x] 无 run_id 的旧报告不显示按钮（不报错）
- [x] quality 与 valuation 两条链路都可用（共用 `_download_run_session`）
- [x] 后端 pytest 通过（442 passed）；前端 `tsc --noEmit` 通过

## 实施结果（2026-11-12）

- `hermes_client.py`：新增 `get_session` / `get_session_messages`（session_not_found 用 HermesApiError 前缀表达）
- `services/session_export.py`（新）：`build_session_markdown` 组装会话摘要 + 逐条消息（含与上条耗时差、超长工具输出截断标注），quality/valuation 共用
- 两个 service 的 `_save_one` 落盘 `run_id`；路由新增 `GET /{valuation|quality}/runs/{run_id}/session`，markdown attachment 下载，404/502/503 分档
- 前端：`api-client.ts` 新增 `downloadFile`/`saveBlob`；`SessionDownloadButton` 共用组件挂在两个报告弹窗的元数据行（无 run_id 不渲染，失败行内红字）
- 真实验证：通过 nginx 下载历史 run 会话 200，markdown 含 token 统计与 107 条逐条消息
- 测试：端点 5 个用例 + run_id 落盘 + markdown 组装用例，全量 442 passed
