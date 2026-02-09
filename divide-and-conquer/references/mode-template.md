# Mode Template

Copy this file to `modes/{project-name}.md` and fill in each section. Delete any sections that don't apply.

---

# {Project Name} Mode

## Detection

```
cwd_match: ~/repos/{project-name}
```

## Agent Preferences

- **Preferred agent types**: Explore + general-purpose | mostly general-purpose | Explore-heavy research
- **Max agents**: 3-5 (adjust based on project complexity)
- **Default model**: sonnet (or haiku for simple tasks, opus for complex reasoning)
- **Background by default**: true | false

## Repo Structure

Key directories and their purposes:

- **Source**: `src/` — main application code
- **Tests**: `tests/` or `src/__tests__/` — test files
- **Config**: project root — config files (tsconfig, package.json, etc.)
- **Build command**: `npm run build` | `cargo build` | etc.
- **Test command**: `npm test` | `pytest` | `cargo test` | etc.
- **Lint command**: `npm run lint` | `ruff check` | etc.

## Split Boundaries

Project-specific seams where work naturally divides. List the major concern boundaries:

- **Frontend**: `src/app/` or `src/components/` — UI components, pages, styling
- **Backend**: `src/api/` or `server/` — API routes, business logic
- **Database**: `src/db/` or `prisma/` — schema, migrations, queries
- **Shared types**: `src/types/` — interfaces, type definitions used across boundaries
- **Infrastructure**: `deploy/` or `.github/` — CI/CD, Docker, deployment configs
- **Tests**: `tests/` — keep test agents separate from implementation agents

Add or remove boundaries to match your project layout.

## Naming Conventions

How agents should be labeled for this project:

- **Pattern**: `Agent [N]: {Boundary} — {Goal}` (e.g., "Agent 1: Frontend — Add user profile page")
- **Prefix**: Use the boundary name from Split Boundaries above
- **Numbering**: Sequential, write-agents first, then explore-agents

## Validation

Command to run after all agents complete and work is merged:

```bash
cd ~/repos/{project-name} && npm run build && npm test
```
