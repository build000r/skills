# Grok Sidecar Observations

Purpose: accumulate concrete evidence about which divide-and-conquer sidecar
tasks Grok handles well or poorly, so future orchestrators can route low-risk
work more deliberately.

## 2026-06-15: Jame CRAP Slice Selection

- Repo: `/Users/b/repos/jame`
- Task: read-only sidecar analysis for `record_corpus.rs::run_recorded_batch_take`,
  current CRAP 14.88, and propose one deterministic test/refactor seam.
- Good: Grok correctly identified that the hotspot is an interactive batch loop
  and proposed a deterministic seam that avoids live microphone input.
- Bad: the first run with `--max-turns 2` returned no useful output and exited
  with `Max turns reached`; the retry returned a broader dependency-injection
  seam for capture and decision sources even though the requested slice was a
  smaller pure report-formatting extraction.
- Routing lesson: Grok is acceptable for read-only candidate generation on
  simple hotspot analysis, but the lead should narrow the final worker prompt
  and not hand it direct edit authority unless the write scope is trivial and
  easily reversible.
- Good future task shape: "Inspect this one function and list two pure helper
  seams; do not design test harness injection or broad architecture changes."
- Risky future task shape: "Refactor this interactive loop to make it testable"
  without a strict edit budget; it may widen into dependency injection.

### CASS Search Strings

- `grok \"Max turns reached\" \"record_corpus\"`
- `grok sidecar \"run_recorded_batch_take\"`
- `Grok CRAP slice selection dependency injection`
- `grok sidecar read-only candidate generation low-risk`
