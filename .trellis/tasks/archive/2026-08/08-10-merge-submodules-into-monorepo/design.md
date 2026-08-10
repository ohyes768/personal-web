# Design — 合并 git submodules 为单仓

## 技术方案

使用 `git subtree add` 将三个子模块以 subtree 形式合入主仓。这种方式相比直接复制代码 + 单个 squash commit 的优势是**完整保留子模块的历史**，将来要追溯某段代码"为什么这么写"时不丢上下文。

### 选型对比

| 维度 | subtree add（选） | 直接拷贝 + squash | rm .gitmodules + 保留 gitlink |
|------|--------------------|-------------------|------------------------------|
| 历史 | 完整 | 仅 squash commit | 仍指向原 commit hash，但目录里无代码 |
| 体积 | 略大（历史带入） | 小 | 不变 |
| 实施 | 中等（命令复杂） | 最简单 | 无效 |
| 兼容旧仓库 | 历史可查 | 历史全丢 | 旧仓库删除后断链 |

**选 subtree add**，理由：用户明确要求"历史处理选项 1"。

## 关键技术点

### 1. subtree vs submodule

submodule 的特点是 `.gitmodules` + `.git/modules/<x>/` + 工作区的 `backend/<x>/.git` 文件。subtree add 后这些标记全部消失，`backend/<x>/` 变成主仓的普通目录。语法：

```bash
git subtree add --prefix=backend/douyin-processor \
    git@github.com:ohyes768/douyin-processor.git main \
    --squash  # 可选：squash 成单个 merge commit
```

注意：用户要求"保留完整历史"，**不**加 `--squash`，让每个原 commit 都能在 `git log -- backend/<x>/` 中看到。

### 2. SSH 远端处理

三个子模块用 SSH URL（`git@github.com:ohyes768/...`），subtree add 沿用相同远端即可。但合并后这些远端不再需要（仓库已合并进来）。**不**主动清理——保留作为冗余信息也无害（git remote list 不影响日常）。

### 3. 路径不变

合并前 `backend/<x>/` 是 submodule path，合并后仍是同名目录。零冲击到：
- `docker-compose.nas.yml` 的 `build.context: ./backend/<x>`
- nginx 的 `proxy_pass`（基于路径，无关目录类型）
- 前端 `BACKEND_URL` 环境变量（拼路径）
- 个人 IDE 索引、调试脚本

### 4. 合并顺序

按代码量从小到大：**douyin-processor → global-macro-fin → dividend-select**。
- 第一个跑通 = 验证流程可行
- dividend-select 最大且最复杂，留到最后减少返工成本

### 5. global-macro-fin 用 master 分支

注意此仓库默认分支是 `master`（其他两个是 `main`），subtree add 命令需相应指定 `--branch master`（默认是 main，不指定会失败）。

### 6. 实施隔离

进入 git worktree 隔离，避免污染当前工作树（用户当前 active task `decouple-price-m120` 也在改代码）。worktree 路径建议：

```
.f:\github\person_project\personal-web-worktrees\merge-submodules\
```

回退方案：如果 worktree 在 Windows 上有兼容问题，回到主仓直接做（操作仍是本地，未 push 前都能 `git reset --hard` 回滚）。

## 边界与契约

### 数据流 / 契约

无新接口、无新代码逻辑。纯仓库结构变更。

### 兼容性

- **前端**：零影响（路径不变）
- **docker compose**：零影响（context path 不变）
- **CI/CD**：若 GitHub Actions 用了 `submodule` 相关关键字需要 review；本项目无 CI 文件，零影响
- **NAS 部署**：零影响（部署脚本按路径工作）

### 已知风险

1. **git 体积膨胀**：subtree add 带历史，主仓体积会显著变大（三个仓库历史加起来可能 +50-200MB）。可通过 `git gc` 缓解，但**不**是阻塞项
2. **冲突风险**：理论上 `backend/<x>/` 当前在主仓是空目录（仅含 `.git` 标记文件），subtree add 不会冲突。但若用户本地有未提交改动，需先 stash
3. **Windows + SSH**：subtree add 走 SSH 拉取，Windows 用户需确保 SSH key 已配置且 `ssh -T git@github.com` 可通。若 SSH 失败，subtree add 会立即报错（不会半成功）
4. **active task 冲突**：用户当前有 in_progress task `08-10-decouple-price-m120`，本任务建议先 finish 那个（或至少 commit + 暂停），避免 worktree 与主仓状态混乱

## 回滚策略

1. **未 push 前**：本地 `git reset --hard pre-submodule-merge-2026-08-10` 即可（保留 backup tag 是关键）
2. **已 push 后**：
   - 主仓 `git revert <merge-commit-hash>`（subtree add 产生的 merge commit 可整体 revert）
   - 恢复 `.gitmodules` 文件 + 各 submodule 的 gitlink
   - 用户重新跑 `git submodule update --init --recursive`

## 实施后状态

合并完成后，主仓结构：

```
personal-web/
├── apps/
│   ├── dividend/
│   ├── douyin/
│   ├── economic/
│   └── news/
├── backend/                          # 不再是 submodule
│   ├── dividend-select/              # 普通目录，含 .py / .csv / Dockerfile 等
│   ├── douyin-processor/
│   └── global-macro-fin/
├── scripts/
├── docker-compose.nas.yml
└── .gitmodules                       # 不存在
```

工作流从"3 步 push + 4 步部署"变成"1 步 push + 1 步部署"。
