# Implement — global-macro-fin /api/macro/signal

执行顺序:config → models → service → routes → docs → 验证 → commit。

## Phase A: 配置与模型

- [ ] A1 修改 `backend/global-macro-fin/src/config.py`
  - 加 `macro_signal_data_dir: str = "F:/personal-projects/macro-fin-skill/skills"` 字段
  - Pydantic Settings 自动从 `MACRO_SIGNAL_DATA_DIR` 环境变量读取
  - validate: `python -c "from src.config import get_settings; print(get_settings().macro_signal_data_dir)"` 通过

- [ ] A2 修改 `backend/global-macro-fin/src/models.py`
  - 在文件末尾追加 `MacroIndicator`、`MacroSignalGroup`、`MacroSignalSnapshot`、`MacroSignalResponse`、`MacroMonthsResponse`、`ErrorResponse`(参考 design §3)
  - validate: `python -c "from src.models import MacroSignalSnapshot; print(MacroSignalSnapshot.model_fields)"` 通过

## Phase B: Service

- [ ] B1 创建 `backend/global-macro-fin/src/services/macro_signal_service.py`
  - 完整实现 `MacroSignalService` 类 + `get_macro_signal_service()` 单例工厂
  - 内容按 design §5
  - 容错:每个 `_read_json` 返回 `None` 时对应维度返回空 group,不抛异常
  - validate: 单元自测
    ```python
    from src.services.macro_signal_service import get_macro_signal_service
    svc = get_macro_signal_service()
    snap = svc.get_snapshot('2026-05')
    assert snap is not None
    assert len(snap.groups) == 6
    assert snap.groups['monetary_policy'].conclusion == '偏宽松'
    months = svc.get_available_months()
    assert '2026-05' in months
    ```

## Phase C: 路由

- [ ] C1 修改 `backend/global-macro-fin/src/api/routes.py`
  - 顶部 import 区域加:
    ```python
    from src.services.macro_signal_service import get_macro_signal_service
    from src.models import MacroSignalResponse, MacroSignalSnapshot, MacroMonthsResponse
    ```
  - 文件末尾追加 2 个 `@router.get` 接口(参考 design §6)
  - validate: `python -c "from src.api.routes import router; print([r.path for r in router.routes if 'macro' in r.path])"` 看到 `/macro/signal` 和 `/macro/months`

## Phase D: 接口文档

- [ ] D1 创建 `backend/global-macro-fin/docs/MACRO_SIGNAL_API.md`
  - 完整列出 2 个接口的:
    - 请求示例(curl + 响应 JSON)
    - 字段表(类型 + 含义)
    - 错误码(404 / 500 + 触发条件)
    - **agent 实施指南**:如何更新 macro-fin-skill 的 JSON 让前端拿到最新数据;缓存策略(5 分钟)
    - 数据源路径配置(`MACRO_SIGNAL_DATA_DIR` 环境变量)
  - validate: 文档至少包含 2 个接口的完整示例

## Phase E: 端到端验证

- [ ] E1 启动后端:
  ```bash
  cd backend/global-macro-fin
  ./.venv/bin/uvicorn src.main:app --reload --host 0.0.0.0 --port 8094
  ```
  期望无 import 错误

- [ ] E2 curl 测试 3 个接口:
  ```bash
  curl http://localhost:8094/api/macro/signal?month=2026-05 | jq
  curl http://localhost:8094/api/macro/signal?month=2024-01
  curl http://localhost:8094/api/macro/months | jq
  ```
  期望:第一个返回完整 6 维度;第二个返回 404;第三个返回 `{"months":["2026-05"]}`

- [ ] E3 前端集成验证:
  ```bash
  cd apps/economic && pnpm dev  # 端口 3001
  # 浏览器 http://localhost:3001/modules/economic
  # 切到「宏观信号」Tab
  ```
  期望:卡片数据来自真实接口(不再是 mock);改 mock 数据中的某个 indicator value,重启后端,等 5 分钟缓存过期后,刷新前端页面看到变化

## Phase F: 子模块 commit + 主仓库 gitlink 更新

- [ ] F1 在 `backend/global-macro-fin` 子模块内:
  ```bash
  git checkout -b feat/macro-signal-api
  git add src/config.py src/models.py src/api/routes.py src/services/macro_signal_service.py docs/MACRO_SIGNAL_API.md
  git commit -m "feat(macro-signal): 加 /api/macro/signal + /api/macro/months 接口

  读 macro-fin-skill 输出的 6 个 macro_signal.json + risk_data.json,
  聚合成前端 MacroSignalSnapshot shape。

  - 新增 src/services/macro_signal_service.py(读 JSON + 5min 缓存)
  - 加 2 个 GET 路由到 src/api/routes.py
  - Pydantic 模型加到 src/models.py
  - 配置项 macro_signal_data_dir(默认 F:/personal-projects/macro-fin-skill/skills)
  - 文档 docs/MACRO_SIGNAL_API.md

  Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"

  git push -u origin feat/macro-signal-api
  ```

- [ ] F2 回到主仓库:
  ```bash
  cd ../..  # 个人 web 主仓库
  git add backend/global-macro-fin
  git commit -m "chore: bump global-macro-fin pointer

  + 新增 /api/macro/signal + /api/macro/months 接口
  + docs/MACRO_SIGNAL_API.md

  Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
  git push origin master
  ```

## 回滚

每个 Phase 是独立 commit。Phase F 之前任何 Phase 失败,只 revert 该文件改动。Phase F 之后整体回滚:
```bash
cd backend/global-macro-fin
git revert HEAD  # 或 git reset --hard HEAD~1
cd ../..
git add backend/global-macro-fin
git commit --amend --no-edit
```

## 评审 Gate(Phase 1.4)

启动任务前(执行 task.py start)需要用户确认:
- [ ] prd.md 范围与验收条款无异议
- [ ] design.md 接口契约(MacroSignalSnapshot shape 对齐前端 types.ts)无异议
- [ ] implement.md 6 个 Phase 顺序无异议

确认后 task.py start 进入实现。