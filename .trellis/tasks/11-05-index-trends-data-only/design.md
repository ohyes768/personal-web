# Data service ownership

Delete ReportService and DingTalkNotifier and their feature tests. Replace ReportScheduler with a single-job RefreshScheduler. Keep the daily callback's try/finally valuation collection and startup valuation task. Track the actual scheduled daily task for bounded shutdown, retaining Shanghai timezone and existing cron defaults.

Remove report-settings and report-jobs APIs, keeping GET reports for existing history. Keep Store schema/migrations and historical access unchanged to preserve deployed databases. Remove report-only environment settings, NAS compose injection and unused ReportSettings frontend type. Preserve ReportRecord as the historical response type.

Rollback is a code rollback; no data migration/deletion is required. Production remains unchanged until deployment.
