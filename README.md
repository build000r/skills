# AI Coding Agent Skills

A collection of open-source skills for AI coding agents — compatible with [Claude Code](https://claude.ai/claude-code), [Codex](https://openai.com/index/introducing-codex/), [Cursor](https://www.cursor.com/), and more.

https://github.com/user-attachments/assets/531fe967-ed44-4863-80be-c21e36b9331a

## Skills

| Skill | Description |
|-------|-------------|
| [divide-and-conquer](./divide-and-conquer/) | Decompose complex tasks into independent, parallel sub-agents with zero conflicts |
| [prompt-reviewer](./prompt-reviewer/) | Review and score your AI prompting quality on a 23-point scale |
| [trend-to-content](./trend-to-content/) | Transform social media trends into SEO pages, videos, and copy at scale |
| [research-paper](./research-paper/) | Generate dense, academic research papers on any topic with project-specific modes |
| [skill-issue](./skill-issue/) | Create, update, and package skills for AI coding agents |
| [openclaw-client-bootstrap](./openclaw-client-bootstrap/) | Generate a production OpenClaw client kit for DigitalOcean + Tailscale + Telegram with read-only governance |

## Utility Skills

Small, composable primitives called by other skills.

| Skill | Description |
|-------|-------------|
| [codex-tmux](./codex-tmux/) | Run Codex in a persistent tmux session with signal-based completion |
| [ask-cascade](./ask-cascade/) | Hierarchical, dependency-aware question ordering |
| [commit](./commit/) | Batch-commit working changes with clean messages |

## Install

```bash
# Install all skills
npx skills add build000r/skills --all
```

Or install individually:

```bash
npx skills add build000r/skills -s divide-and-conquer
npx skills add build000r/skills -s prompt-reviewer
npx skills add build000r/skills -s trend-to-content
npx skills add build000r/skills -s research-paper
npx skills add build000r/skills -s skill-issue
npx skills add build000r/skills -s openclaw-client-bootstrap
npx skills add build000r/skills -s codex-tmux
npx skills add build000r/skills -s ask-cascade
npx skills add build000r/skills -s commit
```

## Quick Usage

Yes. You can just tell your AI to use the skill directly, for example:

```text
Use $openclaw-client-bootstrap to create a new client kit for DigitalOcean + Tailscale + Telegram.
Set it to read-only by default and approval-gated for writes.
```

## Local Development (Claude + Codex)

For local iteration, symlink each skill directory into both agent homes:

```bash
./scripts/link-skills.sh
```

This creates/updates links in:

- `~/.claude/skills/`
- `~/.codex/skills/`

## License

MIT
