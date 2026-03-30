# OSS Readiness Rubric

Use this rubric to grade a repository's public documentation surface.

Start at `100/100`.

## Categories

### 1. Correctness And Active-Stack Alignment: 40 points

Full score means:

- active docs match the active codebase
- no dead routes are documented as shipped
- no stale stack instructions survive on the active surface
- examples and payloads match real implementations

Suggested deductions:

- `-10` docs present a missing or `501` endpoint as live
- `-8` major route or payload drift cluster
- `-8` stale stack migration cluster
- `-6` wrong deployment or operational instructions
- `-4` misleading but lower-risk example drift

### 2. Validation And Guardrails: 20 points

Full score means:

- docs validation commands exist
- they run successfully
- CI covers the critical doc surfaces

Suggested deductions:

- `-10` broken validator or validator aimed at deprecated code
- `-6` critical docs surface has no functioning guardrail
- `-4` docs CI exists but misses important surfaces

### 3. Contributor Surface Clarity: 15 points

Full score means:

- README, CONTRIBUTING, workflow docs, and release docs match reality
- contributors are pointed at the right commands and files

Suggested deductions:

- `-6` stale workflow or branch-protection guide
- `-5` contributor docs still point to deprecated paths or commands
- `-4` root docs overclaim alignment that is not true

### 4. Security, Privacy, And Public Hygiene: 15 points

Full score means:

- no private IPs, local paths, or internal-only values in active docs
- no secret-like examples that look real
- public runbooks are safe to publish

Suggested deductions:

- `-6` leaked infrastructure details in active docs
- `-5` local absolute paths or internal-only instructions on active surface
- `-4` secret-like examples or confusing placeholder hygiene

### 5. Licensing And Publishability: 10 points

Full score means:

- repo and package license posture is internally consistent
- package READMEs and manifests agree
- publish metadata matches public intent

Suggested deductions:

- `-6` repo/package license mismatch
- `-4` package README and package manifest disagree about publish posture

## Fail Gates

If any of these are present, the repo is not `100/100`:

- a public API doc describes a route that does not exist
- a public API doc describes a `501` stub as shipped
- a primary docs validator is broken
- active contributor docs still target a deprecated stack
- licensing or publish posture is contradictory on the active surface

## Interpretation

- `90-100`: ready; only minor cleanup remains
- `75-89`: usable, but still risky to publish broadly
- `50-74`: substantial drift; public readers will be misled
- `0-49`: not OSS-ready; active docs and guardrails are untrustworthy
