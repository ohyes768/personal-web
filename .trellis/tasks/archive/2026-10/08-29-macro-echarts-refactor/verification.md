# 验证记录（2026-10-10，Asia/Shanghai）

## 自动检查
- TypeScript：`cd apps/macro && ./node_modules/.bin/tsc --noEmit` 通过。
- 图表测试：本地 tsc 将 echartsOptions.test.ts 编译到临时目录，`node --test` 8/8通过。覆盖双轴、空值、非有限值、日期对齐、缩放复位、变换tooltip、不可变输入、首尾日期标签及空图无孤立缩放组件。
- 生产构建：`next build` 通过，8个静态页面生成成功。
- `git diff --check` 通过。
- 独立lint没有通过：仓库无ESLint配置，`next lint`要求交互初始化；未擅自引入全项目lint配置。

## 浏览器验收
使用当前生产构建和只监听本机、拒绝POST的合成数据服务；不更新真实数据。
- 七个图表Tab均渲染；四种对比模式逐一走查。
- 实际拖动滑条：rates三图同时变为2026-06-12至2026-10-09；复位后三图range=null。
- 图例开关、隐藏Tab重绘、1440px与375px均检查，无横向溢出。
- 手机日期标签修复后首尾标签完整，双轴与完整单位标题可读。
- 空选择发现并修复ECharts孤立dataZoom问题：取消全部指标显示空状态，重新选中国利差恢复1个canvas，无页面异常。
- 桌面/手机截图保存在/private/tmp/macro-echarts-desktop.png与macro-echarts-mobile.png。

## 包体积
同一Next/依赖环境的HEAD源代码在临时目录构建作为Plotly基线。初始页面First Load JS基本不变（112kB），因为图表原本已按需加载；改善在异步图表代码。
- Plotly最大图表块：4,526,679字节，gzip 1,323,661字节。
- 当前ECharts构建：{"total_js": 1725148, "total_gzip": 555785, "largest_chunk": [612722, 208143, "499.03bf234acacaf1b5.js"]}。
- 基线全量static/chunks JS：5,646,404字节；gzip合计1,673,483字节。此指标是所有页面代码总量，不代表单页网络请求总量或加载耗时。

## 范围与收尾
模型未接入；已有ChartContext/onContextChange预留接口，Agent任务依赖已更新。真实第三方源和线上部署未执行。代码等待用户确认提交；其他任务工作区改动排除。
