# build000r/skills

<p align="center">
  <img alt="Catalog" src="https://img.shields.io/badge/catalog-38_skills-111111?style=for-the-badge" />
  <img alt="Works with Claude Code, Codex, and Cursor" src="https://img.shields.io/badge/agents-Claude_Code%20%7C%20Codex%20%7C%20Cursor-2f6feb?style=for-the-badge" />
  <img alt="Licensing is skill-specific" src="https://img.shields.io/badge/license-skill--specific-6b7280?style=for-the-badge" />
</p>

<p align="center">
  Reusable agent workflows for planning, verification, coding, operations, content, and OpenClaw runtime work.
</p>

<p align="center">
  Install the full tracked catalog with:
</p>

```bash
npx skills add build000r/skills --all
```

## TL;DR

### The Problem

Most agent setups collapse into one of two bad patterns:

- giant system prompts that try to do everything
- one-off prompt snippets that solve one task once and then disappear

That usually means weak reuse, inconsistent quality, poor discoverability, and
no clean place for helper scripts, templates, or private local overlays.

### The Solution

This repo is a skill monorepo. Each top-level skill packages a durable workflow
in `SKILL.md`, with optional `references/`, `scripts/`, `assets/`, app code, and
private local `modes/` overlays where needed.

Use it when you want agents to follow repeatable operating procedures instead of
re-inventing the same workflow on every run.

### Why Use This Repo?

| Need | What this repo gives you |
| --- | --- |
| Reusable engineering workflows | Skills for planning, review, reproduction, mutation testing, and commits |
| Structured local context | Mode templates for skills that need private portfolio, repo, or deployment context |
| Deterministic helpers where prompts are not enough | App-backed skills such as [`clawgs`](./clawgs/) |
| Deployable asset bundles | Runtime kits and embedded child skills in [`openclaw-client-bootstrap`](./openclaw-client-bootstrap/) |
| Pick-your-surface installs | Install one skill, a lane, the whole catalog, or symlink a local checkout |
| Honest boundaries | Skill-specific licensing, partial packaging in `dist/`, and explicit limitations |

## Quick Example

The fastest way to get value is to install a few workflows you will actually use:

```bash
# Install a small engineering stack from GitHub
npx skills add build000r/skills -s describe
npx skills add build000r/skills -s reproduce
npx skills add build000r/skills -s commit

# Clone the repo locally if you want to inspect or iterate on the skills
git clone git@github.com:build000r/skills.git
cd skills

# Link the local checkout into Claude + Codex
./scripts/link-skills.sh

# Add a private mode overlay for skills that need local context
cp domain-planner/references/mode-template.md modes/my-portfolio.local.md

# If you want an app-backed skill, install and verify it separately
./clawgs/scripts/install.sh
./clawgs/scripts/check.sh
```

## Design Philosophy

### 1. Workflows, Not Prompt Scrapbooks

Each skill is meant to encode a repeatable decision process, not just a catchy
prompt. The point is to preserve operating discipline.

### 2. Prompt First, Runtime When Necessary

Most skills are plain instruction packs. When deterministic behavior matters,
the repo allows app-backed helpers, scripts, or asset bundles to sit beside the
workflow.

### 3. Public Core, Private Overlays

Tracked files stay reusable. Local portfolio paths, internal domains, server
IPs, or customer-specific rules belong in gitignored mode files.

### 4. Small, Composable Units

The default install surface is the set of tracked top-level directories that
contain `SKILL.md`. You can install one skill, a lane, or the full catalog.

## Comparison

| Approach | Good for | Breaks down when | Why this repo exists |
| --- | --- | --- | --- |
| Ad-hoc prompt snippets in notes | Tiny one-off tasks | Nothing is standardized, searchable, or reusable | Skills give each workflow a stable home |
| One giant agent prompt | Opinionated personal setup | Too much context, weak discoverability, hard to maintain | Each workflow becomes independently installable |
| Full custom app/plugin only | Deterministic heavy lifting | Overkill for mostly-instructional workflows | Skills keep the simple cases lightweight |
| This repo | Agent workflows with optional code, templates, and private overlays | You still need local mode files for context-heavy skills | Best middle ground for reusable agent operations |

## Skill Lanes

### Engineering And Workflow

