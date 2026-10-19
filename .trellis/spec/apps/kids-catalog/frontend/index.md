# Kids Catalog frontend

## Pre-Development Checklist

Read app/page.tsx, app/device-playlist.tsx, app/globals.css and [device directory contracts](../../../backend/kids-catalog/backend/device-directory.md). Preserve the established cream/orange/green visual style. Use `/api/kids/` for API requests; next.config.mjs handles the existing rewrite with basePath:false.

## Quality Check

Run `pnpm exec tsc --noEmit` and `pnpm build`. Check desktop and 390px mobile layouts. Keep the last snapshot visible while generation is running or a request fails. Poll only while a generation is running; clean up timers on unmount. Disable concurrent actions, report request failures, and make history-completion confirmation an explicit user action. Tables must have headers and status messages must be accessible.
