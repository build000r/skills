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

# Load them into the current shell, then run the tool normally:
. scripts/overlay_env.sh
overlay_env_load oracle || exit 1
oracle --engine browser ...
```

> **Load it with `overlay_env.sh`, never with a bare `eval "$(...)"`.**
> See [Why not `eval "$(...)"`](#why-not-eval) below — that form cannot detect a
> failed resolver, and silently running unoverlaid is the outcome that hurts.

Mapping is mechanical: each scalar key `k` in section `s` becomes
`<S>_<K>` (uppercased), e.g. section `oracle`, key `cdp_port` →
`ORACLE_CDP_PORT`. Override the prefix with `--prefix`. Booleans render as
`true`/`false`; `~` and `$VAR` are expanded; nested mappings/lists are skipped
in env output (use `--format json` to read them structurally).

It is a **silent no-op** when no overlay matches or the section is absent
(exit 0, no output), so callers fall back to their own defaults. Pass
`--require` to make a miss a non-zero exit instead.

<a id="why-not-eval"></a>
### Why not `eval "$(...)"`

The obvious consumer line is unsafe, and was the documented one until this was
found:

```bash
eval "$(python3 "$RESOLVER" --section oracle --format env)"   # DO NOT — see below
```

Command substitution discards the resolver's exit status. `eval` reports the
status of *the text it evaluated*, not of the process that produced it, and
empty text evaluates to 0. So when the resolver dies — a stack trace, a missing
PyYAML, a PEP-604 union under Python 3.9 — that line returns **0 with nothing
set**, and the caller proceeds with its own defaults exactly as if no overlay
had ever been configured.

Neither `--require` nor `set -e` catches it: the non-zero exit is thrown away by
the same substitution before either can see it.

That matters because the fallback defaults are *plausible* — the default CDP
port, the default model, no account pin. The run appears to succeed while
targeting the wrong thing. A loud failure is recoverable; a silent wrong target
is not.

### Consumer contract (graceful, optional)

Source `scripts/overlay_env.sh` and call `overlay_env_load`. It keeps the
soft-dependency behaviour and adds the two checks the bare `eval` cannot make:

```bash
. "$SKILL_ISSUE/scripts/overlay_env.sh"   # or ./.claude/skills/skill-issue/...
overlay_env_load oracle || exit 1
# Tool still works with its own defaults if the resolver or overlay is absent.
```

| Situation | `overlay_env_load` |
| --- | --- |
| resolver absent (skill-issue not installed) | no-op, returns 0 — optional dependency |
| resolver present but fails | returns non-zero, sets nothing, prints the interpreter and stderr |
| resolver output is not pure `export` lines | returns non-zero, sets nothing, never evals |
| resolver succeeds | variables exported, returns 0 |

Absent and broken are deliberately different: a missing optional dependency is
expected, a crashing one is a bug you need to see. Set `OVERLAY_ENV_REQUIRE=1`
to make absent an error too. `OVERLAY_ENV_PYTHON` overrides the interpreter,
`OVERLAY_ENV_RESOLVER` the resolver path.

Output is checked against an allowlist — every non-blank line must be
`export NAME=…` — before anything is evaluated, so a truncated write or a
traceback on stdout is refused rather than executed. The check is all-or-nothing:
a half-valid payload sets nothing, because a half-configured environment is the
same silent-wrong-target failure in a smaller costume. A value containing a
literal newline is refused too; use `--format json` for structured values.

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
