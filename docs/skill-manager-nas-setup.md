# skill-manager NAS 部署指南

Skill 发布管理台（`apps/skill-manager` 前端 + `backend/skill-manager` 后端）在 NAS 上的部署与回滚说明。架构与安全边界见任务设计文档：后端是唯一允许执行 Git、扫描与 symlink 发布的组件；前端不持有任何管理密码。

## 前置条件

### 1. 克隆 Skills 源库

```bash
git clone https://github.com/ohyes768/skills.git ~/skills
```

管理台把 `${SKILLS_SOURCE_ROOT}/registry.json` 作为登记真源。若开放注册表推送（见第 4 步），该 clone 需具备对 `ohyes768/skills` 的写权限。

### 2. 创建缓存与状态目录

```bash
mkdir -p ~/skill-manager/github-cache ~/skill-manager/state
```

目录属主须为运行 `docker compose` 的用户（后端容器以该 uid 通过 bind mount 读写）。`OPENCLAW_SKILLS_HOST_PATH` 与 `HERMES_SKILLS_HOST_PATH` 指向 NAS 上 OpenClaw / Hermes 实际生效的技能目录，须真实存在：

```bash
mkdir -p ~/openclaw/skills ~/hermes/skills   # 按实际部署路径调整
```

### 3. 在 .env 中填写变量（.env 已被 .gitignore 忽略，勿提交）

| 变量 | 含义 |
|---|---|
| `SKILLS_SOURCE_HOST_PATH` | NAS 上 `ohyes768/skills` clone 的绝对路径 |
| `GITHUB_SKILL_CACHE_HOST_PATH` | GitHub 仓库缓存目录的绝对路径 |
| `OPENCLAW_SKILLS_HOST_PATH` | OpenClaw 生效技能目录的绝对路径 |
| `HERMES_SKILLS_HOST_PATH` | Hermes 生效技能目录的绝对路径 |
| `SKILL_MANAGER_ADMIN_PASSWORD` | 管理密码。发布/下架/回滚/登记时在确认窗口输入；缺失时 compose 拒绝启动后端 |

四个 `*_HOST_PATH` 会以读写方式 bind mount 进后端容器的固定容器路径（`/mnt/skills-source`、`/mnt/github-skill-cache`、`/mnt/targets/openclaw`、`/mnt/targets/hermes`），后端不会收到宿主机路径本身。除此之外后端没有其他挂载，也没有 docker.sock。

### 4.（可选）Skills 仓库写凭据

登记 GitHub Skill 时管理台会把 `registry.json` 的变更 commit 到 Skills 源库；是否 push 取决于源库 clone 自身的凭据（如已配置的 credential helper 或 deploy key）。不配置写凭据时，登记仍可用，但变更只保留在 NAS 本地 commit，审计中标记"待推送"。

## 部署

```bash
./scripts/deploy-nas.sh skill-manager both --no-pull   # 或不加 --no-pull 先 git pull
./scripts/deploy-nas.sh nginx                          # 下发 /skills 与 /api/skills 路由并 reload
```

## NAS 上线验证清单

按顺序执行；前五步只读不写，最后一步用真实发布验证 symlink 链路。

### 1. 部署后端与前端

```bash
./scripts/deploy-nas.sh skill-manager both --no-pull   # 或去掉 --no-pull 先拉取镜像
```

### 2. 后端健康检查

```bash
curl -fsS http://127.0.0.1:8097/api/health    # 期望 {"status":"ok"}
```

### 3. Nginx 配置校验并下发路由

```bash
docker run --rm -v "${PWD}/nginx/web.conf:/etc/nginx/conf.d/web.conf:ro" nginx nginx -t
./scripts/deploy-nas.sh nginx                 # 下发 /skills 与 /api/skills 路由并 reload
```

### 4. 页面可达

浏览器打开 `https://<NAS 地址>:9443/skills/`，双栏工作台应正常渲染，左栏能看到注册表中的 Skill。

### 5. 计划预览不改文件系统

在界面上把任一 Skill 加入右栏并执行"发布计划"预览；随后在 NAS 上确认目标目录未新增任何条目（预览是只读操作）：

```bash
ls -la "$OPENCLAW_SKILLS_HOST_PATH"           # 应无新增链接
```

### 6. 一次真实发布（测试目录）

建议先指向一个临时目标目录做冒烟验证，再切换到真实 Agent 目录：

1. 在 `.env` 中把 `OPENCLAW_SKILLS_HOST_PATH` 临时指向测试目录（如 `~/skill-manager/smoke-target`）并 `mkdir -p` 该目录。
2. `./scripts/deploy-nas.sh skill-manager both --no-pull` 重建后端。
3. 在界面登记一个 GitHub Skill（或选用现有 local Skill），加入右栏、选择 openclaw、执行发布并输入管理密码。
4. 验证链接落在目标根内且指向受控源：

   ```bash
   ls -la "$OPENCLAW_SKILLS_HOST_PATH/<skill-id>"     # 应为 symlink
   readlink -f "$OPENCLAW_SKILLS_HOST_PATH/<skill-id>" # 应位于 /mnt/skills-source 或 /mnt/github-skill-cache 对应的宿主目录内
   ```

5. 在界面对同一项执行"回滚"验证快照链路；再执行"下架"确认只删除链接本身：

   ```bash
   ls "$OPENCLAW_SKILLS_HOST_PATH/"                   # 该 skill 链接应消失，目录仍在
   ```

6. 验证完毕后把 `OPENCLAW_SKILLS_HOST_PATH` 改回真实路径并重建后端。

### 7. 错误密码不产生副作用

在确认窗口输入错误密码提交发布，界面应提示密码错误，且目标目录无任何变化。

## 回滚

- **单项 Skill 回滚**：管理台内对该 Skill × 目标执行"回滚"，恢复最近一次成功链接；无需登录 NAS。
- **管理台自身下线**：管理台是独立服务，删除它不影响既有 Agent 的技能链接。

  ```bash
  docker compose -f docker-compose.nas.yml -f docker-compose.skill-manager.nas.yml down --remove-orphans skill-manager-frontend skill-manager-backend
  ```

  然后从 `nginx/web.conf` 删除 `/skills*` 与 `/api/skills`（含 `location = /api/skills` 精确匹配块）路由块并执行 `./scripts/deploy-nas.sh nginx`。
- **注册表错误**：`registry.json` 在 Skills Git 仓库中，从 Git 历史恢复。
- **已发布项错误**：从管理台回滚；或按"管理台自身下线"处理后手工修复目标目录中的符号链接（只删链接本身，不删目录）。

## 安全要点

- 管理密码仅存在于 NAS `.env` 与后端进程环境；前端镜像与构建参数中不出现。
- 浏览、筛选、检查更新、发布计划预览无需密码；登记、发布、下架、回滚必须输入管理密码。
- 后端容器的文件系统写入被限制在上述四个 bind mount 与 `skill-manager-state` volume 内。
