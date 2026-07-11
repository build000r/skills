# Codex MCP Orchestration Template

Use this template when running `domain-reviewer` with Codex MCP + worker agents.

## What This Provides

- One Codex MCP server rooted at the target repository
- Orchestrator + worker model (`audit`, `re-review`, `fix-backend`, `fix-frontend`, `retire`)
- Same-repo concurrency contract (no extra worktrees required)

## Runtime Contract

- Assign explicit path ownership per worker.
- Shared files are orchestrator-owned and edited sequentially.
  - Examples: `package.json`, lockfiles, root configs, `INDEX.md`, session index files.
- Workers must not revert/reset teammate changes.
- If scope crossing is required, worker requests handoff.

## Codex MCP Server Bootstrap (Agents SDK)

```python
import asyncio
from agents.mcp import MCPServerStdio


async def main() -> None:
    async with MCPServerStdio(
        name="Codex CLI",
        params={
            "command": "npx",
            "args": ["-y", "codex", "mcp-server"],
            "cwd": "/path/to/repo",
        },
        client_session_timeout_seconds=360000,
    ) as codex_server:
        print("Codex MCP server started")


if __name__ == "__main__":
    asyncio.run(main())
```

## Worker Prompt Templates

### Audit Worker

```md
Audit the `{slice}` slice implementation against its plan.

Context:
- Plan files: {plan_root}/{slice}/
- Plan index: {plan_index}
- Backend code: {backend_path}
- Frontend code: {frontend_path}
- Backend standards: {backend_standards}
- Frontend standards: {frontend_standards}
- Client config: {context_yaml}

Guardrails:
- Stay in owned scope.
- Do not run destructive git commands (`git reset --hard`, `git checkout --`, mass reverts).
- Do not revert teammate changes.
- Request handoff for scope crossing.

Instructions:
1. Follow `references/audit-workflow.md`.
2. Write/update `{plan_root}/{slice}/AUDIT_REPORT.md`.
3. Keep parseable score line: `### Overall Compliance Score: **XX/100**`.
4. Update `plan_index` status.
5. Include `## Agent Handoffs` section if issues remain.
```

### Re-Review Worker

```md
Re-review the `{slice}` slice after fixes (re-review #{iteration}).

Context:
- Same as audit worker

Instructions:
1. Read plan files + current AUDIT_REPORT.md.
2. Diff against baseline and mark each issue FIXED/PARTIALLY FIXED/NOT ADDRESSED.
3. Append Re-Review section.
4. Recompute score and update `plan_index` if needed.
```

### Backend Fix Worker

```md
Apply backend fixes for `{slice}` from handoff block:

{backend_handoff_block}

Context:
- Backend code: {backend_path}
- Backend standards: {backend_standards}
- Plan files: {plan_root}/{slice}/

Instructions:
1. Write/fix tests first, then implementation.
2. Edit backend-owned scope only.
3. Commit with `fix({slice}): {brief description}`.
```

### Frontend Fix Worker

```md
Apply frontend fixes for `{slice}` from handoff block:

{frontend_handoff_block}

Context:
- Frontend code: {frontend_path}
- Frontend standards: {frontend_standards}
- Plan files: {plan_root}/{slice}/

Instructions:
1. Edit frontend-owned scope only.
2. Follow frontend standards from mode.
3. Commit with `fix({slice}): {brief description}`.
```

## Preferred: `/codex:rescue` (via `codex-plugin-cc`)

When the plugin is loaded, delegate workers directly from Claude Code:

```
# Audit worker
/codex:rescue --model gpt-5.6-sol --effort medium \
  Audit the agent_billing slice implementation against its plan. \
  [paste audit worker prompt from above with paths substituted]

# Fix workers (parallel when scopes are disjoint)
/codex:rescue --background --model gpt-5.6-sol --effort medium \
  Apply backend fixes for agent_billing from handoff block: \
  [paste backend handoff block from AUDIT_REPORT.md]

/codex:rescue --background --model gpt-5.6-sol --effort medium \
  Apply frontend fixes for agent_billing from handoff block: \
  [paste frontend handoff block from AUDIT_REPORT.md]

# Re-review worker
/codex:rescue --model gpt-5.6-sol --effort medium \
  Re-review agent_billing after fixes (re-review #1). \
  [paste re-review worker prompt from above]
```

Check background jobs with `/codex:status`, retrieve with `/codex:result`.

## Fallback: Helper Scripts

The Python scripts remain available for environments without the plugin:

```bash
# Generate or run a single worker prompt
python3 domain-reviewer/scripts/launch_codex_worker.py \
  --slice agent_billing \
  --worker audit \
  --repo ~/repos/your-project

# End-to-end orchestration loop
python3 domain-reviewer/scripts/run_codex_audit_loop.py \
  --slice agent_billing \
  --repo ~/repos/your-project \
  --mode your-mode
```
