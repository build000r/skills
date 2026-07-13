# Local Self-Release Standard

Use this standard when GitHub Actions is an avoidable cost center rather than a
required trust boundary. The release host may be an operator workstation or an
always-on build box. GitHub remains the source forge; it does not need to be the
machine that builds, tests, or deploys each push.

## Decision

The default release path is a repo-owned command such as `make release` or
`scripts/release/self-release.sh` run on a trusted release host:

1. lock the release lane
2. fetch the intended protected branch or explicit release ref
3. create a clean detached worktree for the full commit SHA
4. run the source-level portion of the canonical release gate for that exact SHA
5. build the production artifact once
6. run the artifact-level remainder of the gate against that exact artifact
7. transport that exact artifact directly to the target
8. activate it without rebuilding on production
9. prove behavior and deployed state
10. persist a release manifest and retain rollback artifacts

GitHub Actions is not the normal orchestrator. Keep a manual
`workflow_dispatch` fallback only when it provides useful disaster recovery.
Do not replace paid hosted jobs with a self-hosted Actions runner by default;
that keeps GitHub queueing, workflow syntax, and control-plane availability in
the critical path without solving artifact identity or rollback.

## What Moves Off Actions

Classify every workflow before changing triggers.

| Workflow purpose | Default home | Notes |
| --- | --- | --- |
| tests, lint, typecheck, build | repo-owned local gate | Preserve one canonical command; optimize caches and fixtures locally |
| production deploy | repo-owned self-release | Direct provider CLI or SSH transport from the release host |
| diagnosis and rollback | local read-only and guarded scripts | Do not require a hosted runner to recover production |
| backups, certificate renewal, periodic probes | target-side timer or provider scheduler | Use locking, durable logs, alerting, and a manual run command |
| untrusted contributor PR checks | GitHub Actions when useful | Do not expose release-host secrets to untrusted code |
| platform-specific checks unavailable locally | the matching trusted machine or a narrow hosted job | Keep the exception explicit and measured |
| public release events or marketplace automation | case-by-case | Keep only when the external event and hosted identity are genuinely useful |

Do not churn dormant workflows merely to make the YAML uniform. Start with
workflows that consume real minutes, duplicate a local gate, fail chronically,
or sit on the production critical path.

## Canonical Gate

Expose one repository entry point, typically `make release` backed by
`make verify`, `make prepush-full`, or `scripts/prepush.sh --full`. The release
entry point owns all checks required before production in three logical phases:
source checks, one production build, then checks against that exact artifact.

- dependency lock or frozen-install verification
- secret and generated-artifact scans
- unit and integration tests
- type, lint, formatting, and documentation checks
- one production build whose output is retained for transport
- migration compatibility or disposable-database rehearsal
- surface-specific packaging or signature checks

A pre-push hook should call the same entry point for fast feedback, but the hook
is not proof of release eligibility: hooks are bypassable and may have run
against a dirty tree or another SHA. The self-release command must run the gate
inside its clean release worktree. A SHA-bound cached receipt is acceptable only
when it records the command, inputs, outputs, and artifact digest and the release
command verifies all of them.

If an existing verification command already performs the production build, the
release command must reuse that output; it must not perform a throwaway build
and rebuild for deployment. A source-only gate may build afterward exactly once,
then run migration, signature, packaging, or smoke checks on that output.

Use quick or affected-test modes during development. Never substitute them for
the full production gate. Make the full gate cheap enough to keep by using
persistent dependency caches, a tuned local test database, bounded parallelism,
and reusable fixtures.

## Provenance And Concurrency

Require all of these before building:

- a full immutable commit SHA, never a floating branch name in the manifest
- a clean detached worktree at that SHA
- an explicit relationship to the protected release ref
- a host-level lock so two releases cannot overlap
- a no-op check when the same deployable inputs are already live

The default policy may require the release SHA to equal `origin/main`. Releasing
an explicit tag or approved SHA is also valid when the repo documents that
policy. Do not silently deploy whatever happens to be checked out in the
operator's editable worktree.

## Build Once, Promote Exactly

The tested artifact and deployed artifact must be identical.

### Server Or Container

Build the image once on the release host and tag it with the full SHA. Run
migration and image-level checks against that image. Prefer one of these
transports:

- registryless: archive by `docker save`, checksum it, transfer over an
  authenticated private SSH path, then `docker load`
- registry by digest: push once, record the immutable digest, and make the
  target pull that digest rather than a mutable tag

Registryless transport is the default when removing avoidable GitHub
dependencies is the priority. Registry-by-digest is useful for multi-host
rollouts or offsite retention. Never rebuild on the production host: it spends
production CPU, reintroduces network and dependency drift, and breaks the
build-once invariant.

### Pages, Edge, Or Static Hosting

