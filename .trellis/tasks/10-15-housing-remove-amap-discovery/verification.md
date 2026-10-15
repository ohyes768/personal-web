# 验收 · 2026-10-15

- 删除高德区域polygon请求、细分扫描、分页/预算/覆盖报告、AmapIncomplete及amap适配器。管理页取消采集来源选择，固定透明售房网；采集POST默认且只接受单个tmsf。
- API传amap或tmsf+amap返回422且不启动任务；collect_names和DirectoryJob.start在任何处理/报告写入之前拒绝amap，包括注入自定义适配器。相关接口/服务/UI测试先失败再实现通过。
- 保留AmapClient.search_name、normalize_poi、密钥解析/错误脱敏，以及已知小区坐标补全、地图、历史高德来源筛选/关联/分类。数据库历史coverage和错误报告继续原样读取，未迁移/删除历史数据。
- 删除退役区域扫描测试；保留并验证位置/地区/边界/附属设施过滤、住宅用途线索、密钥脱敏。采集完成生成候选的测试改用TMSF，历史失败报告测试增加旧coverage持久化。
- 全量后端：`.venv\Scripts\python.exe -m pytest --basetemp=.pytest-tmp-remove-amap-full -q` → **456 passed**，61.98秒，退出0。3条原有Starlette/anyio和GBK子进程解码警告未隐藏。
- 前端：`npm run lint`、`npx tsc --noEmit`通过；全套node测试 **54 passed**；`npm run build -- --webpack`成功（编译11.9秒、TypeScript12.5秒、静态页与追踪完成），退出0。
- `git diff --check`通过；运行时无place/polygon、amap_names或AmapIncomplete引用。未运行任何上游采集，未部署、改生产数据、提交或推送；其他窗口的skill-manager等改动保留。
