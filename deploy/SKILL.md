---
name: deploy
description: Deploy, rollback, debug, and operate multi-service Docker or VPS stacks, plus Pages/edge frontends, using a skillbox client overlay for hosts, repos, domains, and paths. Use when deploying code, checking health, reviewing logs, comparing env rollout plans, validating package publishing, or working in SSH dev environments where production safety rules matter.
---

# Deploy

Operate a live stack without hardcoding one portfolio's topology into the
tracked skill.

Start the first progress update with:

`Using deploy to load the client overlay, run preflight, and execute the smallest safe operational step.`

## Use This For

- Deploys, rollbacks, migrations, and post-deploy verification
- Production debugging, health checks, backups, env drift checks, and restart decisions
- Pages or edge-frontdoor deploys that sit in front of API services
- SSH dev work under `<ssh-dev-root>/*` where deploy context and prod safety rules matter

## Do Not Use This For

- Pure connection lookup with no operational action
- Generic product planning or implementation design
- Local-only debugging when no deploy, infra, or shared runtime concern is involved

## Client Overlay Contract

This skill is public and generic. Real repos, domains, hosts, and paths belong
in the skillbox client overlay at
`skillbox-config/clients/{client}/overlay.yaml`. This is the only supported
contract. Do not add or depend on any legacy private mode directory.

Load the resolved context before deploy/debug work:

```bash
SKILL_DIR="$HOME/.claude/skills/deploy"
[[ -d "$SKILL_DIR" ]] || SKILL_DIR="$HOME/.codex/skills/deploy"
eval "$("$SKILL_DIR/scripts/select_mode.py" "$PWD" --format shell)"
```

`select_mode.py` resolves the matching client overlay, then narrows the deploy
payload to the current repo when the overlay carries a shared `deploy.services`
or `deploy.packages` portfolio. The emitted `MODE_*` vars should describe the
repo under the current cwd, not the entire portfolio.

If no client overlay matches, the selector exits non-zero and prints a legacy
transition message with:

- read-only probe output for inferable values such as `repo_slug`, compose
  services, and CI workflow path
- a valid `overlay.yaml` stub you can paste into `skillbox-config/clients/{id}/overlay.yaml`
- the bootstrap command for `manage_overlays.py create`

If you need to bootstrap a new overlay directly:

```bash
python3 ~/.claude/skills/skill-issue/scripts/manage_overlays.py create --client-id {CLIENT_ID} --cwd "$PWD" --json
```

The error starts with:

```text
Legacy transition: no skillbox-config overlay matches <cwd>.
```

Then re-resolve deploy context. Do not guess hosts, repo paths, or deploy
roots.

See [references/mode-template.md](references/mode-template.md) for the overlay
key reference.

## Required Preflight

Run this checklist before any irreversible step:

1. Load overlay values and confirm the target environment.
2. Identify the deploy surface:
   - Docker/Compose service
   - package publish
   - Pages/edge frontend
   - SSH dev environment
3. Compare the code change to the rollout shape:
   - one-phase deploy
   - two-phase deploy because env/schema/auth changes must land first
4. Check current health and version before changing anything.
5. Confirm the verification path you will use after the change.

For auth, env, or schema changes, explicitly answer:

- Which secret or env source is authoritative?
- Does GitHub Actions or another CI system need updated secrets?
- Does rollout require two phases so old and new code can coexist briefly?

### Required CI Secret Parity Check

When deploy auth depends on CI secrets, do not treat "local auth works" as
enough. Before any irreversible step such as `git push`, run a concrete parity
probe against the same auth surface CI will use.

For Cloudflare Workers / Pages deploys, the minimum contract is:

1. Identify the exact GitHub secret names from the workflow file.
   Example: `.github/workflows/deploy-cloudflare.yml` may export
   `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`.
2. Verify the authoritative local credential separately.
   Example:
   ```bash
   npx wrangler whoami
   ```
3. Verify the workflow actually references the same secrets you think it does.
   Example:
   ```bash
   sed -n '1,220p' .github/workflows/deploy-cloudflare.yml
   ```
4. State the parity result before `git push`:
   - `parity confirmed`: the CI secret source was freshly checked and matches
     the intended rollout target
   - `parity unknown`: local auth works, but CI secret freshness/ownership is
     not verified
   - `parity failed`: CI auth is known stale, missing, or invalid

If parity is `unknown` or `failed`, stop and treat the rollout as blocked until
the CI secret is rotated, synced, or deliberately bypassed by an approved
manual deploy path.

## Permission Model

Use these defaults unless the user explicitly changes them:

| Category | Permission | Examples |
| --- | --- | --- |
| Local/dev edits | Free | edit app code, dev containers, dev DB |
| Prod read ops | Ask once per session | `SELECT`, `docker exec ... alembic current`, read-only config inspection |
| Prod write ops | Ask once per session | `UPDATE`, `INSERT`, `DELETE`, env sync, running migrations |
| Prod restarts | Ask once per session | `docker compose restart api` |
| Git push | Ask every time | any push to any branch |
| Destructive schema ops | Ask per query | `DROP`, `TRUNCATE`, `ALTER ... DROP` |

## Default Flow

### 1. Load overlay

Resolve the client overlay first. Use overlay vars instead of hardcoded literals everywhere.

Typical vars:

- repo roots and repo slugs
- SSH host/user
- deploy root paths
- health URLs
- compose project names
- Pages/edge project names
- reverse-proxy or frontdoor paths

### 2. Run the smallest credible diagnostic

Pick the least invasive command that answers the user's question:

