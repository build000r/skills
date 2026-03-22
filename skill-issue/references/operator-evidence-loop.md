# Operator Evidence Loop

Use this reference when a skill has enough real transcript history to justify more than intuition, but not enough stability or scale to justify a full eval suite.

The goal is to create a durable middle layer between:

- **Vibe updating**: edit the skill from the last memorable run
- **Full eval suites**: versioned datasets, automated graders, CI gates

This middle layer is built from **operator evidence packets** and judged by future real
invocations, not synthetic reruns by default.

## When To Use It

Use operator evidence packets when:

- transcript review already shows recurring corrections, checkpoints, or verification gaps
- maintainers can read representative runs but do not yet have a stable benchmark harness
- the task surface is still moving enough that a heavy suite would freeze the wrong assumptions

Do not skip straight from aggregate rates to patching `SKILL.md`. Build or read one evidence packet first.

## Packet Structure

Each packet should capture one failure family:

1. **Failure family**
   Example: `contract-clarity`, `verification-gap`, `checkpoint-defaults`, `risk-gating-gap`
2. **Why this cluster matters**
   One short statement tying the packet to user pain or workflow drift
3. **Expected contract**
   What the skill should have done instead
4. **Representative traces**
   Two to five real examples with timestamps, user request, and the signal that triggered the packet
5. **Historical reference slice**
   A small set of target examples plus a few holdout examples from past real runs that should not regress
6. **Suggested fix class**
   Example: tighten trigger language, add verification block, move preferences into defaults
7. **Target files**
   Usually `SKILL.md`, `references/`, `scripts/`, or `modes/`
8. **Watch metric**
   The rate or signal that should improve after the patch
9. **Post-ship observation window**
   The next live window to watch, for example the next 10 invocations or next 14 days
10. **Graduate condition**
   What would justify converting this packet into a fuller eval or automated check

## Default Failure Families

These map cleanly onto `skill-issue`'s current review metrics:

| Failure family | Typical trigger | Expected contract | Watch metric |
|---|---|---|---|
| `observability-gap` | skill path touched without explicit ack | emit a stable `Using <skill>` acknowledgement early | `ack_rate` |
| `verification-gap` | no validation command detected | run a concrete verification path before handoff | `validation_rate` |
| `checkpoint-defaults` | repeated checkpoint prompts | default common choices; ask only when missing or risky | `checkpoint_rate` |
| `risk-gating-gap` | user says wait/ask first/bring in review before proceeding | pause for confirmation, clarification, or named outside review before risky actions | `risk_gating_rate` |
| `contract-clarity` | user redirects after activation | branch correctly earlier using tighter triggers and non-goals | `correction_rate` |
| `closeout-gap` | no completion event detected | end with explicit verification evidence and clear completion | `completion_rate` |
| `automation-gap` | repeated raw shell stems | bundle recurring shell work into scripts or concise references | raw shell stem frequency |

## Operating Sequence

1. Run `scripts/review_skill_usage.py` to get the current transcript-derived report.
2. Run `scripts/generate_skill_evidence_packets.py` to turn repeated failures into packets.
3. Pick **one packet** to work on first.
4. Patch the skill against that packet's expected contract and historical reference slice.
5. Validate the changed skill.
6. Ship once, log the packet decision, and watch the next real invocation window.
7. Re-run transcript review after enough new live traces arrive and compare the packet's watch metric.

This sequence prevents the two common mistakes:

- patching from memory
- patching for one bad run and silently regressing adjacent cases
- overfitting to synthetic reruns that are easier than real traffic

## Packet Triage Rules

- Prefer packets with clear user-visible pain over abstract cleanliness.
- Prefer packets with repeated real traces over one spectacular anecdote.
- Prefer one high-prevalence packet at a time over editing five weakly supported areas.
- If two packets implicate the same underlying contract, merge them before patching.

## Graduation Rules

Stay in operator-evidence mode when:

- the failure taxonomy still changes week to week
- the historical reference slice is small and mostly curated by hand
- one or two maintainers still hold most of the operational context

Graduate toward a fuller eval suite when:

- the same packet recurs often enough to justify automation
- the expected contract has stabilized
- regressions are costly enough to justify CI or scheduled replay
- multiple maintainers need the same executable proof of behavior
