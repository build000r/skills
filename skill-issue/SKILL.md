---
name: skill-issue
description: Create, update, and package skills for AI coding agents. Use when asked to "create a skill", "make a skill", "new skill", "skill template", "design a skill", "build a skill", or when working with SKILL.md files, frontmatter, bundled resources (scripts/, references/, assets/), or .skill packaging. Also triggers on "how do I make a skill", "skill best practices", "skill structure", or requests to extend an agent's capabilities with reusable workflows.
license: Complete terms in LICENSE.txt
---

# Skill Creator

Create effective skills for AI coding agents: modular packages that extend agents with specialized workflows, domain expertise, and reusable tools.

## Modes

Modes customize skill creation for specific organizations or projects — naming conventions, required sections, publishing targets, testing workflows, and review processes. Stored in `modes/` (gitignored, never committed).

### How Modes Work

Each mode is a markdown file: `modes/{project-name}.md`. It contains org-specific configuration: skill naming patterns, required SKILL.md sections, publishing target (marketplace, GitHub org, internal registry), validation commands, standard bundled resources, and the review/approval workflow.

### Mode Selection (Step 0)

1. List `.md` files in `modes/` (if directory exists)
2. Each mode file has a `cwd_match` field — a path prefix to match against cwd
3. If cwd matches exactly one mode, use it automatically
4. If cwd matches multiple or none, ask the user which mode (or use generic defaults)
5. If `modes/` doesn't exist, use generic skill creation (no org-specific standards)

### Creating a Mode

Copy `references/mode-template.md` to `modes/{project-name}.md` and fill in org standards, publishing targets, and review process. When a user runs the skill with no matching mode, offer to create one.

Modes are gitignored — they contain org-specific paths and workflows that should not be committed to the skill repo.

## Core Principles

### Concise is Key

The context window is a public good. Only add context the agent doesn't already have. Challenge each piece: "Does this paragraph justify its token cost?"

Prefer concise examples over verbose explanations.

### Set Appropriate Degrees of Freedom

Match specificity to the task's fragility:

- **High freedom (text instructions)**: Multiple valid approaches, context-dependent decisions
- **Medium freedom (pseudocode/parameterized scripts)**: Preferred pattern exists, some variation acceptable
- **Low freedom (specific scripts)**: Fragile operations, consistency critical, exact sequence required

### Skill Structure

Every skill has a required `SKILL.md` (YAML frontmatter + markdown body) and optional bundled resources (`scripts/`, `references/`, `assets/`).

For directory structure details, resource types, progressive disclosure patterns, and what NOT to include, see [references/skill-structure.md](references/skill-structure.md).

## Skill Creation Process

1. Understand the skill with concrete examples
2. Plan reusable skill contents (scripts, references, assets)
3. Initialize the skill (run init_skill.py)
4. Edit the skill (implement resources and write SKILL.md)
5. Validate and package the skill (run package_skill.py)
6. Iterate based on real usage
7. Publish to marketplaces (optional) — see `references/publishing.md`

Follow these steps in order, skipping only if clearly not applicable.

### Step 1: Understand the Skill

Skip only when usage patterns are already clearly understood.

Gather concrete examples of how the skill will be used — from the user or by generating examples and validating with feedback. Ask about functionality scope, usage examples, and trigger phrases. Don't overwhelm with questions; start with the most important and follow up.

### Step 2: Plan Reusable Contents

**Choose a searchable name first.** Two searchable keywords, `[domain]-[action]` pattern, lowercase with hyphens. Test: "What would someone search for?" See `references/publishing.md` for detailed naming guidance.

Then analyze each example: consider how to execute from scratch, and identify what scripts, references, and assets would help when repeating these workflows.

Example: A `pdf-editor` skill for "Help me rotate this PDF" — rotating requires the same code each time → include `scripts/rotate_pdf.py`.

### Step 3: Initialize the Skill

Skip if the skill already exists and only needs iteration or packaging.

```bash
scripts/init_skill.py <skill-name> --path <output-directory> [--minimal]
```

Creates a template skill directory with SKILL.md, example `scripts/`, `references/`, and `assets/`. Use `--minimal` when you already know what you're building. Customize or remove generated example files as needed.

### Step 4: Edit the Skill

The skill is for another agent instance. Include non-obvious procedural knowledge, domain-specific details, and reusable assets.

#### Consult Design Pattern Guides

- **Multi-step processes**: Read references/workflows.md
- **Consistent output formats**: Read references/output-patterns.md
- **Complete example**: Read references/example-minimal-skill.md
- **Publishing**: Read references/publishing.md

