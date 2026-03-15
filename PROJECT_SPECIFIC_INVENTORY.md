# Project-Specific Inventory

Baseline inventory captured before the cleanup pass. See
`PROJECT_SPECIFIC_CLEANUP_PLAN.md` for disposition and what was actually changed.

Generated from tracked files in this repo using `git ls-files` plus targeted scans for high-confidence project identifiers. I excluded broad/generic matches like `Codex`, `Claude`, `Reddit`, `LinkedIn`, and false positives like the plain word `ingredients`.

## High-Confidence Project/Product-Specific Tracked Content

### 1. OpenClaw / Unclawg / SPAPS stack

These are not generic skills; they are branded and/or operationally tied to the OpenClaw / Unclawg / SPAPS stack.

- [`.github/workflows/deploy-0-claw-runtime-skills.yml`](/Users/b/repos/opensource/skills/.github/workflows/deploy-0-claw-runtime-skills.yml)
- [`.gitignore`](/Users/b/repos/opensource/skills/.gitignore)
- [`README.md`](/Users/b/repos/opensource/skills/README.md)
- [`_shared/agent-bootstrap.md`](/Users/b/repos/opensource/skills/_shared/agent-bootstrap.md)
- [`openclaw-client-bootstrap/.gitignore`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/.gitignore)
- [`openclaw-client-bootstrap/SKILL.md`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/SKILL.md)
- [`openclaw-client-bootstrap/assets/client-kit/.env.example`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/assets/client-kit/.env.example)
- [`openclaw-client-bootstrap/assets/client-kit/AGENTS.md`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/assets/client-kit/AGENTS.md)
- [`openclaw-client-bootstrap/assets/client-kit/README.md`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/assets/client-kit/README.md)
- [`openclaw-client-bootstrap/assets/client-kit/SOUL.md`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/assets/client-kit/SOUL.md)
- [`openclaw-client-bootstrap/assets/client-kit/USER.md`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/assets/client-kit/USER.md)
- [`openclaw-client-bootstrap/assets/client-kit/checklists/FIRST_CLAW_CHECKLIST.md`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/assets/client-kit/checklists/FIRST_CLAW_CHECKLIST.md)
- [`openclaw-client-bootstrap/assets/client-kit/checklists/OPERATOR_RUNBOOK.md`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/assets/client-kit/checklists/OPERATOR_RUNBOOK.md)
- [`openclaw-client-bootstrap/assets/client-kit/openclaw.json`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/assets/client-kit/openclaw.json)
- [`openclaw-client-bootstrap/assets/client-kit/scripts/01-bootstrap-do.sh`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/assets/client-kit/scripts/01-bootstrap-do.sh)
- [`openclaw-client-bootstrap/assets/client-kit/scripts/02-install-tailscale.sh`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/assets/client-kit/scripts/02-install-tailscale.sh)
- [`openclaw-client-bootstrap/assets/client-kit/scripts/03-install-openclaw.sh`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/assets/client-kit/scripts/03-install-openclaw.sh)
- [`openclaw-client-bootstrap/assets/client-kit/scripts/04-validate.sh`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/assets/client-kit/scripts/04-validate.sh)
- [`openclaw-client-bootstrap/assets/client-kit/scripts/05-setup-collab-tmux.sh`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/assets/client-kit/scripts/05-setup-collab-tmux.sh)
- [`openclaw-client-bootstrap/assets/client-kit/security/PERMISSIONS_PLAYBOOK.md`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/assets/client-kit/security/PERMISSIONS_PLAYBOOK.md)
- [`openclaw-client-bootstrap/assets/client-kit/security/WRITE_GATEWAY_CONTRACT.md`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/assets/client-kit/security/WRITE_GATEWAY_CONTRACT.md)
- [`openclaw-client-bootstrap/assets/instances/README.md`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/assets/instances/README.md)
- [`openclaw-client-bootstrap/assets/instances/0_claw/custom-skills/find-customers-openclawth/SKILL.md`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/assets/instances/0_claw/custom-skills/find-customers-openclawth/SKILL.md)
- [`openclaw-client-bootstrap/assets/instances/0_claw/custom-skills/unclawg-discover/SKILL.md`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/assets/instances/0_claw/custom-skills/unclawg-discover/SKILL.md)
- [`openclaw-client-bootstrap/assets/instances/0_claw/custom-skills/unclawg-feed/SKILL.md`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/assets/instances/0_claw/custom-skills/unclawg-feed/SKILL.md)
- [`openclaw-client-bootstrap/assets/instances/0_claw/custom-skills/unclawg-internet/SKILL.md`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/assets/instances/0_claw/custom-skills/unclawg-internet/SKILL.md)
- [`openclaw-client-bootstrap/assets/instances/0_claw/custom-skills/unclawg-respond/SKILL.md`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/assets/instances/0_claw/custom-skills/unclawg-respond/SKILL.md)
- [`openclaw-client-bootstrap/references/deployed-instances.example.md`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/references/deployed-instances.example.md)
- [`openclaw-client-bootstrap/references/deployment-workflow.md`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/references/deployment-workflow.md)
- [`openclaw-client-bootstrap/references/read-only-governance.md`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/references/read-only-governance.md)
- [`openclaw-client-bootstrap/references/review-rubric.md`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/references/review-rubric.md)
- [`openclaw-client-bootstrap/scripts/new_client_kit.sh`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/scripts/new_client_kit.sh)
- [`openclaw-client-bootstrap/scripts/review_kit.sh`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/scripts/review_kit.sh)
- [`openclaw-client-bootstrap/scripts/review_live.sh`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/scripts/review_live.sh)
- [`openclaw-client-bootstrap/scripts/sync-runtime-skills.sh`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/scripts/sync-runtime-skills.sh)
- [`openclaw-client-bootstrap/scripts/talk.sh`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/scripts/talk.sh)
- [`openclaw-client-bootstrap/scripts/update-oauth-token.sh`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/scripts/update-oauth-token.sh)
- [`openclaw-client-bootstrap/scripts/validate_client_kit.sh`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/scripts/validate_client_kit.sh)
- [`openclaw-docs-audit/SKILL.md`](/Users/b/repos/opensource/skills/openclaw-docs-audit/SKILL.md)
- [`openclaw-docs-audit/references/config-schema-snapshot.md`](/Users/b/repos/opensource/skills/openclaw-docs-audit/references/config-schema-snapshot.md)
- [`openclaw-docs-audit/scripts/audit.sh`](/Users/b/repos/opensource/skills/openclaw-docs-audit/scripts/audit.sh)
- [`unclawg-discover/SKILL.md`](/Users/b/repos/opensource/skills/unclawg-discover/SKILL.md)
- [`unclawg-discover/references/competitor-signals.md`](/Users/b/repos/opensource/skills/unclawg-discover/references/competitor-signals.md)
- [`unclawg-discover/references/feed-quality-checklist.md`](/Users/b/repos/opensource/skills/unclawg-discover/references/feed-quality-checklist.md)
- [`unclawg-discover/references/mode-example-checklist.md`](/Users/b/repos/opensource/skills/unclawg-discover/references/mode-example-checklist.md)
- [`unclawg-discover/references/mode-template.md`](/Users/b/repos/opensource/skills/unclawg-discover/references/mode-template.md)
- [`unclawg-discover/references/personas.md`](/Users/b/repos/opensource/skills/unclawg-discover/references/personas.md)
- [`unclawg-discover/references/target_profiles.md`](/Users/b/repos/opensource/skills/unclawg-discover/references/target_profiles.md)
- [`unclawg-discover/references/twitter-replyguy.md`](/Users/b/repos/opensource/skills/unclawg-discover/references/twitter-replyguy.md)
- [`unclawg-discover/references/voice-guide.md`](/Users/b/repos/opensource/skills/unclawg-discover/references/voice-guide.md)
- [`unclawg-discover/scripts/package_public.sh`](/Users/b/repos/opensource/skills/unclawg-discover/scripts/package_public.sh)
- [`unclawg-discover/scripts/reddit_user_socials.sh`](/Users/b/repos/opensource/skills/unclawg-discover/scripts/reddit_user_socials.sh)
- [`unclawg-discover/scripts/search_hn.sh`](/Users/b/repos/opensource/skills/unclawg-discover/scripts/search_hn.sh)
- [`unclawg-discover/scripts/search_indeed.sh`](/Users/b/repos/opensource/skills/unclawg-discover/scripts/search_indeed.sh)
- [`unclawg-discover/scripts/search_instagram_comments.sh`](/Users/b/repos/opensource/skills/unclawg-discover/scripts/search_instagram_comments.sh)
- [`unclawg-discover/scripts/search_linkedin.sh`](/Users/b/repos/opensource/skills/unclawg-discover/scripts/search_linkedin.sh)
- [`unclawg-discover/scripts/search_linkedin_jobs.sh`](/Users/b/repos/opensource/skills/unclawg-discover/scripts/search_linkedin_jobs.sh)
- [`unclawg-discover/scripts/search_log.sh`](/Users/b/repos/opensource/skills/unclawg-discover/scripts/search_log.sh)
- [`unclawg-discover/scripts/search_reddit.sh`](/Users/b/repos/opensource/skills/unclawg-discover/scripts/search_reddit.sh)
- [`unclawg-discover/scripts/search_tiktok.sh`](/Users/b/repos/opensource/skills/unclawg-discover/scripts/search_tiktok.sh)
- [`unclawg-discover/scripts/search_tiktok_comments.sh`](/Users/b/repos/opensource/skills/unclawg-discover/scripts/search_tiktok_comments.sh)
- [`unclawg-discover/scripts/search_twitter.sh`](/Users/b/repos/opensource/skills/unclawg-discover/scripts/search_twitter.sh)
- [`unclawg-discover/scripts/search_youtube.sh`](/Users/b/repos/opensource/skills/unclawg-discover/scripts/search_youtube.sh)
- [`unclawg-discover/scripts/select_mode.sh`](/Users/b/repos/opensource/skills/unclawg-discover/scripts/select_mode.sh)
- [`unclawg-feed/SKILL.md`](/Users/b/repos/opensource/skills/unclawg-feed/SKILL.md)
- [`unclawg-feed/references/api-contract.md`](/Users/b/repos/opensource/skills/unclawg-feed/references/api-contract.md)
- [`unclawg-internet/SKILL.md`](/Users/b/repos/opensource/skills/unclawg-internet/SKILL.md)
- [`unclawg-internet/references/artifact-templates.md`](/Users/b/repos/opensource/skills/unclawg-internet/references/artifact-templates.md)
- [`unclawg-internet/references/default-soul.md`](/Users/b/repos/opensource/skills/unclawg-internet/references/default-soul.md)
- [`unclawg-internet/references/soul-interview.md`](/Users/b/repos/opensource/skills/unclawg-internet/references/soul-interview.md)
- [`unclawg-respond/SKILL.md`](/Users/b/repos/opensource/skills/unclawg-respond/SKILL.md)
- [`unclawg-respond/references/api-contract.md`](/Users/b/repos/opensource/skills/unclawg-respond/references/api-contract.md)
- [`unclawg-respond/scripts/uc_respond`](/Users/b/repos/opensource/skills/unclawg-respond/scripts/uc_respond)
- [`unclawg-respond/tests/test_uc_respond.py`](/Users/b/repos/opensource/skills/unclawg-respond/tests/test_uc_respond.py)

