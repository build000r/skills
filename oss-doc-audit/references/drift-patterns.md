# Common Drift Patterns

Use this file when the first audit pass found more issues than expected or when
the skill needs a sharper second pass.

## High-Signal Patterns

- Docs present a missing route as live.
- Docs present a `501 not implemented` stub as shipped.
- Docs use a deprecated route path after a framework migration.
- Payload examples include fields the active schema does not accept.
- Workflow docs reference nonexistent CI files or status checks.
- Validator scripts still target the deprecated tree after a stack migration.
- README, package manifest, and repo license disagree on public posture.
- Active docs include real IPs, local paths, or internal-only deployment values.

## Proof Strategy

For each suspected issue:

1. Open the doc that makes the claim.
2. Open the implementation or schema that proves the claim wrong.
3. Record the exact mismatch, not a vague “stale” label.

## Remediation Bias

When the drift is large, prefer one of these over incremental tweaks:

- replace the doc with a short current-status stub
- move the doc out of the active surface
- point readers at the real source of truth until a full rewrite exists
