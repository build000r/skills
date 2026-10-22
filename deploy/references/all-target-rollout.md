# All-target rollout

The desired result is a usable current application on every declared project
machine. A completed source change or release package is an intermediate result.

## Select the complete target set

1. Read the matched overlay's release targets and distribution roles before a write.
2. Include installation consumers, managed runtime replicas, and developer/build
   machines explicitly declared to consume the application. Deduplicate aliases
   by machine and installation identity. Keep distinct installations on one host.
3. Honor an explicit user target restriction. Do not expand a single-host request,
   update unrelated services, enumerate arbitrary SSH hosts, or create repositories
   on machines declared to be binary-only consumers.
4. Resolve "latest" once to an exact source SHA allowed by the release ref policy.
   Record the requested change and its ancestry. Merge an authorized pending
   feature through the normal protected-ref path before creating release artifacts.
   If the protected ref moves during rollout, finish or report the selected SHA;
   do not silently change the candidate midway.
5. Record each target's OS/architecture, installation, runtime, credentials mechanism,
   health/version, active work, retained previous release, and rollback compatibility.
   Capture dirty/untracked source and active writers before source synchronization.

Missing target configuration is preparation work. Repair it from authoritative
repo/overlay/runtime evidence when the request authorizes configuration. Ask only
for a material choice that the evidence cannot resolve. Keep private topology
in the owning overlay, never in this public skill.

## Build and deliver

- Run the canonical complete gate for the selected SHA on each required native
  release platform. Build each required artifact once and retain its manifest,
  checksums, inputs, gate receipt, and previous compatible artifact.
- Reuse that exact artifact for every matching target. Build-host success does
  not update the build host's installed application; install it there explicitly
  when the host is also a consumer.
- Use the repo-owned installer and configured transport. A local machine is also
  a target. Support its existing local activation path rather than starting an
  SSH server merely to reuse remote delivery.
- Restart or replace only application runtimes within the authorized scope. Keep
  tmux/agent sessions, user configuration, data, and unrelated services intact.
  Inventory old TUI/client processes separately: replacing an executable does not
  update an already running process. Use a supported safe handoff, or report that
  process as pending. Do not kill active work to make the table green.
- Synchronize source only on declared development machines when the request
  includes source convergence. Preserve dirty work and active branches; use an
  isolated checkout when necessary. Source parity never substitutes for runtime proof.
- If activation status is uncertain, inspect the same run and target before any
  retry. Preserve native exit status and classify partial outcomes using
  [release outcomes](release-outcomes.md).

## Verify every required phase

For each target, obtain:

| Phase | Required evidence |
| --- | --- |
| Source, when required | The intended SHA is present; concurrent work has custody. |
| Installed | Both required programs/assets match the selected artifact and manifest. |
| Running, when configured or active | The actual process and served build match the selected release. |
| Behavior | The changed user flow succeeds against that target's actual runtime. |
| Recovery | A compatible previous release is retained and the rollback path is available. |

For an intentionally inactive or install-only machine, state that role explicitly.
Verify its installed program with the repo's isolated smoke. Mark the normal
runtime `not_running` or `not_checked`, as observed. Do not invent a permanent
service, claim normal-runtime proof from a staging process, or hide an active old
client behind an install-only label.

For resource/status features, inspect newly sampled values from the target itself.
A green health endpoint or another machine's cached response does not prove the
new behavior. For browser clients, verify the target serves the selected assets.

Before closing the rollout, repeat per-target behavior and state checks after
the final mutation. Save one fleet receipt with the exact SHA, expected target
set, per-platform artifact digests, native command outcomes, and phase evidence.
Report coverage as verified targets / expected targets; never as an average.
All required phases must pass on all targets before declaring all machines current.
An offline host or old active process is a named remaining target, not an omission.

## Cold-start checks

- **Developer machine also consumes:** building there leaves the old installation
  untouched. Include its installation and applicable runtime checks.
- **One host unreachable:** retain its failed preflight, complete independent safe
  targets, and report the whole rollout incomplete with that host named.
- **Install succeeds, old process remains:** report installed-current and
  running-old separately; use the authorized supported runtime activation path.
- **Mixed native platforms:** require platform-specific checked artifacts from
  the same selected source SHA, then verify the matching artifact on each host.
- **Explicit one-target instruction:** update only that target; list other
  machines as outside this request rather than silently expanding authorization.
