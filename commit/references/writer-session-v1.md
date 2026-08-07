# Writer Session v1

`commit-writer-session/v1` is a public, provider-neutral contract for holding
repository writer exclusion across a mutation transaction. Providers own their
authority and exclusion mechanism. The commit skill owns discovery, fail-closed
aggregation, transaction execution, and cleanup.

Use `scripts/run_writer_fences.py` as the lifecycle boundary. Do not invoke a
provider yourself and then run mutations in later shell calls: that loses the
guaranteed `end` path and can create gaps between protected steps.

## Invariants

- Discover providers before changing ignore files, the index, the worktree, or
  `HEAD`.
- Invoke providers and protected steps as argv arrays with `shell=False`.
- Call every provider's `begin`, then aggregate all begin verdicts.
- If every begin allows, call every acquired provider's `check` and aggregate
  all check verdicts.
- Run no protected step unless both aggregate verdicts are `allow`.
- Treat `blocked`, `indeterminate`, timeouts, invocation errors, and schema
  errors during preflight as denials. The runner leaves the mutation plan
  unexecuted, so the index, worktree, and `HEAD` stay as they were.
- Call `end` in reverse discovery order for every attempted `begin`, including
  a timed-out or malformed begin. `end` is idempotent and can cancel by
  `request_id` when no valid session response was received.
- Keep every mutation in one runner invocation when one hold must span the
  whole batch. Multiple runner calls create unheld gaps between transactions.
- Surface release failures. A release failure happens after an authorized
  mutation may have run; do not blindly retry the mutation. Reconcile the
  provider receipt and repository state first.

Providers must not mutate the protected repository during `begin`, `check`, or
`end`. They may mutate only their own lease/session state.

## Discovery

Repository policy is discovered first. When the canonical repository root
contains `.commit-writer-session.json`, it must have this exact shape:

```json
{
  "schema": "commit-writer-session-policy/v1",
  "required": true,
  "providers": [
    {
      "argv": ["{python}", "{repo}/tools/writer_provider.py", "--config", "{resource:config}"],
      "source": "tools/writer_provider.py",
      "source_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
      "modules": [
        {
          "name": "writer_protocol",
          "source": "tools/writer_protocol.py",
          "source_sha256": "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
        }
      ],
      "resources": [
        {
          "name": "config",
          "source": "config/writer-policy.json",
          "source_sha256": "123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0"
        }
      ]
    }
  ]
}
```

Policy keys, provider keys, module keys, and resource keys are closed schemas. `required` must
be `true`, and `providers` must be non-empty. Each provider declares an ordered
`modules` array, which may be empty when the entry has no local imports. Module
names must be safe dotted Python identifiers; names and source paths may not
repeat, and each module has an exact repo-relative path and SHA-256. The order
is dependency-first: a module may import a previously declared sealed module,
not one declared later. `{python}` expands to the runner's absolute
Python interpreter. `{repo}` and `{repo}/RELATIVE` expand from the canonical
Git root; absolute paths, parent traversal, symlinks, unsupported placeholders,
and expansions outside that root are rejected. Each provider must use
`{python}` followed by its pinned repo-relative `source`. A provider may also
declare uniquely named `resources`, each with a safe name, repo-relative path,
and SHA-256. Every resource must appear exactly once in argv as
`{resource:NAME}`. The placeholder stays inert during discovery and expands
only at invocation to an inherited `/dev/fd/N` pseudopath; raw resource bytes
and live paths never enter argv. For every provider
operation, the runner opens that source with `O_NOFOLLOW`, binds its file
identity before and after the read, and verifies the SHA-256. It then copies
those already-verified bytes into a mode-`0600` secure temporary inode, fsyncs
it, opens the same inode read-only with `O_NOFOLLOW`, verifies identity and
size, unlinks its name, and closes the writable descriptor before spawning.
Only anonymous read-only descriptors reach the fixed bootstrap; attempted
writes through them fail with `EBADF`. Code snapshots are consumed by the
bootstrap; resource snapshots stay open through provider execution. The
bootstrap removes the empty cwd entry and every `sys.path`/`PYTHONPATH` entry
whose resolved path is the managed repo root or any descendant, loads sealed modules into
`sys.modules` in declared order, then reads and executes the sealed entry.
Undeclared local imports and incorrect dependency order therefore fail instead
of falling through to mutable repo files, even when cwd or `PYTHONPATH` names a
live source directory. Standard-library and installed-package paths remain
available. Entry and modules receive synthetic non-live `__file__` values and
their verified source digest as `_HELD_SOURCE_SHA256`; no live code pathname is
available through those globals. The bootstrap never rereads mutable source
paths or inodes. Provider
request JSON remains the sole stdin payload, and source/request content is
never placed in argv or a reusable named temporary file. Atomic replacement or
in-place rewrite after verification cannot swap in unverified bytes.