### 2. Throngterm-specific tracked branding/assets

These are repo-specific sprites/branding and tooling for the `throngterm` runtime.

- [`.throngterm/colors.json`](/Users/b/repos/opensource/skills/.throngterm/colors.json)
- [`.throngterm/logo-source.svg`](/Users/b/repos/opensource/skills/.throngterm/logo-source.svg)
- [`.throngterm/sprites/active.svg`](/Users/b/repos/opensource/skills/.throngterm/sprites/active.svg)
- [`.throngterm/sprites/drowsy.svg`](/Users/b/repos/opensource/skills/.throngterm/sprites/drowsy.svg)
- [`.throngterm/sprites/sleeping.svg`](/Users/b/repos/opensource/skills/.throngterm/sprites/sleeping.svg)
- [`.throngterm/sprites/deep_sleep.svg`](/Users/b/repos/opensource/skills/.throngterm/sprites/deep_sleep.svg)
- [`throngterm-sprite/SKILL.md`](/Users/b/repos/opensource/skills/throngterm-sprite/SKILL.md)
- [`throngterm-sprite/scripts/generate.js`](/Users/b/repos/opensource/skills/throngterm-sprite/scripts/generate.js)
- [`throngterm-sprite/scripts/generate-logo-pack.js`](/Users/b/repos/opensource/skills/throngterm-sprite/scripts/generate-logo-pack.js)
- [`clawgs/src/emit/model_client.rs`](/Users/b/repos/opensource/skills/clawgs/src/emit/model_client.rs)

