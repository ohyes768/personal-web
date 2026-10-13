# Housing-map backend

## Pre-Development Checklist
- Read [Community directory](./community-directory.md) for names, multi-source identity, automatic/manual association, deletion and discovery. It supersedes the original human-only rental-source model in the current deployment.
- Read [Rental sources](./rental-sources.md) when changing source discovery, confirmation, migration or refresh membership.
- Read [Rental reference](../../../guides/housing-map-rental-reference.md) when changing statistics, snapshots, availability or dashboard columns.
- Read [Fang collection](../../../guides/housing-map-fang-rentals.md) for public source collection and URL constraints.

## Quality Check
- `backend/housing-map/.venv/bin/python -m pytest` from the backend directory (use `.venv/bin/python`, with a separate `--basetemp`).
- Related frontend: `npm run lint`, `npx tsc --noEmit`, `node --test tests/*.test.cjs`, `npm run build` from `apps/housing-map`.
- Verify existing-volume migration, source uniqueness, refresh/edit exclusion, and old snapshot isolation on source changes.
- Verify management on desktop/mobile with disposable source data; live source requests are low frequency and bounded.