| Skill | What it does |
| --- | --- |
| [`ask-cascade`](./ask-cascade/) | Orders user-facing questions from high-level dependencies down to details |
| [`audit-plans`](./audit-plans/) | Audits plans, order, focus, and backlog state |
| [`build-vs-clone`](./build-vs-clone/) | Decides whether work belongs in an existing repo, shared home, or new build |
| [`codex-tmux`](./codex-tmux/) | Runs Codex in persistent tmux sessions for long jobs |
| [`commit`](./commit/) | Batches working changes into clean, high-level commits |
| [`crap`](./crap/) | Ranks risky hotspots with CRAP-style scoring |
| [`describe`](./describe/) | Turns bugs or features into pass/fail test cases before patching |
| [`dev-sanity`](./dev-sanity/) | Checks local dev ecosystem health across services and logs |
| [`divide-and-conquer`](./divide-and-conquer/) | Splits complex work into parallel, non-overlapping sub-agents |
| [`domain-planner`](./domain-planner/) | Plans multi-repo domain slices and implementation contracts |
| [`domain-reviewer`](./domain-reviewer/) | Audits live work against a plan and retires completed slices |
| [`domain-scaffolder`](./domain-scaffolder/) | Scaffolds backend or frontend domain code from accepted slice plans |
| [`mutate`](./mutate/) | Runs mutation testing and triages surviving mutants |
| [`prompt-reviewer`](./prompt-reviewer/) | Scores prompting quality from Claude/Codex session history |
| [`reproduce`](./reproduce/) | Uses a command-first QA ladder before handing testing back |
| [`skill-issue`](./skill-issue/) | Creates, validates, improves, and packages skills |

### Ops, Recon, And Operator Tools

| Skill | What it does |
| --- | --- |
| [`deploy`](./deploy/) | Handles deployment, rollback, health checks, and infra debugging |
| [`dropbox-ocr`](./dropbox-ocr/) | OCRs invoices and receipts, then matches them to QuickBooks work |
| [`erac-portal-api`](./erac-portal-api/) | Authenticates to the ERAC legacy portal for API recon and replay |
| [`spaps-register`](./spaps-register/) | Registers new apps with SPAPS and wires credentials |
| [`ssh-info`](./ssh-info/) | Returns server connection info and targeted live-status checks |

### Tooling, Docs, And Creative Systems

| Skill | What it does |
| --- | --- |
| [`clawgs`](./clawgs/) | Extracts structured data from Claude/Codex logs and emits thought updates |
| [`remotion`](./remotion/) | Encodes practical Remotion guidance for React video work |
| [`research-paper`](./research-paper/) | Produces dense research pages plus social companions |
| [`session-to-tweet`](./session-to-tweet/) | Converts technical work sessions into high-signal X posts |
| [`throngterm-sprite`](./throngterm-sprite/) | Generates thronglet sprite packs from master pixel assets |
| [`trend-to-content`](./trend-to-content/) | Turns search and social trends into research, PSEO, and video ideas |

### OpenClaw And Unclawg

| Skill | What it does |
| --- | --- |
| [`openclaw-client-bootstrap`](./openclaw-client-bootstrap/) | Builds production-ready OpenClaw client kits with runtime assets |
| [`openclaw-docs-audit`](./openclaw-docs-audit/) | Audits bootstrap docs and config against upstream OpenClaw changes |
| [`unclawg-admin`](./unclawg-admin/) | Handles waitlist triage and account-management actions |
| [`unclawg-internet`](./unclawg-internet/) | Runs onboarding, device auth, and setup for OpenClaw agents |
| [`unclawg-discover`](./unclawg-discover/) | Finds leads and social-listening candidates |
| [`unclawg-feed`](./unclawg-feed/) | Generates replies and submits approval requests |
| [`unclawg-respond`](./unclawg-respond/) | Processes revision feedback and fulfills approved edits |

## Installation

### 1. Install The Full Tracked Catalog

This installs the tracked top-level directories that contain `SKILL.md`.

```bash
npx skills add build000r/skills --all
```

### 2. Install Only What You Need

```bash
npx skills add build000r/skills -s describe
npx skills add build000r/skills -s reproduce
npx skills add build000r/skills -s commit
```

### 3. Install By Lane

Engineering core:

```bash
for skill in \
  crap \
  mutate \
  ask-cascade \
  commit \
  describe \
  divide-and-conquer \
  domain-planner \
  domain-reviewer \
  domain-scaffolder \
  reproduce \
  skill-issue
do
  npx skills add build000r/skills -s "$skill"
done
```

