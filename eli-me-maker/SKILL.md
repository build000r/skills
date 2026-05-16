---
name: eli-me-maker
description: >-
  Create or update a private eli-me skill that captures a user's preferred
  explanation style. Use when the user says "eli-me-maker", asks to make an
  "eli-me" skill, wants a reusable personalized communication-preference skill,
  or wants examples-based questions that discover how they like concepts
  defined, explained, scoped, and checked.
depends_on:
  - ask-cascade
  - mmdx
  - skill-issue
---

# Eli Me Maker

Create a private `eli-me` skill for one person. This public skill owns the
repeatable maker workflow; `ask-cascade` owns dependency-aware calibration
questions; `mmdx` owns optional preference maps; the generated `eli-me` skill
owns the private preference content.

## First Progress Marker

Start with the exact prefix:

`Using eli-me-maker`

Preferred format:

`Using eli-me-maker to build a private explanation-preference skill. I will separate the public maker workflow from the private eli-me output, use ask-cascade for calibration, and use MMDX only when a map clarifies the preference.`

## Ownership Boundary

- `eli-me-maker` belongs in a public skills catalog.
- `eli-me` belongs in a private skills root or private client overlay.
- Do not put a real person's preference card, examples, repo map, names, or
  private writing samples in the public `eli-me-maker` skill.
- Do not claim the generated skill is saved until the files are actually
  written and validated.
- Ask before writing to memory, global instructions, or a long-lived agent
  profile. Writing a private `SKILL.md` in the requested private root is the
  normal output of this workflow.

## Inputs

Before asking the user, infer what you can from the prompt and environment:

- Target skill name: default `eli-me`.
- Target root: a private skills directory, private overlay, or user-named path.
- Starting examples: any explanation-style examples the user provided.
- Existing skill: whether a private `eli-me/SKILL.md` already exists.

If the target root is unclear, ask one placement question before collecting
style preferences. Placement changes where every generated file goes.

## Workflow

### 1. Confirm Placement

Use this branch only when placement is not already clear.

```text
Root decision: where should the private eli-me skill live?

1. Private skills root (recommended)
   Why: the skill is reusable across projects but contains personal preference.
   Happy path:
   - create or update eli-me/SKILL.md privately
   - keep public eli-me-maker generic
   - validate the private skill
   - optionally activate/link it for the current workspace
2. Repo-local private overlay
3. Print a draft only; do not write files

Reply with 1, 2, 3, or give the target path.
```

### 2. Gather Examples With Ask-Cascade

Do not dump a survey. Run the ladder in
[Calibration Prompts](references/calibration-prompts.md).

Rules:

- Ask the highest-impact explanation fork first.
- Use concrete A/B/C examples, not abstract adjectives like "friendly" or
  "detailed" by themselves.
- Accept terse answers such as `1`, `2B`, `more like the failure-first one`, or
  `none`.
- Stop after enough signal to write a useful first version. The private
  `eli-me` skill can improve from future corrections.

### 3. Map The Preference With MMDX When Useful

Use MMDX when the user's preference has several interacting axes, such as
starting shape, evidence type, compression, and checkpoint cadence. Do not make
a diagram when a short preference card is clearer.

Public reference:

```bash
python3 mmdx/scripts/mmd.py eli-me-maker/references/eli-me-maker-flow.mmdx --preflight-only
```

Private generated maps:

- Save maps beside the private `eli-me` skill or in a private overlay, not in
  this public skill.
- Keep the public MMDX stack generic. Do not add real preference answers,
  personal examples, or private repo references to it.
- Link only high-leverage nodes, such as `Ask-cascade calibration` or
  `MMDX preference map`, so drilldowns answer "why this step exists" rather than
  restating every branch.

### 4. Synthesize The Preference Contract

Turn the answers into a compact, operational card:

```markdown
## Eli-Me Preference Card

Default explanation shape:
- Start with:
- Then show:
- Then prove:
- Then ask:

Definition preference:
- Preferred:
- Avoid:

Examples:
- Use:
- Avoid:

Question cadence:
- Ask before explaining when:
- Explain first when:

Compression:
- Default:
- Expand when:
```

Keep it behavioral. Avoid vague traits such as "clear", "smart", "human", or
"good" unless each one is tied to an observable output rule.

### 5. Generate Or Patch The Private Skill

Use [eli-me-template.md](references/eli-me-template.md) as the starting point.

For a new skill:

1. Create `{private_skills_root}/eli-me/SKILL.md`.
2. Fill the preference-card placeholders from calibration.
3. Add only generic process guidance plus the user's private preference card.
4. Avoid scripts unless the user explicitly needs deterministic transforms.

For an existing skill:

1. Read the current private `eli-me/SKILL.md`.
2. Preserve existing validated preferences unless the user corrected them.
3. Patch the smallest section that needs updating.
4. Add a dated note only when it helps explain a preference change.

### 6. Validate And Activate

Run the skill validator from the public skills checkout when available:

```bash
python3 skill-issue/scripts/quick_validate.py {private_skills_root}/eli-me
```

If the user wants the generated skill usable immediately, activate or link it
only at the requested scope. Prefer project/workspace scope for personal
operator skills unless the user explicitly asks for global installation.

## Output Shape

Close with:

- Private skill path written or draft-only status.
- Validation command and result.
- Activation/link status if performed.
- Any unresolved placement or preference question.

Do not include the full private preference card in a public PR description,
public issue, or public README.

## Required Closeout

Before finishing, verify:

- Public `eli-me-maker` stayed generic.
- The generic MMDX stack validates if it changed.
- Private `eli-me` contains the personalized preference content.
- The generated or patched private skill validates, or the validation blocker is
  explicit.
- No public repo file contains private examples or personal preference details.

If this public skill changed, validate it from the public skills repo:

```bash
python3 skill-issue/scripts/quick_validate.py eli-me-maker
```
