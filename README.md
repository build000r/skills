# AI Agent Skills

An open-source collection of reusable skills for agentic workflows.
This repo includes coding-focused skills plus supporting skills for planning,
operations, and content workflows.

Compatible with [Claude Code](https://claude.ai/claude-code),
[Codex](https://openai.com/index/introducing-codex/),
[Cursor](https://www.cursor.com/), and similar tools.

https://github.com/user-attachments/assets/531fe967-ed44-4863-80be-c21e36b9331a

## Skill Catalog

| Skill | Category | Description |
|-------|----------|-------------|
| [divide-and-conquer](./divide-and-conquer/) | Engineering | Split complex implementation work into parallel, non-overlapping sub-agents |
| [domain-planner](./domain-planner/) | Engineering | Create multi-repo feature plans with a structured 6-phase process |
| [domain-reviewer](./domain-reviewer/) | Engineering | Audit domain slices against plan and retire completed slices cleanly |
| [domain-scaffolder-backend](./domain-scaffolder-backend/) | Engineering | Scaffold backend domain code from plans using a tests-first flow |
| [domain-scaffolder-frontend](./domain-scaffolder-frontend/) | Engineering | Scaffold frontend domain code from plans using project UI patterns |
| [skill-issue](./skill-issue/) | Engineering | Create, iterate, validate, and package reusable skills |
| [reproduce](./reproduce/) | Engineering | Enforce command-first verification and keep browser DevTools as a strict last resort |
| [codex-tmux](./codex-tmux/) | Utility | Run Codex in persistent tmux sessions with completion signaling |
| [ask-cascade](./ask-cascade/) | Utility | Enforce high-level-to-detail question ordering for user decisions |
| [commit](./commit/) | Utility | Batch and commit working changes with clean conventional messages |
| [prompt-reviewer](./prompt-reviewer/) | Analysis | Score prompting quality and track performance trends over time |
| [trend-to-content](./trend-to-content/) | Content | Turn trends into SEO pages, video scripts, and copy workflows |
| [research-paper](./research-paper/) | Content | Generate dense, research-paper style writing from a topic |
| [openclaw-client-bootstrap](./openclaw-client-bootstrap/) | Ops | Bootstrap production OpenClaw client kits with guarded defaults |
| [unclawg-internet](./unclawg-internet/) | OpenClaw | Self-service onboarding — CLI device auth, agent machine keys, env block |
| [unclawg-discover](./unclawg-discover/) | OpenClaw | Multi-platform social listening and customer discovery |
| [unclawg-feed](./unclawg-feed/) | OpenClaw | Generate proposed replies and submit approval cards to the portal |
| [unclawg-respond](./unclawg-respond/) | OpenClaw | Poll revision requests, generate edits, fulfill via API |

## If You Only Want Coding Skills

Install this subset first:

```bash
npx skills add build000r/skills -s divide-and-conquer
npx skills add build000r/skills -s domain-planner
npx skills add build000r/skills -s domain-reviewer
npx skills add build000r/skills -s domain-scaffolder-backend
npx skills add build000r/skills -s domain-scaffolder-frontend
npx skills add build000r/skills -s skill-issue
npx skills add build000r/skills -s reproduce
npx skills add build000r/skills -s codex-tmux
npx skills add build000r/skills -s ask-cascade
npx skills add build000r/skills -s commit
```

## Install Everything

```bash
# Install all skills (coding + utility + content + ops)
npx skills add build000r/skills --all
```

Or install individually:

```bash
npx skills add build000r/skills -s divide-and-conquer
npx skills add build000r/skills -s prompt-reviewer
npx skills add build000r/skills -s trend-to-content
npx skills add build000r/skills -s research-paper
npx skills add build000r/skills -s skill-issue
npx skills add build000r/skills -s reproduce
npx skills add build000r/skills -s openclaw-client-bootstrap
npx skills add build000r/skills -s unclawg-internet
npx skills add build000r/skills -s unclawg-discover
npx skills add build000r/skills -s unclawg-feed
npx skills add build000r/skills -s unclawg-respond
npx skills add build000r/skills -s domain-planner
npx skills add build000r/skills -s domain-reviewer
npx skills add build000r/skills -s domain-scaffolder-backend
npx skills add build000r/skills -s domain-scaffolder-frontend
npx skills add build000r/skills -s codex-tmux
npx skills add build000r/skills -s ask-cascade
npx skills add build000r/skills -s commit
```

## Quick Usage

Tell your agent to use a skill directly:

```text
Use $divide-and-conquer to split this feature into parallel implementation agents.
Then run a review pass and give me one commit per logical unit.
```

```text
Use $trend-to-content in research mode to find trends in the AI coding niche
and return 10 content ideas ranked by distribution potential.
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
