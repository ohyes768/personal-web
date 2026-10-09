# ECharts迁移设计

## 边界与数据流
保留各Tab数据获取、指标归一化/百分位/相关性计算。图表组件构建库无关ChartSeries、ChartLayout及子图规格，共享MacroEChart把描述转为按需引入的ECharts line/grid/tooltip/legend/dataZoom。删除Plotly包装、hook、类型shim与依赖。

## 交互
独立子图实例通过日期范围回调联动；共享范围使用不可变值并去重，程序同步不反向派发。日期按实际观测category对齐，空值保留为null、connectNulls=false。dataZoom滑条、内部缩放和显式复位；隐藏Tab用ResizeObserver重算。窄屏缩短轴标题，完整标题留在图上。tooltip保留原值和展示变换信息。对比图多单位分组不超过每图双轴。

## Agent接入
每个图定义稳定chartId、seriesId；ChartContext包含完整曲线列表、显示变换及可视日期范围，onContextChange可供下一任务接入，图例隐藏不改变主曲线列表。此层不传模型配置。

## 验证和回滚
先记录Plotly基线bundle，再迁移全图并比较构建产物。类型检查、构建、纯option/范围单测与真实桌面/375px交互验收。无后端更改，回退前端提交即可。
