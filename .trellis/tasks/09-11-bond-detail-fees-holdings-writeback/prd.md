# 债基·市场 tab 详情页自给自足：新套补写 FundFees + FundHoldingsBond

## Goal

债基·市场 tab 详情页当前依赖老债基三分法（v1 yaml）写的 FundFees/FundHoldingsBond。新套（v2 market pipeline）补写这两张表，让债基详情页自给自足，不依赖 v1 yaml。复用 fetch_fees/fetch_bond_hold fetcher，加并发阶段。

## Requirements

- TBD

## Acceptance Criteria

- [ ] TBD

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
