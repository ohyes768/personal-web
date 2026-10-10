# Design — 挡位 batch API + token 校验

## Architecture

复用现有 `FavoritesService` 单例（幂等 `add` + 覆盖式 `update_alerts`），新增一条路由 + 一个 token 依赖 + 一组 Pydantic 模型。零存储层改动，零现有路由改动。

```
External Agent
   │  POST /api/dividend/favorites/alerts/batch
   │  Header: X-API-Token: <token>
   ▼
[verify_agent_token dependency]  ← 读 AGENT_API_TOKEN env，secrets.compare_digest
   │
   ▼
[route handler]
   │  for each update in body.updates:
   │    1. _normalize_code(code)              # ValueError → 该条 fail
   │    2. FavoritesService.add(code)          # 自动加收藏（幂等）
   │    3. FavoritesService.update_alerts(code, alerts_dict)
   │       内部 _alert_config_to_dict 转换 Pydantic → dict
   │    4. 收集 {code, ok, error?}
   ▼
AlertBatchResponse
```

## Module Changes

### 1. `src/api/models.py` — 新增 Pydantic 模型

```python
class AlertBatchLevelInput(BaseModel):
    """单档输入：price 必填，pe/pb 可选"""
    price: float = Field(..., gt=0, description="档位价格（必填，>0）")
    pe: Optional[float] = Field(None, description="该档 PE（选填）")
    pb: Optional[float] = Field(None, description="该档 PB（选填）")

class AlertBatchLevelsInput(BaseModel):
    """4 档输入：每档独立可带 pe/pb"""
    heavy_position: AlertBatchLevelInput
    add_position: AlertBatchLevelInput
    reduce_position: AlertBatchLevelInput
    full_exit: AlertBatchLevelInput

class AlertBatchUpdateItem(BaseModel):
    """batch 单条"""
    code: str = Field(..., min_length=1, max_length=6, description="6 位股票代码")
    levels: AlertBatchLevelsInput
    enabled: bool = Field(True, description="是否启用监控，默认 true")

class AlertBatchRequest(BaseModel):
    """batch 请求体"""
    updates: list[AlertBatchUpdateItem] = Field(..., min_length=1, max_length=100)

class AlertBatchResultItem(BaseModel):
    """batch 单条结果"""
    code: str
    ok: bool
    error: Optional[str] = None

class AlertBatchResponse(BaseModel):
    """batch 响应"""
    results: list[AlertBatchResultItem]
    success_count: int
    fail_count: int
```

**为什么 price 用 `gt=0` 而不是 `ge=0`**：和现有 `AlertConfigRequest.levels[*].price` 校验对齐——后者在路由层用 `lv.price is None` 检查，batch 这边用 Pydantic 直接拒掉 0 和负数。

**为什么 not reuse `AlertConfigRequest`**：现有 AlertConfigRequest 的 levels 字段允许 None（未设置档），batch 不允许（4 档全必填）。语义不同，新建一组更清晰。

### 2. `src/api/routes.py` — 新增 token 依赖 + batch 路由

**位置**：紧跟现有 `# ========== 挡位监控（alerts）路由 ==========` 段尾，在 `manually_check_alerts` 之后。

```python
import secrets

async def verify_agent_token(x_api_token: str = Header(..., alias="X-API-Token")):
    """
    Agent API token 校验依赖。
    - 未配置 AGENT_API_TOKEN 环境变量 → 503
    - token 不匹配 → 401
    - 用 secrets.compare_digest 防 timing attack
    """
    expected = os.getenv("AGENT_API_TOKEN", "").strip()
    if not expected:
        raise HTTPException(503, "服务端未配置 AGENT_API_TOKEN")
    if not x_api_token or not secrets.compare_digest(x_api_token, expected):
        raise HTTPException(401, "invalid or missing X-API-Token")


@router.post("/favorites/alerts/batch", response_model=AlertBatchResponse)
async def batch_set_alerts(
    body: AlertBatchRequest,
    _: None = Depends(verify_agent_token),
):
    """
    批量设置挡位监控（外部 agent 入口）

    - 每条独立处理，部分失败不影响其他
    - 未收藏的 code 自动加入 favorites 再设挡位
    - 4 档 price 必填 > 0；pe/pb/enabled 可选
    """
    if favorites_service is None:
        raise HTTPException(500, "收藏服务未初始化")

    results: list[AlertBatchResultItem] = []
    for item in body.updates:
        try:
            alerts_dict = _alert_batch_item_to_dict(item)
            # 自动加收藏（幂等：已存在不重复加）
            if not favorites_service.has(item.code):
                favorites_service.add(item.code)
            favorites_service.update_alerts(item.code, alerts_dict)
            results.append(AlertBatchResultItem(code=item.code, ok=True))
        except ValueError as e:
            results.append(AlertBatchResultItem(code=item.code, ok=False, error=str(e)))
        except KeyError as e:
            # 理论上 unreachable（add 之后必然在收藏中），保留兜底
            results.append(AlertBatchResultItem(code=item.code, ok=False, error=str(e)))
        except Exception as e:
            logger.exception(f"[batch_set_alerts] code={item.code} unexpected error")
            results.append(AlertBatchResultItem(code=item.code, ok=False, error=f"unexpected: {e}"))

    return AlertBatchResponse(
        results=results,
        success_count=sum(1 for r in results if r.ok),
        fail_count=sum(1 for r in results if not r.ok),
    )


def _alert_batch_item_to_dict(item: AlertBatchUpdateItem) -> dict:
    """
    batch 单条 → favorites.json alerts dict（结构对齐现有 _alert_config_to_dict）
    复用 level key 顺序，保证 favorites.json 字段顺序一致
    """
    levels_dict: dict[str, dict] = {}
    for key in ("heavy_position", "add_position", "reduce_position", "full_exit"):
        lv: AlertBatchLevelInput = getattr(item.levels, key)
        d: dict = {"price": float(lv.price)}
        if lv.pe is not None:
            d["pe"] = float(lv.pe)
        if lv.pb is not None:
            d["pb"] = float(lv.pb)
        levels_dict[key] = d
    return {
        "enabled": item.enabled,
        "updated_at": datetime.now().isoformat(),
        "levels": levels_dict,
    }
```

