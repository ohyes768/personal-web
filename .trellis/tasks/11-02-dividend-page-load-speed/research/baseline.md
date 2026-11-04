# 2026-11-02 性能基线

## 方法与限制

通过 NAS SSH，在运行容器内用 urllib 请求 127.0.0.1:8092；另外经 NAS nginx 9443、公共域名读取 HTML。均为只读，未触发更新或部署。少量样本不代表 p95，并发请求顺序及缓存状态会影响结果。

开发机 curl 和 web 工具无法打开目标页面，尚无用户浏览器瀑布，因此不能排除公网、JS 加载或渲染延迟。

| 单独请求 | 耗时 | 未压缩字节 |
|---|---:|---:|
| /health | 16 ms | 104 |
| /favorites | 2 ms | 3321 |
| /favorites/alerts/status | 2 ms | 3401 |
| /stocks?min_yield=3.5 | 379 ms | 238864 |
| /stocks?min_yield=0 | 400 ms | 397034 |
| /m120 | 479 ms | 37238 |

一批 15 条混合读请求并发：stocks(3.5) 582 ms、stocks(0) 1034 ms、health 1037 ms、m120 1553 ms、stats 1559 ms。探测中的 /refresh/state 为错误路径、返回 404；业务刷新状态路径是 /refresh/jobs?kind=...。

独立进程调用 Reader：主表 202 行首次 7.12 ms、缓存 0.04 ms；股东 5253 行首次 11.16 ms、再次 10.20 ms；财务 216 行首次 3.85 ms、再次 3.59 ms。收藏 11 只。

NAS nginx 回环 HTML 约 12 ms，NAS 访问公共域名 HTML 约 86 ms，仅代表 HTML。gzip 已生效，stocks(0) 约 61 KB。quality 未压缩约 533 KB、压缩约 180 KB，但源码由筛选 Tab 加载，不能列为 alerts 已确认瓶颈。

## 代码证据

- page.tsx 无条件启动通用 hooks；收藏后再次请求全量 stocks；技术指标请求全量 M120。
- get_stocks 每次遍历全部股东/财务数据，逐行组装模型。
- DataReader 已缓存主表；ShareholderReader/FinancialReader 有 _cache 字段但 read_csv 未复用。
- async 路由直接执行同步 Pandas 和循环；实际 uvicorn 命令为单 worker。结合 health 排队，确认存在事件循环阻塞；各计算步骤占比尚待 profile。
- 空闲快照约 190 MiB 内存、0.2% CPU，不能据此判断请求期间峰值。

结论：文件读取仅占部分耗时，先减少重复请求/转换并隔离计算，再判断存储迁移。
