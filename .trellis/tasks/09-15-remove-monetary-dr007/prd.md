# 移除货币政策 DR007 推送

## 目标

货币政策 skill 不再抓取、保存、评分或向宏观信号接口推送 DR007；仅以 MLF 净投放和 LPR 生成货币政策信号。

## 验收标准

1. 运行入口不会调用或输出 DR007。
2. 构建出的 `macro_signal.json` 不含 `dr007`。
3. MLF、LPR 均可用时总分按 50/50 加权；单项缺失时正确归一化。
4. 测试通过，且不再存在 DR007 抓取模块。
## 扩展范围：月频上传边界

仅以下四个 skill 保留线上 `--upload`：`monetary-policy-skill`、`money-supply-skill`、`entity-economy-skill`、`inflation-skill`。`exchange-rate-skill` 与 `risk-appetite-skill` 移除 `--upload` 参数及上传分支；不改页面、后端和这四个 skill。