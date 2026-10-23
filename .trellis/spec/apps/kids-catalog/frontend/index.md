# Kids Catalog frontend

## Pre-Development Checklist

Read app/page.tsx, app/device-playlist.tsx, app/globals.css and [device directory contracts](../../../backend/kids-catalog/backend/device-directory.md). Preserve the established cream/orange/green visual style. Use `/api/kids/` for API requests; next.config.mjs handles the existing rewrite with basePath:false.

## Page Structure

`/kids` has two tabs carried in the query string (`?tab=catalog` default, `?tab=playlist`): 「本月精选」keeps the album catalog, 获取最新 and downloads; 「设备歌单」holds the device playlist, the candidate checklist and the skipped-collection confirmation flow. `useSearchParams` needs a Suspense boundary or the production build fails.

## Quality Check

Run `pnpm exec tsc --noEmit` and `pnpm build`. Check desktop and 390px mobile layouts. Keep the last snapshot visible while generation is running or a request fails. Poll only while a generation is running; clean up timers on unmount. Disable concurrent actions, report request failures, and make history-completion confirmation an explicit user action. Tables must have headers and status messages must be accessible. The candidate checklist defaults to every candidate checked and keeps the user's unchecks across refreshes; block generation when nothing is checked instead of sending an empty selection.
