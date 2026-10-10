# Implement — 挡位 batch API + token 校验

## 执行顺序

所有改动都在 `backend/dividend-select` 子模块内，最后再回主仓库 bump gitlink。

### Step 1 — Pydantic 模型

**文件**：`backend/dividend-select/src/api/models.py`

**改动**：在现有 `AlertLevel` / `AlertLevels` / `AlertConfigRequest` 之后追加 6 个新模型（见 design.md 第 1 节）。

**验证**：
```bash
cd backend/dividend-select
python -c "from src.api.models import AlertBatchRequest, AlertBatchResponse; print('OK')"
```

**回归检查**：grep `AlertConfigRequest` 调用方，确认未受影响。

### Step 2 — Token 依赖 + Batch 路由

**文件**：`backend/dividend-select/src/api/routes.py`

**改动**：
- 文件顶部 import 加 `secrets`、`os`（如未引入）、`Header`、`Depends`（如未引入）
- 在 `# ========== 挡位监控（alerts）路由 ==========` 段尾（`manually_check_alerts` 之后）追加 `verify_agent_token` 依赖 + `batch_set_alerts` 路由 + `_alert_batch_item_to_dict` helper（见 design.md 第 2 节）

**验证**：
```bash
cd backend/dividend-select
python -c "from src.api.routes import router; print([r.path for r in router.routes if 'batch' in r.path])"
# 应输出 ['/favorites/alerts/batch']
```

**Review gate**：启动 uvicorn 本地调一次（手工 curl）确认路由可发现。

### Step 3 — .env.example 添加环境变量

**文件**：`backend/dividend-select/.env.example`

**改动**：在文件尾追加（见 design.md 第 3 节）：
```
# 外部 agent 调用 batch 接口的鉴权 token（POST /api/dividend/favorites/alerts/batch）
# 留空或未设置 → batch 接口返回 503；外部调用必带 header: X-API-Token: <token>
# 实际部署写入 .env.local（已 .gitignore），不要 commit
AGENT_API_TOKEN=
```

### Step 4 — 单测

**文件**：`backend/dividend-select/tests/test_alerts_batch_api.py`（新建）

**测试 setup**：
- `tmp_path` fixture 创建临时 favorites.json，`FavoritesService.reset_instance()` + 重新 init
- `monkeypatch.setenv("AGENT_API_TOKEN", "test-token")`
- 用 `fastapi.testclient.TestClient` 创建 app（参考已有 `tests/test_alert_service.py` 的 setup 模式）

**用例**（对应 design.md 第 4 节表格）：

```python
def test_batch_happy_path_already_favorite(...)
def test_batch_auto_add_favorite(...)
def test_batch_partial_failure(...)
def test_batch_missing_token_returns_401(...)
def test_batch_wrong_token_returns_401(...)
def test_batch_no_env_token_returns_503(...)
def test_batch_updates_over_limit_returns_422(...)
def test_batch_invalid_price_returns_422(...)
def test_batch_enabled_defaults_true(...)
```

**验证**：
```bash
cd backend/dividend-select
python -m pytest tests/test_alerts_batch_api.py -v
```

**Review gate**：所有用例 PASS；如果有 fail，先排查 fixture 是否正确隔离单例。

### Step 5 — 启动本地服务手工验证

**目的**：单测覆盖逻辑，但启动 + curl 一次验证路由前缀和 OpenAPI 文档正确。

```bash
cd backend/dividend-select
export AGENT_API_TOKEN=test-token
python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8092
```

**curl 验证**（新开 shell）：
```bash
# 1. happy path
curl -X POST http://localhost:8092/api/dividend/favorites/alerts/batch \
  -H "Content-Type: application/json" \
  -H "X-API-Token: test-token" \
  -d '{"updates":[{"code":"600000","levels":{"heavy_position":{"price":10},"add_position":{"price":12},"reduce_position":{"price":15},"full_exit":{"price":18}}}]}'
# 期望: {"results":[{"code":"600000","ok":true}],"success_count":1,"fail_count":0}

# 2. 缺 token → 401
curl -X POST http://localhost:8092/api/dividend/favorites/alerts/batch \
  -H "Content-Type: application/json" \
  -d '{"updates":[{"code":"600000","levels":{...}}]}'
# 期望: {"detail":"invalid or missing X-API-Token"}

# 3. OpenAPI
curl http://localhost:8092/openapi.json | python -c "import sys,json; d=json.load(sys.stdin); print([p for p in d['paths'] if 'batch' in p])"
# 期望: ['/api/dividend/favorites/alerts/batch']
```

**Review gate**：3 个 curl 都符合预期。注意确认路由前缀是 `/api/dividend` 还是根（看 main.py 怎么 include router）。

### Step 6 — 子模块 commit + push

```bash
cd backend/dividend-select
git status
# 确认改动文件：
#   src/api/models.py
#   src/api/routes.py
#   .env.example
#   tests/test_alerts_batch_api.py（新）

git add src/api/models.py src/api/routes.py .env.example tests/test_alerts_batch_api.py
git commit -m "$(cat <<'EOF'
feat(alerts): batch 接口 + token 校验（外部 agent 入口）

- POST /favorites/alerts/batch：一次写多只股票 4 档
- 入参简化：4 档 price 必填，pe/pb/enabled 可选（默认 true/null）
- 未收藏自动加入 favorites 再设挡位
- X-API-Token header 校验（secrets.compare_digest 防 timing attack）
- 单次上限 100 条；per-stock 隔离，部分失败不影响其他
- AGENT_API_TOKEN 未配 → 503；缺/错 token → 401
EOF
)"
git push origin main
```

**Review gate**：push 成功，远端 commit hash 记下来。

### Step 7 — 主仓库 bump gitlink

```bash
cd F:/github/person_project/personal-web
git status
# 应显示: modified: backend/dividend-select (modified content)

git add backend/dividend-select
git commit -m "chore: bump dividend-select (batch alerts API + token)"
git push origin master
```

**Review gate**：主仓库 push 成功，子模块 gitlink 指向新 commit。

## Validation Commands Summary

| Step | 验证命令 | 预期 |
|---|---|---|
| 1 | `python -c "from src.api.models import AlertBatchRequest"` | OK |
| 2 | grep batch in router routes | `['/favorites/alerts/batch']` |
| 4 | `pytest tests/test_alerts_batch_api.py -v` | all PASS |
| 5 | curl happy / 缺 token / OpenAPI | 3 个响应正确 |
| 6 | `git push origin main`（子模块） | 成功 |
| 7 | `git push origin master`（主仓库） | 成功 |

## Rollback Points

- **Step 1-5 前**：未 commit，直接 `git checkout -- <file>` 即可
- **Step 6 后**：子模块已 push，无法撤回；但回滚只需在子模块新建 revert commit + push，再主仓库 bump gitlink
- **Step 7 后**：主仓库 gitlink 已 bump，回滚同上

## Out of Scope

- 前端 agent 调用代码（由 agent 项目自己实现）
- MCP server 包装（按 prd 范围外）
- 现有 PUT/DELETE 路由加 token（前端在用，破坏性改动，本期不做）
- batch 响应里返回 `added` 字段（自动加收藏是否真的新增）——后续可加

## Estimation

- Step 1-3：30 min（机械改动）
- Step 4：1 h（单测是最大头）
- Step 5：15 min（本地启动 + curl）
- Step 6-7：10 min（commit/push）
