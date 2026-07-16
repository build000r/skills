# Vision Source Ladder

Scope verdicts are only as good as the vision they score against. Work down
this ladder; stop at the first source that yields a confirmed, current vision.

## 1. Explicit vision artifacts (authoritative)

- `VISION.md`, `MISSION.md`
- "Vision", "Philosophy", "Goals", "Non-goals", "What this is / is not"
  sections in `README.md`, `CLAUDE.md`, `AGENTS.md`, `docs/`

Check staleness: if the artifact predates major pivots visible in git history
or contradicts what the product now sells, treat it as source material for
vision-recovery instead of authority.

## 2. Client overlay context (authoritative when present)

Operator environments may carry per-repo scope declarations in a client
overlay (e.g. a `repo_landscape` block with `owns`, `does_not_own`, and
`prefer_for` lists). `does_not_own` entries are pre-ratified non-goals —
import them directly into the working vision.

## 3. What the product sells (strong evidence)

Landing page copy, App Store / marketplace description, pricing page, demo
script. A feature the product charges for or leads its marketing with is
core by revealed preference; a feature never mentioned anywhere user-facing
is breadth until proven otherwise.

## 4. The issue graph (moderate evidence)

Epic-level issues/beads and their stated goals show where the operator is
*trying* to go. Weight recent epics over old ones. Count how many epics each
feature area appears in — persistent presence suggests core; a single
orphaned epic suggests an experiment.

## 5. Git archaeology (weak but always available)

- The first ~20 commits usually build the core loop — what a project was
  *for* before it had time to sprawl.
- `git log --oneline | tail -30` (origins) vs `--since="3 months ago"`
  (recent drift): compare the two vocabularies.
- Files with the most total churn over the project's life are usually the
  core; long-untouched leaf directories added late are usually breadth.

## Vision-Recovery Mode

When sources 1–2 are missing or stale:

1. Draft a candidate vision from sources 3–5 using
   `assets/templates/VISION.md`. Keep it under ~15 lines.
2. Mark every inference with its source ("pricing page leads with X",
   "first commits built Y").
3. Present it to the operator and get explicit confirmation or edits
   **before scoring**. If the operator is unavailable and the run must
   proceed, score anyway but mark every verdict `PROVISIONAL` and do not
   propose any writes.
4. On confirmation, offer to commit `VISION.md` to the repo so the next run
   (and the next feature-adding agent) starts from authority instead of
   archaeology.

## What a Usable Vision Names

- **The one user** — a person/role, not "everyone"
- **The one job** — the outcome that user hires the project for
- **The core loop** — the repeated action sequence that delivers the job
- **Non-goals (3+)** — adjacent things this project deliberately does not do

If any of the four is missing, the vision cannot discriminate between CORE
and breadth, and verdicts will drift toward "keep everything". Push for all
four before scoring.
