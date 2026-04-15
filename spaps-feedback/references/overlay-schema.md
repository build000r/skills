# `spaps_feedback` overlay schema

This is the per-client config block that `spaps-feedback` reads from `skillbox-config/clients/{client}/overlay.yaml`. Drop it under `client.context` (or wherever the client overlay nests skill-specific config — match the surrounding pattern).

## Full shape

```yaml
spaps_feedback:
  db:
    droplet_ssh: ops@example-host          # optional; falls back to deploy.droplet_ssh
    ssh_key: tailscale                     # optional; falls back to deploy.ssh_key
    container: spaps-db                    # required: postgres docker container name
    user: spaps                            # required: psql user
    database: spaps                        # required: psql database name
    table: issue_reports                   # optional, default "issue_reports"
    application_filter: null               # optional UUID; restrict to one SPAPS application row

  defaults:
    since: 7d                              # default time window for "list recent"
    limit: 25

  skill_registry:
    - id: client/portfolio-skill
      path: ~/repos/client/.agents/skills/portfolio-skill
      tags: [service-a, service-b, renewal, audit]
      match_fields: [note, component_label, page_url]
      applications: []                     # optional whitelist of application_id UUIDs
      pages: []                            # optional whitelist of page_url prefixes
```

## Field reference

### `db`

Read-only postgres connection. The fetch script wraps `docker exec <container> psql -U <user> -d <database>` inside `ssh <droplet_ssh>`. If `droplet_ssh` is omitted here, the skill uses `client.context.deploy.droplet_ssh` from the same overlay (the same key `ssh-info` and `deploy` already use).

`table` exists so a client can repoint at a renamed or sharded table without forking the script.

`application_filter` is a hard-scope at the SQL layer — useful when one client owns one SPAPS application row and should never see another tenant's reports.

### `defaults`

Optional. Operator-friendly defaults so common requests do not need flags. CLI flags always override.

### `skill_registry`

The matching table. Each entry describes one sibling skill the operator might want to hand an issue off to.

- `id`: human-readable identifier, used in matcher output. Convention: `<repo>/<skill-name>`.
- `path`: absolute or `~`-rooted directory of the sibling skill. Used to verify it still exists before recommending it.
- `tags`: lowercase keywords. The matcher counts how many appear (case-insensitive, word-boundary) in the issue's `match_fields` text.
- `match_fields`: which `issue_reports` columns to search. Default `[note, component_label, page_url]`. Available columns: `note`, `component_key`, `component_label`, `page_url`, `surface_ref`, `source_app`, `source_record_id`, plus any string keys inside `target_metadata`.
- `applications`: optional UUID whitelist. Empty list = match for any app.
- `pages`: optional list of `page_url` prefixes. Empty list = match for any page.

## Inheritance

Per the skillbox client overlay convention, a client overlay can pull common defaults from `_shared/spaps_feedback.yaml` if one exists. The skill itself does not enforce inheritance — it reads only the resolved overlay. Use the standard `_shared` merge step in your overlay loader if you want global defaults across all clients.

## Privacy note

Tags and skill paths in the registry are operator-side metadata, not user-visible. Do not put customer names or PII in tags. Issue text itself may contain user PII — the fetch script keeps it on the operator machine and never uploads it anywhere.
