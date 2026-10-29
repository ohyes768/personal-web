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
