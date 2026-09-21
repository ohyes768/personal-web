# 迁移滨江购房地图为 personal-web 新服务

## Goal

把独立仓库 `F:/personal-projects/hangzhou-housingmap`（杭州滨江区房价地图，Next.js + 高德地图 + Python 采集脚本）迁移进 personal-web monorepo，成为第 6 组前后端服务，遵循仓库现有服务（fund-select / macro）的开发与部署规范。

## 已确认决策（用户拍板）

| 决策项 | 结论 |
|--------|------|
| 架构 | 前后端分离：`backend/housing-map`（FastAPI）+ `apps/housing-map`（纯前端 Next.js） |
| URL 前缀 | basePath = `/map`，API 前缀 = `/api/map/*`（nginx 剥前缀直转后端，对齐 macro/fund-select） |
| Next.js 版本 | 保留源项目的 16.2.6（不降级到仓库主流 15.4） |
| 采集脚本 | 随迁进 `backend/housing-map`，refresh 能力归后端 |
| 端口 | 前端 3007、后端 8096（顺延现有序列：前端 3001-3006 已用、后端 8092-8095 已用） |

## Requirements

### R1 后端 `backend/housing-map`（FastAPI）

- 移植源项目 Next.js API 路由（communities / score / transit / refresh）为 FastAPI 端点，行为与源项目对齐
- 数据加载（data-loader）、评分计算（scoring）逻辑用 Python 重写，保持评分公式与结果一致
- 被引用的数据文件随服务分发（具体清单以 research 结论为准）；数据目录挂 volume，refresh 更新写入 volume
- Python 采集脚本迁入 `backend/housing-map/scripts/`，refresh 端点可触发采集（对齐 dividend 的采集模式）
- 提供 health 端点；pyproject.toml + uv 管理依赖（`package = false`）；提供 Dockerfile；pytest 测试

### R2 前端 `apps/housing-map`（Next.js 16.2.6）

- 迁移 `web/src` 页面、地图组件、类型定义；删除 API 路由目录（后端已接管）
- `next.config.js`：`output: 'standalone'`、`basePath: '/map'`
- 所有 `fetch('/api/...')` 改调 `/api/map/*`（nginx 直转后端，前端不做 BFF）
- 高德地图 Key 保持 `NEXT_PUBLIC_*` 环境变量方式，不硬编码
- package.json name 改为 `housing-map-frontend`，scripts 端口 3007；提供 Dockerfile

### R3 nginx（`nginx/web.conf`）

- 新增 upstream：housing_map_backend（:8096）、housing_map_frontend（:3007），带 resolve + keepalive
- 新增路由（对齐 macro/funds 写法）：
  - `location /map/_next/static/` → 静态资源（URI 替换含 basePath）
  - `location /map`（不带尾斜杠，避免 trailingSlash redirect loop）→ 前端
  - `location /api/map/` → rewrite 剥前缀 → 后端 `/api/*`

### R4 部署编排（`docker-compose.nas.yml`）

- 新增 `housing-map-backend` / `housing-map-frontend` 两个服务：healthcheck、named volumes、环境变量
- 高德相关 key 进根目录 `.env`（已被 .gitignore 忽略），NEXT_PUBLIC_* 通过 build args 传入
- 头部注释的路由说明同步更新

### R5 首页聚合页（nginx `location = /`）

- 单行 HTML 中新增入口：`🏠 滨江购房地图` → `/map`（风格对齐现有 5 个入口）

### R6 文档与脚本

- `CLAUDE.md` 常用命令节补充 housing-map 前后端启动命令
- `scripts/start-housing-dev.bat`（仿照现有 start-*-dev.bat，可选交付，见验收标准）
- docker-compose.nas.yml 顶部注释、README（如有服务清单）同步

## Constraints

- 高德 Key / 透明售房网相关凭据一律走环境变量，不提交仓库
- 不改动其他 5 组服务的行为与配置语义（nginx/compose 仅做增量）
- 源项目 `F:/personal-projects/hangzhou-housingmap` 保持只读，迁移为复制不是移动
- data/ 中 raw 中间文件（`*_raw*`、`_temp*`）不随迁移，只带被 API 引用的最小集合
- 评分结果与源项目一致（移植正确性的核心指标）

## Acceptance Criteria

- [ ] `apps/housing-map`：`pnpm build` 成功；`pnpm dev` 下地图页能加载小区点位、价格、评分（经本地 FastAPI）
- [ ] `backend/housing-map`：`python -m pytest tests/ -v` 全绿；`GET /api/health` 返回 200
- [ ] 移植的 API（communities 等）返回数据与源项目 Next.js 版本一致（关键字段抽样比对：小区数量、评分区间）
- [ ] `nginx/web.conf`：/map 与 /api/map/ 路由语法正确（`nginx -t` 或等效审查通过），静态资源 location 含 basePath 替换
- [ ] `docker-compose.nas.yml`：两服务定义结构对齐现有服务（healthcheck / volumes / networks / depends_on）
- [ ] 首页聚合页出现"滨江购房地图"入口且链接为 /map
- [ ] 全仓库无新增硬编码 key；`.env` 相关变量已列入 compose 环境变量
- [ ] CLAUDE.md 命令说明已更新

## Notes

- 复杂任务：需 design.md（架构/数据流/接口契约）+ implement.md（分阶段执行清单）后方可 `task.py start`
- 源项目已知约束：page.tsx 约 650 行混合多组件、dashboard 等空目录——迁移时按需拆分，不做超出迁移范围的重构
