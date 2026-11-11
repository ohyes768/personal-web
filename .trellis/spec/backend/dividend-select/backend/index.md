# Backend Development Guidelines

> Best practices for backend development in this project.

---

## Overview

This directory contains guidelines for backend development. Fill in each file with your project's specific conventions.

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Code Type Guidelines](./code-type-guidelines.md) | 股票代码/指数代码全链路 str 契约、CSV dtype 规范 | Active |
| [Snapshot Cache Contract](./snapshot-cache-contract.md) | 源文件签名快照缓存（失效/失败不发布/并发去重）、读取路由线程隔离、/stocks codes 过滤、前端按 Tab 请求边界 | Active |
| [Background Refresh Jobs](./refresh-jobs-contract.md) | M120/financial/quality 202 jobs, progress, persistence, atomic publication and scheduler results | Active |
| [Hermes Quality Rating](./quality-rating-contract.md) | 五维基本面评级：skill 契约、Hermes Runs API、幂等、落盘与前端映射 | Active |
| [Valuation (Four-Level Prices)](./valuation-contract.md) | 收藏跟踪四挡位估值：skill 17 字段契约、valuation job 队列、apply 身份校验、alerts/enabled 启停、收藏跟踪 UI 语义 | Active |
| [M120 Snapshot Continuity](./m120-snapshot-contract.md) | 跨周读取、历史文件保留、状态时间与周六调度 | Active |
| [Scheduler Lifecycle](./scheduler-lifecycle.md) | 调度器有界关闭、在跑任务等待与取消 | Active |
| [Screening / Watchlist Contract](./screening-watchlist-contract.md) | 筛选三态、历史 ROE、批量收藏与旧缓存迁移 | Active |
| [Stock Search Contract](./stock-search-contract.md) | 「全部」页股票搜索：完整收集池匹配、相关度排序、收藏范围收窄 | Active |
| [Financial Quarterly Contract](./financial-quarterly-contract.md) | 最新季度扣非单季口径、数据季度=报告期、latest_quarter_label 全链路透传 | Active |
| [Directory Structure](./directory-structure.md) | Module organization and file layout | To fill |
| [Database Guidelines](./database-guidelines.md) | ORM patterns, queries, migrations | To fill |
| [Error Handling](./error-handling.md) | Error types, handling strategies | To fill |
| [Quality Guidelines](./quality-guidelines.md) | Code standards, forbidden patterns | To fill |
| [Logging Guidelines](./logging-guidelines.md) | Structured logging, log levels | To fill |

---

## How to Fill These Guidelines

For each guideline file:

1. Document your project's **actual conventions** (not ideals)
2. Include **code examples** from your codebase
3. List **forbidden patterns** and why
4. Add **common mistakes** your team has made

The goal is to help AI assistants and new team members understand how YOUR project works.

---

**Language**: All documentation should be written in **English**.
