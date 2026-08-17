# Oracle benchmark harness

`references/oracle-slo.md` records one live measurement, taken by hand on
2026-08-06. That is enough to state a verdict once and not enough to state
whether anything improved. The next measurement has to be taken in the same
order, summarized with the same arithmetic, and compared field for field — or
the two numbers are not comparable and "we made it faster" is an opinion.

This harness is that fixed procedure. It turns recorded samples into a
versioned, redacted receipt whose digest covers every field, so two runs are
either byte-identical or provably different.

- Script: `assets/scripts/oracle-subagent-benchmark.mjs`
- Tests: `tests/oracle-subagent-benchmark.test.mjs`
- Targets: `references/oracle-slo.md`

## It cannot invoke the Oracle

Structural, not a promise, and the part to re-check if the module is ever
edited:

- **Five imports.** `MODULE_IMPORT_ALLOWLIST` is `node:crypto`, `node:fs`,
  `node:fs/promises`, `node:path`, `node:url`. The test suite parses the
  module's own source — static `from "…"` and dynamic `import("…")` both, since
  a dynamic import is exactly where an unwanted reach would hide — and fails on
  anything else. There is no `node:child_process`, no `node:net`, no
  `node:http`, and no import of any `oracle-*` module, so no code path starts a
  service, opens a socket, reads a credential, or submits a prompt.
- **Measurement is injected.** `collectSamples` takes the probes as function
  arguments. The harness holds the *procedure*, not the ability to run it.
- **The CLI has no live mode.** `--live` is refused with
  `live_collection_unavailable` rather than quietly wiring one up. The only
  input is a recorded sample file.

## Invalid input throws; a bad result does not

This is the distinction the module is built around, and getting it backwards
would break the thing in opposite directions.

A sample file with a negative duration, a torn index, an unknown key, or a
non-canonical timestamp is **unreadable**. Summarizing it would invent a number,
so `normalizeSampleSet` throws (`sample_invalid`, `samples_invalid`,
`rss_observation_invalid`).

A run where every warm call errored is perfectly **readable**, and it means the
lane is broken. That becomes a receipt with `warm.code =
"no_successful_samples"`, a `no_samples` gate verdict, and an overall `fail` —
because throwing there would destroy the very measurement someone needs to see.

The same reasoning governs the `degraded` status. `final_dom_to_output_p95` is
declared in the SLO and marked `applicable: false`: this lane returns over HTTPS
and has no final DOM. A run that meets every applicable gate still reports
`degraded`, never `pass`, so an untested gate cannot go green by never being
exercised. Deleting the gate would quietly shrink the contract to whatever this
lane happens to measure.

## The sample set

Schema `oracle-subagent.benchmark-samples.v1`. Key set is exact; unknown keys
are refused.

```json
{
  "schema": "oracle-subagent.benchmark-samples.v1",
  "run_id": "oracle-bench-2026-08-06",
  "model": "gpt-5-5-instant",
  "started_at": "2026-08-06T19:32:42.383Z",
  "ended_at": "2026-08-06T19:36:56.426Z",
  "cold": [{ "index": 0, "duration_ms": 7273.8893, "outcome": "ok" }],
  "warm": [{ "index": 0, "duration_ms": 4206.743224, "outcome": "ok" }],
  "rss": [{ "index": 0, "root_pid": 4242, "rss_bytes": 958316544 }]
}
```

- `outcome` is `ok`, `error`, or `aborted`. Only `ok` samples enter a
  percentile: otherwise a lane could improve its p95 by failing faster, which is
  the opposite of the property being measured. Failures are counted in
  `failed` and gated separately by `warm_successful_runs`.
- `index` must be contiguous from zero. A gap means samples were dropped
  somewhere between the run and the file, and a percentile over an unknown
  subset of a run is not that run's percentile.
- Timestamps must be **canonical** RFC3339, not merely parseable. One that
  round-trips differently on two machines makes the digest irreproducible.
- `root_pid` is read and discarded. Only the distinct count reaches the
  receipt.
- Normalization is idempotent, so the set `collectSamples` returns is still
  accepted by `buildReceipt`.

**Measurement order**, matching `references/oracle-slo.md`: all cold runs, then
one baseline RSS reading, then each warm run followed by an RSS reading. The
series therefore has `warm_runs + 1` points and `index` is the run number.

## The receipt

Schema `oracle-subagent.benchmark-receipt.v1`. The fields `.6.16` needs to
compare two runs are `cold.p95_ms`, `warm.p95_ms`, `browser_pids`,
`max_rss_growth_bytes`, and `receipt_sha256`.

