# Skill Manager backend

## Pre-Development Checklist

Read [Repository packs](./repo-packs.md) before GitHub changes. Also read shared
guides/skill-manager-registry-sync.md, skill-manager-export-targets.md and
backend/testing-environment.md for local/ZIP/Windows boundaries.

## Quality Check

Run backend tests and frontend lint/typecheck/test. Clearly record Windows
requires_symlink skips rather than claim they pass; actual target deployment
needs separate Agent discovery verification. Explicit user test-scope choices
take precedence over the default Linux validation recommendation.
