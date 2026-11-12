# 设计：Hermes 会话记录打包下载

## 数据来源（已实测）

- `GET {HERMES_BASE_URL}/api/sessions/{run_id}`（Bearer HERMES_API_KEY）
  → `{session: {id, model, started_at, ended_at, message_count, tool_call_count, api_call_count, input_tokens, output_tokens, cache_read_tokens, ...}}`
- `GET {HERMES_BASE_URL}/api/sessions/{run_id}/messages`
  → `{data: [{id, role, content, tool_name, tool_calls, timestamp, ...}]}`
- session_id 与 run_id 同值；messages 对进行中 session 同样可查
- hermes_client.py 不动——这两个接口与 runs API 同 base/key，直接在服务层用 requests 调（复用 HTTP_TIMEOUT / 鉴权头模式）

## 后端

### hermes_client.py 新增

```python
def get_session(cfg, session_id) -> dict        # 404 → HermesApiError("session 不存在")
def get_session_messages(cfg, session_id) -> list  # 返回 data 数组
```

### services/session_export.py（新文件，quality/valuation 共用）

`build_session_markdown(cfg, run_id) -> str`：
1. 调 get_session + get_session_messages
2. 头部：run_id、模型、起止时间、消息/工具/API 调用数、token 四项
3. 逐条消息：`## #n [MM-DD HH:MM:SS (+Δs)] role (tool_name)`，content 原文放进代码围栏；assistant 文本直接输出；超长 tool output（>4000 字符）截断并标注总长
4. 路由层以 `Response(content, media_type="text/markdown", headers={"Content-Disposition": f"attachment; filename=hermes-{run_id}-session.md"})` 返回

### run_id 落盘

- `valuation_service._save_one`：record 增加 `run_id: item.get("run_id")`
- `quality_service._save_one`：同上
- 旧记录无该键 → 前端不显示按钮

### 路由

- `GET /valuation/runs/{run_id}/session`、`GET /quality/runs/{run_id}/session`
- Hermes 未配置 503；Hermes 404 → 404 detail=「Hermes 无此会话记录」；网络错误 502

## 前端

- api.ts：`downloadValuationSession(code)` / `downloadQualitySession(code)`——不能走 directClient JSON 解析，需要 blob 下载（看 directClient 是否支持；不支持就新建轻量 fetch，带 credentials 同源）
- ValuationReportModal / QualityReportModal：元数据行加「下载会话记录」链接按钮，仅 `report.run_id` 存在时显示；点击后按钮态「生成中…」，失败行内红字
- 类型：`ValuationReportRecord` / `QualityScore` 加 `run_id?: string | null`

## 测试

- test_hermes_client：get_session / get_session_messages 打桩 requests
- test_valuation_api / test_quality_api：新端点打桩 get_session 双函数，200 markdown / 404 / 503
- test_valuation_service：落盘记录含 run_id
