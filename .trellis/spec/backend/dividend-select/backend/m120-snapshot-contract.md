# M120 Snapshot Continuity

- `M120_CSV_FILE` is the dynamic **write** destination for the current week in the current month directory. Refresh must preserve previous snapshots.
- `_read_latest_m120_snapshot()` selects the latest usable snapshot by week start, searching month directories across month/year boundaries. Do not sort by modification time: restored backups may have newer mtimes.
- Exclude future week/month files. Require nonempty CSVs with six-digit string stock codes and finite positive M120 values; skip unusable snapshots and continue to older ones.
- M120 data, deviation reads, file availability and last-updated timestamps must all refer to the selected readable snapshot. `/m120/status` must not check the current write destination to decide whether a historical read snapshot has a timestamp.
- Preserve the actual historical timestamp when falling back. Missing coverage remains reported by the existing stock-code comparison.
- APScheduler weekday numbers differ from standard crontab. Use `sat` for Saturday 02:00, with `Asia/Shanghai` on the trigger. Production loads `src/scheduler/scheduler.json` from the backend image, deliberately outside the config volume. Rebuild/restart the backend to apply source changes and verify the live next-run timestamp.
- Regression coverage: `tests/test_m120_rollover.py` exercises rollover, invalid/future files, current snapshot preference, historical preservation and status timestamps without market API access.