| Field | Meaning |
| --- | --- |
| `cold`, `warm` | `count`, `successful`, `failed`, `min_ms`, `p50_ms`, `p95_ms`, `max_ms`, `code` |
| `browser_pids` | distinct root PIDs seen across all RSS observations |
| `browser_pid_samples` | how many observations that spanned |
| `max_rss_growth_bytes` | peak growth over baseline, not the endpoint |
| `rss` | `baseline_bytes`, `final_bytes`, `final_growth_bytes`, `slope_bytes_per_run`, `observations` |
| `slo` | the contract this run was judged against, carried in the receipt |
| `gates` | per-gate `comparator`, `target`, `observed`, `verdict`, `code` |
| `status` | `pass`, `degraded`, or `fail` |
| `receipt_sha256` | digest over everything above |

**`max_rss_growth_bytes` is the peak, not the endpoint.** A run that grows and
then releases still grew, and the endpoint alone would hide it.

**`browser_pids` is the leak detector that matters most.** An RSS series that
looks flat because the browser was restarted underneath it is not a flat RSS
series, and only the distinct-PID count can tell the difference.

**The SLO travels with the receipt.** A stored receipt states the target it was
judged against, so a later target change cannot silently reinterpret an old
result.

### Gates

| Gate | Comparator | Target | Source |
| --- | --- | ---: | --- |
| `cold_cli_to_submit_p95` | `lte` | 12,000 ms | SLO release targets |
| `warm_browser_to_submit_p95` | `lte` | 4,000 ms | SLO release targets |
| `final_dom_to_output_p95` | `lte` | 5,000 ms | declared, `applicable: false` |
| `warm_successful_runs` | `gte` | 20 | SLO release targets |
| `browser_pids` | `eq` | 1 | SLO release targets |
| `max_rss_growth_bytes` | `lt` | 104,857,600 | 100 MiB |

Latency targets are inclusive (`lte`); the RSS budget is not (`lt`). One failing
gate makes the run `fail` — passes elsewhere do not buy it off.

Pass a different contract with `--slo path.json` or the `slo` option. The SLO is
deliberately an *input*, so a hypothesis can be checked without editing the
shipped baseline. It does not change the measurement, only the target the
receipt records having been judged against.

### p95 is nearest-rank

`ceil(p × n)` into the sorted successful samples, no interpolation, so the
result is always an observation that actually happened. Three cold samples
therefore use their maximum; twenty warm samples use the 19th sorted value.

This is the rule `references/oracle-slo.md` already states and the same rule the
host-side summarizer uses. Two summaries of one run must not disagree about
which observation p95 names, so it is pinned here rather than re-chosen.

Selected order statistics (`min_ms`, `p50_ms`, `p95_ms`, `max_ms`) are reported
raw — rounding one would make it stop matching its own run. Derived values
(`slope_bytes_per_run`) are rounded to six decimal places, the precision the SLO
receipt already reports.

### It never carries measurement context out

A benchmark run knows the prompt it sent, the profile it used, and the PID it
watched. None of those are receipt fields. `assertReceiptSafe` inverts the usual
test the way `oracle-subagent-canary.mjs` does: a receipt may contain only keys
this module names, and each key that may hold a string is bound to the one form
that string may take — `run_id` to its pattern, `model` to a model id, `code`
and `gate` to this module's own vocabulary, `status` and `verdict` to their
enums, `receipt_sha256` to hex.

Keyed rather than value-shaped on purpose. A validator that accepted "any
lowercase token up to 64 characters" anywhere in the tree would happily pass a
conversation slug or a profile directory name. Binding each string to its key
means an extra string has nowhere legal to land, so a prompt fragment, a path, a
cookie, a bearer token, and a Tailnet IP all fail the same way.

### The digest

`receipt_sha256` is SHA-256 over the canonical JSON of the receipt with the
digest field removed — keys sorted recursively, so it is stable against key-order
churn and cannot be satisfied by editing a field the hash "happened not to
cover". Tests tamper with `status`, `warm.p95_ms`, `max_rss_growth_bytes`,
`browser_pids`, `rss.baseline_bytes`, `slo.warm_p95_ms_max`, and every gate
verdict, and each is caught.

`buildReceipt` is pure: the same samples and the same `generated_at` produce
byte-identical receipts and the same digest. That is what makes a later run
comparable rather than merely adjacent. `generated_at` is a required argument —
there is no implicit clock in the pure path.

## Running it

