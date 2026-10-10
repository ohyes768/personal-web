# 执行计划

1. 记录现有包体积基线，安装echarts并明确图表描述契约。
2. 实现主题/option构建、共享渲染壳、ResizeObserver和范围联动。
3. 迁移所有Tab及对比四种模式，加入稳定上下文标识；删除Plotly残留。
4. 单测验证空值、双轴、tooltip变换、范围同步；运行tsc及生产构建。
5. 桌面/375px验证全部Tab、缩放复位、切Tab、图例和对比模式，比较bundle。
6. 更新ECharts spec与任务验证记录；按Trellis提交流程收尾。

执行命令：pnpm --dir apps/macro exec tsc --noEmit；pnpm --dir apps/macro build。构建前确认该目录dev已停止，避免.next互相污染。
