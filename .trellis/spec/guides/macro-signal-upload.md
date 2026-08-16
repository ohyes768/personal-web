# Macro Signal Upload API Contract

> **Purpose**: agent 主动推送宏观信号 JSON 到 macro 后端。供 macro-fin-skill 各子 skill 维护者参考。
>
> **Last verified**: 2026-08-15
> **Source files**:
> - `backend/macro/src/api/routes.py` (路由定义)
> - `backend/macro/src/services/macro_signal_service.py` (落盘 + 缓存)
> - `backend/macro/src/config.py` (token / data_dir 配置)

---

## 1. 接口

```
POST https://<host>/api/macro/signal/upload
Header: X-Upload-Token: <token>
Content-Type: application/json
```

- nginx `/api/macro/` → 剥前缀 → 后端 `/api/signal/upload`
- 鉴权：Header `X-Upload-Token`，constant-time 比对 `MACRO_SIGNAL_UPLOAD_TOKEN`
  - **未配置 token** → `401 "upload token 未配置（MACRO_SIGNAL_UPLOAD_TOKEN）"`
  - **token 错误** → `401 "Unauthorized"`

## 2. 请求体

```json
{
  "skill": "monetary-policy-skill",
  "file": "macro_signal.json",
  "data": { /* 该 skill 原始 JSON */ }
}
```

| 字段 | 必填 | 约束 |
|------|------|------|
| `skill` | ✅ | 白名单（见下） |
| `file`  | ✅ | `"macro_signal.json"` 或 `"risk_data.json"` |
| `data`  | ✅ | JSON 对象（dict），不能是 list / string / null |

### 2.1 skill 白名单（6 个）

```
monetary-policy-skill
money-supply-skill
entity-economy-skill
inflation-skill
exchange-rate-skill
risk-appetite-skill
```

### 2.2 file 白名单

| skill 类别 | file |
|-----------|------|
| 5 个「宏观信号类」skill | `macro_signal.json` |
| `risk-appetite-skill`（唯一） | `risk_data.json` |

### 2.3 data 最小结构（后端按此 shape 转换）

**A. macro_signal.json（5 个 skill）**

```json
{
  "conclusion": "偏宽松",
  "data_date": "2026-08-12",
  "details": {
    "dr007": 1.62,
    "mlf_1y": 2.50
  }
}
```

- `data_date` 支持 `YYYY-MM-DD` 或 ISO 时间戳（只取前 10 位）
- `details` 中非数值 key 会被丢弃，不写入 indicators

**B. risk_data.json（risk-appetite-skill）**

```json
{
  "score": { "conclusion": "偏热/乐观" },
  "data": {
    "volume":  { "date": "2026-08-12", "total_amount_yi": 12800 },
    "turnover":{ "date": "2026-08-12", "turnover_rate": 1.35 },
    "margin":  { "date": "2026-08-12", "rzye": 18500 }
  }
}
```

> ⚠️ risk_appetite 结构与其他 5 个不同（嵌套在 `data.*` 下）。混传会读到空指标但不报错。

## 3. 后端处理流程

| 步骤 | 行为 |
|------|------|
| 1 | 校验 token（缺失/错误 → 401） |
| 2 | 校验 `skill`/`file` 白名单（违例 → 400） |
| 3 | 校验 `data` 是 dict（否则 → 400） |
| 4 | 落盘到 `<MACRO_SIGNAL_DATA_DIR>/<skill>/<file>` |
| 5 | **原子写**：临时文件 `.tmp` → `replace`，防止读到半写状态 |
| 6 | `clear_cache()` 清 5 分钟内存缓存，下次 `GET /signal?month=` / `/months` 立即生效 |

## 4. 响应

### 成功（200）

```json
{
  "success": true,
  "skill": "monetary-policy-skill",
  "file": "macro_signal.json",
  "path": "/app/macro_signal_data/monetary-policy-skill/macro_signal.json",
  "bytes": 432
}
```

### 失败

| 状态码 | 触发条件 | detail |
|--------|---------|--------|
| 400 | skill/file 非法 / data 非 dict | `"非法 skill: xxx"` 等 |
| 401 | token 未配置 | `"upload token 未配置（MACRO_SIGNAL_UPLOAD_TOKEN）"` |
| 401 | token 错误 | `"Unauthorized"` |
| 422 | body JSON 解析失败 | FastAPI 默认校验错误 |

## 5. 调用示例

### curl

```bash
curl -X POST https://<host>/api/macro/signal/upload \
  -H "X-Upload-Token: $MACRO_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "skill": "monetary-policy-skill",
    "file": "macro_signal.json",
    "data": {
      "conclusion": "偏宽松",
      "data_date": "2026-08-12",
      "details": {"dr007": 1.62, "mlf_1y": 2.50}
    }
  }'
```

### Python (requests)

```python
import os, requests

TOKEN = os.environ["MACRO_SIGNAL_UPLOAD_TOKEN"]
URL   = "https://<host>/api/macro/signal/upload"

def upload(skill: str, file: str, data: dict):
    r = requests.post(
        URL,
        headers={"X-Upload-Token": TOKEN},
        json={"skill": skill, "file": file, "data": data},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()
```

## 6. 推送后验

| 操作 | 接口 | 说明 |
|------|------|------|
| 看月份是否出现新月份 | `GET /api/macro/months` | 缓存已清，立即生效；返回降序月份列表 |
| 看该月快照 | `GET /api/macro/signal?month=YYYY-MM` | 任一 indicator `updated_at` 落在该月才返回 200，否则 404 |

## 7. skill 端约束

1. **`MACRO_SIGNAL_UPLOAD_TOKEN` 安全**：从 env / secret manager 读，不要硬编码进 skill 代码
2. **`data_date` 必须真实**：后端用它的 `YYYY-MM` 前缀判断「该月是否有数据」，伪造会让前端读到空快照
3. **`details` key 用数字**（macro_signal.json）：字符串 / None 会被丢弃
4. **6 个 skill 都推送**才能让某月完整呈现（任一缺失会缺维度，但不报错）
5. **重推策略**：同名 file 直接覆盖（原子写），可重复推送；幂等由业务层负责，不依赖后端
6. **错误处理**：401 → 检查 token 配置；400 → 检查白名单 / data shape；不要无限重试

## 8. 文件最终落地结构（运维/排查用）

```
$MACRO_SIGNAL_DATA_DIR/
├── monetary-policy-skill/macro_signal.json
├── money-supply-skill/macro_signal.json
├── entity-economy-skill/macro_signal.json
├── inflation-skill/macro_signal.json
├── exchange-rate-skill/macro_signal.json
└── risk-appetite-skill/risk_data.json
```

> 默认开发路径 `F:/personal-projects/macro-fin-skill/skills`（`backend/macro/src/config.py:110`），生产由环境变量覆盖。