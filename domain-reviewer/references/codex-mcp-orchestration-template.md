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
- Mode file: {mode_file}

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

## Optional Helper Script

Use `domain-reviewer/scripts/launch_codex_worker.py` to generate or run these prompts with mode-aware context:

```bash
python3 domain-reviewer/scripts/launch_codex_worker.py \
  --slice agent_billing \
  --worker audit \
  --repo ~/repos/your-project
```

Run with `--execute` to launch Codex immediately.

Use `domain-reviewer/scripts/run_codex_audit_loop.py` for end-to-end orchestration:

```bash
python3 domain-reviewer/scripts/run_codex_audit_loop.py \
  --slice agent_billing \
  --repo ~/repos/your-project \
  --mode your-mode
```

This runs:

1. Initial audit worker
2. Score parse from `AUDIT_REPORT.md`
3. Backend/frontend fix workers from handoff blocks (parallel when both exist)
4. Re-review loop until threshold or max iterations