- health endpoint checks
- `docker ps` / `docker compose ps`
- targeted logs
- CI run status
- package version inspection
- auth identity checks such as `npx wrangler whoami`

Do not jump straight to restarts or rollbacks when logs or health output would
answer the question first.

### 3. Execute the workflow branch

Use the branch that matches the task:

- Docker/Compose deploy
- Pages/edge deploy
- rollback
- env sync or auth drift
- backup/restore
- package publish

### 4. Verify behavior and state

Every deploy/debug run must end with:

- one behavior check
- one state check

Examples:

- Behavior: `curl "$MODE_HEALTH_URL"` returns `200`
- State: running container/image tag/commit hash matches expected version

## Required Closeout Verification Contract

Before handing the run back, rerun both checks after the final deploy/debug
change:

- Behavior check: `curl -fsS "$MODE_HEALTH_URL"` returns `200` (or the
  branch-specific smoke endpoint when health lives elsewhere).
- State check: running container/image tag/commit hash in the target runtime
  matches the expected rollout target.

Do not hand the run back until both rerun checks pass.

## Docker / Compose Deploy

Generic pattern:

```bash
git -C "$MODE_REPO_ROOT" status --short
git -C "$MODE_REPO_ROOT" rev-parse --short HEAD
git -C "$MODE_REPO_ROOT" push origin main
gh run watch -R "$MODE_REPO_SLUG"
curl -fsS "$MODE_HEALTH_URL"
```

If deploy happens over SSH:

```bash
ssh "$MODE_DROPLET_SSH" "cd '$MODE_DEPLOY_ROOT' && docker compose ps"
ssh "$MODE_DROPLET_SSH" "cd '$MODE_DEPLOY_ROOT' && docker compose logs --tail=100 $MODE_COMPOSE_SERVICE"
```

## Pages / Edge Frontends

Use this branch when the user is working on a frontend served by Pages, edge
runtime, or a worker frontdoor.

Typical checks:

- current public bundle hash
- current Pages deployment status
- current edge route or origin config
- post-deploy health or smoke check
- current auth identity for the deploy actor and the CI secret source

Before `git push` or `wrangler deploy`, answer these explicitly for Workers /
Pages deploys:

- Which workflow file owns production deploys?
- Which exact secret names does it read?
- Did you verify local auth with `npx wrangler whoami` (or provider equivalent)?
- Is CI secret parity `confirmed`, `unknown`, or `failed`?

If CI deploy auth later fails but local provider auth succeeds, the run is not
complete. Report the exact failure signature, mark the deploy as blocked on CI
secret drift, and only use a manual local deploy path if the user wants that as
the smallest safe operational step.

Use overlay values for project name, public origin, and worker config path.

## Rollback

Rollback requires a concrete target plus a verification path.

Before rolling back:

1. identify the last known good release or image
2. capture current logs and health state
3. note whether migrations were already applied
4. state whether rollback is code-only or code-plus-config

After rollback:

- re-run health
- confirm the runtime reports the expected version
- note any follow-up remediation still required

## Auth / Env Drift

Treat auth and env drift as first-class deploy issues.

Checklist:

- compare local env source vs deployed env file / CI secrets
- note any new headers, scopes, or callback URLs
- explicitly compare browser origin allowlists against every public hostname and
  alias in the overlay (`example.com`, `www.example.com`, Pages/Vercel aliases)
- decide whether old and new values must overlap temporarily
- verify both behavior and state after sync

See [references/troubleshooting.md](references/troubleshooting.md) for concrete
failure signatures.

## Backups And Migrations

Before a risky migration or restore:

1. capture or verify a fresh backup
2. identify the DB/service/container to touch
3. confirm restore command path before running the change
4. run a minimal post-change query or health check

Prefer overlay variables for DB names, deploy roots, and backup locations.

## SSH Dev Environments

When cwd is `<ssh-dev-root>/*`, switch into the SSH-dev guidance in
[references/ssh-dev-guide.md](references/ssh-dev-guide.md).

Key rule: treat `<ssh-dev-root>/*` as editable dev space and deployed roots such as
`/opt/...` as managed production artifacts unless the user explicitly asks for a
prod operation.

## Failure Signatures

Use the exact failure signature instead of generic “unauthorized” summaries:

| Signature | Likely Cause | Next Check |
| --- | --- | --- |
| `401` + auth error code | missing or stale credential/header | compare env source and deployed secret |
| `403` + permission code | role/scope mismatch | inspect auth config and subject role |
| Cloudflare `10000` / `9109` | stale or invalid CI token | compare `npx wrangler whoami` locally vs workflow secret source, then rotate/sync the GitHub secret before the next push |
| `400` + `Disallowed CORS origin` on `OPTIONS` | browser origin allowlist drift | diff deployed env/secret allowlist against all public hostnames and aliases, then rerun preflight |
| `404` on health URL | wrong route/origin/frontdoor | check overlay host/path values |
| `502` / `503` at proxy | upstream container down or wrong upstream port | check compose status and container-local health |
| migration command fails | schema drift or wrong DB target | verify DB name, container, and current revision |

## References

- [references/mode-template.md](references/mode-template.md)
- [references/architecture.md](references/architecture.md)
- [references/troubleshooting.md](references/troubleshooting.md)
- [references/ssh-dev-guide.md](references/ssh-dev-guide.md)

## Rules

- Never hardcode real hosts, domains, repo names, or server paths in tracked files.
- Use overlay values for deployment-specific details.
- Prefer the smallest safe operational step before escalations.
- Always call out one-phase vs two-phase rollout when env, auth, or schema changes are involved.
- Always end with one behavior check and one state check.
