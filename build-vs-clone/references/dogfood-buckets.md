# Dogfood Buckets

Use this reference during placement, extraction, audit, and prospect work. The
goal is to prevent `BUILD`, `NEW REPO`, or consumer-local implementation
recommendations when the operator already has a stronger internal bucket for
the capability.

## Bucket Pass

1. Resolve client context from `skillbox-config` and read the active overlay's
   repo landscape.
2. Build a bucket map with the current repo, every overlay-declared repo, and
   the stable dogfood buckets below.
3. For each requested capability, choose the owner bucket before recommending
   write paths or external dependencies.
4. If the current repo is only a consumer, recommend a cross-repo slice: owner
   bucket first, consumer integration second.
5. If no existing bucket covers the capability, state `BUILD` or run the normal
   external search path before inventing a local subsystem.

External dependencies can help only after the owner bucket is selected. The
dependency should sit behind that bucket's package, API, overlay, skill, or
service contract instead of being wired directly into a consumer repo as a
one-off bypass.

## Stable Buckets

| Bucket | Owns | Route through when |
| --- | --- | --- |
| `skillbox` | Runtime manager, focus/context generation, MCP/runtime wiring, local devbox behavior, skill distribution mechanics | The task changes how agents discover clients, focus overlays, run local runtime checks, or provision managed agent environments |
| `skillbox-config` | Client overlays, generated contexts, plans, workflows, evaluations, invocation artifacts, repo landscapes, per-client validation commands | The task needs client-specific routing, missing repo metadata, invocation storage, plan roots, or reusable per-client defaults |
| `skills` | Reusable agent workflows, `SKILL.md` contracts, bundled scripts, references, tests, and packaging rules | The task changes what agents should know or do across future sessions |
| `swimmers` | Rust binary crate, local server/TUI interaction surface, multi-agent/session visibility patterns, publishable CLI ergonomics | The task concerns terminal/TUI swarm surfaces, local coordination UX, or reusable Rust server/client patterns |
| `sweet-potato` | SPAPS shared control plane: auth, sessions, API keys, application identity, billing, payments, entitlements, wallet identity, published clients, issue reporting | Any product needs identity, grants, billing, protected sessions, entitlement projection, wallet flow, or issue-reporting integration |

## Sweet Potato Package Buckets

Treat each SPAPS package as a concrete route, not a vague "use Sweet Potato"
instruction:

| Path | Package | Use for |
| --- | --- | --- |
| `packages/python-server-quickstart/` | `spaps-server-quickstart` | FastAPI/Celery backend scaffolding, middleware, app factory, server-side SPAPS patterns |
| `packages/python-client/` | `spaps` | Python client calls into SPAPS APIs |
| `packages/sdk/` | `spaps-sdk` | TypeScript SDK usage from frontends or server-side Node consumers |
| `packages/spaps/` | `spaps` CLI | Local SPAPS workflows, device/connect flows, middleware helpers, Docker Compose orchestration |
| `packages/types/` | `spaps-types` | Shared TypeScript types and runtime guards |
| `packages/issue-reporting-react/` | `spaps-issue-reporting-react` | Shared React issue-reporting surfaces |
| `packages/wallet-utils/` | `spaps-wallet-utils` | Browser wallet connection and signing utilities |

## Recommendation Shape

When bucket routing applies, make it explicit in the build-vs-clone answer:

```text
Verdict: CROSS-REPO SLICE
Owner bucket: sweet-potato/packages/sdk + sweet-potato/packages/types
Consumer repo: product-app
Why: SPAPS owns identity and entitlement projection; product-app owns domain rows.
Sequence:
1. Add or expose the reusable SPAPS contract in the owner bucket.
2. Consume it from product-app without local auth/session/entitlement tables.
External deps: allowed only behind the SPAPS package/API boundary.
```

If the needed API/package does not exist yet, recommend an owner-bucket gap
first:

```text
1. sweet-potato: add missing grant helper or SDK/type surface.
2. consumer-app: integrate against that helper.
```

Do not collapse those into one consumer-local recommendation. That is how
reusable platform work turns into one-off application glue.

## PDSMVP Lesson

For PDSMVP-style product work, separate domain data from platform identity:

- The product repo owns public-works/compliance domain rows, opaque SPAPS refs,
  URLs, audit records, workflow state, and product-specific permissions layered
  on top of SPAPS context.
- Sweet Potato/SPAPS owns passwords, sessions, JWTs, API keys, application
  identity, billing, wallet identity, generic entitlements, and reusable grant
  projection.
- `skillbox-config` owns the client overlay that tells agents where the web,
  server, validation commands, plans, and invocation artifacts live.

If an agent starts debating local database tables for users, sessions, API
keys, generic roles, billing, or entitlement projection in a product repo, the
placement recommendation should route through SPAPS or propose a Sweet Potato
owner-bucket gap. Local domain tables are still appropriate for product-specific
state and opaque refs.