```bash
# Summarize a recorded run. --now pins generated_at so the digest is reproducible.
node deep-research-prompt/assets/scripts/oracle-subagent-benchmark.mjs \
  --samples run.json --json --now 2026-08-06T19:40:00.000Z

# Human line: the five numbers, and nothing else.
node deep-research-prompt/assets/scripts/oracle-subagent-benchmark.mjs --samples run.json
```

```
fail cold_p95=7273.8893 warm_p95=9614.340436 browser_pids=1 \
  max_rss_growth_bytes=14237696 sha256=3e9ee85e…
```

### Collecting on the host

Collection is library-level, because the probes are the seam where this repo
stops and the live box begins:

```js
import {
  buildReceipt,
  collectSamples,
} from "./deep-research-prompt/assets/scripts/oracle-subagent-benchmark.mjs";

const samples = await collectSamples({
  plan: {
    run_id: "oracle-bench-2026-08-20",
    model: "gpt-5-5-instant",
    cold_runs: 3,
    warm_runs: 20,
  },
  // cold: time a fresh Node process from spawn to the `target` progress event.
  // warm: time one sequential askOracle call against the running browser.
  probe: async ({ phase, index }) => ({ duration_ms, outcome: "ok" }),
  // aggregate VmRSS for the oracle-chatgpt-cdp.service MainPID and descendants.
  rssProbe: async ({ index }) => ({ root_pid, rss_bytes }),
  clock: () => new Date().toISOString(),
});

const receipt = buildReceipt({ samples, generatedAt: new Date().toISOString() });
```

Both halves of a probe result are validated, so a probe that returns an extra
field, a negative duration, or an implausible PID is refused
(`probe_result_invalid`, `rss_probe_result_invalid`) rather than folded into a
number.

Keep the host rules from `references/oracle-slo.md`: short non-sensitive
prompts, the configured loopback CDP port, and never stop, restart, log out, or
wipe the shared browser to manufacture a cold sample.

### Exit codes

| Code | Status | Meaning |
| --- | --- | --- |
| 0 | `pass` | every applicable gate ran and passed |
| 0 | `degraded` | nothing failed, but a declared gate was not exercised (without `--require-complete`) |
| 1 | `fail` | a gate failed, or a phase had no successful run |
| 2 | — | usage, unreadable input, or a malformed sample set |
| 3 | `degraded` | not exercised, with `--require-complete` |

`--require-complete` is what a release gate should use: it turns "a declared
gate was never measured" into a non-zero exit instead of a quiet pass.

## Validation

```bash
cd "$HOME/repos/opensource/skills"
node --check deep-research-prompt/assets/scripts/oracle-subagent-benchmark.mjs
node --test deep-research-prompt/tests/oracle-subagent-benchmark.test.mjs
```

The 2026-08-06 run is encoded as a fixture and the harness re-derives that
document's published figures exactly — cold p95 `7273.8893 ms`, warm min
`4206.743224 ms`, p95 `9614.340436 ms`, max `10027.255714 ms`, `browser_pids` 1,
`max_rss_growth_bytes` `14,237,696`, final growth `13,348,864` — including its
**failing** warm gate and its overall `fail`. A summarizer that cannot re-derive
the measurement it is meant to be compared against is not a baseline.

### Not proven here

- **The harness has never run against the live Oracle host.** Nothing in it
  observes the box; `collectSamples` has only ever been driven by test probes.
  Wiring the two real probes on the host is the remaining step, and it needs a
  write scope that includes the host-side runner.
- **The 2026-08-06 fixture reconstructs only what was published.** The SLO
  document gives the warm run's min, p95, and max but not its seventeen interior
  samples, and gives RSS baseline, peak, and final but not the intermediate
  readings. The fixture's interior values are filler chosen to preserve the
  published order statistics. Consequently `p50_ms` and `slope_bytes_per_run`
  from that fixture are **artifacts of the fixture**, not of the original run —
  the harness reports `slope_bytes_per_run` `728,077.302597`, where the document
  records `203,411.616`. Feeding the original per-run series through the harness
  would settle it.
- **The digest is not the host artifact's digest.** `receipt_sha256` covers this
  receipt shape. The `5d5f6629…` in `references/oracle-slo.md` is the SHA-256 of
  the host's `/tmp/oracle-subagent-e2e/FINAL/benchmark.json`, a different
  artifact; the two are not expected to match and neither verifies the other.

## Related

- `references/oracle-slo.md` — the release targets and the 2026-08-06 receipt.
- `references/oracle-subagent-compatibility.md` — the drift canary, whose
  closed-vocabulary redaction this module follows.
- `references/oracle-vps-host.md` — the host, its CDP port, and its doctor.
- `references/oracle-live-proof-matrix.md` — the live success/failure matrix.
