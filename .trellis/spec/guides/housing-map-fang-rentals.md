# Housing-map Fang rental collection contract

Standalone CLI: `backend/housing-map/scripts/fetch_fang_rentals.py`; implementation: `src/services/fang_rentals.py`; usage: `scripts/FANG_RENTALS.md`. Downstream integration (mapping ledger, statistics, publish, API, dashboard): [housing-map-rental-reference.md](./housing-map-rental-reference.md).

- Only public HTTPS Hangzhou Fang rental URLs. Validate redirects and pagination; login/challenge/unrecognized HTML is an error, not an empty success.
- Source community IDs are Fang IDs, not TMSF IDs. Read actual community links; titles may mention unrelated communities. Mapping requires address and phase verification.
- Read area/layout from structured pipe-separated information paragraphs before considering title text.
- Records are monthly asking rents, never signed rents. Batch capture timestamp is not publish/maintenance time; published_at stays null unless independently verified.
- Keep shared/partition-suspect/nonresidential samples with quality flags for review. No automatic rental averages or yields from low samples.
- De-duplicate by source listing ID across pages; this does not imply same-property deduplication.
- All requests have delay; pagination bounded. Detail errors retain list samples and return failure status. Run report contains errors and truncated seed URLs.
- Dedicated output files only; atomic per-file replacement, no concurrent writers or pair-level transaction guarantee. Existing price snapshots and API contracts are untouched.
- Offline tests and Windows basetemp on project drive required. Live smoke tests are low-volume, manual only; do not create automated follow-ups without user authorization.

## Request resilience (2026-10-18)

- All FangClient HTTP hops use FangRequestPolicy: a stable OS sidecar lock serializes same-data-directory clients/processes; last completion time enforces a minimum 5-second gap, including redirects. Do not add another Fang HTTP path outside this policy.
- `rentals/fang_request_state.json` persists version, last_request_at, challenge_level and cooldown_until (UTC epoch). First explicit slider redirect or recognized challenge body stops the batch, including detail failures. Consecutive challenges cool down for 1h/6h/24h; complete successful real rental publication (or complete standalone crawl) resets the level only when no active cooldown remains. Single list success or clock expiry does not reset it.
- Cooling down performs no HTTP and does not extend the deadline. Malformed state causes a conservative one-hour pause with diagnostics. Ordinary timeouts retry at most once after 30 seconds; two timeouts stop that client's round, without labelling it a slider challenge. Waiting for lock/rate/retry supports cancellation.
- `rentals/fang_details/` holds versioned, atomically replaced per-listing static detail entries keyed by Fang listing ID and Fang community ID. Seven-day TTL; cache address/property_type only, retain independent detail_verified_at and detail_fetched. Fresh list owns rent/area/layout/membership. Failures/challenge pages never populate cache; invalid or expired entries are discarded, startup pruning is bounded.
- CLI, source discovery and legacy directory Fang collection reuse the same policy/cache. Discovery propagates detail challenge/cancellation instead of treating it as an ordinary missing-address candidate. Never log full HTML, cookies or full redirect query strings.
- Offline regression coverage: `test_fang_resilience.py`, `test_fang_rentals.py`, `test_fang_rentals_run.py`, plus rental refresh/association/storage/API suites.
