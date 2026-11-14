# 设计：service-manager 瘦身

> 配套 `prd.md`。本文讲**怎么改**：文件级改动、数据流、兼容与风险。

## 1. 改动边界

**只动前端 + spec/PRD 口径**。后端 `backend/service-manager/src/**` 一行不改：

- 入口 / 人工端口 / 发布源 / 组件覆盖的表与数据留着；
- `GET /api/services/{id}`、入口 CRUD、端口 CRUD、发布源、`/services/{id}/releases` 等接口留着；
- 检查子系统（checker / http_probe / tls_probe / releases 同步）留着；
- 备份导出/恢复格式不变。

前端**不再调用**这些接口，但类型与封装**删干净**（调用点没了就没人维护它们）。

## 2. 文件级改动

| 文件 | 动作 |
|------|------|
| `app/service/[id]/page.tsx` | **删除**（整个详情页） |
| `app/page.tsx`（列表） | 删主入口列 / 打开按钮 / 巡检按钮 / URL·证书·发布徽章 / 详情链接；**加**行内编辑名称+用途、删除服务按钮 |
| `app/discovery/page.tsx` | 删「查看服务」链接（指向详情页） |
| `app/resources/page.tsx` | 删「域名」「证书」两个 tab，只留端口 |
| `lib/api.ts` | 删 endpoints / port_notes / release_sources / releases / markRead / 单服务检查 等类型与方法；`ServiceListItem.status` 只用 runtime+health |
| `lib/status.ts` | 删只服务被下线维度的常量与函数（URL_STATE / TLS_STATE / RELEASE_STATE / tlsTone / invalidReasonOf / tlsTooltip / describeCheck 中的 URL/证书分支…），**保留**运行与健康的部分 |
| `components/Widgets.tsx` | `SafeLink` 只被入口列用 → 删；其余保留 |
| `lib/jobs.ts` | 保留（「扫描容器」仍要跟到 job 终态）；`describeJob` 的 kind 文案去掉「巡检」 |
| `e2e/service-manager.spec.ts` | 重写用到详情页的用例；新增行内编辑用例；断言 `/service/{id}` 404 |

## 3. 列表页的新形态

列：**服务**（名称 + 用途 + 标签药丸） | **运行** | **健康** | **操作**（编辑 + 移除）

> 基线说明：「归属」字段与两个分组 tab 已由 `ownership-retirement` 任务退役，
> 列表平铺、归属由 `personal-web` 标签表达。本任务在该基线上做。

```
┌ 服务 ────────────────┬ 运行 ┬ 健康 ┬ 操作 ────────────────┐
│ RSS中转服务            │运行中│ 健康 │  编辑  移除          │
│ 汇集 AI 助手推送的内容…  │      │      │ rss 内容 ＋标签       │
│ rss 内容 ＋标签         │      │      │                        │
└───────────────────────┴──────┴──────┴────────────────────────┘
```

### 3.1 行内编辑（名称 + 用途）

- 点行内「编辑」→ 该行的**名称变 input、用途变 textarea**，旁边出「保存 / 取消」；
- 保存 → `PATCH /api/services/{id}`（带 `revision`），成功后就地更新 `items`
  （`revision` 必须用后端返回值覆盖，否则下一次 PATCH 会 409）；
- 取消 → 丢弃，不发请求；
- Esc 取消；保存期间禁用按钮。

复用已有的一行编辑模式（归属下拉也是就地改的），不再引入新弹窗。

### 3.2 删除服务

- 行内「移除」→ `window.confirm`（文案沿用原详情页：「只删除本应用的记录与关联，运行中的容器不受影响」）→ `DELETE /api/services/{id}` → 重拉列表。

### 3.3 标签编辑

保持现状（`TagEditor` 弹窗，勾选 + 新建），只是入口按钮从「＋标签」继续留在行内。

## 4. 状态维度收敛

列表只渲染两个徽章：

```tsx
<StateBadge tone={RUNTIME[item.status.runtime]} />
<StateBadge tone={HEALTH[item.status.health]} title={healthTooltip(undefined, item.status.health)} />
```

- `healthTooltip` 保留（依赖组件数量，是「-」与「健康」的区别依据）；
- URL / 证书 / 发布三个维度**不再渲染**——它们的依据（入口、发布源）在界面上已经不存在了，
  留着只会给出「不可达 / 证书无效 / 未关联仓库」这类没人能修的假异常。

> 这是**展示层收敛**，不是检查口径变更：后端仍在检查 URL/证书（巡检接口还在），
> 只是前端不展示了。spec 要写明这一点，避免以后有人以为检查停了。

## 5. 资源总览

`/resources` 只剩**端口**视图：

- 「域名」「证书」两个 tab 删掉（它们的数据源是 endpoints，入口下线后必然空）；
- 端口视图的数据源是 Docker 观测（`docker_components.ports`）+ 人工端口备注（`port_notes`，0 条）→ 保留。

## 6. 兼容与风险

| 风险 | 处置 |
|------|------|
| 后端仍在跑 URL/证书检查（巡检接口还在） | 展示层收敛，不改检查口径；spec 写明「前端不展示，检查仍在跑」 |
| 20 条入口数据仍在库里但界面看不见 | 数据不丢、备份照旧导出；以后想接回，接口与数据都现成 |
| 列表接口仍返回 5 个维度的 status | 前端只取 runtime/health；多余字段留着无害 |
| 直接访问 `/service/{id}` | Next 的 not-found → 404（e2e 断言） |
| 旧书签指向详情页 | 404 是预期行为（PRD 明确下线） |

## 7. 不做的事

- 不删后端代码、不改接口、不动数据库、不写迁移；
- 不做解绑/换绑组件；
- 不做组件明细；
- 不删单条服务的检查接口（前端不再调用而已）。
