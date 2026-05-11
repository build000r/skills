# MMDX Registry Audit Rubric

Use this rubric to separate real diagram-registry drift from harmless old
charts, examples, and generated artifacts.

## Surfaces

- **Generated directory index**: `INDEX.mmdx` and any repo-specific MMDX index.
- **Chart stacks**: `.mmdx` files, metadata links, chart ids, visible labels,
  local markdown links, and child-chart topology.
- **Mermaid sources**: `.mmd` files referenced by docs or stacks.
- **Plan trackers**: smart goals, release maps, audit maps, Gantt files, and
  plan diagrams used as current evidence.
- **Skill templates**: reusable MMDX templates in `assets/templates` or
  examples.
- **Client overlays**: generated or client-specific diagram evidence in
  Skillbox config.

## Finding Families

- `index-stale`: generated index is older than active MMDX files or missing
  active roots.
- `preflight-invalid`: Mermaid or MMDX parser validation fails.
- `chart-link-drift`: metadata links target missing chart ids or labels not
  visible in the source chart.
- `file-link-drift`: local links to `.mmd`, `.mmdx`, or diagram evidence point
  at missing files.
- `tracker-placement-drift`: current plan/tracker diagrams live in scratch,
  generated, or wrong-owner paths.
- `stale-plan-evidence`: old diagrams are used as current placement or release
  evidence without refresh proof.
- `template-drift`: reusable MMDX template no longer validates or no longer
  matches the skill's documented output contract.

## Severity

- `HIGH`: active decision evidence is invalid, missing, or linked to a missing
  chart; preflight fails for a required release/placement map; index drift
  causes "latest" answers to be wrong.
- `MEDIUM`: tracker lives in the wrong reviewable location, link labels drift,
  local diagram links are broken, or stale plan evidence is still referenced by
  current docs.
- `LOW`: optional index freshness, examples older than the active plan window,
  discoverability gaps, or diagrams that are stale but not active evidence.
- `INFO`: valid current diagram evidence worth preserving as proof.

## Confirmation Rules

Confirm stale evidence by finding a current README, AGENTS file, workflow,
plan, overlay, or operator instruction that still routes agents through that
diagram. Mtime alone is not enough.

Exclude these by default:

- archived plans
- generated screenshots
- old report artifacts
- examples and templates that are not project state
- node_modules or vendored docs
- scratch files unless promoted by active docs

## Placement Rules

- Keep reusable diagram templates with the skill that teaches them.
- Keep project-state diagrams in repo-local `docs`, `plans`, or equivalent
  reviewable roots.
- Keep client-specific generated plans and invocation artifacts in Skillbox
  config.
- Refresh generated indexes rather than hand-editing them.
- Use MMDX only when chart stacking adds useful drilldown; plain Mermaid is
  enough for a single current chart.

## Report Quality Bar

A production report includes exact paths, mtime or refresh evidence, parser
status, active-reference proof, a placement decision, and a concrete preflight
or index refresh command.
