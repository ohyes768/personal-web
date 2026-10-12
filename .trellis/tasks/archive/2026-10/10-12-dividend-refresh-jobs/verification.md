# 验收记录

2026-10-12，本地实现完成。未提交、推送或部署。

## 验证证据
- 后端：`python -m pytest tests -q --basetemp=F:/personal-projects/personal-web/.tmp/pytest-dividend-refresh-final`，244 passed、3 skipped。
- 前端：`node node_modules/typescript/bin/tsc --noEmit`，exit 0。
- 浏览器：`node node_modules/@playwright/test/cli.js test --reporter=line`，8 passed。包括页面恢复、受理后继续浏览、重复受理提示、抽屉关闭/重开、断网恢复、部分失败重试入口，以及原筛选/收藏回归。
- `git diff --check -- apps/dividend backend/dividend-select .trellis/spec/backend/dividend-select`，exit 0。
- 截图：`.tmp/dividend-refresh-progress.png`，已检查抽屉排版与状态展示。

## 验收映射
| AC | 证据 |
| --- | --- |
| AC1 | 阻塞采集器可等待120秒；释放前验证受理耗时<0.2秒、ASGI请求<0.5秒，进度查询独立返回。没有真实等待120秒或真实市场调用。 |
| AC2 | 任务与事件循环分离；浏览器关闭/重开抽屉、reload、断网恢复；完成后重载原数据与筛选结果。 |
| AC3 | 16个并发启动仅一个采集；同类API复用id；定时202 reused跳过；财务合并保持六位代码并替换旧行。 |
| AC4 | 管理器全成功/部分/全失败；M120五次失败熔断留下remaining；NaN/Inf/非正数失败；原子保存失败整体failed且旧字节保留；损坏财务旧缓存禁止覆盖。 |
| AC5 | 90天节流429，force=true更新指定代码，000090保留、无重复行；原季度/筛选/M120跨周测试全通过。 |
| AC6 | 模拟202 running后partial_failed，等待真实终态才返回历史；count/failed/remaining及refresh_job_id传入持久化并有前端标签。 |
| AC7 | queued/running持久记录重启为interrupted，不自动采集；关闭停止受理且不取消仍执行的线程。 |

## 已知环境限制及部署步骤
- 项目尚无 ESLint 配置；既有 lint 脚本进入配置问答并退出，不能报告 lint通过。本次未新建无关 lint配置。
- 沙箱内 Node 异步realpath返回EPERM，Next误判依赖缺失；只读诊断确认依赖存在，浏览器验证已在获自动批准的本机环境运行。
- 没有线上 nginx 错误日志或已加载配置证据；仅核对仓库 `/api/dividend/` 代理配置。当前504的具体网关原因仍未现场确认。
- 需要前后端同步部署，旧外部调用方不能再将HTTP202认作完成。仓库前端与定时调用方已迁移；HTTP200迁移兼容留在scheduler，确认外部升级后可删除。
- 线程关闭采用有限等待而非强制停止；部署/回滚应确保旧采集进程退出后才启动另一写入进程。部署后再核对线上刷新恢复和下一次定时历史。
