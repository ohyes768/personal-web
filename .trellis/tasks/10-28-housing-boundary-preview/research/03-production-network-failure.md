# 线上生成失败复盘：NAS 连不上 Overpass

发现时间：2026-10-28（功能已部署上线后，用户在地图上点了"生成候选轮廓"）

## 现象

- 地图弹框显示"联网获取建筑中，完成后可以在这里查看候选。"，随后不再变化。
- 用户问"这个日志可以从哪里看"——**说明界面上完全看不出发生了什么**。

## 查证

线上接口（只读）：

```
GET /api/map/communities/local-300f814be4f554d5/boundary-workflow
→ latest_job.phase      = failed
→ latest_job.error_code = network
→ latest_job.error_message:
    所有 Overpass 镜像均失败:
    https://overpass-api.de/api/interpreter: HTTP Error 502: Bad Gateway
    https://overpass.kumi.systems/api/interpreter: The read operation timed out
    https://overpass.private.coffee/api/interpreter: The read operation timed out
```

即：任务早已失败，失败原因只存在接口里，**弹框一个字都没露**。

## 根因

NAS 上没有 OSM 建筑快照（`data/binjiang_osm_*_raw.json` 被 gitignore，NAS 是 git pull 后本地构建），
只能走在线 Overpass；而 NAS 出口打不通 Overpass。**两头落空 → 生成必然失败。**

这正是 `01-current-gap-and-snapshot.md` 第 4 节预判的风险，在生产落地了。

## 处置（用户选择方案 B：快照随仓库走）

1. `.gitignore` 给全量快照开例外（`!data/binjiang_osm_buildings_all_raw.json`）。
   依据：这份数据在 NAS 上**无法重建**（Overpass 不通），"可重新生成的抓取产物"这个前提已不成立。
   仓库本来就跟踪 11.8MB 的 `binjiang_pois.json`，9.2MB 的快照与既有实践一致；
   gzip 后 1.56MB。
2. Dockerfile 把它复制进 `seed-data`，容器启动时补齐到数据卷（沿用既有 3 个文件的 seed 模式）。
   `tests/test_dockerfile.py` 加断言守住"COPY + CMD 补齐 + 未被 gitignore"三件事。
3. 全量快照的 bbox（30.10–30.26 / 120.10–120.28）**盖得住全部 25 个缺口小区**，已核对。

## 顺带修掉自己的两个漏洞

1. **弹框不显示失败原因**（用户直接踩到的）：`BoundaryWorkflowSection` 只渲染进行态。
   现在渲染 `error` / `jobError`，按钮文案在失败后变为"重新生成轮廓"。
2. **240s 单任务总预算没强制**：`TASK_BUDGET_SECONDS` 定义了却没用。现已强制——
   预算耗尽即放弃剩余镜像，单次请求超时还会被剩余预算压住；用假时钟做了 2 个测试。
3. **"重新获取建筑"会静默无效**：`use_cache=False` 只绕开缓存不绕开快照。
   现在 `use_cache=False` 连本地快照一起绕开，语义才是"取最新的"。

## 遗留

- 快照是 2026-10-17 的，之后新建的楼不在里面；线上环境无法刷新（Overpass 不通）。
- "重新获取建筑"按钮在 NAS 上必然失败（要联网），界面会显示网络错误——这是诚实行为，不是 bug。
- 未做代理（方案 A）。若日后需要更新快照，走代理或从本机重新抓一份再提交。
