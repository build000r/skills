# Skill Registry Audit Rubric

Use this rubric to turn registry inventory into confirmed findings.

## Surfaces

- **Source registry**: `skill-repos.yaml`, trusted skill roots, skill source
  declarations, archived duplicate roots.
- **Skill manifests**: `SKILL.md` frontmatter, bundled scripts, references,
  templates, validation instructions.
- **Skillbox runtime**: default skill sources, generated manifests, client
  manifests, sync/install/runtime scripts, local devbox behavior.
- **SBP policy**: `skill-scope.yaml`, effective cwd skills, global allowlist,
  repo-local activation, overlay activation.
- **MCP visibility**: Claude `.mcp.json`, Codex `.codex/config.toml`, disabled
  entries, parity mismatch, repo-local server expectations.
- **Client overlays**: repo-local `.buildooor/skillbox-config/clients/*` and
  shared `skillbox-config/clients/*`.

## Finding Families

- `missing-registry-source`: a declared repo, skill root, source file, or bundle
  entry is absent.
- `manifest-drift`: `SKILL.md` frontmatter is incomplete, duplicate, malformed,
  or inconsistent with registry naming.
- `scope-drift`: a skill is global, repo-local, or overlay-scoped contrary to
  policy.
- `bundle-drift`: default bundle or runtime manifest includes missing, private,
  archived, or wrong-owner skills.
- `overlay-drift`: client-specific instructions, generated context, or
  invocation artifacts are missing, stale, or stored in the wrong layer.
- `mcp-parity-drift`: Claude and Codex do not see the same required MCP server.
- `placement-drift`: portable contract, runtime behavior, and client config are
  mixed into the wrong repo.

## Severity

- `HIGH`: required skill or MCP surface is invisible, runtime/default bundle
  points at missing source, global task-skill exposure can misroute work, or a
  public skill contract contains private client material.
- `MEDIUM`: duplicate skill names, stale bundle entries, overlay path drift,
  repo-local scope mismatch, or docs that teach the wrong registry path.
- `LOW`: optional adoption gaps, weak trigger language, missing convenience
  index, or report/template drift that does not affect current visibility.
- `INFO`: confirmed correct routing worth preserving as proof.

## Confirmation Rules

Do not report a finding from a filename match alone. Confirm it against active
policy, manifest, overlay, README, workflow, runtime script, or SBP output.

Treat these as excluded unless active guidance links to them:

- archived duplicate client trees
- handoff kits
- generated audit reports
- agent scratch artifacts
- vendored copies of public skills
- historical plans under archive folders

## Placement Rules

- Move or create portable skill contracts in `opensource/skills`.
- Keep private contracts in private skill roots until scrubbed.
- Put runtime delivery, install/sync, manifest generation, and default bundle
  curation in Skillbox.
- Put client overlays, generated context, validation commands, plans, and
  invocation artifacts in Skillbox config.
- Treat MCP config as delivery/config; fix parity there unless the skill
  contract itself needs new MCP guidance.

## Report Quality Bar

A production report has exact paths, confirmed active evidence, a severity,
expected versus actual registry state, a dry-run command where mutation is
suggested, and a verification command. Open questions are allowed only when
source evidence cannot answer the policy decision.
