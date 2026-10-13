# 需求
## 目标
在小区管理 Tab 直观看到每条记录的住宅状态，可筛选住宅/待核实/非住宅。
## 验收
- 列表新增 residential 状态列：✅住宅 / ❓待核实 / ❌非住宅。
- 工具栏增加下拉：residential_state in {all, residential, pending, non_residential}。
- 详情页或管理面板上显示物业类型来源（tmsf/fang）与原始页链接。
- 当类型冲突或缺失时，提供"标记为已核实"操作。