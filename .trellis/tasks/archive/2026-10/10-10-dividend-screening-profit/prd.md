# Goal
Enhance dividend screening with configurable single-quarter adjusted profit decline and positive annual adjusted profit.
# Requirements
- Positive percentage threshold defaults to 30; either adjacent quarter YOY <= negative threshold excludes; retain two negative quarters exclusion and one mild negative warning.
- Latest annual adjusted net profit must be >0 and annual YOY >=0. Missing/nonfinite stays insufficient; definite failure wins.
- Persist threshold, default missing legacy field to 30, reset and changed-condition notice include it; API snapshots include it.
- Carry annual amount/year from latest 12-31 statement through CSV, reader, API and frontend; old cache signals update.
# Acceptance
Boundary -30 excludes; configurable 20/50 works; missing/nonfinite and failure precedence covered; old storage works; relevant backend tests and frontend types pass.
# Constraints
No other screening changes, no stock advice. Selective Chinese Conventional Commit, no push; preserve unrelated working files.
