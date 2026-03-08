# AI Agent Skills

An open-source monorepo of reusable skills for agentic workflows.
It includes engineering workflows, creator/media systems, OpenClaw runtime
skills, and a few skill-backed local apps.

Compatible with [Claude Code](https://claude.ai/claude-code),
[Codex](https://openai.com/index/introducing-codex/),
[Cursor](https://www.cursor.com/), and similar tools.

https://github.com/user-attachments/assets/531fe967-ed44-4863-80be-c21e36b9331a

## What This Repo Actually Contains

This repo is not just a folder of prompt files. It is a skill monorepo with
several different patterns:

- top-level installable skills (`*/SKILL.md`)
- helper scripts and reference docs bundled with those skills
- skill-backed local apps, like `clawgs/`
- asset/runtime bundles, like `openclaw-client-bootstrap/`

The public install surface is the set of tracked top-level directories that
contain `SKILL.md`. If you are browsing a local checkout, you may also see
gitignored or incubating skill directories. `npx skills add build000r/skills --all`
installs the tracked top-level catalog, not every directory in a developer's
local checkout.

At the repo level:

- `_shared/` contains shared snippets reused by multiple skills
- `scripts/` contains repo-wide helper scripts
- `dist/` contains packaged `.skill` build artifacts

## Skill Lanes

### Engineering And Agent Workflow

| Skill | What it is for |
|------|-----------------|
| [ask-cascade](./ask-cascade/) | High-level-to-detail question ordering before asking the user |
| [codex-tmux](./codex-tmux/) | Long-running Codex work in persistent tmux sessions |
| [commit](./commit/) | Batch commits with clean, high-level messages |
| [describe](./describe/) | Turn a bug or feature conversation into concrete test cases before patching |
| [divide-and-conquer](./divide-and-conquer/) | Split complex work into non-overlapping parallel agents |
| [domain-planner](./domain-planner/) | Multi-repo slice planning, contracts, and implementation orchestration |
| [domain-reviewer](./domain-reviewer/) | Audit live work against plans and retire completed slices cleanly |
| [domain-scaffolder-backend](./domain-scaffolder-backend/) | Tests-first backend scaffolding from an approved plan |
| [domain-scaffolder-frontend](./domain-scaffolder-frontend/) | Frontend scaffolding from an approved plan plus project UI patterns |
| [prompt-reviewer](./prompt-reviewer/) | Score prompting quality from Claude/Codex session history |
| [reproduce](./reproduce/) | Command-first verification and QA ladder before handing testing back |
| [skill-issue](./skill-issue/) | Create, iterate, validate, and package skills themselves |

### Tooling, Media, And Creative Systems

| Skill | What it is for |
|------|-----------------|
| [clawgs](./clawgs/) | Transcript extraction and thought-emission daemon for Claude/Codex logs |
| [remotion](./remotion/) | Remotion best-practices reference pack for video work in React |
| [research-paper](./research-paper/) | Dense research-paper style pages plus companion X article drafts |
| [throngterm-sprite](./throngterm-sprite/) | Generate repo-specific thronglet sprite packs |
| [trend-to-content](./trend-to-content/) | Trend research, PSEO generation, and video/copy workflows |

### OpenClaw And Unclawg Operator Skills

| Skill | What it is for |
|------|-----------------|
| [openclaw-client-bootstrap](./openclaw-client-bootstrap/) | Build deployable OpenClaw client kits with Tailscale, Telegram, SPAPS, and embedded runtime skills |
| [openclaw-docs-audit](./openclaw-docs-audit/) | Diff bootstrap/docs config against upstream OpenClaw releases |

### Unclawg Runtime And Marketing Loop

These four skills are the approval-gated discovery-to-reply loop:

`onboard -> discover -> feed approvals -> respond to revisions`

| Skill | What it is for |
|------|-----------------|
| [unclawg-internet](./unclawg-internet/) | Onboarding, machine-key setup, soul interview, and discovery mode creation |
| [unclawg-discover](./unclawg-discover/) | Social listening and lead discovery across multiple platforms |
| [unclawg-feed](./unclawg-feed/) | Generate proposed replies and submit approval cards |
| [unclawg-respond](./unclawg-respond/) | Process revision requests and fulfill approved edits |

## Install Patterns

Use `--all` only if you want the full tracked catalog.
If you want an "all of this lane" install, use one of the bundles below.
The examples use the top-level directory name after `-s`.

### Everything In This Repo

```bash
npx skills add build000r/skills --all
```

### Engineering Core

```bash
for skill in \
  ask-cascade \
  commit \
  describe \
  divide-and-conquer \
  domain-planner \
  domain-reviewer \
  domain-scaffolder-backend \
  domain-scaffolder-frontend \
  reproduce \
  skill-issue
do
  npx skills add build000r/skills -s "$skill"
done
```

### Engineering Tooling

```bash
for skill in \
  clawgs \
  codex-tmux \
  prompt-reviewer
do
  npx skills add build000r/skills -s "$skill"
done
```

### Unclawg Marketing / Runtime Loop

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

### OpenClaw Operator / Bootstrap

```bash
for skill in \
  openclaw-client-bootstrap \
  openclaw-docs-audit
do
  npx skills add build000r/skills -s "$skill"
done
```

### Content / Media

```bash
for skill in \
  remotion \
  research-paper \
  throngterm-sprite \
  trend-to-content
do
  npx skills add build000r/skills -s "$skill"
done
```

You can mix bundles as needed. There is no repo-defined category-aware `--all`
flag today, so the bundle loops above are the clearest "all skills in this lane"
pattern.

## Repo Patterns

### 1. Standard Skill Pack

Most skills look roughly like this:

```text
domain-planner/
├── SKILL.md
├── references/
├── scripts/
└── assets/templates/
```

The skill instructions live in `SKILL.md`. Reusable commands go in `scripts/`.
Reference material and templates live beside them.

### 2. App-Backed Skill

`clawgs` is the clearest example of a skill that also ships a real local tool:

```text
clawgs/
├── SKILL.md
├── scripts/install.sh
├── scripts/check.sh
├── references/
├── Cargo.toml
├── src/
└── tests/
```

In this pattern, the skill tells the agent when and how to use the tool, while
the app handles deterministic work such as parsing, protocol handling, or a
daemon lifecycle. Use this pattern when plain prompt instructions are not enough.

### 3. Asset And Runtime Bundle Skill

`openclaw-client-bootstrap` is a skill that ships deployable assets and embedded
child skills:

```text
openclaw-client-bootstrap/
├── SKILL.md
├── scripts/
├── references/
└── assets/
    ├── client-kit/
    └── instances/0_claw/custom-skills/
```

The top-level skill handles authoring, review, deployment, and sync. The
embedded custom skills are runtime-safe copies or variants that get shipped with
the generated instance kit.

### 4. Mode-Overlay Skill

Several skills are designed as public generic instructions plus local private
overlays in `modes/`. Good examples include:

- `domain-planner`
- `prompt-reviewer`
- `research-paper`
- `unclawg-discover`

Tracked files stay reusable. Project-specific paths, domains, and private config
stay in gitignored mode files.

## Local Development

For local iteration, symlink the top-level skill directories in your checkout
into Claude and Codex:

```bash
./scripts/link-skills.sh
```

This creates or updates links in:

- `~/.claude/skills/`
- `~/.codex/skills/`

It links top-level skill directories only. Embedded runtime custom skills stay
inside their parent asset bundles. If your local checkout includes private or
incubating top-level skills, those get linked too.

If a skill is app-backed, do its own install/verify step after linking. For
example, `clawgs/` includes `scripts/install.sh` and `scripts/check.sh`.

## Licensing

Licensing is skill-specific. Check each skill directory's frontmatter and any
bundled `LICENSE` or `LICENSE.txt` file before redistributing or packaging it.
