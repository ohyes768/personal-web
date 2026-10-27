# Cached certificate retry investigation (2026-10-27)

## Evidence

- Production browser is healthy and running snapshot fix image `85c52a3bb0ff1714f7685fc4fe5dd5799f66eb76b64c28dc44391582d968e0f0`.
- Latest stored collection: 06:18:04–06:18:55 UTC, retry_failed, 18 existing, 1 successful type, 0 failed types, 17 deferred. Error is source 1404301782 (领界大厦) missing certificate location due browser_timeout. Its source already retains 非住宅; no valid full address is saved.
- Earlier log specifically shows Page.goto commit timeout on `presell_33_1404301782_1640067349.htm`, not on its project homepage.
- Source `newhouse_detail_cache.checked_at=2026-10-27T05:48:57.703830+00:00` contains verified project/type/status facts, truncated address error and one certificate link. `_project_detail(previous=source)` accepts this cache for 24h and directly requests the certificate. A new BrowserClient task creates a fresh browser context; cached facts are not browser/session state.
- Cold-certificate controlled read: timeout after 10.19s readiness observation, document.readyState=loading, #locatedrr empty, no `.captcha` element. The certificate URL returned two HTTP200 responses; no presell-info API response was observed in that interval.
- Warm controlled read, fresh browser: homepage succeeds in 5.17s; after a 3s pause, certificate succeeds at cumulative11.38s. #locatedrr contains `杭州市滨江区东信大道1188号（东信大道与江南大道交汇处）`, readyState=complete, and `NewPropertyHz_createPresellInfo.jspx` returns200.
- A third cold-load observation exceeded the SSH command's50s limit without a complete returned record. Do not classify that incomplete diagnostic as success or infer its detailed failure cause.
- These reads never invoked ingest/enrich or started collection tasks. No production service or source change was made during this investigation.

## Bug analysis

### 1. Root cause category

E (implicit assumption) and D (test coverage gap): a fresh evidence cache was assumed to allow deep-page navigation with a new browser context. Earlier full-flow smoke checks omitted `previous`, and so always visited the homepage first. Evidence supports a cold-vs-warm path difference; it does not yet identify cookies, session initialization, asset caching or external script delays as the sole mechanism.

B (cross-layer contract): BrowserClient caches every BrowserFetchError as task-wide failure. An individual certificate timeout is caught as partial address_error in `_project_detail`, but client.failure still blocks every later project. A partial source failure is thereby expanded into17 deferred sources.

### 2. Why earlier fixes were insufficient

DOMContentLoaded wait and count/text_content race were real faults and were fixed. Neither addressed the actual cached-source retry route or the blanket failure latch. Passing uncached single-page reads was insufficient acceptance evidence.

### 3. Prevention and proposed design (not implemented)

- Test with the real shape of persisted previous.newhouse_detail_cache and a fresh browser task, not just no-previous flows.
- Establish the own-project browser context before a cold certificate request, without treating cached facts as a cookie/profile cache. Preserve exact project identity and certificate checks. Measure bounded cold-vs-warm behavior; do not assume simply increasing timeout fixes it.
- Separate per-project navigation/content timeout from task-wide pause. Continue other projects after an isolated timeout; stop immediately for explicit manual verification and service unavailability, and cap consecutive transport failures to avoid uncontrolled requests during an outage.
- Add integration coverage for cached deep-link failure followed by another project succeeding; actual captcha must still defer all subsequent requests. Include the actual persisted cache in read-only NAS acceptance checks.

### 4. Systematic expansion

Presell address supplements and homepage retrieval share the same client latch. Preserve partial verified facts and the previous valid address, but make the lifecycle/pause decision explicit rather than hidden inside a catch that returns partial success. The current headline's type-success count should not imply complete project success when address_error remains.

### 5. Knowledge capture

This record preserves the architectural diagnosis before another implementation iteration. No further timeout tuning or production deploy was attempted. Updating the worker/client pause contract requires a planned implementation and tests, rather than claiming that one successful probe fixes the batch.
