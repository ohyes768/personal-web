# Verification — 2026-10-29

## Delivered

- Screening table: one clickable rating column with five slash-separated scores and parenthesized version, preserving partial/null positions; report also shows provenance.
- Skill source in F:/personal-projects/skills: contract 4.3.0, deterministic version stamp from its own SKILL.md, 11-field validator, synchronized reference docs and fixed-field-count tests.
- Backend: optional validated skill_version retained in score files, current installed metadata exposed, expected version captured per admission and checked against output, version-aware cache keys (unique attempt fallback when current version is unknown).
- Configuration: .env.example guidance and optional read-only installed-skill compose override at deploy/docker-compose.dividend-quality-version.example.yml. No production writes or publication.

## Checks

- Backend: `python -m pytest tests/test_quality_version.py tests/test_quality_service.py tests/test_quality_api.py tests/test_hermes_client.py -q` — 64 passed.
- Skill: `PYTHONUTF8=1 python -m unittest discover -s tests/basic-quality-rating` — 199 passed. UTF-8 mode avoids existing Windows GBK subprocess decoding assumptions.
- Browser: full screening.spec.ts — 18 passed; the extended five-dimension screenshot/never-rated test passed again after adding those assertions. Used a temporary Playwright config on port 3021 to avoid an occupied 3003.
- TypeScript: local typescript/bin/tsc --noEmit — passed.
- Skill script lint, git diff whitespace checks and compose override YAML parsing — passed. Impeccable mechanical detector returned no findings. Inspected the rendered 1600px table screenshot; compact score/version text, partial scores and the 需重评 hint align correctly.

## Deployment boundary

New code is not deployed. Publish the changed basic-quality-rating to the actual Hermes profile before setting an expected version. Configure HERMES_QUALITY_SKILL_PATH to a readable installed SKILL.md (optional compose override), or maintain HERMES_QUALITY_SKILL_VERSION explicitly. Unavailable metadata leaves current version unknown and does not claim scores are current. Old unversioned scores remain readable without backfill.

User requested commit and push after verification. The skill changes are committed and pushed as e8a1777; personal-web changes are included in the corresponding feature commit. Other active tasks' edits are excluded. No production deployment was run.

## Compact layout follow-up

User requested one column such as 4/4/3/2/1（v1.1.1）. Implemented directly; whole text opens the report, nullable dimensions use —, and version-unknown/needs-reanalysis semantics remain. Updated regression first failed on the missing 评级结果 header, then all 18 screening browser tests and TypeScript passed. Inspected the new screenshot.

## 4.4.0 no-stars follow-up

- Removed the modal's aggregate stars/count, overall unrated banner and boundary banner, preserving dimension rows, version, dates, elapsed duration and reanalysis.
- Skill 4.4.0 removes star/boundary report sections and adds finalizer rejection of aggregate rating prose in summary/report_md/risks/watch_points. JSON arithmetic and all 11 fields remain compatible. Read-only validation no longer requests a boundary section. Tests allow actual hotel grades and 三星电子 business facts.
- Red/green evidence: new skill narrative tests initially failed; the browser regression initially exposed the old ⭐⭐⭐/3-star boundary display. After implementation: skill full suite 203 passed, skill Ruff checks passed, TypeScript passed. Full screening suite: 21/22 passed on the first run, with an in-progress queue-cancellation test timing out; both that test and the new historical-star regression passed in an isolated 2-test rerun. No queue-control code was changed in this follow-up.
- Updated deployment examples to 4.4.0. User subsequently requested commit/push: skill commit 630c85f, frontend/spec changes in the corresponding personal-web feature commit. No production deployment. Historical stored report narratives remain archival; publish the new skill and reanalyze to regenerate those texts without stars.
