# Findings

- InstallManager, legacy publish API and startup migration currently call stage_github_skill; planner computes planned_staging_dir.
- list_skills derives has_update from persisted check-time cached revision, so shared cache updates can leave sibling badges stale.
- Shared cache checkout is serialized by operation_lock, and changing a repo affects all installed direct links.
- Windows has no symlink privilege: requires_symlink tests must skip honestly. Existing four install API tests and cleanup test lack that marker and fail with WinError 1314.
- Developer script has two OpenClaw environment/mkdir lines; removed, diff and Hermes initialization verified.
- Real direct links share the repository HEAD. Using each member's older remote-check record could suggest a downgrade; installation/plans/lists now use the repository's newest successful check.
- Legacy staging directories are retained during migration, so missing cache or blocked targets cannot destroy the existing snapshot source. Normal direct links are skipped on repeated startups.
- A successful checkout can still raise because the selected Skill is removed in the new revision. Refresh sibling fingerprints in finally after HEAD changes, and block invalid sibling items without discarding their registered metadata.
