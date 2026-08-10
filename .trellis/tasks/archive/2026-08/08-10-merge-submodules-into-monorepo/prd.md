# 合并 git submodules 为单仓

## Goal

将 personal-web 主仓库的三个 backend git submodule（`dividend-select`、`douyin-processor`、`global-macro-fin`）合并进主仓库代码树，消除子模块维护负担，让所有代码在一个仓库里走单条 git 工作流。

## Background

- 个人项目三个后端都是 ohyes768 名下、由用户独立维护的独立仓库，但合并前实际收益≈0（仅自己维护），反而制造负担：
  - 改一处代码要走"子模块 push → 主仓 bump gitlink → 主仓 push"3 步，顺序错就断链
  - 部署必须 `git submodule update --init --recursive`，漏一步镜像就是旧的（历史踩坑）
  - 跨仓 IDE 跳转/搜索不连贯
- 三个子模块当前 commit（pre-merge 基线）：
  - `backend/dividend-select` @ `4cad20a4`（branch main）
  - `backend/douyin-processor` @ `5b2f25b9`（branch main）
  - `backend/global-macro-fin` @ `e5682efa`（branch master）
- 旧子模块仓库由用户自行删除/归档，本任务**不**做任何 GitHub 端操作（不删远端、不 archive、不迁移 issue）。

## Scope

### In Scope

- `backend/dividend-select/` 目录从 git submodule → 普通目录（含完整 git 历史）
- `backend/douyin-processor/` 目录同上
- `backend/global-macro-fin/` 目录同上
- 删除 `.gitmodules`、`.git/config` 里的 submodule 段、各子模块的 `backend/<x>/.git`（submodule 标记文件）
- 验证三个 backend 各自能本地启动 + docker compose build 成功

### Out of Scope

- **不**改 `apps/` 下任何前端代码
- **不**改 `docker-compose.nas.yml`（路径已对齐，无需改）
- **不**改 nginx / `.env*` 文件
- **不**碰 GitHub 远端：旧仓库的删除/archive 由用户自己处理
- **不**重构后端代码、不改 import、不动业务逻辑（仅做"搬仓库"）

## Requirements

### 功能性

- **R1**：执行 `git subtree add` 把三个子模块的 main/master 分支以 subtree 形式合入 `backend/<x>/`，保留原始 commit 历史
- **R2**：`git submodule status` 输出为空；`cat .gitmodules` 失败（文件已删）
- **R3**：合并后 `backend/<x>/` 下的代码文件**逐字节**等价于合并前对应 submodule 指向 commit 的文件树
- **R4**：合并后三个 backend 各自能 `uvicorn` 起来，主路由响应 200
- **R5**：`docker compose -f docker-compose.nas.yml config` 不报错；`docker compose build --no-cache <backend>` 三个后端 service 全部 build 成功

### 非功能性 / 约束

- **R6**：合并过程**只在主仓本地**，不 push（避免主仓公开可见中途状态）；全部本地验证通过后再一次性 push
- **R7**：保留合并前的 backup tag（如 `pre-submodule-merge-2026-08-10`），便于回滚
- **R8**：合并顺序按代码量从小到大：**douyin-processor → global-macro-fin → dividend-select**（先小后大、出问题影响面小）
- **R9**：token budget 控制——本次 planning 阶段 ≤ 4000 tokens，execute 阶段每个 backend ≤ 2000 tokens

## Acceptance Criteria

- [ ] AC1：执行 `git submodule status` 无任何输出（三个 submodule 全部 unregister）
- [ ] AC2：`.gitmodules` 文件不存在
- [ ] AC3：`backend/<x>/.git`（submodule 标记文件）不存在（普通目录里不该有这个文件）
- [ ] AC4：`backend/dividend-select/`、`backend/douyin-processor/`、`backend/global-macro-fin/` 三个目录各自有完整代码树
- [ ] AC5：合并前的 commit 历史可在 `git log -- backend/<x>/` 中追溯到对应原仓库的 commit
- [ ] AC6：三个 backend 各自能 `python -m uvicorn src.main:app --port <x>` 起来（dividend-select 8092 / douyin-processor 8093 / global-macro-fin 8094），`/health` 端点返回 200
- [ ] AC7：`docker compose -f docker-compose.nas.yml build --no-cache dividend-select-backend douyin-processor-backend global-macro-fin-backend` 全部成功
- [ ] AC8：本地有 backup tag `pre-submodule-merge-2026-08-10`
- [ ] AC9：合并完成后 git status 干净（除 `.trellis/tasks/08-10-merge-submodules-into-monorepo/` 和文档外，无其他未提交改动）
- [ ] AC10：push 主仓远端后，远端 clone + checkout 可正常工作（不依赖任何 submodule 命令）

## Notes

- 本任务**不**自动开始实施，需用户 review prd/design/implement 后 `task.py start`
- 实施阶段建议进入 worktree 隔离（避免污染当前工作树）——见 `design.md`