**为什么 `_alert_batch_item_to_dict` 不复用 `_alert_config_to_dict`**：batch 的 4 档全部必填（无 None 分支），逻辑更简单；复用反而要塞 None 检查。两边输出 schema 完全一致。

**为什么自动加收藏用 `has + add` 而不是直接 `add`**：`add` 内部对已存在的 code 也会走一次 `_save()`（写盘），N 条已有收藏会触发 N 次原子写。先 `has` 判断避免无谓写盘。注意：`has` 和 `add` 各自加锁，存在 TOCTOU 但单进程 + 单 agent 调用场景无害。

### 3. `.env.example` — 添加环境变量

```bash
# 外部 agent 调用 batch 接口的鉴权 token（POST /api/dividend/favorites/alerts/batch）
# 留空或未设置 → batch 接口返回 503；外部调用必带 header: X-API-Token: <token>
# 实际部署写入 .env.local（已 .gitignore），不要 commit
AGENT_API_TOKEN=
```

### 4. `tests/test_alerts_batch_api.py` — 新增单测

用 `TestClient` + 临时 favorites.json（`tmp_path` fixture）。覆盖：

| 用例 | 输入 | 预期 |
|---|---|---|
| happy 已收藏 | code 已在 favorites，token 对，4 档全 | ok=true，挡位写入 |
| happy 未收藏 | code 不在 favorites | 自动加入 + ok=true |
| 部分失败 | 1 条 code 非法 + 1 条 code 合法 | 1 fail + 1 ok |
| 缺 token | 不带 X-API-Token | 401 |
| 错 token | X-API-Token: wrong | 401 |
| 未配 AGENT_API_TOKEN | env 未设 | 503 |
| 超限 | updates 101 条 | 422（Pydantic） |
| price ≤ 0 | price=0 或 -1 | 该条 422 在请求层直接拒掉 |
| enabled 默认 true | 不传 enabled | favorites.json 里 enabled=true |

## Data Flow

```
POST body ──► Pydantic AlertBatchRequest (422 if invalid)
          │
          ▼
      verify_agent_token (401/503 if fail)
          │
          ▼
   ┌──────────────────────────────────────┐
   │  for each item in updates:           │
   │    has(code)? ──no──► add(code)      │
   │       yes                            │
   │       │                              │
   │       ▼                              │
   │    update_alerts(code, alerts_dict)  │
   │       │                              │
   │       ▼                              │
   │    results.append({ok})              │
   └──────────────────────────────────────┘
          │
          ▼
   AlertBatchResponse (200, 部分失败也算 200)
```

## Contracts

### 请求

```http
POST /api/dividend/favorites/alerts/batch HTTP/1.1
Content-Type: application/json
X-API-Token: <token>

{
  "updates": [
    {
      "code": "600000",
      "levels": {
        "heavy_position":  {"price": 10.0, "pe": 8.5, "pb": 1.2},
        "add_position":    {"price": 12.0},
        "reduce_position": {"price": 15.0},
        "full_exit":       {"price": 18.0}
      }
    },
    {
      "code": "000001",
      "levels": {
        "heavy_position":  {"price": 11.0},
        "add_position":    {"price": 13.0},
        "reduce_position": {"price": 16.0},
        "full_exit":       {"price": 19.0}
      },
      "enabled": false
    }
  ]
}
```

### 响应（200，部分失败也是 200）

```json
{
  "results": [
    {"code": "600000", "ok": true},
    {"code": "000001", "ok": true}
  ],
  "success_count": 2,
  "fail_count": 0
}
```

### 错误码

| HTTP | 场景 | body |
|---|---|---|
| 200 | 部分或全部成功 | `AlertBatchResponse` |
| 401 | 缺/错 token | `{"detail": "..."}` |
| 422 | body 校验失败（updates 空 / >100 / price ≤ 0 等） | FastAPI 默认 |
| 500 | favorites_service 未初始化 | `{"detail": "收藏服务未初始化"}` |
| 503 | 服务端未配 token | `{"detail": "服务端未配置 AGENT_API_TOKEN"}` |

## Compatibility / Rollout

- **前端零影响**：现有 PUT/DELETE/GET 路由完全不动；前端不带 token，不调 batch
- **后端零破坏**：复用 FavoritesService 现有方法（`has/add/update_alerts`），不改 schema
- **配置向后兼容**：`AGENT_API_TOKEN` 未设时 batch 路由 503，不影响其他路由
- **回滚**：删除新增路由 + 模型 + token 依赖 + .env.example 条目；favorites.json 数据保留

## Naming Conventions

- 路由：`/favorites/alerts/batch` —— 和现有 `/favorites/alerts/status`、`/favorites/alerts/check` 命名对齐
- 模型前缀：`AlertBatch*` —— 和现有 `Alert*` 区分
- 函数：`batch_set_alerts` —— 和现有 `set_favorite_alerts` 对称
- Token header：`X-API-Token` —— 标准命名，无定制
