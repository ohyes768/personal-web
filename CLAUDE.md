# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## 项目概述

个人财富网站，5 个独立 Next.js 前端 + 3 个 Python 后端（git submodule）。
```
apps/
├── dividend/      # A 股高股息分析（Next.js 15, React 19, Tailwind CSS v4）
├── douyin/         # 抖音视频文字转写
├── economic/       # 宏观经济
├── fund-flow/      # 资金流向
└── news/           # 新闻联播分析

backend/
├── dividend-select/  # 股息率后端（FastAPI, akshare, 阿里云行情 API）
├── douyin-processor/  # 抖音后端
└── global-macro-fin/ # 宏观金融后端
```

## 常用命令

### 前端开发（apps/dividend 为例）
```bash
cd apps/dividend
pnpm dev          # 启动开发服务器（端口 3003）
pnpm build        # 生产构建
pnpm lint         # ESLint 检查
```

### 后端开发
```bash
# dividend-select
cd backend/dividend-select
python -m pytest tests/ -v          # 运行所有测试
python -m pytest tests/test_calculator.py::test_calculate_dividend_yield -v  # 单个测试

# 启动后端服务
python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8092

# douyin-processor
cd backend/douyin-processor
python -m uvicorn src.server.main:app --reload --host 0.0.0.0 --port 8093

# global-macro-fin
cd backend/global-macro-fin
./.venv/bin/uvicorn src.main:app --reload --host 0.0.0.0 --port 8094
```

### Windows 开发脚本
```bash
scripts\start-dividend-dev.bat   # 启动股息率前后端
scripts\stop-dividend-dev.bat   # 停止
scripts\start-fundflow-dev.bat # 资金流向
scripts\start-news-dev.bat     # 新闻
scripts\start-macro-dev.bat    # 宏观经济
scripts\start-douyin-dev.bat    # 抖音
```

### Docker（本地）
```bash
docker compose up -d --build
docker compose logs -f [service-name]
docker compose down
```

## 架构说明

### 股息率数据流（dividend-select）
```
红利指数成分股 (akshare index_stock_cons_weight_csindex)
         ↓ data/fetcher.py → IndexHoldingsFetcher 获取股票列表
         ↓ core/calculator.py → DividendCalculator 计算股息率
  ↓ 分红数据: akshare.stock_dividend_cninfo() (巨潮财富)
  ↓ 价格数据: 阿里云行情 API /query/comkm
  ↓ 公式: 股息率 = 年度分红 / 年度均价 × 100%
         ↓ services/m120_service.py → M120均线及偏离度
         ↓ api/routes.py → RESTful API 输出
         ↓ apps/dividend (前端)
```

### 关键 API 路由（dividend-select/src/api/routes.py）
| 路由 | 说明 |
|------|------|
| GET /api/dividend/stocks | 股息率股票列表 |
| GET /api/dividend/stocks/{code} | 股票详情 |
| POST /api/dividend/refresh | 刷新股息率数据 |
| GET /api/dividend/m120 | M120均线及偏离度 |
| POST /api/dividend/m120/refresh | 刷新M120数据 |
| POST /api/dividend/realtime-price | 实时价格 |
| GET /api/dividend/report/one-pager | A4 一页通报告 |
| GET /api/dividend/report/carousel | 移动端轮播报告 |

### 前端状态管理（apps/dividend/src/lib/hooks.ts）
- `useDividendData()` — 股息率主数据 Hook
- `useTechnicalData()` — M120/实时价格 Hook
- `useDataUpdate()` — 数据刷新状态管理

## 子模块管理规范

三个后端都是 `ohyes768` 名下的独立仓库，**用户都作开为发者维护**：

| 子模块 | 远端 | 说明 |
|--------|------|------|
| `backend/dividend-select` | `ohyes768/dividend-select` | A 股股息率后端，FastAPI + akshare |
| `backend/douyin-processor` | `ohyes768/douyin-processor` | 抖音视频文字转写处理后端 |
| `backend/global-macro-fin` | `ohyes768/global-macro-fin` | 宏观金融后端 |

更新流程：
1. `cd backend/<submodule>` 在子模块内改代码
2. 子模块内 `git add` + `git commit` + `git push origin main`
3. 回到主仓库 `git add backend/<submodule>` 更新 gitlink
4. 主仓库 `git commit -m "chore: bump <submodule> pointer"`
5. 主仓库 `git push origin master`

**顺序很重要**：子模块必须先 push 到远端，主仓库才能 push gitlink 更新（否则 clone 后 `git submodule update` 会断链接）。

## 其他约定

- 不要在代码中硬编码端口号，使用环境变量
- 前端 `basePath` 配置：dividend 用 `/dividend`，douyin 用 `/douyin`，其他三个无 basePath
- 所有环境变量文件（.env.local）已被 .gitignore 忽略，不要提交