### 3. Project-specific references embedded inside otherwise broader docs/tools

These are not entire project-specific subsystems, but they do embed stack-specific examples or assumptions.

- [`reproduce/SKILL.md`](/Users/b/repos/opensource/skills/reproduce/SKILL.md)
  Notes: explicitly references the "HTMA/OpenClaw local ecosystem" and `.env-manager`.
- [`reproduce/references/probe-ladder.md`](/Users/b/repos/opensource/skills/reproduce/references/probe-ladder.md)
  Notes: probes for local `../.env-manager`, `../../.env-manager`, and `$HOME/repos/.env-manager`.
- [`remotion/rules/project-hub.md`](/Users/b/repos/opensource/skills/remotion/rules/project-hub.md)
  Notes: includes concrete example names like `htma-recipe.jpg` and `cyclechef-logo.png`.

## Machine/Checkout-Specific Path Assumptions

These are not necessarily branded, but they do assume one local repo layout or persist absolute-ish cwd conventions.

- [`codex-tmux/SKILL.md`](/Users/b/repos/opensource/skills/codex-tmux/SKILL.md)
- [`codex-tmux/scripts/run.py`](/Users/b/repos/opensource/skills/codex-tmux/scripts/run.py)
- [`divide-and-conquer/references/mode-template.md`](/Users/b/repos/opensource/skills/divide-and-conquer/references/mode-template.md)
- [`domain-planner/references/mode-template.md`](/Users/b/repos/opensource/skills/domain-planner/references/mode-template.md)
- [`domain-planner/scripts/init_slice.py`](/Users/b/repos/opensource/skills/domain-planner/scripts/init_slice.py)
- [`domain-planner/scripts/review_plan.py`](/Users/b/repos/opensource/skills/domain-planner/scripts/review_plan.py)
- [`domain-reviewer/references/codex-mcp-orchestration-template.md`](/Users/b/repos/opensource/skills/domain-reviewer/references/codex-mcp-orchestration-template.md)
- [`domain-reviewer/references/mode-template.md`](/Users/b/repos/opensource/skills/domain-reviewer/references/mode-template.md)
- [`domain-reviewer/scripts/launch_codex_worker.py`](/Users/b/repos/opensource/skills/domain-reviewer/scripts/launch_codex_worker.py)
- [`domain-scaffolder-backend/references/mode-template.md`](/Users/b/repos/opensource/skills/domain-scaffolder-backend/references/mode-template.md)
- [`domain-scaffolder-frontend/references/mode-template.md`](/Users/b/repos/opensource/skills/domain-scaffolder-frontend/references/mode-template.md)
- [`openclaw-client-bootstrap/.gitignore`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/.gitignore)
- [`openclaw-client-bootstrap/SKILL.md`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/SKILL.md)
- [`prompt-reviewer/references/mode-template.md`](/Users/b/repos/opensource/skills/prompt-reviewer/references/mode-template.md)
- [`research-paper/SKILL.md`](/Users/b/repos/opensource/skills/research-paper/SKILL.md)
- [`research-paper/references/mode-template.md`](/Users/b/repos/opensource/skills/research-paper/references/mode-template.md)
- [`skill-issue/SKILL.md`](/Users/b/repos/opensource/skills/skill-issue/SKILL.md)
- [`skill-issue/references/mode-template.md`](/Users/b/repos/opensource/skills/skill-issue/references/mode-template.md)
- [`skill-issue/scripts/init_context.py`](/Users/b/repos/opensource/skills/skill-issue/scripts/init_context.py)
- [`skill-issue/scripts/lib/reporter.py`](/Users/b/repos/opensource/skills/skill-issue/scripts/lib/reporter.py)
- [`skill-issue/scripts/lib/scanner.py`](/Users/b/repos/opensource/skills/skill-issue/scripts/lib/scanner.py)
- [`skill-issue/scripts/quick_validate.py`](/Users/b/repos/opensource/skills/skill-issue/scripts/quick_validate.py)
- [`trend-to-content/references/mode-template.md`](/Users/b/repos/opensource/skills/trend-to-content/references/mode-template.md)
- [`trend-to-content/references/remotion-hub.md`](/Users/b/repos/opensource/skills/trend-to-content/references/remotion-hub.md)
- [`unclawg-discover/references/mode-template.md`](/Users/b/repos/opensource/skills/unclawg-discover/references/mode-template.md)
- [`unclawg-discover/scripts/select_mode.sh`](/Users/b/repos/opensource/skills/unclawg-discover/scripts/select_mode.sh)
- [`unclawg-internet/references/artifact-templates.md`](/Users/b/repos/opensource/skills/unclawg-internet/references/artifact-templates.md)

