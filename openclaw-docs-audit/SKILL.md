---
name: openclaw-docs-audit
description: >-
  Audit openclaw-client-bootstrap config and skill against the latest upstream
  OpenClaw releases. Fetches GitHub releases, diffs config schema, and produces
  a ranked drift report (breaking, recommended, nice-to-have). Use when:
  "audit openclaw", "check openclaw docs", "openclaw drift", "config freshness",
  "what changed in openclaw", "sync with upstream", "/openclaw-docs-audit".
---

# OpenClaw Docs Audit

Continuous compliance checker for the `openclaw-client-bootstrap` skill against
upstream OpenClaw releases and documentation.

## On Trigger

Run the audit script first, then do a deep-dive analysis.

### Step 1: Run the audit script

```bash
AUDIT="$(ls ~/.claude/skills/openclaw-docs-audit/scripts/audit.sh \
            ~/.codex/skills/openclaw-docs-audit/scripts/audit.sh \
            ./scripts/audit.sh 2>/dev/null | head -1)"
bash "$AUDIT" --instances
```

This produces a quick structural report: version drift, removed keys, instance
staleness, and SKILL.md coverage gaps.

### Step 2: Fetch upstream release notes

For each release newer than the pinned version, fetch the full release body:

```bash
gh release view <tag> --repo openclaw/openclaw --json body -q '.body'
```

Scan each release for:
- Config schema changes (new keys, removed keys, type changes, renamed keys)
- Default value changes
- New validation rules (`openclaw doctor` changes)
- Security fixes that affect config (SSRF, auth, sandbox, exec)
- Channel behavior changes (dmPolicy, groupPolicy, allowFrom enforcement)

### Step 3: Fetch upstream config reference

```bash
# WebFetch the config reference for the latest schema
```

Use WebFetch on `https://docs.openclaw.ai/gateway/configuration-reference` to
get the authoritative config schema. Compare against the snapshot in
`references/config-schema-snapshot.md`.

### Step 4: Diff and classify changes

Cross-reference upstream changes against THREE targets:

1. **Template config** (`assets/client-kit/openclaw.json`)
2. **Deployed instance configs** (`assets/instances/*/openclaw.json`)
3. **SKILL.md schema notes** (the "Config Schema Notes" section)

Classify each finding:

#### Breaking (must fix before next deploy)
- Removed config keys still present in template/instances
- Type changes that would crash gateway startup
- Security fixes that change default behavior (e.g., dmPolicy enforcement)
- Validation rules that now reject previously-valid configs

#### Recommended (should fix in next maintenance window)
- New config keys that improve security posture
- Default value changes that alter behavior
- Deprecated keys that still work but will be removed
- Schema notes in SKILL.md that don't cover recent versions

#### Nice-to-have (opportunistic improvements)
- New features available via config (new channels, tools, plugins)
- Performance tuning knobs added upstream
- UX improvements (streaming modes, button styles, etc.)
- CLI commands that could simplify operations

### Step 5: Produce the report

Output a structured report with:

```
## Breaking Changes (N items)
- [version] Description of what changed and what breaks
  - Affected: template / instance-name / SKILL.md
  - Fix: Concrete config change or SKILL.md update

## Recommended Changes (N items)
- [version] Description
  - Affected: ...
  - Fix: ...

## Nice-to-Have (N items)
- [version] Description
  - Benefit: ...

## Suggested SKILL.md Updates
- Add schema notes for versions X through Y
- Update meta.lastTouchedVersion to Z
- Add/remove keys from removed-keys list
- Update validate_client_kit.sh checks

## Suggested Config Changes
- Template: { specific JSON changes }
- Instance X: { specific JSON changes }
```

### Step 6: Update the schema snapshot

After analysis, update `references/config-schema-snapshot.md` in THIS skill
with any newly discovered schema changes so future audits have a local baseline.

## Reference Files

- `scripts/audit.sh` — Quick structural drift check (version, keys, instances)
- `references/config-schema-snapshot.md` — Point-in-time schema reference with
  per-version change notes

## Upstream Sources

- Repo: `openclaw/openclaw` on GitHub
- Releases: `gh release list --repo openclaw/openclaw`
- Config docs: `https://docs.openclaw.ai/gateway/configuration-reference`
- Install: `curl -fsSL https://openclaw.ai/install.sh | bash`

## Integration with openclaw-client-bootstrap

After completing the audit, the recommended workflow is:

1. Apply breaking fixes to template + instances
2. Update SKILL.md schema notes section
3. Update `meta.lastTouchedVersion` in template openclaw.json
4. Run validation: `bash scripts/validate_client_kit.sh assets/client-kit`
5. Run review: `bash scripts/review_kit.sh --skill`
6. For live claws: `bash scripts/review_kit.sh --live`
7. Commit changes to the bootstrap skill repo
