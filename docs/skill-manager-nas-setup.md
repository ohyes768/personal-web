# skill-manager NAS 部署指南

Skill 发布管理台（`apps/skill-manager` 前端 + `backend/skill-manager` 后端）在 NAS 上的部署与回滚说明。架构与安全边界见任务设计文档：后端是唯一允许执行 Git、扫描与 symlink 发布的组件；前端不持有任何管理密码。

## Hermes GitHub 目录直链

GitHub 安装不生成版本快照：`Hermes/skill-id` 直接软链到共享仓库缓存的登记目录。
合集成员分别指向各自子目录；单项根 Skill 指向仓库根。更新仓库缓存后，同仓库已安装成员同步读取新内容，无需重新创建各个软链。
检查更新只查询远端，实际 fetch/checkout 在确认安装/更新或显式 Clone 时执行。
共享资源保留仓库原始结构，不再另行拷入快照。其他目标仍走下述 ZIP 导出。
服务启动时离线把已安装的旧快照链接迁移到缓存目录；正常直链不重复改写，旧快照目录保留。

## Windows 外部目标导出

Hermes 继续使用 NAS symlink 发布。Windows Codex / Claude Code
是外部导出目标，无需添加 Windows 路径、网络挂载或本地 CLI。

1. 在自研或 GitHub Skill 卡片点击「导出」，选择 Windows Codex 或 Windows Claude Code。
2. 下载 ZIP 后，新建本地 `<skill-id>` 目录并解压到其中：Codex 放在
   `%USERPROFILE%\.codex\skills\<skill-id>`，Claude Code 放在
   `%USERPROFILE%\.claude\skills\<skill-id>`。ZIP 根目录直接包含 `SKILL.md`，没有外层目录。
3. 导出成功即记录版本、内容哈希与时间；这表示已下载，管理台无法确认本地是否已经解压安装。
4. 源目录变化后，刷新列表显示黄色「源已更新」。点击该记录重新导出，台账更新为当前版本。
   本地覆盖安装时应替换整个 Skill 目录，以清除新版本已移除的旧文件。
5. 记录旁的垃圾桶仅清除台账，不删除 Windows 文件。删除 Skill 登记时，export 台账一并清理。

导出与清除台账免密；NAS 发布与下架仍需管理密码。GitHub 缓存缺失时需先 Clone；
导出使用缓存当前检出的登记子目录，不联网更新，也不包含仓库根的 `shared_paths`。
库启动时自动为 `deployment` 补 `content_hash` 列，旧空哈希记录不误报过期。

## 前置条件

### 1. 克隆 Skills 源库

```bash
git clone https://github.com/ohyes768/skills.git ~/skills
```

管理台的登记真源是自身 SQLite 状态库（`skill-manager.sqlite3`，位于 `skill-manager-state` volume 的 `/app/state` 目录）。首次启动时若 `registry_skill` 表为空，会自动扫描 `SKILLS_SOURCE_HOST_PATH` 目录下含 `SKILL.md` 的子目录并登记。

### 2. 创建缓存与状态目录

```bash
mkdir -p ~/skill-manager/github-cache ~/skill-manager/state
```

目录属主须为运行 `docker compose` 的用户（后端容器以该 uid 通过 bind mount 读写）。`HERMES_SKILLS_HOST_PATH` 指向 NAS 上 Hermes 实际生效的技能目录，须真实存在：

```bash
ls -ld /home/ohyes768/.hermes/skills /home/ohyes768/.hermes/profiles
# 使用已有 Hermes 目录；bind mount 不自动创建宿主目录。
```

### 3. 在 .env 中填写变量（.env 已被 .gitignore 忽略，勿提交）

