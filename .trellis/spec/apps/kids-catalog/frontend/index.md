# Kids Catalog frontend

## Pre-Development Checklist

Read app/page.tsx, app/device-playlist.tsx, app/globals.css and [device directory contracts](../../../backend/kids-catalog/backend/device-directory.md). Preserve the established cream/orange/green visual style. Use `/api/kids/` for API requests; next.config.mjs handles the existing rewrite with basePath:false.

## Page Structure

`/kids` has three tabs carried in the query string (`?tab=catalog` default, `?tab=manual`, `?tab=playlist`): 「本月精选」lists only `source='chart'` albums with 获取最新 and downloads; 「手动添加」holds the link-import form and only `source='manual'` albums (no month heading, no 获取最新); 「设备歌单」holds the device playlist, the candidate checklist and the skipped-collection confirmation flow. Device-playlist candidates keep coming from downloaded collections of BOTH sources. The album card is shared by the catalog and manual tabs; the 「手动添加」badge is redundant inside the manual tab and is not rendered. `useSearchParams` needs a Suspense boundary or the production build fails.

## Quality Check

Run `pnpm exec tsc --noEmit` and `pnpm build`. Check desktop and 390px mobile layouts. Keep the last snapshot visible while generation is running or a request fails. Poll only while a generation is running; clean up timers on unmount. Disable concurrent actions, report request failures, and make history-completion confirmation an explicit user action. Tables must have headers and status messages must be accessible. The candidate checklist (app/candidate-picker.tsx) defaults to every candidate checked and keeps the user's unchecks across refreshes; each row shows its ledger track count and a select-all/deselect-all toggle sits in the checklist header; block generation when nothing is checked instead of sending an empty selection.

## Browser Playback

The device playlist page (app/device-playlist.tsx) owns the playing state; the candidate checklist and the published-collection table both offer a 「播放」 action and share it, so only one collection plays at a time. The player (app/audio-player.tsx) expands only where playback was started — never two players for one collection. It provides previous/next (disabled on the first/last track), the native `<audio controls>` for pause/seek/volume, and an inline readable error when the collection directory is missing (never a blank page). Playback stops when the page unmounts. On 390px the published table keeps the 合集名称 column readable (about 100px, at most two lines) and must not introduce page-level horizontal scrolling.
