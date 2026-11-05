# index-trends 移除推送职责并保留 Web 每日刷新

## Goal

Hermes owns brief generation, scheduling and delivery. index-trends remains the Web data service and owns daily market/valuation refresh.

## Requirements

- Remove DingTalk delivery, weekly report generation/scheduling, startup catch-up and report configuration/trigger APIs.
- Preserve the weekday 16:30 Asia/Shanghai refresh, startup valuation initialization, manual refresh and all market/valuation read APIs.
- Preserve existing SQLite report/settings/attempt tables and historical report reads; no destructive migration.
- Remove obsolete configuration and frontend types; update deployment comments and package/spec documentation.
- Do not configure Hermes, deploy, commit or push in this task.

## Acceptance Criteria

- [x] Only daily_refresh is registered; shutdown drains or cancels that task.
- [x] Daily refresh calls market refresh and valuation refresh even when market refresh fails.
- [x] Startup has no report catch-up; existing report rows survive startup.
- [x] GET/PATCH report-settings and POST report-jobs return404; GET reports remains read-only.
- [x] Current status API contract remains unchanged and backend regression suite passes.

## Notes

- User approved removal after reviewing the ownership split and explicitly confirmed Web owns daily refresh.