| 变量 | 含义 |
|---|---|
| `SKILLS_SOURCE_HOST_PATH` | NAS 上 `ohyes768/skills` clone 的绝对路径 |
| `GITHUB_SKILL_CACHE_HOST_PATH` | GitHub 仓库缓存目录的绝对路径 |
| `HERMES_SKILLS_HOST_PATH` | 默认 skills 的绝对路径；缺省 `/home/ohyes768/.hermes/skills`，存量配置保持原值 |
| `HERMES_PROFILES_HOST_PATH` | profiles 父目录的绝对路径；缺省 `/home/ohyes768/.hermes/profiles` |
| `SKILL_MANAGER_ADMIN_PASSWORD` | 管理密码。发布/下架/回滚/登记时在确认窗口输入；缺失时 compose 拒绝启动后端 |

源库、缓存、默认 skills 和 profiles 父目录以读写方式同路径 bind mount 进后端容器，发布的 symlink target 在宿主机同样可解析。2026-10-14 用户确认一次性挂载 profiles 父目录，新增 profile 不再逐项增加挂载；容器因此也能访问父目录内其他 profile 文件，应用功能仅管理 skills。容器没有 docker.sock。

登记/删除不再产生任何 git 操作；源库无需配置任何写凭据。

## 后台克隆任务（2026-09 起）

GitHub 扫描、登记、Clone 缓存均为**后台任务**：接口同步完成可达性预检（≤30s）
后立即返回 `task_id`，clone 在后端进程内执行（超时上限 30 分钟），前端每 2 秒
轮询进度（阶段/百分比/速度）。两点运维须知：

- 任务是**内存态**：后端容器重启会丢失进行中的任务（前端轮询会得到
  `task_not_found` 并提示重试），已完成的登记不受影响（真源在 SQLite）；
