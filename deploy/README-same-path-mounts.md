# skill-manager 发布链接同路径挂载（宿主机路径一致性）部署说明

skill-manager 后端跑在容器里，发布动作是在容器内创建 symlink、文件却落在
宿主机的 Hermes/OpenClaw 技能目录；两个 agent 都跑在宿主机上。symlink 的
target 是创建时写入的字面路径——旧配置挂载为 `HOST_PATH → /mnt/*`，
Publisher 写进链接的是容器内绝对路径（`/mnt/github-skill-cache/<id>`、
`/mnt/skills-source/<path>`），宿主机按自身文件系统解析必然断链，agent
读不到 SKILL.md。修复方式是**同路径 bind mount**：四个业务目录两侧都用
同一个宿主路径，容器内校验与宿主机解析天然一致。

## NAS 一次性迁移步骤

### 1. 同步代码并重建后端容器

```bash
cd ~/personal-web
git pull origin master
docker compose -f docker-compose.nas.yml -f docker-compose.skill-manager.nas.yml \
  up -d --build skill-manager-backend
```

`.env` 无需改动（复用现有四个 `*_HOST_PATH` 变量）。

### 2. 清理旧断链（只删失效链接，不影响实体目录）

```bash
find ~/.hermes/skills -maxdepth 1 -type l ! -exec test -e {} \; -delete
find ~/.openclaw/workspace/skills -maxdepth 1 -type l ! -exec test -e {} \; -delete
```

不清理直接走 plan 也能自愈发现（旧链接 resolve 不到受控根 → blocked
"现有链接指向受控目录之外"），但无法经界面修复，所以以 find 删除为标准步骤。

### 3. 界面重新发布相关 skill

管理台对受影响的 skill 逐个"生成计划 → 发布"，链接按新路径原子重建。

### 4. 宿主机验收

```bash
ls -l ~/.hermes/skills/<id>              # target 应为 /home/<user>/... 宿主路径
cat ~/.hermes/skills/<id>/SKILL.md       # 可读即通
```

## 回滚注意

revert 相关 commit 并把 compose 恢复 `/mnt` 挂载重建即可；但**已按新路径
发布的链接在回滚后的容器内不可解析**（plan 会 blocked），需再执行一遍
上面第 2 步的 find 清理。