#### Sprite Variant Contract (Character Diversity + Compatibility)

When creating or updating sprite-generation skills, enforce this contract:

- Keep runtime naming/API contract fixed:
  - Files: `active.svg`, `drowsy.svg`, `sleeping.svg`, `deep_sleep.svg`
  - Field names: `active`, `drowsy`, `sleeping`, `deep_sleep`
- Keep directory convention fixed (project local): `.throngterm/sprites/`
- Preserve state semantics:
  - `active`: awake/engaged
  - `drowsy`: transitional low-energy
  - `sleeping`: asleep
  - `deep_sleep`: deepest rest state
- Encourage visual diversity per repo/domain:
  - Distinct palettes tied to repo branding
  - Distinct silhouettes/accessories/motifs (not only recolors)
  - Keep readability at small sizes
  - If sibling repos share a base thronglet, include a structural identity marker group (`<g id="backend-id">` / `<g id="frontend-id">`) in every state, not just palette shifts
- Make sprite SVGs self-contained when using logo/image wrappers:
  - Avoid external image refs like `<image href=\"/logo.png\">` or `./logo.png`
  - Prefer embedded data URIs so assets render when injected cross-origin/cross-app
- Do not break loaders to achieve style changes. Creativity is applied inside the fixed naming + state contract.

Quick validation before shipping:
```bash
for s in active drowsy sleeping deep_sleep; do
  test -f ".throngterm/sprites/${s}.svg" || echo "missing ${s}.svg"
done

# Should output nothing for self-contained SVG packs
rg -n '<image[^>]+href="/' .throngterm/sprites
rg -n '<image[^>]+href="./' .throngterm/sprites

# Optional but required when differentiating sibling repos (for example frontend vs backend)
MARKER_ID="backend-id"
for s in active drowsy sleeping deep_sleep; do
  rg -q "<g id=\"${MARKER_ID}\"" ".throngterm/sprites/${s}.svg" || echo "missing marker ${s}.svg"
done

# Marker must be in the primary body window (not a tiny corner stamp)
for s in active drowsy sleeping deep_sleep; do
  perl -0777 -e '
    my ($file,$id)=@ARGV;
    local $/; open my $fh, "<", $file or die $!;
    my $svg=<$fh>;
    $svg =~ m{<g id="\Q$id\E"[^>]*>(.*?)</g>}s or die "missing marker group\n";
    my $g=$1;
    my @x = ($g =~ /x="(\d+)"/g); my @y = ($g =~ /y="(\d+)"/g);
    die "marker has no coords\n" unless @x && @y;
    my ($minx,$maxx)=($x[0],$x[0]); for (@x){$minx=$_ if $_<$minx; $maxx=$_ if $_>$maxx;}
    my ($miny,$maxy)=($y[0],$y[0]); for (@y){$miny=$_ if $_<$miny; $maxy=$_ if $_>$maxy;}
    die "marker out of body window: $minx,$maxx,$miny,$maxy\n" if $minx < 160 || $maxx > 352 || $miny < 160 || $maxy > 368;
    my $motif_cells = () = $g =~ /class="m"/g;
    die "marker motif too subtle: $motif_cells\n" if $motif_cells < 6;
  ' ".throngterm/sprites/${s}.svg" "${MARKER_ID}" || echo "marker-check-fail ${s}.svg"
done
```

#### Reliability Hardening Gate (Ops / Deploy Skills)

If the skill touches deployment, auth, env sync, or production debugging, include an explicit anti-footgun section before finalizing.

Required checks:
- Add a preflight checklist that catches stale GitHub secrets vs local env files.
- If a change introduces new credential scopes/headers/env vars, document whether rollout requires one deploy or a two-phase deploy.
- Add a concrete failure-signature map (`HTTP code + error code`) for auth failures, not just generic "unauthorized" language.
- If the skill contains shell scripts, ensure no-arg behavior prints usage cleanly (no `${1:?}` crash UX).
- Include at least one command-first verification path for behavior and one side-effect/state verification path.

Recommended shell-script sanity checks:
```bash
# Syntax
for f in <skill>/scripts/*.sh; do bash -n "$f"; done

# No-arg UX should return usage text and non-zero
for f in <skill>/scripts/*.sh; do "$f" >/tmp/out 2>/tmp/err || true; head -n1 /tmp/out /tmp/err; done
```

#### Open-Source Readiness (Privacy Gate)

Before committing or packaging any skill for public release, scrub ALL files (SKILL.md, scripts/, references/, assets/) for:

- **Personal info**: Names, emails, phone numbers, social handles (@handle)
- **Secrets**: API keys, tokens, passwords, connection strings — even in examples
- **Hardcoded paths**: `/Users/<name>/`, `/srv/<workspace>/`, `~/repos/<specific-project>`
- **Business names**: Company names, product names, internal project names, domain names (*.yourcompany.com)
- **Real IPs/hostnames**: Server IPs, internal DNS names, container names tied to deployments
- **Referral/affiliate links**: URLs with tracking parameters (`fpr=...`, `ref=...`, etc.)
- **Business intelligence**: Customer lists, personas, targeting criteria, pricing, competitor data

**Mode files are safe** — `modes/` is gitignored and never committed. Project-specific config belongs there, not in tracked files.

**Pattern**: Use `{placeholder}` syntax for values that vary per deployment. Scripts should accept CLI args or mode config instead of hardcoded defaults. Reference files should use generic examples ("auth service", "your-project") instead of real names.

**Quick check**: `grep -rE 'your-real-company|/Users/you|real-ip|@yourhandle' <skill-dir>/` before committing.

#### Open-Source Skill Architecture

Skills intended for public repos use a dual-layer pattern: **generic tracked files + private mode overlays**.

```
my-skill/                      ← public (git tracked)
├── SKILL.md                   ← generic instructions, {placeholder} variables
├── references/                ← generic patterns, workflows
├── scripts/                   ← generic utilities
├── assets/templates/          ← generic templates
│   ├── default.md             ← tracked
│   └── my-project.md          ← gitignored (project-specific template)
└── modes/                     ← gitignored entirely
    └── my-project.md          ← project-specific: paths, names, conventions
```

**The SKILL.md reads mode config at runtime** to fill in `{placeholder}` values:
- `{auth_packages_root}` → mode provides `../auth-service/packages`
- `{plan_root}` → mode provides `~/.claude/plans/my-project`
- `{backend_repo}` → mode provides `~/repos/my-api`

Anyone cloning the public repo gets a working generic skill. You keep your project-specific overlay locally.

#### Repo-Level .gitignore for Skill Collections

For repos containing multiple skills, the root `.gitignore` should cover:

```gitignore
# All modes across all skills (private project config)
modes/

# Python artifacts
__pycache__/
*.pyc

# Build artifacts
*.skill
*.zip
dist/

# Project-specific skills that should never be public
my-private-skill/

# Project-specific asset variants (template naming convention)
# Example: gitignore frontend-*.md but track frontend.md
my-skill/assets/templates/frontend-*.md
!my-skill/assets/templates/frontend.md
```

**Key patterns:**
- `modes/` at the root catches all nested `*/modes/` directories
- Use `skillname/` entries for entire skills that must stay private
- Use `!` exceptions to track generic templates while ignoring project-specific variants
- Private deployment data (instance configs, deployed IPs) should have dedicated gitignore entries

#### Sanitization Workflow (Existing Repo → Public)

When preparing an existing skill repo for open source:

1. **Audit tracked files**: `git ls-files | xargs grep -lE 'project-name|internal-domain|api-key-name'`
2. **Extract project content → modes/**: Move project-specific references from SKILL.md body into mode files. Replace with `{placeholder}` syntax referencing mode config.
3. **Genericize examples**: Replace domain-specific slice names with generic ones ("task_assignments"). Replace internal service names with generic terms ("backend API"). Keep generic role names (practitioner, admin, user).
4. **Verify gitignore coverage**: Ensure `modes/`, project-specific templates, and deployment data are all excluded.
5. **Final audit**: `git ls-files | xargs grep -lE 'project|company|internal'` — zero tolerance for the real names.
6. **Check git history**: If project names exist in past commits, consider `git filter-repo` or starting a clean history.

#### Handling API Keys and Secrets

Never hardcode API keys. Use `$ENV_VAR` references in curl/script templates and document the required variable.

Users should set keys in their shell profile (`~/.zshrc` or `~/.bash_profile`):

```bash
export MY_API_KEY
```

**Known issue:** The `env` field in `~/.claude/settings.json` does not reliably expand variables in Bash tool commands. Shell profile exports work correctly.

In SKILL.md, document requirements like:

```markdown
## Prerequisites
Add to `~/.zshrc`: `export MY_API_KEY`
```

#### Local Development with Symlinks

Store skill source in a version-controlled repo, then symlink into each agent's skills directory (Claude + Codex) for discovery:

```bash
ln -s ~/repos/skills/my-skill ~/.claude/skills/my-skill
ln -s ~/repos/skills/my-skill ~/.codex/skills/my-skill
```

In this repo specifically, use `./scripts/link-skills.sh` to link all skills into both directories automatically.

The marketplace plugin version (if installed) takes precedence over local skills directories — use a different name to avoid conflicts.

#### Implement Resources First

Start with `scripts/`, `references/`, and `assets/` files identified in Step 2. This may require user input (e.g., brand assets, documentation). Test added scripts by running them. Delete unneeded example files from initialization.

#### Write SKILL.md

**Writing guidelines:** Use imperative/infinitive form.

**Frontmatter** (YAML):
- `name` (required): The skill name
- `description` (required): Primary triggering mechanism. Include what the skill does AND specific triggers/contexts. All "when to use" goes here — not in the body (which only loads after triggering).
  - Example for a `docx` skill: "Comprehensive document creation, editing, and analysis with support for tracked changes, comments, formatting preservation, and text extraction. Use when working with .docx files for: creating, editing, tracked changes, comments, or any document task."
- `license`, `allowed-tools`, `metadata`: Optional

**Body** (Markdown): Instructions for using the skill and its bundled resources. Keep under 500 lines — split to reference files when approaching this limit.

### Step 5: Validate and Package

Validate during development:

```bash
scripts/quick_validate.py <path/to/skill-folder>
```

Package when complete:

```bash
scripts/package_skill.py <path/to/skill-folder> [output-directory]
```

Packaging validates automatically, then creates a `.skill` file (zip with .skill extension). Fix any validation errors and re-run.

For ops/deploy skills, do an additional manual quality pass:
- Run every documented preflight command at least once.
- Run at least one intentional failure-path probe and verify the troubleshooting guidance matches the real error.

### Step 6: Iterate

1. Use the skill on real tasks
2. Notice struggles or inefficiencies
3. Update SKILL.md or bundled resources
4. Test again

If you hit a production near-miss or rollback-causing mistake, treat the skill update as part of the fix:
1. Add the symptom/cause/fix to the skill's troubleshooting reference.
2. Add the prevention command/checklist to the main SKILL.md preflight section.
3. Re-run the updated checklist to prove it catches the original failure mode.

### Step 7: Publish (Optional)

1. Create a public GitHub repo
2. Add a README.md (for humans, not Claude)
3. Add a `.zip` package: `zip -r skill-name.zip SKILL.md scripts/ references/`
4. Promote to drive downloads (downloads = ranking)

**Read `references/publishing.md`** for the complete checklist and promotion strategies.

## Environment Management

Beyond individual skills, skill-issue can audit your entire Claude environment.

### Audit

Scan `~/.claude/` and project directories, generate a context registry, and produce a health report:

```bash
scripts/audit_context.py                                 # Scan ~/repos, write to ~/.claude/context/
scripts/audit_context.py --scan-root ~/projects          # Custom scan root
scripts/audit_context.py --report-only                   # Print report without writing registry
scripts/audit_context.py --scan-root ~/repos --scan-root ~/work  # Multiple roots
```

The audit discovers: projects with `.claude/` config, CLAUDE.md files, MCP servers, project-level hooks and skills, global skills (symlinked, packaged, local), and skill modes.

Issues detected: secrets in MCP configs, broken skill symlinks, stale empty `.claude/` directories, duplicate MCP definitions across projects, mode files targeting nonexistent paths, parent CLAUDE.md inheritance.

Registry output goes to `~/.claude/context/` with `manifest.yaml`, `projects/*.yaml`, `mcps/*.yaml`, and `machines/*.yaml`.

### Init

Bootstrap `~/.claude/context/` for a new machine or add a single project:

```bash
scripts/init_context.py                              # Interactive machine setup
scripts/init_context.py --non-interactive            # Accept all defaults
scripts/init_context.py --project ~/repos/my-app     # Add one project to existing registry
scripts/init_context.py --scan-root ~/projects       # Custom scan root
```

Full init walks through: machine name, scan roots, project discovery, and registry creation. Use `--project` to add a single project without re-scanning everything.

### Sync

Detect drift between the registry and filesystem:

```bash
scripts/sync_context.py                    # Check for drift (exit code 1 if drift found)
scripts/sync_context.py --check            # Same as above
scripts/sync_context.py --update           # Re-scan and update registry
```

Drift detection compares: project paths still exist, config files unchanged (by content hash), skills added/removed, hooks changed, MCP servers changed. Exit code 0 means no drift, 1 means drift detected.