- clone 期间后端进程被停止（如 `docker compose down`）不会留下半成品缓存：
  首次 clone 先落 `.tmp` 临时目录、校验后原子改名进正式目录，残留临时目录由
  后端下次启动时自动清理。

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
ls -la "$HERMES_SKILLS_HOST_PATH"           # 应无新增链接
```

### 6. 一次真实发布（测试目录）

建议先指向一个临时目标目录做冒烟验证，再切换到真实 Agent 目录：

1. 在 `.env` 中把 `HERMES_SKILLS_HOST_PATH` 临时指向测试目录（如 `~/skill-manager/smoke-target`）并 `mkdir -p` 该目录。
2. `./scripts/deploy-nas.sh skill-manager both --no-pull` 重建后端。
3. GitHub 输入仓库并扫描、选择候选、确认安装到 Hermes；自研直接选择 Skill 并确认安装。一次管理密码即可完成。
4. 验证链接落在目标根内且指向受控源：

   ```bash
   ls -la "$HERMES_SKILLS_HOST_PATH/<skill-id>"     # 应为 symlink
   readlink -f "$HERMES_SKILLS_HOST_PATH/<skill-id>" # 应位于 SKILLS_SOURCE_HOST_PATH 或 GITHUB_SKILL_CACHE_HOST_PATH 指向的宿主目录内
   ```

5. 在安装看板执行"下架"，确认只删除链接本身：

   ```bash
   ls "$HERMES_SKILLS_HOST_PATH/"                   # 该 skill 链接应消失，目录仍在
   ```

6. 验证完毕后把 `HERMES_SKILLS_HOST_PATH` 改回真实路径并重建后端。

### 7. 错误密码不产生副作用

在确认窗口输入错误密码提交发布，界面应提示密码错误，且目标目录无任何变化。

## 回滚

- **单项 Skill 回滚**：管理台内对该 Skill × 目标执行"回滚"，恢复最近一次成功链接；无需登录 NAS。
- **管理台自身下线**：管理台是独立服务，删除它不影响既有 Agent 的技能链接。

  ```bash
  docker compose -f docker-compose.nas.yml down --remove-orphans skill-manager-frontend skill-manager-backend
  ```

  然后从 `nginx/web.conf` 删除 `/skills*` 与 `/api/skills`（含 `location = /api/skills` 精确匹配块）路由块并执行 `./scripts/deploy-nas.sh nginx`。
- **登记数据错误**：登记真源在 `skill-manager-state` volume 内的 SQLite 库（`registry_skill` 表），从该卷的备份恢复；源库 `registry.json` 不承载管理台登记内容，不要用它恢复。
- **已发布项错误**：从管理台回滚；或按"管理台自身下线"处理后手工修复目标目录中的符号链接（只删链接本身，不删目录）。

## 安全要点

- 管理密码仅存在于 NAS `.env` 与后端进程环境；前端镜像与构建参数中不出现。
- 浏览、筛选、检查更新、发布计划预览无需密码；登记、发布、下架、回滚必须输入管理密码。
- 后端容器的文件系统写入被限制在上述四个 bind mount 与 `skill-manager-state` volume 内。


## ZIP 导出目标管理

打开技能管理器的一级“导出目标”页，可为不同工具或设备新增目标、编辑名称/安装目录说明/备注、启用/停用或删除。ID 创建后不可修改，名称可改；同一 ID 的既有台账保留。安装目录只是手动解压说明，不会自动写入 Windows 或其他设备目录。

现有 Windows Codex、Windows Claude Code 会一次性迁移为默认配置。配置保存在 `skill-manager-state` 卷内 SQLite `export_target` 表；用户修改会保留，删除默认目标后重启不会重新添加。

在“管理看板”中点击 Skill 卡片的下载按钮，选择启用目标下载 ZIP。下载成功后卡片显示目标名称、导出版本与日期；源更新后可重新导出。停用目标仍显示历史记录，允许清除记录，但不能重新导出。删除目标前须在相关 Skill 卡片清除所有导出记录；历史审计保留。

本次更新需要部署技能管理器前后端，并执行 `./scripts/deploy-nas.sh nginx` 下发和 reload 新路由：`/api/export-targets` 与 `/api/export-targets/`。否则页面会报告目标加载失败。此配置管理及 ZIP 导出免密，Hermes 的 NAS 发布路径与管理密码边界保持原样。

## Hermes 单目标升级（2026-10-13）
升级前停止旧后端并备份状态库。若需清理旧目标链接，在旧目录仍可访问时先运行：
```bash
python scripts/cleanup_retired_target.py --db /path/skill-manager.sqlite3 --root /path/old-target
# 复核报告后加 --execute；仅删除账本一致的受管链接，不跟随链接删除源文件。
```
新版本移除旧目标挂载与环境变量。首次启动将旧目标记录归档到 retired_deployment / retired_deployment_history，保留 before-hermes-only 备份；不会自动删除宿主机链接。备份已存在且迁移未完成时启动失败，请先核查备份，不自动覆盖。保留独立 ZIP 导出。安装计划有效10分钟，结果保留30分钟；任务在服务重启后丢失，请先刷新安装实况再重试。运行单 backend worker。

## Hermes 多 profile 安装目标

`hermes` 是存量安装身份，始终沿用原 `HERMES_SKILLS_HOST_PATH`，不要因显示名改为“默认环境”就挪目录。上线前核对它实际对应的 Hermes 环境。新增 profile 不会自动获得任何安装。

升级前已有的 `SKILL_MANAGER_HERMES_TARGETS` JSON 仅用于首次受信任导入；升级后 profile 配置由管理台 SQLite 持久保存，后续新增、改名和删除通过“安装目标”页完成。下面使用已确认的 NAS 用户路径；其他部署按实际 home 调整：

```dotenv
HERMES_SKILLS_HOST_PATH=/home/ohyes768/.hermes/skills
HERMES_PROFILES_HOST_PATH=/home/ohyes768/.hermes/profiles
SKILL_MANAGER_HERMES_TARGETS='[{"id":"hermes","name":"默认环境","profile_name":"default","skills_root":"/home/ohyes768/.hermes/skills"},{"id":"hermes:profile:ohyes768","name":"ohyes768","profile_name":"ohyes768","skills_root":"/home/ohyes768/.hermes/profiles/ohyes768/skills"}]'
```

默认 `hermes` 使用原 `HERMES_SKILLS_ROOT`，网页只读，不可改目录或删除。首次迁移保留旧 named profile ID；新目标由服务端生成身份，页面只选择已有 profile 并填写显示名称。之后 env 不覆盖网页改名，也不复活已删除目标。

`docker-compose.nas.yml` 已默认同路径挂载 `/home/ohyes768/.hermes/skills` 和 `/home/ohyes768/.hermes/profiles`，无需额外 override。需要其他 home 时设置上述两个 HOST_PATH。profiles 父目录下新增环境无需修改 Docker 挂载；不要把整个 `.hermes` 挂入容器。首次启用新挂载需重建后端容器；两个宿主目录必须已存在，否则启动明确失败，不自动创建空目录。后端 `SKILL_MANAGER_HERMES_PROFILES_ROOT` 与 profiles 挂载源/目标使用同一环境变量。挂载本身不登记目标或自动安装 Skill。

管理和部署看板共用当前 profile，URL `target` 保存选择。安装弹窗默认只选当前目标，可勾选多个目标；预览逐 Skill/profile 显示结果。密码确认一次，部分失败只重试失败组合；下架仅移除所选 profile 的受管链接。

各 profile 共享一份自研源和 GitHub 缓存内容，无法独立固定版本。仓库更新预览列出同仓库其他已安装 profile，包括本次未选择的目标；Clone 同样可能改变其共享内容。Hermes 对可写源的修改也会被其他 profile 看到。

移除配置不会清除安装台账，也不会赋予旧目录写权限。仍有 active 安装时禁止同 ID 更换规范目录，源删除也被这些记录阻止；应恢复原配置并明确下架。目录替换或链接变化会使已有计划失效，需重新预览。

升级前备份 SQLite；首次旧库追加 install_target 表时自动创建 `.before-hermes-profiles` 备份。先上线后端兼容接口，再上线前端。后端回退必须恢复升级前数据库和配置，旧单目标后端不能安全读取包含 profile 的新台账。已创建的链接需要继续保留源和缓存挂载。

部署验收另行执行：记录实际 Hermes 版本和各 profile home，在两个环境各发现并读取同一 Skill；核对源路径可达、运行权限和同名 Skill 遮蔽。管理台显示安装成功只表示已验证目标链接，不表示完成 Hermes 运行验收。本任务不操作真实 NAS。

### 网页维护 profile 安装目标

打开“安装目标”页 → “新增 profile 目标” → 选择已存在且 skills 子目录可用的环境 → 填写显示名称 → 管理密码确认。保存后立即出现在管理/部署选择器和安装弹窗，不需要修改 `.env`、Docker 挂载或重启。

默认行固定只读。profile 目标仅能改显示名称，不能换 ID、profile 或目录；改变实际环境应先下架后移除旧目标，再登记另一环境。active 安装即使链接缺失/目录不可达也阻止删除；弹窗提供进入对应部署看板下架的入口。没有 active 后可密码确认移除配置，磁盘目录、源 Skill 和历史保留。再次登记同一 profile 恢复原身份。

候选发现只检查 profiles 直接子目录的 skills；目录缺失/无权限/符号链接重定向会提示不可用，不创建 Hermes profile 或 skills 目录，不读取 auth/config/.env。原 configured named 目标在授权父根外的，保留异常台账且不自动迁移；未配置父根的旧部署仅保留明确配置的旧安装操作，网页新增不可用。

旧库 UI schema 升级前创建 `.before-target-ui` 备份，一次性导入只信任当时明确配置的目标，不给历史 catalog 路径恢复权限。父目录授权、默认目录变动或目标配置版本变化要求重新预览；并发安装/删除被同一操作锁和数据库事务保护。回退到旧后端必须恢复升级前备份与旧配置，不能让旧 env sync 覆盖新持久设置。
