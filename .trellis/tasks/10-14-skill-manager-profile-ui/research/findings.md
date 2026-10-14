# 界面设置目标 — 研究记录

直接复用当前 task 的四份 skill-manager guides 和 profile contracts。现有 SourceWorkspace/SkillPool/InstallDialog/DeployBoard 已动态消费 install-targets，因此管理入口可复用名单刷新，不需重建多目标安装流程。

关键变化发生在目标配置真源和授权边界：当前 TargetResolver 在启动时从 Settings 捕获配置，DB catalog 不能授权操作；启动 sync 会从 env 更新 catalog。若界面设置只是改 catalog，重启可能覆盖或新目标仍不可写。设计必须明确独立持久操作字段与一次性 env 迁移，并使 resolver 每次操作读取当前授权版本。

Docker bind mounts 由部署控制，网页创建 DB 行不能访问未挂载目录。当前 named profile mount 示例只挂 skills，不包含 profile 凭据；不能默认挂载整个 ~/.hermes/profiles 或引入 Docker socket 来假称新增即生效。

目录 identity/root overlap、source/cache/state 分离、active ID 换根阻止、shared cache impacts 与 exact retry 必须保留。移除目标需区别 catalog tombstone、启停/退役和 uninstall，避免清除历史引用后误删源。

产品范围待用户确认：已挂载目录登记 vs 新增 profile 无需后续挂载调整。后续再收敛入口位置、编辑/移除行为和一次密码确认 UX。

## 用户确认 B 后的部署方案比较

- 逐 profile bind mount 不能满足 B；改 registry DB 或给容器改环境变量都不改变现有 mount namespace。
- 候选 1（推荐）：宿主机轻量 helper，运行于 Hermes 所属用户，通过专用 Unix socket 接收受控 target 操作。后端继续管理 registry/cache/SQLite/密码与计划；helper 对已授权默认 skills 和 profiles/<name>/skills 做目录状态/identity/受管链接原子更新/移除，不运行任意命令、不接任意宿主路径、不暴露 profile 凭据。后续 targets 不必进入管理容器 mount namespace，安装与账实核对需经统一 filesystem adapter RPC，不能只改 UI/CRUD。
- 候选 2：一次性 profiles 根同路径 bind mount，后端继续本地 Path 实现，改动小；实际 mounted 根也包含 profile 的其他文件。仅在应用代码里拒绝读取其他文件无法缩小容器自身的访问范围，不满足前任务原有 skills-only 挂载边界，需要用户明确接受该范围改变。
- helper 增加一个宿主机常驻进程的安装/升级/健康检查/故障恢复与 RPC 部分失败契约，需形成独立部署材料；此前项目没有这套运行机制（现有 skill-manager-backend 只有 FastAPI 容器）。
- 未选择方案前不定义最终目录授权 API，不改启动脚本/compose 或扩大真实环境访问。

## 最新挂载表述核对

用户表示“挂载整个 profiles skill目录，之前就是这样的吧？”。仓库实际 compose 默认挂载 ~/.hermes/skills，新增 named profile 示例逐项挂载 ~/.hermes/profiles/ohyes768/skills；此前并未整体挂 profiles 父目录。尚不能把用户对“skills-only 挂载”的表述解释成已同意访问包含配置/凭据的 profiles 父目录。需要明确该路径差异后收敛部署选择。

## 已确认部署路线与前置修改

用户随后明确同意 profiles 父目录挂载，并要求先改好 `/home/ohyes768/.hermes/profiles` 与 `.hermes/skills` 两个挂载。已修改主 compose 默认同路径长格式 bind（不自动创建路径）、同步后端默认技能根的 env 缺省值，并更新例子和部署文档。保留已有 HOST_PATH override，不替用户转移 legacy hermes。

`docker compose config --format json` 用临时虚拟 env 验证默认路径和自定义路径各一次，两目录源/目标完全一致、读写、HERMES_SKILLS_ROOT 与默认 skills 相同；不读取实际 .env，不连接/部署 NAS。

此为用户单独授权的部署前置改动，UI 功能保持 planning。宿主机 helper 方案不再采用。