The runner reads all policy planes before provider discovery:

- the exact regular blob committed at `HEAD`;
- the index entry, which must be one regular stage-zero blob;
- the regular non-symlink worktree file.

Once `HEAD` contains a strict policy, it is the durable managed marker and
required-policy floor. Index and worktree policies must both exist, agree byte
for byte, and independently pass the strict current-policy/provider-pin checks.
`git rm`, unstaged deletion, staged weakening, unstaged replacement, conflict
stages, or unreadable/ambiguous Git evidence is a configuration failure with
`mutation_started=false`. HEAD and current bytes need not be identical: a
deliberate staged strict policy and provider-hash upgrade is admitted when index
and worktree agree, and the upgraded provider is the one executed under its
new pin.

When `HEAD` has no policy, a strict worktree policy is admitted so it can fence
its own first landing; a staged copy, when present, must match it. A staged-only
policy is rejected because the provider path and policy cannot be verified as
one worktree state. Only absence from HEAD, index, and worktree selects portable
mode. A malformed or weakened policy, unavailable provider source, or digest
mismatch also fails closed. Repository providers are additive: ambient
providers cannot replace them or downgrade their required-provider condition.

After repository policy, ambient discovery uses the first configured source:

1. Explicit `--provider EXECUTABLE` and `--provider-json JSON_ARGV` options.
2. `COMMIT_WRITER_SESSION_PROVIDERS`, a JSON array whose entries are executable
   strings or argv arrays.
3. An executable named `commit-writer-session-provider` on `PATH`.

Examples:

```bash
export COMMIT_WRITER_SESSION_PROVIDERS='[
  ["python3", "/opt/writer/provider.py"],
  "/usr/local/bin/site-writer-fence"
]'
```

```bash
python3 commit/scripts/run_writer_fences.py \
  --repo /path/to/repo \
  --provider-json '["python3","/opt/writer/provider.py"]' \
  --step-json '["git","add","src","tests"]' \
  --step-json '["git","commit","-m","feat(core): add change"]'
```

Configured values are argv, not shell fragments. Pipes, redirects, command
substitutions, and quoting syntax are never interpreted.

When neither repository policy nor ambient discovery finds a provider, the default is portable mode: the runner
executes the protected argv steps without a provider. Require an authority
provider explicitly with either:

```bash
--require-provider
```

or:

```bash
export COMMIT_WRITER_SESSION_REQUIRE_PROVIDER=1
```

Required-provider mode fails before mutation when discovery is empty. Accepted
boolean environment values are `1/0`, `true/false`, and `yes/no`.

It also fails before mutation when discovery yields **only unpinned providers**.
Ambient entries carry no pinned source and no digest, so `_verify_provider_source`
has nothing to check and the executable that runs is whatever the ambient
configuration names; treating that as satisfying a fail-closed requirement is the
opposite of what the flag promises. Such a run exits `EXIT_PROVIDER_REQUIRED` with
outcome `provider_required_but_unpinned` and an `unpinned_providers` list, without
invoking any of them. Because repository providers are additive, an ambient provider
alongside a pinned one only adds veto power and is still accepted. Override with:

