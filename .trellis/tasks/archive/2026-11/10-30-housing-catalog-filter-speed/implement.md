# Implementation plan

Goal: unchanged data reuses projections; next read reflects changes.

- [x] Write failing cache tests, then implement bounded cache with file/DB invalidation, concurrency and copy isolation tests.
- [x] Group matched sources in community_admission.py and directory_workflow.py; test lookup work grows linearly.
- [x] Add request-flow regression and split summary/list loading, preserving unrelated edits.
- [x] Run backend and frontend checks; see validation.md for the exact results and environment limitations.
- [x] Review source and update directory-flow spec. No business-data migration.
- [ ] NAS deployment and cold/warm measurements remain pending; user next requested a local Git commit only.
