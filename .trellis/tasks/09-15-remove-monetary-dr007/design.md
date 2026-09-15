# 设计

原始载荷仅保留 `mlf` 和 `lpr`。推送 `details` 只包含 `mlf_net_yi`、`lpr_1y`、`lpr_5y`，综合分数由 MLF 和 LPR 各占 50%。后端兼容透传，因此无需修改 personal-web 接口或前端。