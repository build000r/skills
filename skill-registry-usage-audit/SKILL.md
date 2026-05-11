---
name: skill-registry-usage-audit
description: >-
  Audit skill registry surfaces including skill-repos.yaml, SKILL.md manifests,
  Skillbox runtime manifests, SBP policy, MCP visibility, default bundles,
  overlays, and private/public placement. Use when placement or adoption depends
  on whether a skill, bundle, overlay, or MCP server is registered, visible,
  fresh, scoped correctly, or owned by opensource/skills, skillbox,
  skillbox-config, or a private skill corpus.
---

# Skill Registry Usage Audit

Audit the registry layer that decides which agent skills exist, where they are
owned, and whether agents can see the right Skillbox/SBP/MCP surface from a
given repo.

## First Progress Marker

Start with:

`Using skill-registry-usage-audit to audit skill registry visibility. First I will inventory registry files, skill manifests, SBP scope, overlays, and MCP parity before proposing any routing or sync change.`

## Ownership Contract

- Portable skill contracts live in `opensource/skills` when their instructions,
  scripts, references, and templates are public and generic.
- Reusable private contracts live in a private skill corpus when the skill body
  contains private repo maps, operator-only workflows, or non-public examples.
- Runtime delivery, default bundle curation, sync, install, and local agent
  environment behavior live in Skillbox-style runtime repos.
- Client overlays, generated contexts, invocation artifacts, per-client
  validation commands, and repo landscapes live in Skillbox config.
- MCP server visibility must be checked as a delivery/config surface, not as a
  reason to move the canonical skill contract.

## Scanner

Run the bundled read-only scanner first:

```bash
python3 scripts/scan_skill_registry.py --root . --dry-run
python3 scripts/scan_skill_registry.py --root . --json --dry-run
```

Use a broader root only when the audit is intentionally cross-repo:

```bash
python3 scripts/scan_skill_registry.py --root ~/repos --json --dry-run
```

The scanner inventories `skill-repos.yaml`, `SKILL.md`, Skillbox manifest/source
files, `skill-scope.yaml`, repo-local overlays, `.mcp.json`, and
`.codex/config.toml`. It reports candidate issues only; confirm every serious
finding by reading the cited files.

## Workflow

1. Read the active repo docs and registry files that define the local contract:
   `README.md`, `AGENTS.md` or equivalent, `skill-repos.yaml`, overlay files,
   Skillbox manifests, `skill-scope.yaml`, `.mcp.json`, and
   `.codex/config.toml`.
2. Run the scanner in dry-run mode and save the JSON when a durable report is
   needed.
3. Run SBP read-only checks when available:
   ```bash
   sbp
   sbp skills --issues-only --no-global --format json
   sbp mcp --format json
   ```
4. Confirm high-severity candidates by opening the registry source and the
   downstream repo that is supposed to consume it.
5. Classify the issue using `references/audit-rubric.md`.
6. Create or update the MMDX map from
   `assets/templates/usage-audit-stack.mmdx`.
7. Write the report from `assets/templates/USAGE_AUDIT_REPORT.md`.
8. Recommend narrow dry-run commands before any sync, unlink, prune, overlay, or
   MCP config change.

If `sbp` is unavailable or unhealthy, continue from registry files and mark the
SBP evidence as degraded. Do not present filesystem inventory as proof of
effective runtime visibility.

## What To Catch

- `skill-repos.yaml` points at missing repos, archived copies, wrong roots, or
  stale skill source directories.
- A `SKILL.md` manifest is missing `name` or `description`, has duplicate names,
  or lives in a repo that does not own its contract.
- Default bundles include skills whose source is missing, private-only, not
  portable, or scoped too broadly.
- A task skill is globally visible when policy requires cwd or overlay-scoped
  activation.
- A required skill is not visible for the current repo through SBP.
- Skillbox overlay or blueprint files carry the real contract, but docs tell
  agents to edit a reusable `SKILL.md` instead.
- Claude `.mcp.json` and Codex `.codex/config.toml` disagree about required MCP
  servers.
- Invocation artifacts, generated plans, or client-specific defaults are stored
  in reusable skill contracts instead of Skillbox config.

## False-Positive Rules

- Do not flag archived handoff kits, old duplicate clients, generated reports,
  or vendored skill copies unless current docs or policy files route agents
  through them.
- Do not treat a missing global skill link as a bug for task skills; prefer
  repo-local or overlay-scoped activation.
- Do not move a private skill into `opensource/skills` just to make it visible.
  Scrub it first or keep it private.
- Do not treat MCP parity drift as a skill-contract placement issue unless the
  skill's core behavior depends on that MCP server.
- Do not report a string match from docs as active policy until a manifest,
  overlay, scope file, README, workflow, or current instruction confirms it.

## Handoff To Usage-Auditor-Maker

Escalate back to a package-specific usage auditor only when the registry issue
is really about one upstream package, SDK, service, or MCP server being consumed
incorrectly across repos. Include:

- upstream owner and scan terms
- registry evidence that made the issue visible
- confirmed consumer repos
- false-positive class to promote or keep local
- first scanner command the new auditor should ship

Keep purely registry-scoping defects in this auditor.

## Output

Return:

- registry surfaces inspected
- repo and skill inventory
- ranked findings with exact file evidence
- SBP/Skillbox/MCP visibility table
- placement decision for each affected surface
- MMDX map path
- dry-run commands to review
- verification commands and degraded evidence

## Required Verification

Before closing edits to this skill, run:

```bash
python3 ~/repos/opensource/skills/skill-issue/scripts/quick_validate.py ~/repos/opensource/skills/skill-registry-usage-audit
python3 ~/repos/opensource/skills/skill-registry-usage-audit/scripts/scan_skill_registry.py --root ~/repos/opensource/skills --dry-run
python3 ~/repos/opensource/skills/skill-registry-usage-audit/scripts/scan_skill_registry.py --help
python3 ~/repos/opensource/skills/mmdx/scripts/mmd.py ~/repos/opensource/skills/skill-registry-usage-audit/assets/templates/usage-audit-stack.mmdx --preflight-only
```

Before closing a real audit run, also run the repo-native SBP/MCP read-only
checks where available and state exactly where scanning stopped.
