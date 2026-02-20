# Permissions Playbook

Use this when adding a new skill + endpoint combo so reads stay autonomous and writes stay approval-gated.

## 1) Choose the execution mode first

1. `Strict review mode`:
`tools.exec.ask: "always"` for every command.
2. `Autonomous read mode`:
`tools.exec.security: "allowlist"` + `tools.exec.ask: "on-miss"` so approved reads run, everything else requests approval.
3. `Lockdown mode`:
`tools.exec.security: "deny"` during incidents.

Default template posture is strict. Move to autonomous read mode only after wrapper + allowlist are tested.

## 2) Wrap external access in a policy command

Do not let skills call raw `curl`/`node` directly for external systems.
Create one wrapper per integration under `${OPENCLAW_HOME}/bin`.

Example wrapper (`ccurl`) pattern:

1. Allow only `https://` targets.
2. Restrict hostnames to an allowlist (`*.your-api.example.com`, etc.).
3. Block dangerous options (`--config`, `--proxy`, `--resolve`, `--connect-to`).
4. Delegate to system `curl` only after checks pass.

## 3) Map permissions in config

Example for autonomous reads:

```json
{
  "tools": {
    "exec": {
      "host": "gateway",
      "security": "allowlist",
      "ask": "on-miss",
      "safeBins": ["jq", "grep", "head", "tail", "wc", "echo", "printf", "ccurl"],
      "pathPrepend": ["/home/openclaw/.openclaw/bin"]
    }
  }
}
```

Approval target must be concrete:

```json
{
  "approvals": {
    "exec": {
      "mode": "targets",
      "targets": [
        { "channel": "telegram", "to": "OPERATOR_TELEGRAM_ID" }
      ]
    }
  }
}
```

Do not use `${env:...}` inside `approvals.exec.targets[*].to`; this may not interpolate on some runtimes.

## 4) Seed the allowlist

Every command segment in a pipeline must be allowlisted or covered by `safeBins`.

```bash
openclaw approvals allowlist add --agent "*" "/home/openclaw/.openclaw/bin/ccurl"
openclaw approvals allowlist add --agent "*" "/usr/bin/jq"
```

If the skill uses `ccurl ... | jq ...`, both `ccurl` and `jq` must be permitted.

## 5) Skill authoring contract

Inside `SKILL.md` examples:

1. Use wrapper commands (`ccurl`, `qbget`, `crmget`), not raw `curl`.
2. Use env vars for credentials (`${INTEGRATION_API_KEY}`), never hardcoded keys.
3. Include an endpoint matrix:
read endpoints, draft/create endpoints, blocked endpoints.
4. Make write behavior explicit:
proposal-only vs direct draft-safe writes.

## 6) Future endpoint/skill examples

### Example A: Data catalog skill (current pattern)

Allowed read:

```bash
ccurl -s -H "X-API-Key: ${BACKEND_AGENT_API_KEY}" \
  "https://api.your-service.example.com/v1/catalog/stats" | jq .
```

Why it works:
- `ccurl` wrapper restricts host + protocol.
- `jq` is explicitly allowlisted.
- Non-allowlisted commands go to approval (not silent deny) with `ask: "on-miss"`.

### Example B: Future accounting skill (new endpoint family)

Create wrapper `qbget` for read-only accounting APIs:

```bash
qbget "/v3/company/${QB_COMPANY_ID}/query?query=select * from Customer"
```

Pattern:
1. `qbget` enforces host `quickbooks.api.intuit.com` only.
2. `qbget` enforces method `GET` only.
3. Any mutation (`POST/PATCH`) is blocked in wrapper and must become a proposal card for portal approval.

If you later add a write-proposal helper, keep it non-mutating:
it should create a proposal object, not call vendor mutation endpoints directly.

## 7) Validation sequence

1. `bash scripts/validate_client_kit.sh /tmp/<client>-openclaw`
2. `bash scripts/review_kit.sh /tmp/<client>-openclaw`
3. `bash scripts/review_live.sh --host <ip> --service <unit> --home <openclaw-home> --user <app-user>`
4. Smoke tests:
- allowed read command succeeds
- blocked host fails in wrapper
- non-allowlisted command creates approval event
- approval notification is delivered to Telegram target