Legacy wrapper aliases `domain-scaffolder-backend` and
`domain-scaffolder-frontend` remain installable for compatibility, but new
setups should install only `domain-scaffolder`.

Tooling:

```bash
for skill in \
  clawgs \
  codex-tmux \
  prompt-reviewer 
do
  npx skills add build000r/skills -s "$skill"
done
```

OpenClaw loop:

```bash
for skill in \
  unclawg-internet \
  unclawg-discover \
  unclawg-feed \
  unclawg-respond
do
  npx skills add build000r/skills -s "$skill"
done
```

### 4. Use A Local Checkout During Development

```bash
git clone git@github.com:build000r/skills.git
cd skills
./scripts/link-skills.sh
```

That script creates or updates symlinks in:

- `~/.claude/skills/`
- `~/.codex/skills/`

You can also point it at a checkout explicitly:

```bash
./scripts/link-skills.sh /path/to/skills
```

### 5. Use Prebuilt `.skill` Artifacts For Selected Skills

The repo currently ships packaged artifacts for some skills in `dist/`.

```bash
ls dist/*.skill
```

Do not assume every skill has a packaged artifact. The repo is mixed-mode.

## Quick Start

1. Install one or two skills you will genuinely use.
2. Clone the repo if you want local inspection, editing, or symlinked dev.
3. Run [`scripts/link-skills.sh`](./scripts/link-skills.sh) to point Claude and Codex at your checkout.
4. If a skill needs private context, copy its `references/mode-template.md` into `modes/*.local.md` and fill it in.
5. If a skill ships app code, run its own install and check scripts after linking.

## Command Reference

| Command | What it does | Example |
| --- | --- | --- |
| `npx skills add build000r/skills --all` | Installs the full tracked catalog | `npx skills add build000r/skills --all` |
| `npx skills add build000r/skills -s <skill>` | Installs one named skill | `npx skills add build000r/skills -s describe` |
| `./scripts/link-skills.sh` | Symlinks top-level skills from a local checkout into Claude and Codex | `./scripts/link-skills.sh` |
| `./scripts/link-skills.sh /path/to/skills` | Links a different checkout path explicitly | `./scripts/link-skills.sh ~/repos/skills` |
| `./clawgs/scripts/install.sh` | Installs the `clawgs` helper app | `./clawgs/scripts/install.sh` |
| `./clawgs/scripts/check.sh` | Verifies the `clawgs` install | `./clawgs/scripts/check.sh` |
| `ls dist/*.skill` | Shows packaged artifacts for selected skills | `ls dist/*.skill` |

## Configuration

There is no single repo-wide config file.

Most skills are usable immediately after install. The ones that need private
local knowledge use gitignored mode overlays in `modes/`, usually created from a
skill-specific `references/mode-template.md`.

Example mode overlay:

```md
# modes/my-portfolio.local.md

# Example private overlay for skills that need repo or portfolio context.
# Start from the relevant references/mode-template.md for the skill you are using.

## Detection

cwd_match: ~/repos

## Scan Roots

- ~/repos

## Repo Ownership

- product-repo
  - path: ~/repos/product-repo
  - owns: auth, billing, admin tooling
  - prefer_for: API changes, schema changes

- marketing-repo
  - path: ~/repos/marketing-repo
  - owns: landing pages, website copy
  - prefer_for: presentation and content work

## Shared Rules

- Prefer the skills repo for reusable agent workflows and developer tooling.
- Keep private domains, credentials, server notes, and customer context here.
```

Skills that commonly rely on mode templates include:

- [`build-vs-clone`](./build-vs-clone/)
- [`deploy`](./deploy/)
- [`domain-planner`](./domain-planner/)
- [`domain-reviewer`](./domain-reviewer/)
- [`domain-scaffolder`](./domain-scaffolder/)
- [`prompt-reviewer`](./prompt-reviewer/)
- [`research-paper`](./research-paper/)
- [`trend-to-content`](./trend-to-content/)
- [`unclawg-discover`](./unclawg-discover/)

## Architecture

```text
                    GitHub repo / local checkout
                               |
                               v
        +--------------------------------------------------+
        | top-level skill directories with SKILL.md        |
        | ask-cascade/  describe/  deploy/  clawgs/  ...   |
        +--------------------------------------------------+
             |                |                 |
             |                |                 |
             v                v                 v
      references/        scripts/         assets/ or app code
   templates, docs    install/check      runtime kits, Rust app,
   examples, guides   helpers, glue      embedded child skills
             \                |                 /
              \               |                /
               +--------------+----------------+
                              |
                              v
                    agent runtime loads skill
                  (Claude Code / Codex / Cursor)
                              |
                              v
                 optional local overlay from modes/*.local.md
                              |
                              v
               repeatable workflow with repo-specific context
```

