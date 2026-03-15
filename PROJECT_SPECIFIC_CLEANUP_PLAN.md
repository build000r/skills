# Project-Specific Cleanup Plan

Goal: keep intentionally public branded skill families, while removing repo-specific
operational state and genericizing examples that leak one live environment.

## Cleaned In This Pass

- Removed the tracked `0_claw` deploy workflow.
- Removed repo-root `.throngterm/` branding artifacts and ignored that directory going forward.
- Moved tracked runtime-safe custom skills from `openclaw-client-bootstrap/assets/instances/0_claw/custom-skills/`
  to `openclaw-client-bootstrap/assets/runtime-skills/`.
- Updated repo/docs references from `instances/0_claw/custom-skills` to `assets/runtime-skills`.
- Stopped whitelisting `assets/instances/0_claw/**` in gitignore rules.
- Replaced `ingredient-claw` / `0_claw` examples with generic `example-claw` or `<runtime-claw-id>` examples.
- Replaced `LARRY_ENV_PATH` / `larry.env` fallback handling with generic runtime env loading in `unclawg-respond`.
- Reduced a few generic-doc leaks (`htma-recipe.jpg`, `cyclechef-logo.png`, repo-root `.env-manager` assumptions).

## Kept Intentionally

- Public OpenClaw / Unclawg / SPAPS skill families.
- Public `throngterm-sprite` skill and `.throngterm` path convention inside skill docs.
- Public product URLs inside intentionally product-specific skills.

## Remaining Optional Cleanup

- Replace `~/repos/...` examples across generic mode templates with `/path/to/...` placeholders.
- Rework `.env-manager` mentions in generic skills if you want zero repo-family naming in public docs.
- Decide whether `find-customers-openclawth` should remain public or move to a private/runtime-only pack.
