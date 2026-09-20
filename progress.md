# Progress

- 2026-09-20: User approved the curl_cffi lightweight transport and service integration design. Design addendum and implementation plan created.
- 2026-09-20: Added fetcher contract tests before implementation; expected to fail until the new service exists.
- 2026-09-20: Created `src/services/tmsf_fetcher.py`; it centralizes Chrome-fingerprint transport, parsers and snapshot output.
- 2026-09-20: Added refresh integration tests for residential target selection and in-process merge; expected to fail until refresh drops subprocess execution.
- 2026-09-20: Refresh now runs in-process; legacy price CLI and the Binjiang bulk script both call the shared fetcher for active collection paths.
- 2026-09-20: Updated the shared legacy `fetch_html` entry and property-type collector to use the same light Chrome-fingerprint transport.
- 2026-09-20: CLI subprocess reproduction showed `src` cannot be imported when a script is run directly; added a regression test before fixing its module path.
- 2026-09-20: Replaced the old price script implementation with a thin shared-service CLI wrapper; refreshed the HTTP refresh documentation to reflect in-process execution.
- 2026-09-20: Added an all-failure refresh regression so a fully blocked source cannot be reported as a successful update.
- 2026-09-20: Added a retry regression for transient TMSF transport failures.
