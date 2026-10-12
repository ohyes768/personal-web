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
