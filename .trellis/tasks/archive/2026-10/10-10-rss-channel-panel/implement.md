# RSS channel panel implementation plan

Goal: unify subscription and management in a compact channel dialog.
Architecture: reuse ChannelPanel, API, CopyText and RelayDialog; notify the page on successful mutations.
Tech Stack: Next.js, React, TypeScript, Tailwind.

- [x] Replace management mode with one list, compact rows, search, disabled filter and inline form.
- [x] Add accessible disclosure actions and preserve stop confirmation, copy fallback and token handling.
- [x] Replace homepage entries and refresh registered channels after mutations.
- [x] Update README/contracts; verify TypeScript, production build and browser interactions where available.

## Verification
- `npx tsc --noEmit`: passed.
- `npm run build`: passed after stopping dev server (simultaneous dev/build writes to .next caused an earlier prerender failure).
- Playwright, mocked channels: search, create, edit, disable confirmation, restore, create-to-homepage sync, example disclosure, Escape, desktop and375px layouts passed.
- Mobile rows: 71.66px, system row70.66px, no horizontal overflow. Screenshots: desktop.png, mobile.png.
- Local RSS token absent, feed copy remains disabled as expected; CopyText implementation and manual fallback unchanged.
- Code remains uncommitted; no deployment performed.
