# 技术设计:宏观定时任务与独立管理页面

## 总体方案

**复制(非共享)股息率的 scheduler 架构到 macro 后端**,核心差异:宏观一个 job
= 一组有序的 update 路径(组任务),而股息率一个 job = 一个 target。前端做独立
路由页而非弹框。不抽公共包(两后端独立部署,复制是本项目已接受的惯例,避免为
两个消费者过早抽象)。

## 一、后端 backend/macro

### 1.1 新增 `src/scheduler/` 包

| 文件 | 来源 | 改动 |
|------|------|------|
| `manager.py` | 复制 dividend-select | 删 `get_holdings_codes`(股息专属);`_run_job_wrapper` 结果增加 `items` 透传 |
| `jobs.py` | 重写 | 通用组执行器 `run_group`(见 1.2) |
| `trading_calendar.py` | 复制(114 行,akshare+缓存) | 缓存路径改为 macro 的 data 目录 |
| `history.py` | 原样复制(JSONL append/tail) | 无 |
| `cron_human.py` | 原样复制(cron→中文) | 无 |
| `routes.py` | 原样复制(4 个 API) | prefix `/api/scheduler` 对齐 macro 路由挂载方式 |
| `scheduler.json` | 新写 | 2 个分组任务预设 |

保留的关键机制(股息率踩坑沉淀,注释一并复制):Asia/Shanghai 统一时区、
`max_instances=1 + coalesce`、单 worker 校验、延迟 self-call 端口探活、
jobs 为空时大声报错(volume 覆盖坑)、`_run_locks` 防重入、启停写回配置。

### 1.2 组任务模型(scheduler.json)

```json
{
  "version": 1,
  "jobs": [
    {
      "id": "a_share_daily",
      "name": "A 股数据日度组",
      "target": "run_group",
      "cron": "10 16 * * 1-5",
      "enabled": true,
      "check_trading_day": true,
      "targets": [
        "/update/china-bonds", "/update/dr007", "/update/fund-flow",
        "/update/volume", "/update/turnover", "/update/margin"
      ],
      "description": "A 股收盘后顺序更新中债/DR007/北向/成交额/换手率/融资余额"
    },
    {
      "id": "global_daily",
      "name": "全球市场日度组",
      "target": "run_group",
      "cron": "30 7 * * 1-5",
      "enabled": true,
      "check_trading_day": false,
      "targets": [
        "/update/us-treasuries", "/update/exchange-rates", "/update/eu-bonds",
        "/update/jp-bonds", "/update/vix", "/update/tga", "/update/hibor",
        "/update/ted-spread", "/update/commodities", "/update/indices"
      ],
      "description": "北京早晨(美东收盘后)顺序更新美债/汇率/欧日债/VIX/TGA/HIBOR/TED/商品/指数"
    }
  ]
}
```

- 字段冲突说明:`target`(job 类型,兼容 manager 的 JOB_TARGETS 查找)与
  `targets`(路径列表)并存。前者固定 `"run_group"`,后者才是真正要跑的端点。
- cron 时间点是建议值,后续直接改 scheduler.json 即可(无在线编辑,用户已确认)。

### 1.3 `run_group` 执行器(src/scheduler/jobs.py)

```
async def run_group(ctx, job_id) -> record dict
  1. check_trading_day → False 时 return {status: "skipped", reason: "non_trading_day"}
  2. for path in spec["targets"]:
       POST http://127.0.0.1:{port}/api{path}   (httpx, timeout=600, 顺序执行)
       item = {path, status, count, ms, error}
       - 200 且 resp.success=True → item.status="success"(count 取 data 条数,可空)
       - 200 但 success=False → "failed",记 message;继续下一个
       - 网络异常/超时 → "failed";继续下一个(单源失败不中断)
  3. 聚合:全 success→"success";≥1 失败且 ≥1 成功→"partial";全失败→"failed"
  4. count = 成功数;items 列表随 record 落 JSONL 历史
```

注意:macro 的 update 端点返回 `UpdateResponse{success, message, data?}`(HTTP 200
+ `success:false` 表业务失败),与股息率的 409 语义不同——按 body.success 判定,
不引入 409 特判。

### 1.4 历史记录格式(JSONL,每 job 运行一条)