```bash
--allow-unpinned-provider
```

## Policy Home

By default the protected repository declares its own fence, so a repository can only
be fenced by an authority it already carries — leaving un-onboarded repositories with
a choice between planting a policy file in each one or mutating them unfenced.

```bash
--policy-home /path/to/trusted-repo
```

or:

```bash
export COMMIT_WRITER_SESSION_POLICY_HOME=/path/to/trusted-repo
```

The policy document, its pinned provider sources, and the sealed entry's import
sandbox root all come from the policy home; `{repo}` in policy argv expands to the
policy home. The protected repository stays `--repo`, and that is the root sent in
the request `repository` block, so the provider still leases the repository actually
being mutated. The policy home must pass the same strict checks as an in-repo policy
(HEAD binding, index/worktree agreement, digest pins); a home with no strict policy
fails closed. When the protected repository declares its own policy, `--policy-home`
is **rejected** rather than silently ignored — its own policy is authoritative. A
policy home that resolves to the protected repository itself is a no-op.

## Acquisition Sealing

Pinned sources are read and digest-verified exactly once, before the first `begin`,
and the verified bytes are held for the life of the transaction. Every `begin`,
`check`, and `end` seals fresh read-only unlinked fds from those held bytes, after
re-asserting the acquisition digest.

The runner previously re-read each pinned source from disk on every call, including
the `end` call in its release `finally` block. A protected step that legitimately
rewrote a pinned source therefore poisoned its own release: the mutation landed,
`end` failed with `provider ... source digest does not match repository policy`, the
receipt became `release_failed_after_preflight`, and the durable session was left
held until released by hand. Holding at acquisition removes that path — the process
executes exactly what it verified, and later on-disk churn cannot strand a session.

Drift that exists *before* the run is unaffected and still fails closed at preflight,
with `mutation_started` false and nothing acquired. Acquisition digests are reported
per provider in the receipt under `provider_acquisitions`.

## Request Schema

The runner writes one compact JSON object to provider stdin. A provider reads
stdin to EOF and writes exactly one JSON response object to stdout. Diagnostics
belong on stderr.

All operations use this request shape:

```json
{
  "schema": "commit-writer-session/v1",
  "request_id": "transaction-uuid:provider-index",
  "operation": "begin",
  "repository": {
    "root": "/canonical/repo/root",
    "git_dir": "/canonical/repo/git-dir",
    "git_common_dir": "/canonical/repo/common-dir",
    "head_oid": "0123456789abcdef...",
    "head_ref": "refs/heads/main"
  },
  "session": null,
  "transaction": {
    "step_count": 2
  }
}
```

`head_oid` is `null` for an unborn repository. `head_ref` is `null` for a
detached `HEAD`. `git_dir` and `git_common_dir` let a provider distinguish a
linked worktree from its shared repository. Treat all repository identity
fields as inputs to validate, not as proof by themselves.

The same `request_id` is reused for `begin`, `check`, and `end` for one
provider. This is the provider's idempotency and cleanup key.

### `begin`

`begin` attempts to acquire and hold writer exclusion. Its request has
`session: null`.

An allowed response is:

```json
{
  "schema": "commit-writer-session/v1",
  "request_id": "transaction-uuid:provider-index",
  "operation": "begin",
  "verdict": "allow",
  "message": "writer session acquired",
  "session": {
    "id": "opaque-session-id",
    "fencing_token": "opaque-fencing-token"
  }
}
```

`session.id` and `session.fencing_token` must be non-empty opaque strings. The
provider must check the fencing token during later operations; merely parsing
it is not authority validation.

A denied begin uses `blocked` or `indeterminate` and a null session:

```json
{
  "schema": "commit-writer-session/v1",
  "request_id": "transaction-uuid:provider-index",
  "operation": "begin",
  "verdict": "blocked",
  "message": "another writer owns the component",
  "session": null
}
```

