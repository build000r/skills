# Per-project config in overlays

Client overlays are the place to set per-project settings that more than one
skill needs to agree on. Instead of each skill inventing its own dotfile or
relying on ambient environment variables an agent must remember to set, put the
setting once in the project's `overlay.yaml` and let skills read it at runtime.

This keeps configuration:

- **Project-scoped**: the matched overlay (`manage_overlays.py match`) decides
  which values apply, so the same skill behaves correctly across repos.
- **Reviewable**: repo-local `.buildooor/skillbox-config/clients/<client>/`
  overlays are git-tracked; private/operator-wide values stay in the shared
  `skillbox-config/clients/<client>/` fallback.
- **One source of truth**: skills don't hardcode paths, accounts, or endpoints.

## Where config sections live

Runtime config sits under `client.context.<section>` in `overlay.yaml`. The
`context` block is the read-model skills consume (`cwd_match`, `deploy`,
`plans`, etc. already live there). A generated `context.yaml` flattens those
keys to the top level; the resolver below reads either shape.

```yaml
version: 1
client:
  id: my-project
  context:
    cwd_match: [~/repos/my-project]
    oracle:                 # <- a per-project config section
      cdp_port: 9222
      chatgpt_url_match: g-p-abc123
```

## The env-var bridge: `resolve_overlay_config.py`

Most CLI tools already read environment variables. `resolve_overlay_config.py`
resolves a section of the matched overlay into `export` lines so those tools
pick up project settings unchanged:

```bash
# Emit: export ORACLE_CDP_PORT='9222'  export ORACLE_CHATGPT_URL_MATCH='g-p-abc123' ...
scripts/resolve_overlay_config.py --section oracle --format env

# Source them into the current shell, then run the tool normally:
eval "$(scripts/resolve_overlay_config.py --section oracle --format env)"
oracle --engine browser ...
```

Mapping is mechanical: each scalar key `k` in section `s` becomes
`<S>_<K>` (uppercased), e.g. section `oracle`, key `cdp_port` →
`ORACLE_CDP_PORT`. Override the prefix with `--prefix`. Booleans render as
`true`/`false`; `~` and `$VAR` are expanded; nested mappings/lists are skipped
in env output (use `--format json` to read them structurally).

It is a **silent no-op** when no overlay matches or the section is absent
(exit 0, no output), so callers can `eval` it unconditionally and fall back to
their own defaults. Pass `--require` to make a miss a non-zero exit instead.

### Consumer contract (graceful, optional)

A skill that wants overlay-aware config should treat the resolver as a soft
dependency:

```bash
RESOLVER=""
for d in "./.claude/skills/skill-issue" "$HOME/.claude/skills/skill-issue"; do
  [ -f "$d/scripts/resolve_overlay_config.py" ] && { RESOLVER="$d/scripts/resolve_overlay_config.py"; break; }
done
[ -n "$RESOLVER" ] && eval "$(python3 "$RESOLVER" --section oracle --format env)"
# Tool still works with its own defaults if the resolver or overlay is absent.
```

Declare it in frontmatter so `check_skill_deps.py` flags resolver-interface
drift: `depends_on: [skill-issue]`.

## The `oracle` section (worked example)

`oracle` is the [oracle CLI](https://askoracle.sh) — a wrapper that drives
GPT-5.x Pro / ChatGPT Deep Research via a browser (CDP) or the API. Its
genuinely *per-project* knobs were previously scattered across `ORACLE_*` env
vars with no project home — most importantly **which ChatGPT account (Chrome
profile)** and **which ChatGPT Project/folder** a repo's research runs use. An
ambiguous account/tab is the classic footgun: a run silently submits under the
wrong login or as a normal (non-Deep-Research) turn.

Recognized keys (all optional; keys ending in a known `ORACLE_*` name map 1:1
to the env vars the oracle CLI and the `deep-research-prompt` CDP helpers
already read):

| Key | Env var | Meaning |
|-----|---------|---------|
| `cdp_host` | `ORACLE_CDP_HOST` | Chrome DevTools host (default `127.0.0.1`) |
| `cdp_port` | `ORACLE_CDP_PORT` | Chrome DevTools port (default `9222`) |
| `chatgpt_url_match` | `ORACLE_CHATGPT_URL_MATCH` | Unique substring of the project URL that selects exactly one ChatGPT tab |
| `chatgpt_target_id` | `ORACLE_CHATGPT_TARGET_ID` | Exact CDP target id (when known) |
| `browser_profile_dir` | `ORACLE_BROWSER_PROFILE_DIR` | Chrome `--user-data-dir` = which logged-in ChatGPT account |
| `profile_directory` | `ORACLE_PROFILE_DIRECTORY` | Chrome subprofile inside the user-data-dir (e.g. `Profile 1`) that actually holds the logged-in ChatGPT session — `Default` is often logged out |
| `chatgpt_project_url` | `ORACLE_CHATGPT_PROJECT_URL` | Full ChatGPT Project/folder URL (human reference + selector source) |
| `account_label` | `ORACLE_ACCOUNT_LABEL` | Human label for the account behind this profile |
| `default_engine` | `ORACLE_DEFAULT_ENGINE` | `browser` or `api` |
| `default_model` | `ORACLE_DEFAULT_MODEL` | e.g. `gpt-5.4-pro` (oracle's own default) |
| `deep_research_default` | `ORACLE_DEEP_RESEARCH_DEFAULT` | Whether to toggle Deep Research on by default |
| `slug_prefix` | `ORACLE_SLUG_PREFIX` | Prefix for `--slug` session names |

```yaml
# overlay.yaml (private skillbox-config fallback — holds the real URLs)
client:
  context:
    oracle:
      browser_profile_dir: ~/.oracle/browser-profile
      profile_directory: Profile 1
      account_label: a
      chatgpt_project_url: https://chatgpt.com/g/g-p-EXAMPLE/project
      chatgpt_url_match: g-p-EXAMPLE
      cdp_host: 127.0.0.1
      cdp_port: 9222
      default_engine: browser
      default_model: gpt-5.4-pro
      deep_research_default: true
      slug_prefix: my-project
```

**Multiple profiles / accounts.** One Chrome `browser_profile_dir` corresponds
to one logged-in ChatGPT account, and each account typically has its own
ChatGPT Project/folder. Pin both per project: `browser_profile_dir` selects the
account, `chatgpt_url_match` selects the project tab within it. Also pin
`profile_directory` when the logged-in session lives in a Chrome subprofile —
check with
`sqlite3 "<root>/<profile>/Cookies" "select host_key, count(*) from cookies
where host_key like '%chatgpt%' group by host_key;"`; the subprofile with the
most `chatgpt.com` cookie rows is the logged-in one. Keep the real
project URLs in the **private** `skillbox-config` overlay, never in a public
skill or repo — public docs use `g-p-EXAMPLE` placeholders.

## Validation

`manage_overlays.py validate` checks the `oracle` block when present: it must be
a mapping, `cdp_port` must be an integer, `deep_research_default` must be
boolean, and a literal `browser_profile_dir` is warned about if it doesn't
exist on disk. Unknown keys are allowed (forward-compatible) but reported as
info so typos surface.
