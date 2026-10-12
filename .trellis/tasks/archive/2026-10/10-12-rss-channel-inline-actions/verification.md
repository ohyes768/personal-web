# Verification

- TypeScript `npx tsc --noEmit`: passed.
- Production `npm run build`: passed.
- Playwright with mocked channels: edit and stop visible immediately; no overflow menu; edit/save, stop confirmation/cancel, restore, protected system channel passed.
- 375px: action buttons on description row; ordinary rows73px, system70.66px; no horizontal overflow.
- 1440px: actions beside copy button; row height below75px; no overflow.
- Screenshot inspected: mobile.png.
- No commit or deployment performed in this follow-up.
