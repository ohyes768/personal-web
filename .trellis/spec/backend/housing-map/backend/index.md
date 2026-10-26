# Housing-map backend

## Pre-Development Checklist
- Read [Candidate-to-admission pipeline v2](./collection-pipeline.md) before changing the versioned candidate identity, selected-POI use evidence, strict admission or full re-review migration. It supersedes v1 position/use behavior only after explicit activation.
- Read [Amap position status](./directory-position.md) for catalog POI states, per-community query/confirmation, historical coordinates and manual position protection.
- Read [TMSF directory workflow](./directory-flow.md) for TMSF-only admission, five collection tasks, auction-only association and explicit offline migration; it supersedes the legacy multi-source review flow after activation.
- Read [Amap use-category review](./use-review.md) when changing the second-source use evidence, the conflict matrix, the batch review job or the human use confirmation.
- Read [New residential projects and enrichment](./community-enrichment.md) for newhouse identity/use evidence, bounded position repair and price isolation.
- Read [TMSF newhouse browser](./tmsf-browser.md) for the independent Playwright worker, session/pause protocol, presell location evidence and read-only preview.
- Read [Automatic residential review](./community-auto-review.md) for read-only snapshots, explicit enablement, automatic decisions and manual vetoes.
- Read [Unified community review](./community-review.md) for candidate aggregation, member transactions, synchronization and the two management lists.
- Read [Community admission](./community-admission.md) when changing residential status, human withdrawal, migration or map membership; it supersedes the earlier display scope.
- Read [Community directory](./community-directory.md) for names, multi-source identity, automatic/manual association, deletion and discovery. It supersedes the original human-only rental-source model in the current deployment.
- Read [Rental sources](./rental-sources.md) when changing source discovery, confirmation, migration or refresh membership.
- Read [Xingfuli rental pilot](./xingfuli-rentals.md) for provider selection, seed-vs-neighborhood IDs, explicit pilot import and cross-provider snapshot isolation.
- Read [Rental reference](../../../guides/housing-map-rental-reference.md) when changing statistics, snapshots, availability or dashboard columns.
- Read [Fang collection](../../../guides/housing-map-fang-rentals.md) for public source collection and URL constraints.

## Quality Check
- `backend/housing-map/.venv/bin/python -m pytest` from the backend directory (use `.venv/bin/python`, with a separate `--basetemp`).
- Related frontend: `npm run lint`, `npx tsc --noEmit`, `node --test tests/*.test.cjs`, `npm run build` from `apps/housing-map`.
- Verify existing-volume migration, source uniqueness, refresh/edit exclusion, and old snapshot isolation on source changes.
- Verify management on desktop/mobile with disposable source data; live source requests are low frequency and bounded.
