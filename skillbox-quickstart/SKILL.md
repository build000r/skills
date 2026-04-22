---
name: skillbox-quickstart
description: >
  Assess a user's local environment (repos, tools, skills, Claude config),
  generate a skillbox client overlay, and provision a working skillbox container
  on DigitalOcean or locally. Use for "up up up", "set up my skillbox",
  "quickstart", "new box", "onboard me to skillbox", "spin up a box",
  or when a user wants to go from zero to a working skillbox environment.
---

# Skillbox Quickstart

Intelligent onboarding that scans what you have and builds a working skillbox from it.

## Do Not Use This For

- Managing an existing running box (use `skillbox-operator`)
- Deploying code to a box (use `deploy`)
- Planning domain slices (use `domain-planner`)

## On Trigger

Run the 5-phase flow below. Each phase gates the next.

## Phase 1: Scan

Run the environment scanner to assess what the user has:

```bash
python3 ~/.claude/skills/skillbox-quickstart/scripts/scan_environment.py --json > /tmp/skillbox-scan.json
```

If the user wants to scan specific directories:

```bash
python3 ~/.claude/skills/skillbox-quickstart/scripts/scan_environment.py \
  --scan-root ~/repos --scan-root ~/projects --json > /tmp/skillbox-scan.json
```

Read the output. Present a human-readable summary:
- Repos found (name, stack, remote)
- Tools status (installed / missing)
- Claude config (skills count, MCP servers)
- Gaps (blocking vs recommended)

**If blocking gaps exist** (docker, git missing): stop and help the user install them before proceeding.

## Phase 2: Decide

Run the overlay generator to get a recommendation:

```bash
cat /tmp/skillbox-scan.json | python3 ~/.claude/skills/skillbox-quickstart/scripts/generate_overlay.py \
  --client-id {CLIENT_ID} --json > /tmp/skillbox-recommendation.json
```

The `{CLIENT_ID}` should be inferred from context:
- If the user named a project, use that (snake_case)
- If they have one dominant repo, use its name
- Otherwise ask: "What should we call this client? (snake_case, e.g., `my_project`)"

Present the recommendation to the user with structured questions:

1. **Blueprint choice**: "I'd recommend `{blueprint}` because {reason}. Sound right?"
2. **Repo selection** (if multiple found): "Found {N} repos. Which ones belong in this box?"
3. **Primary repo**: "Which repo should be the default working directory?"
4. **Deployment target**: "Run locally (Docker on this machine) or remote (DigitalOcean droplet)?"

Use the decisions list from recommendation.json — don't re-derive questions.

## Phase 3: Generate

After user confirms decisions, write the overlay:

```bash
cat /tmp/skillbox-scan.json | python3 ~/.claude/skills/skillbox-quickstart/scripts/generate_overlay.py \
  --client-id {CLIENT_ID} --output /tmp/skillbox-quickstart-{CLIENT_ID}
```

Read the generated `overlay.yaml`. If the user refined repo selection or primary repo in Phase 2, edit the overlay to match before proceeding.

Show the user the final overlay and the `first-box` command that will be run. Get explicit confirmation: **"Ready to build? This will create the container and sync your repos."**

## Phase 4: Provision

Two paths based on the deployment target decision:

### Path A: Local (Docker on this machine)

Requires: the skillbox repo cloned locally.

```bash
# From the skillbox repo root
cd {SKILLBOX_REPO}

# Copy overlay into place
mkdir -p ../skillbox-config/clients/{CLIENT_ID}
cp /tmp/skillbox-quickstart-{CLIENT_ID}/overlay.yaml ../skillbox-config/clients/{CLIENT_ID}/

# Run first-box
python3 .env-manager/manage.py first-box {CLIENT_ID} \
  --private-path ../skillbox-config \
  --format json
```

If the skillbox repo isn't cloned yet:

```bash
curl -fsSL https://raw.githubusercontent.com/build000r/skillbox/main/install.sh | \
  bash -s -- --client {CLIENT_ID}
```

### Path B: Remote (DigitalOcean)

Requires: `SKILLBOX_DO_TOKEN` and `SKILLBOX_TS_AUTHKEY` env vars set.

Use the `skillbox-operator` MCP tools:

1. `operator_profiles` — show available box sizes, let user pick
2. `operator_provision` with `dry_run=true` — preview what will be created
3. Confirm with user
4. `operator_provision` with `dry_run=false` — create the droplet
5. Wait for ready state
6. `operator_box_exec` — copy overlay and run first-box on the remote box

## Phase 5: Verify

After provisioning completes:

1. **Check health**: Run `operator_doctor` (remote) or `make dev-sanity` (local)
2. **Report results**: Show which repos synced, which services started, any issues
3. **Show next steps**:
   - "Your box is ready. Run `make shell` to enter it."
   - "Inside the box, run `focus {CLIENT_ID}` to activate the client context."
   - If skills were detected: "Your {N} local skills will be available inside the box."

## Error Recovery

- **Docker not running**: "Start Docker Desktop and re-run."
- **Port conflicts**: "Port {PORT} is in use. Stop the conflicting process or edit .env to change the port."
- **DO provision fails**: "Check SKILLBOX_DO_TOKEN is valid. Run `operator_boxes` to see current fleet."
- **Repo clone fails**: "Check the remote URL is accessible. You may need to add an SSH key to the box."
- **first-box fails**: Read the JSON output, identify the failing step, and surface the specific error.

## Skill Dependencies

- `skillbox-operator` — for remote provisioning via MCP tools
- `dev-sanity` — for post-provision health checks

## Related

- [[skill-issue]]
