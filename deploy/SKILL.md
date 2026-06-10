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
6. For browser-facing surfaces, identify the canonical production origin and
   every first-party alias from the overlay before changing code or config.
7. For browser API/auth flows, map every backend the browser calls, not only
   the frontend host:
   - frontend origins: canonical origin plus first-party aliases
   - browser-called API/auth origins
   - exact preflight route, method, and non-simple request headers
   - callback, return, and checkout redirect allowlists that must match those
     origins
8. For login/auth facade releases, prove the public auth endpoints are still
   unauthenticated at the frontdoor and that the browser bundle contains only
   browser-safe credentials.

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

Browser CORS/auth probe:

When users are blocked by a browser login or app API call, prove CORS with a
real browser-shaped `OPTIONS` request before blaming application auth. Health
checks and server-to-server `GET` requests do not prove browser preflight.

```bash
FRONTEND_ORIGIN="https://www.example.com"
API_ORIGIN="https://api.example.com"

curl -i -X OPTIONS "$API_ORIGIN/api/auth/login" \
  -H "Origin: $FRONTEND_ORIGIN" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,authorization,x-api-key"
```

Use the exact route, method, and custom headers from the browser request. Repeat
the probe for every canonical frontend origin, first-party alias, and
browser-called API/auth backend in the overlay. For credentialed requests, the
response must include `access-control-allow-origin` matching the request origin
and `access-control-allow-credentials: true`; the allowed headers must include
each requested non-simple header. A passing preflight followed by `401` or
`403` is not a CORS failure: split stale-token/session refresh from route
authorization and role/scope checks.

Auth facade regression probe:

When the frontend logs in through a same-origin or API-fronted auth facade,
health checks are not enough. Before declaring a browser-facing auth deploy
healthy, run a real unauthenticated login probe against the public production
route and inspect the response shape.

```bash
AUTH_ORIGIN="https://api.example.com"
LOGIN_PATH="/api/auth/login"

curl -sS -i -X POST "${AUTH_ORIGIN}${LOGIN_PATH}" \
  -H "content-type: application/json" \
  --data '{"email":"__probe_invalid__@example.invalid","password":"__probe_invalid__"}' \
  | sed -n '1,80p'
```

Expected result: the request reaches the auth service and returns the auth
service's invalid-credentials response. Block the deploy if the response is a
generic protected-route failure such as `Authorization header missing`,
`Bearer token is required`, a proxy auth challenge, or a route-not-found from
the application API. That means the login path is mounted behind the wrong
middleware or frontdoor route.

Browser bundle secret probe:

For Pages, static, or edge frontends, fetch the production HTML and bundled JS
after deploy. Block the deploy if browser assets contain secret-prefixed API
keys, private tokens, or server-only env values. Prefer project-specific
patterns from the overlay, but always include obvious secret prefixes used by
the auth provider.

```bash
FRONTEND_ORIGIN="https://www.example.com"
html="$(curl -fsS "$FRONTEND_ORIGIN/")"
printf '%s\n' "$html" | rg -o '/assets/[^"]+\.js' | sort -u | while read -r asset; do
  curl -fsS "${FRONTEND_ORIGIN}${asset}" |
    rg -n '(_sec_|secret|private|sk_live|BEGIN [A-Z ]*PRIVATE KEY)' && exit 1
done
```

If this catches a secret in an already-deployed bundle, rotate the exposed
credential before redeploying with a browser-safe publishable/public key.

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
- For browser auth surfaces: unauthenticated login reaches the auth service,
  not protected application middleware, and production bundles contain no
  server-only secret patterns.

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
For `pages_edge` targets, the overlay should be the source of truth for:

- `project` / Pages project name
- `pages_origin` / `*.pages.dev` origin
- `production_domain` / canonical public origin
- `production_aliases` / first-party aliases that must be redirected or allowed
- `canonical_redirect` / expected alias-to-canonical redirect
- `required_github_secrets` / deploy auth contract
- `wrangler_config`
- `smoke` / post-deploy commands

Deploy is not complete unless the canonical origin serves successfully and each
declared alias behaves according to the overlay policy. If an API consumes that
frontend, compare the same alias set against CORS, auth callback, and checkout
redirect allowlists before rollout.

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
- for each browser-called API/auth backend, run an explicit `OPTIONS` preflight
  with the real route, method, origin, and non-simple request headers
- for public login/auth facade routes, run the unauthenticated auth-facade
  regression probe and confirm protected-route middleware is not intercepting
  login, refresh, magic-link, device-flow, or callback routes
- for browser bundles, fetch production assets and scan for server-only secret
  prefixes before and after frontend deploy
- for checkout or billing flows, compare redirect allowlists against the
  canonical origin and first-party aliases in the overlay, then test one
  rejected lookalike host
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
| `401` + `Authorization header missing` on unauthenticated login | auth facade route is behind protected app middleware or wrong frontdoor route | inspect route ordering/proxy config, then rerun the auth-facade regression probe |
| `403` + permission code | role/scope mismatch | inspect auth config and subject role |
| Cloudflare `10000` / `9109` | stale or invalid CI token | compare `npx wrangler whoami` locally vs workflow secret source, then rotate/sync the GitHub secret before the next push |
| `400` + `Disallowed CORS origin` on `OPTIONS` | browser origin allowlist drift | diff deployed env/secret allowlist against all public hostnames and aliases, then rerun preflight |
| `OPTIONS` passes but browser `401` persists | stale token/session/header issue | clear or refresh the session, compare auth headers/cookies, then retry the authenticated route |
| `OPTIONS` passes but authenticated route returns `403` | application authorization or role/scope mismatch | inspect route guards and the subject's app/company/project access |
| `OPTIONS` omits a requested custom header | header allowlist drift | add the exact browser-sent header to the deployed CORS config and rerun preflight |
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

## Related

- [[skill-issue]]
