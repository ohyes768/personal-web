# M120 weekly rollover

## Requirements
- Continue reading the latest valid M120 snapshot across Monday and month/year boundaries until a new snapshot is available.
- Keep refresh writes in the current week's file; preserve historical snapshots.
- Status, timestamps and deviation reads must use the same selected snapshot.
- Empty or malformed snapshots must not hide usable historical data. Future snapshots must not be selected.
- Configure weekly refresh explicitly for Saturday 02:00 Asia/Shanghai.

## Acceptance
- Regression tests reproduce the original rollover failure before implementation and pass afterwards.
- Existing CSV path, M120, status and scheduler tests pass without live market calls.
- Deployment is separate from the local source fix; report whether production has been updated.
