# fund-select 后端 Spec

> 独立项目 `F:/personal-projects/fund-select/backend`（FastAPI :8095）。
> 任务 09-01-fund-select-v1-bond 落地，v1 为 31 只精选基金筛选。

## 目录

| 文件 | 内容 |
|---|---|
| [contracts.md](./contracts.md) | API 契约、ORM schema、费率缓存契约、basePath/代理链路 |

## 一句话架构

`config/funds.yaml`（债基宇宙）+ `config/funds_stock.yaml`（股票宇宙）→ fetcher → SQLite（共用 `funds` 表）→ FilterService 按 yaml 切宇宙 → FastAPI `/api/funds` 与 `/api/funds/stock` → Next.js 代理（:3005/funds）。
