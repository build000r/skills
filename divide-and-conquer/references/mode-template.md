# Mode Template

Copy this file to `modes/{project-name}.md` and fill in each section. Delete
any sections that do not apply.

---

# {Project Name} Mode

## Detection

```text
cwd_match: ~/repos/{project-name}
```

## Swarm Preferences

- **Preferred worker mix**: read-only heavy | balanced | write-heavy
- **Max workers per wave**: 3-5 (adjust based on project complexity)
- **Default model strategy**: use `gpt-5.5` for Codex panes; default to `high`, reserve `medium` for clearly bounded read-only work, use `xhigh` for review or ambiguity, and round up when unsure
- **Wave naming**: `dac-{project}-wave-{nn}`
- **Review wave**: 1 worker | 2 workers
- **Artifact root override**: `workflow_builder.invocation_root` | `client_dir/invocations` | leave unset to use the shared default resolution

## Repo Structure

Key directories and their purposes:

- **Source**: `src/` - main application code
- **Tests**: `tests/` or `src/__tests__/` - test files
- **Config**: project root - config files
- **Build command**: `npm run build` | `cargo build` | etc.
- **Test command**: `npm test` | `pytest` | `cargo test` | etc.
- **Lint command**: `npm run lint` | `ruff check` | etc.

## Split Boundaries

Project-specific seams where work naturally divides. List the major concern
boundaries:

- **Frontend**: `src/app/` or `src/components/`
- **Backend**: `src/api/` or `server/`
- **Database**: `src/db/` or `prisma/`
- **Shared types**: `src/types/`
- **Infrastructure**: `deploy/` or `.github/`
- **Tests**: `tests/`

Add or remove boundaries to match your project layout.

## Naming Conventions

How workgraph nodes and wave labels should be named for this project:

- **Node pattern**: `WG-00N: {Boundary} - {Goal}`
- **Wave pattern**: `dac-{project}-wave-{nn}`
- **Prefix**: Use the boundary name from Split Boundaries above

## Validation

Command to run after all waves complete and the final review worker is ready:

```bash
cd ~/repos/{project-name} && npm run build && npm test
```
