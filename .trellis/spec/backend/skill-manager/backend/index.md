# Skill Manager backend

## Pre-Development Checklist

Read [profile contracts](profiles.md) and shared registry/cache/export guides before changing target resolution, plans, migrations or deployment state.

## Quality Check

Run `uv run pytest` from backend/skill-manager. Use real symlinks for filesystem behavior; only skip with the existing requires_symlink privilege marker. Review old hermes identity, unavailable profile references, request validation before source preparation, password boundaries and shared cache updates.
