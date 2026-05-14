---
name: mmdx-registry-usage-audit
description: >-
  Audit MMDX registry surfaces including INDEX.mmdx freshness, repo-local
  tracker placement, diagram stack links, Mermaid preflight validity, stale
  diagram drift, and plan-to-diagram evidence freshness. Use when placement or
  registry decisions depend on whether MMDX files are indexed, valid, linked,
  current, or stored in the right repo, plan root, skill template, or
  Skillbox-config overlay.
---

# MMDX Registry Usage Audit

Audit the diagram and plan registry layer that lets agents find current MMDX
maps, trust their links, and decide whether tracker evidence is fresh enough to
drive placement or handoff decisions.

Use this as the canonical registry-audit skill when the request is about MMDX,
Mermaid, diagram indexes, chart links, or plan/tracker freshness. If the request
is about whether a `SKILL.md`, skill bundle, SBP policy, MCP server, or overlay
is registered or visible, hand off to `skill-registry-usage-audit` instead of
duplicating that workflow here.

## First Progress Marker

Start with:

`Using mmdx-registry-usage-audit to audit MMDX registry freshness. First I will inventory MMDX files, index freshness, chart links, tracker placement, and preflight status before proposing any diagram or plan move.`

## Ownership Contract

- `mmdx` owns the portable diagram tooling, parser/preflight script, examples,
  and generic chart-stack templates.
- Repo-local plans and diagrams live with the repo when they explain active
  project state or should be reviewed in that repo's history.
- Skill templates that teach reusable MMDX shapes live inside the owning skill.
- Client-specific generated plans, invocation artifacts, and per-client diagram
  indexes live in Skillbox config.
- `INDEX.mmdx` is a generated directory surface. Refresh it before relying on
  "latest" or "current" diagram answers.

## Scanner

Run the bundled scanner first:

```bash
python3 scripts/scan_mmdx_registry.py --root . --dry-run
python3 scripts/scan_mmdx_registry.py --root . --json --dry-run
```

Use preflight only when you want the scanner to run Mermaid validation for each
candidate file:

```bash
python3 scripts/scan_mmdx_registry.py --root . --run-preflight --mmd-script ~/repos/opensource/skills/mmdx/scripts/mmd.py
```

The scanner is read-only. Without `--run-preflight`, it reports the exact
preflight commands that should be run for candidate stacks.

## Workflow

1. Refresh any relevant generated index before making "latest" claims:
   ```bash
   python3 ~/repos/opensource/skills/mmdx/scripts/mmdx_index.py
   ```
2. Run the scanner against the repo or portfolio root and save JSON for durable
   reports.
3. Confirm the active plan/diagram contract from README, AGENTS, plan docs,
   skill templates, or Skillbox config.
4. Validate high-value MMDX files with the real parser:
   ```bash
   python3 ~/repos/opensource/skills/mmdx/scripts/mmd.py path/to/file.mmdx --preflight-only
   ```
5. Confirm link problems by reading the MMDX metadata, chart ids, visible labels,
   and any linked local files.
6. Classify findings with `references/audit-rubric.md`.
7. Update the MMDX map from `assets/templates/usage-audit-stack.mmdx`.
8. Write the report from `assets/templates/USAGE_AUDIT_REPORT.md`.

If `mmd.py` cannot run, continue with metadata and link checks, but mark
preflight evidence as degraded. Do not present structural MMDX parsing as proof
that Mermaid syntax is valid.

## What To Catch

- `INDEX.mmdx` is older than the MMDX files it claims to index.
- A repo has active `.mmdx` trackers but no discoverable index or README link.
- Chart-stack metadata points to missing chart ids.
- Link labels in MMDX metadata are not visible in the source chart.
- Local markdown links to `.mmd` or `.mmdx` files are broken.
- Mermaid preflight fails for active diagrams or skill templates.
- Smart-goal trackers, release maps, or plan diagrams live in scratch paths
  instead of repo-local plan/docs roots, Skillbox config, or skill templates.
- A stale plan diagram is being used as current placement evidence.

## False-Positive Rules

- Do not flag generic templates in `assets/templates` as stale project plans.
- Do not flag archived plans or screenshots unless active docs link to them as
  current guidance.
- Do not require one global index for every repo-local diagram; a repo-local
  README or plan index can be sufficient when it is current and linked.
- Do not treat mtime alone as drift. Confirm that a stale diagram is used as
  active evidence before escalating above `LOW`.
- Do not move client-specific MMDX artifacts into a reusable skill contract.
- Do not audit general `SKILL.md`, SBP, MCP, bundle, or overlay visibility
  here unless the finding specifically blocks MMDX registry trust.

## Handoff To Usage-Auditor-Maker

Escalate back to a package-specific usage auditor only when stale or broken
MMDX evidence masks adoption drift for one upstream package, SDK, service,
skill, or MCP server. Include:

- upstream owner and package terms
- stale MMDX evidence path
- repos whose decisions depended on that evidence
- false-positive rule to promote or keep local
- scanner or preflight command the package auditor should ship

Keep index freshness, tracker placement, and chart-link defects in this auditor.

## Output

Return:

- roots scanned and index refresh status
- MMDX inventory with newest files and indexes
- ranked findings with exact file evidence
- preflight results or degraded reason
- tracker placement decisions
- broken link or stale-plan table
- MMDX map path
- verification commands

## Required Verification

Before closing edits to this skill, run:

```bash
python3 ~/repos/opensource/skills/skill-issue/scripts/quick_validate.py ~/repos/opensource/skills/mmdx-registry-usage-audit
python3 ~/repos/opensource/skills/mmdx-registry-usage-audit/scripts/scan_mmdx_registry.py --root ~/repos/opensource/skills --dry-run
python3 ~/repos/opensource/skills/mmdx-registry-usage-audit/scripts/scan_mmdx_registry.py --help
python3 ~/repos/opensource/skills/mmdx/scripts/mmd.py ~/repos/opensource/skills/mmdx-registry-usage-audit/assets/templates/usage-audit-stack.mmdx --preflight-only
```

Before closing a real audit run, also refresh the relevant index when one
exists, preflight active diagrams where possible, and state exactly where
scanning stopped.