Do not acquire a session that cannot be recovered by `request_id`. If the
runner times out before receiving a valid session object, it sends `end` with
the same `request_id` and `session: null` so the provider can cancel any
uncertain acquisition.

### `check`

`check` revalidates authority and the held fencing token immediately before
the mutation plan. The request carries the session returned by `begin`.

```json
{
  "schema": "commit-writer-session/v1",
  "request_id": "transaction-uuid:provider-index",
  "operation": "check",
  "verdict": "allow",
  "message": "session still owns writer authority"
}
```

Return `blocked` for a known exclusion or authority conflict. Return
`indeterminate` when the provider cannot prove authority, freshness, identity,
or session ownership. Both prevent every protected step.

### `end`

`end` releases or cancels the writer session. It is mandatory, idempotent, and
safe to repeat. The runner calls it in `finally` for every attempted begin.

With a valid begin response, the request carries that session. After a begin
timeout or malformed response, it may carry `session: null`; release by the
stable `request_id` in that case.

```json
{
  "schema": "commit-writer-session/v1",
  "request_id": "transaction-uuid:provider-index",
  "operation": "end",
  "verdict": "allow",
  "message": "writer session released"
}
```

A provider that cannot confirm release returns `indeterminate`. The runner
records the release failure and exits nonzero even when protected steps already
succeeded.

## Response Validation

Responses are deliberately strict. Every response requires exactly:

- `schema`: `commit-writer-session/v1`
- `request_id`: an exact echo of the request
- `operation`: an exact echo of `begin`, `check`, or `end`
- `verdict`: `allow`, `blocked`, or `indeterminate`
- `message`: a string suitable for an operator receipt

An allowed `begin` also requires exactly `session.id` and
`session.fencing_token`. A denied begin permits only a null or omitted
`session`. `check` and `end` responses do not include `session`. Unknown fields,
wrong types, trailing stdout, and mismatched identifiers are schema failures.

Schema failures are `indeterminate`; they never degrade to portable mode. A
configured but broken provider is different from no provider being configured.

## Verdict Aggregation

Aggregate every provider at each preflight phase using this ordering:

```text
allow < indeterminate < blocked
```

The worst verdict wins. A known block remains visible even if another provider
is unreachable. Both non-allow aggregate verdicts prevent the mutation plan.

## Transaction Execution

Pass one command after `--` for a one-step transaction:

```bash
python3 commit/scripts/run_writer_fences.py --repo /path/to/repo -- \
  git commit -m "fix(core): correct boundary"
```

Use repeated `--step-json` arguments when the same session must span multiple
mutations:

```bash
python3 commit/scripts/run_writer_fences.py \
  --repo /path/to/repo \
  --step-json '["python3","/tmp/update-ignore.py","/path/to/repo/.gitignore"]' \
  --step-json '["git","add",".gitignore","src/core.py","tests/test_core.py"]' \
  --step-json '["git","commit","-m","fix(core): correct boundary"]'
```

Prepare helper programs and replacement content outside the protected worktree.
The runner executes steps sequentially with the repository root as `cwd`, stops
after the first nonzero step, and always proceeds to `end`. A protected command
failure can leave an intentionally partial mutation; inspect it before retrying.

The runner emits one JSON receipt on stdout. Protected command output is sent
to stderr so receipt parsing remains deterministic.

## Exit Codes

| Code | Meaning | Mutation plan ran? |
| ---: | --- | --- |
| `0` | all preflight checks allowed, steps succeeded, releases confirmed | yes |
| `64` | local configuration or argv schema error | no |
| `69` | a provider was required but discovery was empty | no |
| `70` | aggregate preflight verdict was `blocked` | no |
| `71` | aggregate preflight verdict was `indeterminate` | no |
| `72` | a release was not confirmed | possibly |
| other | first protected command's nonzero exit | possibly |

Never infer success from process exit alone. Read `preflight_verdict`,
`mutation_started`, `step_results`, `release_verdict`, and `outcome` from the
receipt.
