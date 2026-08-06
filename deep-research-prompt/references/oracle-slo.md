# Oracle latency and resource SLO

This contract covers the live `oracle-ask` path on
`skillbox-portfolio-devbox`: a persistent hidden-headful Chrome supplies the
authenticated session and one sentinel bundle, while the answer travels over
the direct ChatGPT HTTPS lane.

## Release targets

| Gate | Target | 2026-08-06 result |
| --- | ---: | ---: |
| Cold CLI-to-submit p95 | `<= 12,000 ms` | `7,273.8893 ms` — pass |
| Warm browser-to-submit p95 | `<= 4,000 ms` | `9,614.340436 ms` — **fail** |
| Final-DOM-to-output | `<= 5,000 ms` | not exercised; this lane has no final DOM |
| Warm run count | `>= 20` | `20/20` successful — pass |
| Browser PID count | `1` | `1` — pass |
| Chrome-tree RSS growth | `< 100 MiB` | max `14,237,696 bytes` — pass |

The failed warm-latency gate is tracked by
`skillbox-invisible-oracle-subagent-hjuc.6.16`. Do not weaken the threshold or
hide this failure in an aggregate pass.

## Measurement boundaries

- **Cold CLI-to-submit:** parent observes a fresh Node process from spawn until
  `askOracle` emits the `target` progress event immediately before
  `postConversation`.
- **Warm browser-to-submit:** one Node process performs sequential `askOracle`
  calls against the already-running browser; each sample runs from call start
  to the same `target` event.
- **Completion publish proxy:** `askOracle` promise resolution to the benchmark
  recorder. This is not a substitute for a DOM-path measurement.
- **RSS:** aggregate `VmRSS` for the
  `oracle-chatgpt-cdp.service` `MainPID` and all descendants, sampled at the
  baseline and after every warm call.
- **p95:** nearest-rank percentile. Three cold samples therefore use their
  maximum; twenty warm samples use the 19th sorted value.

Prompts must be short and non-sensitive. Benchmark output must never contain
cookies, bearer tokens, sentinel values, profile paths, or raw Tailnet IPs.
Use the configured loopback CDP port; never stop, restart, log out, or wipe the
shared browser to manufacture a cold sample.

## Live receipt: 2026-08-06

- Window: `2026-08-06T19:32:42.383Z` to
  `2026-08-06T19:36:56.426Z`
- Model: `gpt-5-5-instant`
- Cold samples: `7,273.8893`, `6,313.497611`, and `6,755.460291 ms`
- Warm samples: min `4,206.743224 ms`, p95 `9,614.340436 ms`, max
  `10,027.255714 ms`
- Answer success: `3/3` cold and `20/20` warm
- Completion-publish proxy p95: `0.061988 ms`
- Browser root PID count across all RSS samples: `1`
- Chrome-tree RSS baseline: `958,316,544 bytes`
- Chrome-tree RSS final: `971,665,408 bytes`
- Chrome-tree final growth: `13,348,864 bytes`
- Chrome-tree maximum growth over baseline: `14,237,696 bytes`
- RSS linear slope: `203,411.616 bytes/run`
- Machine receipt: `/tmp/oracle-subagent-e2e/FINAL/benchmark.json`
- Receipt SHA-256:
  `5d5f66296e92838e2b7496ec5acb5c658d7927b1c30cbfd27da6ef96f0908448`

Overall verdict: **fail**. Cold latency, twenty-run reliability, PID reuse, and
RSS pass. Warm latency fails. Final-DOM-to-output remains explicitly untested
because the production ask lane returns through HTTPS rather than a DOM
watcher; a DOM fallback benchmark needs a separately authorized node and write
scope.
