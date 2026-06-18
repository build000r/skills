# Mode Template

Copy this file to `modes/{project-name}.md` and fill in each section. Delete any sections that don't apply.

---

# {Project/Team Name} Mode

## Detection

```
cwd_match: ~/repos/{project-name}
```

## Scoring Adjustments

Override default axis weights for this team's context. Increase weight for axes that matter most, decrease for axes that are less relevant given the team's workflow.

- **Clarity**: weight 1.0 (default) | 1.5 (raise for junior teams) | 0.5 (lower for senior teams with shared context)
- **Context & Inputs**: weight 1.0 | adjust based on codebase familiarity
- **Autonomy & Scope**: weight 1.0 | 1.5 (raise for junior devs who need guardrails)
- **Constraint Handling**: weight 1.0
- **Iterative Checkpoints**: weight 1.0 | 0.5 (lower for experienced users who trust the agent)
- **Follow-up Efficiency**: weight 1.0
- **Collaboration Traits**: weight 1.0
- **Adaptability**: weight 1.0
- **Outcome Alignment**: weight 1.0

## Session Sources

Custom paths to session data, if not using the defaults:

- **Claude Code sessions**: `~/.claude/sessions/` (default)
- **Codex sessions**: `~/.codex/sessions/` (default)
- **OpenCode sessions**: `~/.local/state/opencode/` (default)
- **Custom log path**: `/path/to/custom/logs/` (if using a non-standard location)

## Review Cadence

- **Frequency**: weekly | biweekly | monthly | per-sprint
- **Day**: Friday (recommended — review the week's work)
- **Auto-remind**: true | false (if true, suggest review when cadence is due)
- **Backfill on setup**: true | false (backfill past weeks when first configuring)

## Team Context

Context that affects scoring expectations:

- **Team size**: 1 (solo) | 2-5 (small) | 6-15 (medium) | 16+ (large)
- **Experience level**: junior | mixed | senior
- **Typical task complexity**: simple fixes | feature work | architecture | mixed
- **Primary tools**: Claude Code | Codex | AMP | OpenCode | mixed
- **Model usage**: opus | sonnet | haiku | mixed
- **Shared context level**: high (same codebase daily) | low (diverse projects)

## Output Preferences

- **Default format**: quick summary | full scorecard
- **Extra sections**: Include "Prompt MVP" / "Facepalm" superlatives? yes | no
- **Trend display**: always show trend after review | only when asked
- **Export format**: markdown (default) | csv | json
- **History file**: `~/.claude/prompt-review-history.jsonl` (default) | custom path
