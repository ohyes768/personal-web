# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

个人资讯网站，pnpm workspace monorepo 结构，包含 5 个 Next.js 前端应用和 3 个 Python 后端服务。

```
apps/
├── dividend/      # A股高股息率分析 (Next.js 15, React 19, Tailwind CSS v4)
├── douyin/         # 抖音视频文字稿
├── economic/       # 宏观经济
├── fund-flow/     # 资金流向
└── news/           # 新闻联播分析

packages/
├── api-client/     # 统一 API 客户端
├── shared-types/   # 共享类型定义
├── shared-ui/      # 共享 UI 组件
└── shared-utils/   # 共享工具函数

backend/
├── dividend-select/  # 股息率后端 (FastAPI, akshare, 阿里云行情API)
├── douyin-processor/  # 抖音后端
└── global-macro-fin/ # 宏观金工后端
```

## 常用命令

### 前端开发 (apps/dividend 为例)
```bash
cd apps/dividend
pnpm dev          # 开发服务器 (端口 3003)
pnpm build        # 生产构建
pnpm lint         # ESLint 检查
```

### 后端开发
```bash
# dividend-select
cd backend/dividend-select
python -m pytest tests/ -v          # 运行所有测试
python -m pytest tests/test_calculator.py::test_calculate_dividend_yield -v  # 单个测试

# 进入虚拟环境
.\.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# 启动后端服务
cd backend/dividend-select
python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8092
```

### Windows 开发脚本
```bash
scripts\start-dividend-dev.bat   # 启动股息率前后端
scripts\stop-dividend-dev.bat   # 停止
scripts\start-fundflow-dev.bat # 资金流向
scripts\start-news-dev.bat     # 新闻
```

### pnpm workspace
```bash
pnpm install              # 安装所有依赖
pnpm --filter dividend dev  # 只运行 dividend app
```

## 架构说明

### 股息率数据流 (dividend-select)

```
红利指数持仓 (akshare index_stock_cons_weight_csindex)
         ↓
data/fetcher.py → IndexHoldingsFetcher 获取股票列表
         ↓
core/calculator.py → DividendCalculator 计算股息率
  ├─ 分红数据: akshare.stock_dividend_cninfo() (巨潮资讯)
  ├─ 价格数据: 阿里云行情API /query/comkm
  └─ 公式: 股息率 = 年度分红 / 年度均价 × 100%
         ↓
services/m120_service.py → M120均线及偏离度
         ↓
api/routes.py → RESTful API 输出
         ↓
apps/dividend (前端)
```

### 关键 API 路由 (dividend-select/src/api/routes.py)

| 路由 | 说明 |
|------|------|
| `GET /stocks` | 股息率股票列表 |
| `GET /stocks/{code}` | 股票详情 |
| `POST /dividend/refresh` | 刷新股息率数据 |
| `GET /m120` | M120均线及偏离度 |
| `POST /m120/refresh` | 刷新M120数据 |
| `POST /realtime-price` | 实时价格 |

### 前端状态管理 (apps/dividend/src/lib/hooks.ts)

- `useDividendData()` — 股息率主数据 Hook
- `useTechnicalData()` — M120/实时价格 Hook
- `useDataUpdate()` — 数据刷新状态管理

## 非目标

- `dividend-select` 是同 owner 的独立仓库（`ohyes768/dividend-select`），可以修改；commit 后回到主项目更新引用即可
- 禁止直接修改其他第三方子模块：`douyin-processor`、`global-macro-fin`（这两个是真正的三方依赖，改动会跟 upstream 漂移）
- 不要在代码中硬编码凭证，使用环境变量