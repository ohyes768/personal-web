# Verification — 2026-10-29

- Red: API rejected refresh_all (422), service start rejected mode, matched/review/not_found were skipped, UI had no 更新全部 button.
- Backend full suite: 1093 passed (94.11s). Existing FastAPI/Starlette deprecation warnings and one unrelated subprocess GBK decode warning in test_tmsf_property_type; no failures.
- Frontend full suite: 169 passed. npm run lint and npx tsc --noEmit: exit 0.
- npm run build: exit 0 outside sandbox. Initial sandbox run could not connect to Turbopack CSS child process; unrestricted repeat compiled, typechecked and generated static routes successfully. Restored generated next-env.d.ts path change after the build.
- Static SSR preview using the real CollectionControls and project CSS: Playwright at 1440px and 390px; all three buttons within viewport, no dialog horizontal overflow. Screenshots controls-1440.png and controls-390.png under research/. This checks presentation only; action payloads and disabled/running behavior are covered in frontend tests, service behavior in backend tests.
- git diff --check: clean. No live collection, deployment, commit or push.
- Manual and current eligibility protection, compatibility all/no-body and collection followup preserved. Full refresh uses explicit refresh_all and existing request budget.