Build the output once from the release worktree, then deploy that directory
with the provider CLI and local credentials. Embed a build identity endpoint or
file containing the full SHA. Record the provider deployment ID and immutable
deployment URL when available, then verify the immutable URL, canonical domain,
and every first-party alias.

### Package Registry Or App Store

Build the package, archive, or signed bundle locally. Gate and checksum that
exact output before upload. Record its version, build number, checksum, signing
identity fingerprint where safe, registry digest or store build ID, and
processing state. External review and store processing are post-upload gates;
they do not justify rebuilding the artifact elsewhere.

## Credentials And Cutover

Release credentials belong on the trusted release host, in a host credential
store, or on the target when the release path deliberately reuses a protected
remote environment. Keep them out of the repo and release logs.

Before removing an automatic deploy trigger:

1. identify the exact local credential source and target identity
2. run the provider's read-only identity command from the release host
3. run a non-mutating or preview path when the provider supports one
4. complete one real local deploy and verify it end to end
5. only then remove the `push` trigger

If credentials are missing, stale, or scoped to the wrong project, leave the
existing deploy trigger intact. Build the local lane as ready-but-not-cut-over
and report the exact credential gap. This prevents cost work from accidentally
creating a zero-deploy system.

## Optional Automatic Trigger

Start with an explicit operator or agent command. If automatic deploy-on-main is
valuable, add a small local queue after the manual path is proven:

- accept only allowlisted repository and protected-branch refs
- verify webhook signatures or poll the remote ref through authenticated Git
- enqueue the full SHA, not arbitrary shell supplied by the event
- serialize releases and coalesce superseded SHAs
- never execute untrusted pull-request code in the credentialed release context
- expose queue state, durable logs, a manual retry command, and a disable switch

A target-side `systemd` service and timer, or an equivalent local supervisor,
is usually enough. The queue invokes the same repo-owned release command; it
does not create a second pipeline.

## Deploy And Migration Rules

Treat code, configuration, and schema as separate rollout dimensions. State
whether the release is one-phase or two-phase. For a schema-moving release:

1. prove a fresh backup and its restore command
2. rehearse migrations against the exact artifact
3. prefer backward-compatible expand-and-contract changes
4. deploy the compatible phase before removing old fields or behavior
5. record the before and after migration revisions

Rollback is code-only only when the current production schema is compatible
with the target artifact. Otherwise stop and use the documented restore or
forward-fix path. A script that merely selects an older image and restarts is
not a safe database rollback.

## Required Release Proof

Every successful release ends with both kinds of evidence:

- behavior proof: a real health, smoke, login, API, browser, package-install, or
  device flow succeeds
- state proof: the runtime, provider, registry, or store reports the expected
  full SHA, image ID, digest, deployment ID, version, or build number

Persist a JSON manifest locally and, where possible, beside the target release.
Include at least:

- release status, start/end timestamps, actor, and target environment
- repo/ref/full SHA and clean-worktree proof
- gate command, exit status, duration, and log digest
- artifact name, checksum, image ID, registry digest, or store build ID
- configuration fingerprint with secrets redacted
- migration before/head/after revisions and backup reference
- transport and activation result
- behavior proof and state proof
- previous release identity and rollback eligibility

Keep the last several artifacts and manifests according to storage cost and
recovery objectives. For registryless containers, retain compressed archives
on the release host plus loaded image tags on the target. Test rollback before
retiring the old path.

## Break-Glass Workflow

When a GitHub fallback is retained:

- trigger it with `workflow_dispatch` only
- keep its commands aligned with the canonical repo gate and release script
- use narrowly scoped secrets and permissions
- prevent overlapping production releases
- do not cancel a publish, migration, backup, or production release midway
- label it as fallback, not the release authority
- exercise it periodically enough to detect credential drift

For public repositories, keep pull-request verification when it protects the
project from untrusted contributions. The goal is near-zero avoidable Actions
spend, not ideological zero YAML.

## Migration Checklist

1. Measure recent hosted-job minutes and identify duplicate runs by workflow and SHA.
2. Inventory every workflow's commands, secrets, triggers, concurrency, and target.
3. Create the one canonical local gate and prove it blocks an intentional failure.
4. Create the self-release dry run, exact-SHA worktree, lock, manifest, and rollback path.
5. Prove local credentials and complete one real deploy with behavior and state receipts.
6. Convert the hosted workflow to manual fallback and remove redundant push or PR triggers.
7. Push a harmless commit and verify it starts no retired hosted run.
8. Move necessary scheduled jobs to a target-side timer and test the manual invocation.
9. Re-measure hosted minutes after the observation window.
10. Keep exceptions explicit: untrusted PRs, unavailable platforms, or external release identities.

The migration is complete only when the local lane is the documented authority,
the deployed artifact is tied to the gated SHA, recovery works without a hosted
runner, and observed avoidable Actions minutes have fallen as intended.
