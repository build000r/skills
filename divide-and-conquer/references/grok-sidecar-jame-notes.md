# Grok sidecar — observed performance notes (jame repo)

Running log of how the Grok CLI sidecar (`grok -p` headless / `grok --yolo`) performs
on delegated tasks, so future divide-and-conquer runs can pick better Grok work.
Pair with `grok-sidecar-selection.md`. Each entry: task class, prompt shape, verdict,
and a CASS-searchable reference so the evidence is recoverable.

## How to mine the evidence in CASS

Grok sidecar runs and their outcomes are recoverable from the central evidence DB:

```bash
sbp cass search "grok sidecar jame" --limit 20
sbp cass search "grok -p read-only audit jame-core"      # read-only audits
sbp cass search "divide-and-conquer jame grok verdict"   # tagged verdicts below
```

Search the orchestrator transcript (this session) for the literal verdict tags
(`GROK-VERDICT:GOOD` / `GROK-VERDICT:MIXED` / `GROK-VERDICT:BAD`) to jump to the
exact run.

## Routing heuristic (current)

- **Trust Grok with (low risk, easy to verify):** read-only audits/inventories
  (panic-site sweeps, TODO/FIXME scans, "list all X" enumerations), mechanical
  single-file edits with an exact spec, running a named command and summarizing
  output, drafting commit messages from a diff.
- **Do NOT trust Grok with (high blast radius in a shared tree):** anything that
  edits files concurrently with other agents (git-stash-wipe + half-edited-compile
  races), multi-file refactors, anything needing the FFI/ABI or DSP-correctness
  judgment, anything that runs `./scripts/dev-check.sh` (stashes the whole tree).
- **Hard rule learned:** never let a sidecar (grok/codex) run `git stash`,
  `git commit`, `dev-check.sh`, or `cargo fmt --all` (write) in a shared working
  tree while other writers are live. Keep Grok read-only here unless it owns an
  isolated worktree.

## Verdict log

<!-- newest first; tag each with GROK-VERDICT:{GOOD|MIXED|BAD} for CASS -->

### 2026-06-16 — inlined guitar gate excerpt scout — GROK-VERDICT:MIXED
- Task: direct `grok -p` with the relevant `crates/jame-core/src/guitar.rs`
  excerpt inlined, `--disable-web-search`, `--max-turns 1`, `--no-subagents`,
  asking for one read-only low-risk refactor opportunity.
- Result: usable target selection. Grok identified
  `gate_observe_matches_state_machine_model` / `GuitarPitchGate::check` as the
  right low-risk area and stayed read-only.
- Correction needed: its suggested route was to share the production gate
  decision helper with the proptest model. That would reduce the independence
  of the state-machine oracle. The lead kept the production path untouched and
  extracted only test-side helpers (`expected_gate_decision`,
  `expected_implausible_jump`, `observe_expected_acceptance`), then verified
  with the exact proptest and clippy before committing.
- Routing takeaway: Grok can be useful when all code context is inlined and the
  expected output is one tiny candidate, but treat its patch-shape advice as a
  lead, not an implementation plan. Watch specifically for suggestions that
  make tests less independent by reusing production helpers.
- CASS: `sbp cass search "GROK-VERDICT MIXED guitar gate excerpt scout"` /
  `sbp cass search "grok inlined guitar gate model test helper"` /
  `sbp cass search "expected_gate_decision expected_implausible_jump grok"`.

### 2026-06-15 — broad random-fix scout with plan-mode Grok — GROK-VERDICT:BAD
- Task: direct `/Users/b/.grok/bin/grok -p ... --cwd /Users/b/repos/jame
  --permission-mode plan --disable-web-search --no-memory --no-subagents
  --output-format plain` asking for exactly one low-risk deterministic random-fix
  opportunity after all ready Beads were drained. Retries used `--max-turns 1`,
  `--max-turns 3`, and `--max-turns 8`.
- Result: no usable findings. Every run exited with `Max turns reached` and
  returned no candidate title, file/function, root cause, patch plan, validation
  commands, or artifact.
- Why BAD: this is the same failure class as narrower plan-mode source scouts,
  even with a larger turn cap. The task requires repo reading plus judgment about
  recent commits and dirty-file boundaries; Grok spent its turns before emitting
  a packet, so it did not save root-orchestrator attention.
- Routing takeaway: do not use direct headless plan-mode Grok for broad Jame
  random-fix candidate selection. Use it only for tiny inlined clerk/inventory
  artifacts or a named read-only audit with expected output shape; require
  non-empty stdout before acting. For code-opportunity selection, use Codex/root
  inspection or a normal worker.
- CASS: `sbp cass search "grok broad random-fix scout max turns reached"` /
  `sbp cass search "GROK-VERDICT BAD jame broad random-fix scout"` /
  `sbp cass search "grok permission-mode plan max-turns 8 no candidate"`.