```json
{"job_id": "a_share_daily", "target": "run_group", "status": "partial",
 "count": 5, "start": "...", "end": "...",
 "items": [{"path": "/update/margin", "status": "failed", "count": null, "ms": 450, "error": "..."}]}
```

文件:`data/scheduler/history.jsonl`(交易日历缓存同目录)。

> 实施修正:scheduler.json **不放** `data/`——`data/` 在 macro 的 .gitignore 中且
> docker-compose 用宿主机 `./data` 覆盖容器 `/app/data`,放那里会导致新环境 0 任务。
> 改与 dividend 同款:`src/scheduler/scheduler.json`(git 跟踪、随镜像分发)。
> "volume 覆盖坑"的防御机制(jobs 为空大声报错)原样保留。

### 1.5 main.py 集成

- `startup` 事件:`SchedulerManager(port=settings.service_port, ...).start({})`,
  存 `app.state.scheduler`;`shutdown` 事件:`shutdown()`。
- `app.include_router(scheduler_router)`(挂载前缀与现有 `/api` 路由一致)。
- `pyproject.toml` 增加 `"apscheduler>=3.10,<4.0"`(与 dividend 同版本约束)。

## 二、前端 apps/macro

### 2.1 路由与目录(对齐现有 modules 模式)

```
src/app/scheduler/page.tsx            # re-export modules/scheduler/page(同 economic 模式)
src/app/modules/scheduler/page.tsx    # 管理页主体
src/app/modules/scheduler/components/ # JobCard / RunsHistory / ItemTable 等
src/lib/modules/scheduler/api.ts      # schedulerApi
src/lib/modules/scheduler/types.ts    # SchedulerJob / SchedulerJobRun / RunItem
```

API 走现有 rewrite:`/api/macro/scheduler/*` → 后端 `/api/scheduler/*`
(next.config.ts 已有 `/api/macro/:path*` 规则,零配置新增)。

### 2.2 管理页信息架构

- 页头:标题 + 全局刷新按钮
- 任务卡片 × 2:名称/描述、cron 中文(如"工作日 16:10")、下次运行时间、
  上次运行(状态 badge + 时间 + 成功数/总数)、启停 Switch、立即执行按钮
- 点卡片展开运行历史(最近 20 条):状态 badge / 开始时间 / 总耗时 / 成功数
- 历史条目再展开**数据源子明细表**:路径 / 状态 / 条数 / 耗时 / 错误信息
- 交互沿用股息率前端已验证模式:启停乐观更新+失败回滚;立即执行后延时刷新历史;
  toggling/running 的 Set 防连点
- 样式:Tailwind,颜色语义沿用股息率 STATUS_META(绿 success/黄 skipped 或
  partial/红 failed);深色优先(该 app 默认深色 + useDarkMode)

### 2.3 主页入口

`modules/economic/page.tsx` 右下角加固定定位悬浮齿轮按钮,
`next/link` → `/scheduler`(basePath 自动补 `/macro`)。

## 三、兼容与风险

| 风险 | 对策 |
|------|------|
| akshare 慢/挂导致组任务耗时长 | 顺序执行天然限流;httpx timeout=600;单源失败不中断 |
| scheduler.json 被 volume 覆盖(dividend 踩坑) | 复制其"jobs 为空大声报错"逻辑与注释 |
| Windows dev `--reload` 双进程双 scheduler | dividend 同架构已在 Windows dev 验证;macro 用同样启动方式(start-macro-dev.bat),不额外处理 |
| n8n 老链路 | `POST /api/update` 不动;新调度上线后用户自行在 n8n 停旧任务 |
| margin/融资余额等数据源盘后延迟发布 | cron 时间点可在 scheduler.json 手调,增量更新机制自动补数 |

## 四、测试策略

- 后端 pytest(新增 `tests/test_scheduler_*.py`):
  - `run_group` 聚合逻辑:全成功/部分失败/全失败/非交易日 skip(mock httpx)
  - `cron_human`、`history` tail 读写(如从 dividend 移植其测试思路)
- 前端:`pnpm build` 通过 + dev 手动联调(启停/立即执行/历史展开)
- 联调:`start-macro-dev.bat` 起服务,页面点一遍,curl 4 个 API
