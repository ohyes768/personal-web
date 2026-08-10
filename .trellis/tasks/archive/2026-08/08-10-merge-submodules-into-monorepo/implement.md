# Implement — 合并 git submodules 为单仓

## 顺序总览

```
Step 0  prep  → 备份 tag + 切 worktree 隔离
Step 1  merge douyin-processor（最小，验证流程）
Step 2  merge global-macro-fin（注意 master 分支）
Step 3  merge dividend-select（最大最复杂）
Step 4  cleanup → 删 .gitmodules + 各 .git 标记文件
Step 5  verify → 三个 backend uvicorn 起 + docker compose build
Step 6  finalize → commit + 暂不 push（等用户确认）
```

每个 backend 合并步骤相同，但参数不同。

## Step 0: 预备

```bash
cd /f/github/person_project/personal-web

# 0.1 确认当前干净（除 .trellis/tasks/08-10-decouple-price-m120/ 外）
git status --short
# 预期：只有 ?? .trellis/tasks/08-10-decouple-price-m120/（用户旧 task 的 untracked）

# 0.2 打 backup tag
git tag pre-submodule-merge-2026-08-10
git tag -l 'pre-submodule-merge*'   # 验证

# 0.3 验证 SSH 通
ssh -T git@github.com
# 预期：Hi ohyes768! You've successfully authenticated...
```

**verify**: backup tag 存在 + SSH 通

## Step 1: 合并 douyin-processor

```bash
git subtree add --prefix=backend/douyin-processor \
    git@github.com:ohyes768/douyin-processor.git main
```

**verify**:
```bash
git log --oneline -5 -- backend/douyin-processor/   # 看到原仓库 commit
ls backend/douyin-processor/ | head -20             # 看到 src/ 等文件
test ! -f backend/douyin-processor/.git             # 标记文件已消失
```

**回滚**:
```bash
git reset --hard pre-submodule-merge-2026-08-10
```

## Step 2: 合并 global-macro-fin

注意：此仓库默认分支是 **master**，subtree add 必须显式指定（默认是 main）。

```bash
git subtree add --prefix=backend/global-macro-fin \
    git@github.com:ohyes768/global-macro-fin.git master
```

**verify**:
```bash
git log --oneline -5 -- backend/global-macro-fin/
ls backend/global-macro-fin/
test ! -f backend/global-macro-fin/.git
```

## Step 3: 合并 dividend-select

```bash
git subtree add --prefix=backend/dividend-select \
    git@github.com:ohyes768/dividend-select.git main
```

**verify**:
```bash
git log --oneline -5 -- backend/dividend-select/
ls backend/dividend-select/
test ! -f backend/dividend-select/.git
git -C backend/dividend-select log --oneline -3   # 还能用 git -C 看历史
```

## Step 4: cleanup

```bash
# 4.1 删 .gitmodules
git rm .gitmodules

# 4.2 删各 submodule 的 .git 标记（subtree add 后通常已自动消失，但保险起见）
for x in dividend-select douyin-processor global-macro-fin; do
    test -f backend/$x/.git && rm backend/$x/.git && echo "removed backend/$x/.git"
done

# 4.3 清掉 .git/config 里残留的 submodule section（如果有）
git config -f .git/config --remove-section submodule.backend/douyin-processor 2>/dev/null
git config -f .git/config --remove-section submodule.backend/global-macro-fin 2>/dev/null
git config -f .git/config --remove-section submodule.backend/dividend-select 2>/dev/null

# 4.4 删 .git/modules/（submodule 元数据目录）
rm -rf .git/modules/

# 4.5 确认
git submodule status    # 预期：无输出
```

**verify**:
```bash
test ! -f .gitmodules && echo "OK .gitmodules deleted"
git submodule status
test ! -d .git/modules && echo "OK .git/modules deleted"
```

## Step 5: 验证三个 backend

### 5.1 uvicorn 启动（每个 backend 单独验）

```bash
# dividend-select
cd backend/dividend-select
python -m uvicorn src.main:app --port 8092 &
sleep 5
curl -s http://localhost:8092/health   # 或 /docs 看是否能响应
# Ctrl+C

# douyin-processor
cd ../douyin-processor
python -m uvicorn src.server.main:app --port 8093 &
sleep 5
curl -s http://localhost:8093/health

# global-macro-fin
cd ../global-macro-fin
./.venv/bin/uvicorn src.main:app --port 8094 &
sleep 5
curl -s http://localhost:8094/health
```

### 5.2 docker compose build（dry-run）

```bash
cd /f/github/person_project/personal-web
docker compose -f docker-compose.nas.yml config > /dev/null && echo "OK compose config"
docker compose -f docker-compose.nas.yml build --no-cache dividend-select-backend douyin-processor-backend global-macro-fin-backend
```

**verify**: 三个后端 build 都成功 + uvicorn 起来 + `/health` 200

## Step 6: finalize

```bash
cd /f/github/person_project/personal-web

# 6.1 暂存所有改动
git add -A
git status

# 6.2 commit
git commit -m "chore: merge 3 backend submodules into main repo

- backend/dividend-select (4cad20a4, branch main)
- backend/douyin-processor (5b2f25b9, branch main)
- backend/global-macro-fin (e5682efa, branch master)

Removed .gitmodules + submodule metadata. Backend directories are now
regular tracked directories. Build context paths unchanged.

Backup tag: pre-submodule-merge-2026-08-10
User to delete GitHub-side old repos independently."

# 6.3 不 push（等用户 review）
git log --oneline -5
```

**verify**: commit 干净 + log 看到子树 merge commit + 工作区无 untracked

## Rollback 总览

| 触发条件 | 操作 |
|---------|------|
| subtree add 失败（SSH / 网络） | `git reset --hard pre-submodule-merge-2026-08-10` 重试 |
| 某个 backend 合并后 uvicorn 起不来 | reset 后重新 add，或单独 debug 该 backend（最小化回滚面） |
| docker compose build 失败 | 检查 `docker-compose.nas.yml` 的 build context 路径（应不需要改） |
| commit 后想反悔 | `git reset --hard HEAD~1` 撤销 commit（但保留 backup tag） |

## Review Gates

每个 Step 完成后做一次轻量 review：

| Gate | 检查项 |
|------|--------|
| Step 1 完成 | `git log -- backend/douyin-processor/ \| head` 显示历史；目录有 src/ |
| Step 2 完成 | 同上，注意 master 分支 |
| Step 3 完成 | 同上；dividend-select 体量大，多看几个文件确认 |
| Step 4 完成 | `git submodule status` 空；`.gitmodules` 不存在 |
| Step 5 完成 | 三个 uvicorn 起得来；docker build 成功 |
| Step 6 完成 | commit 干净；backup tag 仍在；git log 清晰 |

## Token Budget 控制

- Step 1-3（subtree add）：每个 ≤ 300 tokens（命令固定）
- Step 4-5（cleanup + verify）：≤ 800 tokens
- Step 6（commit）：≤ 200 tokens
- **总预算**：≤ 2500 tokens（远低于 4000 上限）