### 2026-06-15 — record-corpus read-only review with plan-mode Grok — GROK-VERDICT:BAD
- Task: direct `grok --prompt-file ... --permission-mode plan --disable-web-search --max-turns 1 --no-memory --cwd /Users/b/repos/jame` asking for one or two low-risk deterministic hardening opportunities in `crates/jame-cli/src/commands/record_corpus.rs`.
- Result: no usable findings. The process exited with `Max turns reached` and produced no review packet or artifact.
- Why BAD: this prompt shape asked for source-aware judgment, not pure inlined clerk formatting. With `--max-turns 1`, Grok consumed the turn before emitting anything useful. It did not help route or verify the `jame-keow` hardening slice.
- Routing takeaway: do not use a one-turn plan-mode Grok run for source-aware code review. If Grok is used here, keep it to G0/G1 tasks with all input inlined or raise the turn cap only when the work is non-blocking; still require non-empty stdout or a named artifact before acting on it.
- CASS: `sbp cass search "grok record-corpus read-only review max turns reached"` /
  `sbp cass search "GROK-VERDICT BAD jame-keow grok"`.

### 2026-06-15 — serve command read-only scout with plan-mode Grok — GROK-VERDICT:BAD
- Task: direct `/Users/b/.grok/bin/grok --cwd /Users/b/repos/jame --permission-mode plan --disable-web-search --no-subagents --max-turns 4 --output-format plain -p ...` asking for a concise read-only hardening opportunity in `crates/jame-cli/src/commands/serve.rs::serve_command`.
- Result: no usable findings. The process exited with `Max turns reached` before returning a scout packet, so the lead ignored it and performed local inspection instead.
- Why BAD: this was still source-aware code judgment under a tight turn cap. Even with a narrow function and explicit "do not edit" instruction, Grok did not produce the required artifact.
- Routing takeaway: use Grok for Jame only when the input is already inlined and the output is a tiny clerking artifact, or when the run writes a named artifact whose existence can be checked. Do not block a CRAP/refactor loop waiting on a plan-mode code scout.
- CASS: `sbp cass search "grok serve_command read-only scout Max turns reached"` /
  `sbp cass search "GROK-VERDICT BAD serve command read-only scout"` /
  `sbp cass search "Jame random-fix Grok permission-mode plan max-turns 4"`.

### 2026-06-14 — session usage pattern (why grok was used sparingly)
This jame hardening session was dominated by **complex correctness work** —
cross-bead SwiftUI state-machine bugs, DSP regressions (bass_tilt chroma), FFI
ABI safety, native↔wasm parity diagnosis, CRAP-driven refactors with golden
cascades. That is NOT grok's lane (it needs careful multi-file reasoning +
verify-before-commit, which the Claude subagents did well). Grok was used once,
for the read-only panic-site audit below (GOOD). **Lesson for future task
selection:** route to grok the *read-only enumerations / mechanical low-risk*
work (audits that narrow, "list all X", running a named command + summarizing,
drafting a commit message from a diff). Keep grok OUT of: anything that edits a
shared writable tree concurrently (git-stash-wipe + half-edited-compile races —
this repo's `dev-check.sh` stashes the whole tree), DSP/FFI/parity correctness,
golden-cascade changes, and anything where "looks plausible" != "is correct".
CASS: `sbp cass search "jame hardening session grok sidecar"` /
`sbp cass search "GROK-VERDICT jame"`.

### 2026-06-14 — read-only panic-site audit of jame-core (hot/stream path) — GROK-VERDICT:GOOD
- Task: `grok -p` "list .unwrap()/.expect()/index/division that could panic on the
  non-test hot path, file:line + 1-line risk, read-only; skip provably-guarded sites".
- Result: 0 findings, with a *specific* rationale per class — frame-slice indexing is
  behind `while next+frame<=total` + `if relative_end>buffered.len() break` +
  saturating_sub; all 12-element pitch-class indexing via `semitone()` (exhaustive
  0..=11) / `from_semitone` `rem_euclid(12)`; every integer `/`,`%` divisor is a
  non-zero literal or a field validated `>0` at construction; yin_fft `expect("fft
  plan")` always preceded by `prepare(...)`. Named the exact functions it walked
  (stream push/detect/observe, pitch yin/yin_fft, chroma analyze, onset, guitar gate).
- Why GOOD: stayed strictly read-only (git status showed zero grok-caused changes),
  output was structured + falsifiable (cites guards, not vibes), and the conclusion
  matched independent fresh-eyes audits — the only latent panic sites in this repo
  were already beaded (H1 key, M2 tempo) or fixed this session (jame-ncpf
  normalize_peak). A clean negative is a legitimate audit result.
- Caveat: a "0 findings" negative is the hardest to fully trust from any sidecar;
  treat grok read-only audits as a *first pass that narrows*, not a proof of absence.
  Worth a 1-claim spot-check before acting on a negative.
- Routing takeaway: read-only enumerations/audits with a verifiable shape are a
  GOOD grok lane. Keep giving grok these; keep it OUT of the shared writable tree.
- CASS: `sbp cass search "grok panic-site audit jame-core"` /
  `sbp cass search "GROK-VERDICT jame divide-and-conquer"`.