## Specific Patterns Worth Calling Out

- `0_claw` is explicitly wired into tracked automation and instance assets.
- `ingredient-claw` appears in tracked examples in:
  - [`openclaw-client-bootstrap/scripts/talk.sh`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/scripts/talk.sh)
  - [`openclaw-client-bootstrap/scripts/update-oauth-token.sh`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/scripts/update-oauth-token.sh)
  - [`unclawg-feed/SKILL.md`](/Users/b/repos/opensource/skills/unclawg-feed/SKILL.md)
- `larry.env` and `/home/openclaw/.openclaw/...` are hardcoded fallback paths in:
  - [`unclawg-respond/scripts/uc_respond`](/Users/b/repos/opensource/skills/unclawg-respond/scripts/uc_respond)
- `api.unclawg.com` / `unclawg.com` are embedded in:
  - [`_shared/agent-bootstrap.md`](/Users/b/repos/opensource/skills/_shared/agent-bootstrap.md)
  - [`openclaw-client-bootstrap/assets/client-kit/.env.example`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/assets/client-kit/.env.example)
  - [`openclaw-client-bootstrap/references/read-only-governance.md`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/references/read-only-governance.md)
  - [`openclaw-client-bootstrap/scripts/new_client_kit.sh`](/Users/b/repos/opensource/skills/openclaw-client-bootstrap/scripts/new_client_kit.sh)
  - [`unclawg-feed/SKILL.md`](/Users/b/repos/opensource/skills/unclawg-feed/SKILL.md)
  - [`unclawg-internet/SKILL.md`](/Users/b/repos/opensource/skills/unclawg-internet/SKILL.md)
  - [`unclawg-respond/SKILL.md`](/Users/b/repos/opensource/skills/unclawg-respond/SKILL.md)
  - [`unclawg-respond/tests/test_uc_respond.py`](/Users/b/repos/opensource/skills/unclawg-respond/tests/test_uc_respond.py)

## Totals

- High-confidence OpenClaw / Unclawg / SPAPS files: 74
- High-confidence Throngterm files: 10
- Generic docs/tools with embedded project-specific references: 3
- Machine/checkout-specific path assumption files: 27

## Excluded From This List

- Generic references to Codex, Claude, tmux, Reddit, LinkedIn, Twitter/X, DigitalOcean, Tailscale, etc. when they were just normal tool/platform mentions.
- False positives where `ingredient` meant a normal English noun rather than the `ingredient` project.