## Repo Patterns

### Standard Skill Pack

```text
some-skill/
├── SKILL.md
├── references/
├── scripts/
└── assets/
```

### App-Backed Skill

[`clawgs`](./clawgs/) is the clearest example:

```text
clawgs/
├── SKILL.md
├── Cargo.toml
├── src/
├── tests/
└── scripts/
```

### Asset And Runtime Bundle

[`openclaw-client-bootstrap`](./openclaw-client-bootstrap/) ships deployable
assets plus embedded child skills:

```text
openclaw-client-bootstrap/
├── SKILL.md
├── references/
├── scripts/
└── assets/
    ├── client-kit/
    ├── runtime-skills/
    └── instances/
```

## Troubleshooting

### `npx skills add build000r/skills --all` did not install everything I see locally

`--all` installs the tracked top-level directories that contain `SKILL.md`. It
does not promise every private, gitignored, or incubating directory from a
developer's local checkout.

### `link-skills.sh` says a destination already exists and is not a symlink

The script intentionally skips non-symlink targets in `~/.claude/skills/` or
`~/.codex/skills/`. Rename or remove the existing directory, then run the
script again.

### A skill asks for a mode file I do not have

Check whether that skill ships `references/mode-template.md`. Copy it into
`modes/*.local.md`, keep it gitignored, and fill in your private context.

### An app-backed skill still does not work after linking

Linking only exposes the skill directory to the agent. App-backed skills may
need their own install and verification steps. For `clawgs`, run:

```bash
./clawgs/scripts/install.sh
./clawgs/scripts/check.sh
```

### I want packaged artifacts for every skill

That is not the current shape of the repo. `dist/` contains selected `.skill`
artifacts only. Use the GitHub install path or local symlink workflow for the
rest.

## Limitations

- This is a mixed-mode monorepo, not a polished package registry or docs site.
- Some skills depend on private local context, so they are incomplete until you add a mode overlay.
- Some skills are personal or operator-heavy by design and may not generalize cleanly outside the author's environment.
- Not every skill has a packaged `.skill` build in `dist/`.
- Licensing is skill-specific rather than centrally normalized.
- The contribution policy is intentionally closed.

## FAQ

### Is this a prompt library?

Not really. The repo is closer to an operations catalog for agents. Many skills
ship references, scripts, assets, mode templates, or app code next to the core
instructions.

### What is the install surface?

The default public install surface is the set of tracked top-level directories
that contain `SKILL.md`.

### Do I need the whole repo?

No. Installing a few skills you actually use is usually better than installing
everything blindly.

### When should I clone the repo locally?

Clone it when you want to inspect instructions, edit a skill, symlink a local
checkout into Claude/Codex, or work on app-backed helpers.

### What are mode files for?

They hold private local context such as repo maps, domains, deployment notes,
or portfolio rules that should not live in the tracked public skill files.

### Are these skills only for Codex?

No. The repo is meant to work with Claude Code, Codex, Cursor, and similar
agentic environments.

### Is there one license for the whole repo?

No. Check each skill directory's frontmatter plus any bundled `LICENSE` or
`LICENSE.txt` file before redistributing or packaging it.

## About Contributions

> *About Contributions:* Please don't take this the wrong way, but I do not accept outside contributions for any of my projects. I simply don't have the mental bandwidth to review anything, and it's my name on the thing, so I'm responsible for any problems it causes; thus, the risk-reward is highly asymmetric from my perspective. I'd also have to worry about other "stakeholders," which seems unwise for tools I mostly make for myself for free. Feel free to submit issues, and even PRs if you want to illustrate a proposed fix, but know I won't merge them directly. Instead, I'll have Claude or Codex review submissions via `gh` and independently decide whether and how to address them. Bug reports in particular are welcome. Sorry if this offends, but I want to avoid wasted time and hurt feelings. I understand this isn't in sync with the prevailing open-source ethos that seeks community contributions, but it's the only way I can move at this velocity and keep my sanity.

## License

Licensing is skill-specific. Check each skill directory's frontmatter and any
bundled `LICENSE` or `LICENSE.txt` file before redistributing, packaging, or
embedding a skill elsewhere.
