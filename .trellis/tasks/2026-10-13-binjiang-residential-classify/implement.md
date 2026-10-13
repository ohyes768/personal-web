# 实施
1. 扩展 tmsf 物业类型采集（fetch_tmsf_property_type），输出 fang ID 维度。
2. 编写 residential_classifier.py，提供 CLI 与函数接口。
3. 为同名小区但物业类型冲突的样本生成报告。
4. 测试：
   - test_residential_classifier.py：覆盖各状态转换与冲突处理。
   - 校验候选规则与 examples/binjiang 期望。