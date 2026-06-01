# Agent skill ecosystem distribution research - 2026-06-01

## Executive Summary

- Agent workflow standardization is converging at the authoring layer around `SKILL.md`-style directories, not around a single hosted registry. Anthropic Claude Code and OpenAI Codex both document skills as directories containing `SKILL.md` plus optional scripts, references, and assets, and both point to the open Agent Skills standard. Sources: [Claude Code skills](https://code.claude.com/docs/en/skills), [OpenAI Codex skills](https://developers.openai.com/codex/skills), [Agent Skills specification](https://agentskills.io/specification).
- Distribution is converging around plugin marketplaces and git-backed catalogs. Anthropic uses `.claude-plugin/marketplace.json`; Codex uses `.codex-plugin/plugin.json` plus marketplace sources; both support bundling skills with MCP configuration and other components. Sources: [Claude Code plugin marketplaces](https://code.claude.com/docs/en/plugin-marketplaces), [OpenAI Codex plugins](https://developers.openai.com/codex/plugins), [Codex build plugins](https://developers.openai.com/codex/plugins/build).
- MCP is winning the tool/data integration layer, but it is not a direct substitute for `SKILL.md` instruction packs. MCP standardizes resources, prompts, and executable tools over JSON-RPC; Agent Skills standardize agent instructions and progressive disclosure. Sources: [MCP introduction](https://modelcontextprotocol.io/docs/getting-started/intro), [MCP specification](https://modelcontextprotocol.io/specification/2025-06-18), [Agent Skills specification](https://agentskills.io/specification).
- For `build000r/skills`, the highest-leverage move is compatibility rather than replacement: add standards-compliant `name` fields and optional metadata to each `SKILL.md`, add a generated `.claude-plugin/marketplace.json` and `.codex-plugin` compatibility layer, and keep `npx skills add build000r/skills` as the git-native power-user install path. This is an inference from the documented platform formats.
- Public install counts are mostly unavailable. The strongest adoption signals available from allowed sources are official platform documentation, GitHub star counts, curated official marketplaces, and high-engagement developer discussions such as Hacker News. Source gap: no authoritative public install/download counts found for Claude Code plugins, Codex plugins, or most SKILL.md repos.

## Per-Ecosystem Entries

### Anthropic Agent Skills

- **What it is and status:** Claude Code documents skills as reusable capabilities that Claude can invoke when relevant or by explicit `/skill-name`. Custom commands have been merged into skills, and Claude Code states its skills follow the Agent Skills open standard while adding Claude-specific features. Source: [Claude Code skills](https://code.claude.com/docs/en/skills).
- **Format/schema:** A skill is a directory with `SKILL.md` as the required entrypoint; `SKILL.md` uses YAML frontmatter and Markdown instructions. Claude supports personal, project, enterprise, and plugin skill locations, with optional supporting files such as scripts and references. Source: [Claude Code skills](https://code.claude.com/docs/en/skills).
- **Install mechanism and registry:** Local/project skills live under `~/.claude/skills/<skill-name>/SKILL.md` or `.claude/skills/<skill-name>/SKILL.md`. Shareable bundles can be distributed as Claude Code plugins, with `.claude-plugin/plugin.json` and marketplace catalogs under `.claude-plugin/marketplace.json`; users add a marketplace and install plugins from it. Sources: [Claude Code plugins](https://code.claude.com/docs/en/plugins), [Claude Code plugin marketplaces](https://code.claude.com/docs/en/plugin-marketplaces).
- **Adoption signals:** Anthropic maintains `anthropics/claude-plugins-official`, an official plugin directory with `29,032` GitHub stars and a 2026-06-01 push at time of collection (`gh repo view`, 2026-06-01). The Agent Skills spec repo, `agentskills/agentskills`, had `19,738` stars. Developer discussion on Hacker News shows active debate about skill invocation semantics and cross-client support. Sources: [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official), [agentskills/agentskills](https://github.com/agentskills/agentskills), [HN: Agent Skills](https://news.ycombinator.com/item?id=46871173).
- **Compatibility with git-native markdown skills:** compatible. A `build000r/skills` directory can map directly to Agent Skills if each `SKILL.md` satisfies the required frontmatter fields; plugin marketplace generation is an additive wrapper.
- **Confidence:** high for format and install mechanics; medium for adoption because public install counts were not found.

### Anthropic MCP

- **What it is and status:** MCP is an open protocol for connecting AI apps to external systems, including data sources, tools, and workflows. The official docs say MCP is supported across Claude, ChatGPT, VS Code, Cursor, MCPJam, and other clients. Source: [MCP introduction](https://modelcontextprotocol.io/docs/getting-started/intro).
- **Format/schema:** MCP uses JSON-RPC 2.0 and defines hosts, clients, and servers. Server features include resources, prompts, and tools; clients can expose roots, sampling, and elicitation. Source: [MCP specification](https://modelcontextprotocol.io/specification/2025-06-18).
- **Install mechanism and registry:** The MCP Registry is a preview centralized metadata repository for public MCP servers. It stores `server.json` metadata pointing to package registries or remote servers, with DNS/GitHub namespace verification and a REST API for aggregators. Package types include npm, PyPI, NuGet, Docker/OCI, and MCPB. Sources: [MCP Registry](https://modelcontextprotocol.io/registry/about), [MCP package types](https://modelcontextprotocol.io/registry/package-types).
- **Adoption signals:** `modelcontextprotocol/servers` had `86,573` GitHub stars and `modelcontextprotocol/registry` had `6,882` stars at time of collection (`gh repo view`, 2026-06-01). The registry is backed by Anthropic, GitHub, PulseMCP, and Microsoft according to the registry docs. Sources: [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers), [modelcontextprotocol/registry](https://github.com/modelcontextprotocol/registry), [MCP Registry](https://modelcontextprotocol.io/registry/about).
- **Compatibility with git-native markdown skills:** compatible at a different layer. MCP servers can be referenced by skills or plugins, but MCP does not replace the instruction/procedure content in `SKILL.md`.
- **Confidence:** high for protocol/registry mechanics; medium for adoption details beyond GitHub stars and documented backing.

### OpenAI Codex Skills, Plugins, and GPT Successors

- **What it is and status:** OpenAI Codex now documents Agent Skills as a reusable workflow format available in the Codex CLI, IDE extension, and Codex app. Codex states skills build on the open Agent Skills standard and that plugins are the installable distribution unit for reusable skills and apps. Source: [OpenAI Codex skills](https://developers.openai.com/codex/skills).
- **Format/schema:** A Codex skill is a directory with required `SKILL.md` and optional `scripts/`, `references/`, `assets/`, and `agents/openai.yaml`; `SKILL.md` must include `name` and `description`. Source: [OpenAI Codex skills](https://developers.openai.com/codex/skills).
- **Install mechanism and registry:** Codex reads local skills from `.agents/skills`, `$HOME/.agents/skills`, `/etc/codex/skills`, and bundled system locations. For distribution, Codex plugins use `.codex-plugin/plugin.json`, can include `skills/`, hooks, `.app.json`, `.mcp.json`, and assets, and can be shared through marketplace sources added with `codex plugin marketplace add`. Sources: [OpenAI Codex skills](https://developers.openai.com/codex/skills), [OpenAI Codex plugins](https://developers.openai.com/codex/plugins), [Codex build plugins](https://developers.openai.com/codex/plugins/build).
- **GPT/plugin successor state:** ChatGPT GPTs remain a separate no-code, ChatGPT-native surface with instructions, uploaded knowledge, capabilities, apps, and actions; public GPTs can be published to the GPT Store when eligible. This is not the same install surface as Codex plugins or `SKILL.md`, and it does not expose a git-native skill package model in the cited help docs. Sources: [Creating GPTs](https://help.openai.com/en/articles/8554397-creating-a-gpt), [Sharing and publishing GPTs](https://help.openai.com/en/articles/8798878-building-and-publishing-a-gpt), [GPTs in ChatGPT](https://help.openai.com/en/articles/8554407).
- **Adoption signals:** `openai/openai-agents-python` had `26,825` stars and `openai/openai-agents-js` had `3,153` stars at time of collection, but these are agent frameworks rather than skill registries. Public Codex plugin install counts were not found in allowed sources. Sources: [openai/openai-agents-python](https://github.com/openai/openai-agents-python), [openai/openai-agents-js](https://github.com/openai/openai-agents-js).
- **Compatibility with git-native markdown skills:** compatible, with path differences. `build000r/skills` already matches the skill-directory model, but Codex expects `.agents/skills` for local discovery and `.codex-plugin/plugin.json` for distributed plugins.
- **Confidence:** high for documented Codex skill/plugin formats; medium for OpenAI ecosystem adoption because public install counts were not found.

### Google Gemini / ADK / Gemini Enterprise

- **What it is and status:** Google ADK is an open-source, code-first framework for building and deploying agents across Python, TypeScript, Go, Java, and Kotlin. Its docs include MCP tools and "Skills for Agents" as components. Source: [ADK](https://adk.dev/).
- **Format/schema:** ADK itself is code-first: agents are defined in language-specific code with instructions and tools. Separately, Gemini Enterprise Agent Platform has a preview Skill Registry where each skill is a self-contained package with structural instructions, executable code, and documentation. Source: [Gemini Enterprise Skill Registry](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/skill-registry).
- **Install mechanism and registry:** Gemini Enterprise Skill Registry is described as a secure, private, low-latency repository with `Skill` and `Skill revision` API entities for lifecycle and versioning. It points to a Google Cloud Skills repository for expected `SKILL.md` examples. Source: [Gemini Enterprise Skill Registry](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/skill-registry).
- **Adoption signals:** `google/adk-python` had `19,949` stars and `google/adk-js` had `1,189` stars at time of collection (`gh repo view`, 2026-06-01). These indicate ADK framework interest, not public skill registry usage. Sources: [google/adk-python](https://github.com/google/adk-python), [google/adk-js](https://github.com/google/adk-js).
- **Compatibility with git-native markdown skills:** unclear-to-compatible. Google Cloud Skill Registry uses the same high-level package idea and references `SKILL.md` examples, but it is a private managed cloud registry, not a public git-native install surface.
- **Confidence:** medium. The Skill Registry is explicitly preview/pre-GA, and public adoption metrics were not found.

### Open-Source Community

- **What it is and status:** The open-source ecosystem is split across MCP server catalogs, Claude/Codex plugin marketplaces, and raw `SKILL.md` libraries. GitHub remains the dominant discovery evidence source available publicly.
- **Format/schema:** Three formats dominate the researched repos: MCP server packages plus `server.json` metadata; plugin marketplace manifests such as `.claude-plugin/marketplace.json` and `.codex-plugin/plugin.json`; and raw `skills/<name>/SKILL.md` directories.
- **Install mechanism and registry:** Git clone, npm/PyPI/Docker-backed MCP installs, Claude/Codex marketplace source add commands, and local skill installers coexist. No single independent hosted marketplace was found with authoritative public install counts.
- **Adoption signals:** GitHub stars are high for MCP and official/plugin marketplace repos, lower for raw `SKILL.md` libraries. Hacker News and official docs show active discussion and support, but public marketplace install metrics are not available in the cited sources.
- **Compatibility with git-native markdown skills:** compatible, but raw repos need wrappers for each platform's marketplace format.
- **Confidence:** medium. GitHub metadata is current, but discovery is search-dependent and install data is missing.

## Open-Source Skill Repos Comparison

Star counts and pushed dates were collected with `gh repo view` on 2026-06-01. This table is sorted by stars among the scoped repos examined; it is not a claim that GitHub search has perfectly ranked the entire ecosystem.

| Repo | Stars | Last push | Format used | Install/distribution mechanism | Popular workflows |
| --- | ---: | --- | --- | --- | --- |
| [`modelcontextprotocol/servers`](https://github.com/modelcontextprotocol/servers) | 86,573 | 2026-05-30 | TypeScript npm workspaces for MCP servers; package metadata and MCP config, not `SKILL.md` | npm packages, local MCP config, MCP Registry metadata | Filesystem, memory, sequential thinking, and other tool/data servers |
| [`wshobson/agents`](https://github.com/wshobson/agents) | 36,228 | 2026-06-01 | Multi-harness plugin repo with `.claude-plugin`, `.codex-plugin`, `.cursor-plugin`, `.gemini`, `plugins/*/skills`, agents, and commands | Claude/Codex/Cursor/Gemini plugin marketplace-style installs | Development workflows, testing, docs, backend/frontend orchestration |
| [`anthropics/claude-plugins-official`](https://github.com/anthropics/claude-plugins-official) | 29,032 | 2026-06-01 | `.claude-plugin/marketplace.json` plus `plugins/*`; entries reference relative paths, git URLs, git subdirs, and vendor repos | Claude Code plugin marketplace | Security, design, productivity, databases, LSP, code review, setup |
| [`agentskills/agentskills`](https://github.com/agentskills/agentskills) | 19,738 | 2026-05-20 | Specification/docs for `SKILL.md` directories with YAML frontmatter | Spec/library, not a workflow marketplace | Standardization, validation, authoring guidance |
| [`TerminalSkills/skills`](https://github.com/TerminalSkills/skills) | 62 | 2026-05-21 | `skills/<name>/SKILL.md` directories | Raw GitHub skill library; install details not fully verified in this pass | Large catalog of API/framework/task skills |

Comparable baseline: [`build000r/skills`](https://github.com/build000r/skills) had `4` stars and a 2026-05-27 last push at time of collection. It uses top-level skill directories with `SKILL.md` plus optional references/scripts/assets and `npx skills add build000r/skills --all`.

## Format Convergence Assessment

**Position: converging at the authoring layer, fragmenting at the install layer.**

The strongest convergence is `SKILL.md`: Anthropic Claude Code, OpenAI Codex, and the Agent Skills spec all document a directory containing `SKILL.md` with YAML frontmatter, Markdown instructions, optional scripts/references/assets, and progressive disclosure. Sources: [Claude Code skills](https://code.claude.com/docs/en/skills), [Codex skills](https://developers.openai.com/codex/skills), [Agent Skills specification](https://agentskills.io/specification).

The install layer is still fragmented but moving toward git-backed plugin marketplaces. Anthropic and Codex have parallel but not identical plugin manifests and marketplace catalogs. Both can bundle skills and MCP configuration, but the manifest names and paths differ: `.claude-plugin/plugin.json` / `.claude-plugin/marketplace.json` for Claude and `.codex-plugin/plugin.json` for Codex. Sources: [Claude plugin marketplaces](https://code.claude.com/docs/en/plugin-marketplaces), [Codex build plugins](https://developers.openai.com/codex/plugins/build).

MCP is the clear convergence point for executable external tools and data access. It is not the same layer as skills because MCP servers expose resources, prompts, and tools over a protocol, while skills give an agent procedural instructions and local resources. A good compatibility strategy is to let a skill declare MCP dependencies in platform-specific plugin metadata rather than turn every skill into an MCP server. Sources: [MCP specification](https://modelcontextprotocol.io/specification/2025-06-18), [Codex skill optional metadata](https://developers.openai.com/codex/skills), [Claude plugin structure](https://code.claude.com/docs/en/plugins).

**Risk timeline for raw git-native `SKILL.md`:**

- Through 2026: low-to-medium risk. Raw git-native skills are compatible with both Anthropic and Codex authoring formats, and official docs still emphasize filesystem discovery.
- By 2027: medium risk that discoverability and trust shift toward official/curated plugin marketplaces, especially because Claude and Codex both define marketplace metadata and install browsers. Raw repos that do not generate marketplace manifests may be treated as power-user or local-only assets.
- Niche risk trigger: a dominant hosted marketplace begins enforcing review, install telemetry, security scanning, ratings, or identity verification in a way raw GitHub repos cannot match. No definitive evidence of one dominant cross-platform hosted marketplace was found.

## Distribution Channel Findings

- **GitHub remains the public discovery backbone.** The highest visible adoption signals are GitHub stars on MCP, plugin, and skill repos. Official docs themselves often point to GitHub-hosted marketplaces and package repositories.
- **Official plugin directories are gaining importance.** Claude Code documents marketplace catalogs with install/update flows; Codex has a plugin directory in the app and CLI, grouped by marketplace, with curated OpenAI plugins and workspace-shared entries. Sources: [Claude plugin marketplaces](https://code.claude.com/docs/en/plugin-marketplaces), [Codex plugins](https://developers.openai.com/codex/plugins).
- **Package registries matter for executable tools, not for instruction packs.** MCP Registry delegates actual code hosting to npm, PyPI, NuGet, Docker/OCI, or MCPB packages and stores metadata separately. Source: [MCP package types](https://modelcontextprotocol.io/registry/package-types).
- **GPT Store remains ChatGPT-native.** GPTs can be published publicly and can include instructions, knowledge, apps, and actions, but the cited OpenAI GPT docs do not expose a git-native reusable workflow package format. Sources: [GPTs in ChatGPT](https://help.openai.com/en/articles/8554407), [Sharing and publishing GPTs](https://help.openai.com/en/articles/8798878-building-and-publishing-a-gpt).
- **Community discussion is active but not settled.** HN discussions show developers debating invocation control, context budgets, cross-client skill support, and the relationship between skills, MCP, and plugins. Sources: [HN: Agent Skills](https://news.ycombinator.com/item?id=46871173), [HN: Skills are quietly becoming the unit of agent knowledge](https://news.ycombinator.com/item?id=47475832).

## Direct Implications for `build000r/skills`

1. Add or verify standards-compliant frontmatter in every public skill: `name`, `description`, optional `license`, optional `compatibility`, and names matching directories.
2. Generate Claude and Codex marketplace wrappers rather than replacing the current layout:
   - `.claude-plugin/marketplace.json` for a Claude marketplace catalog.
   - `.codex-plugin/plugin.json` wrappers or a Codex marketplace source that points at skill bundles.
3. Add optional metadata for MCP dependencies where skills require external servers. Keep MCP as a declared dependency/tool layer, not as the skill content format.
4. Keep `npx skills add build000r/skills --all` for git-native installs, but document it as one install surface among Claude, Codex, and raw filesystem layouts.
5. Track distribution health with three metrics: GitHub stars/watchers, marketplace manifest compatibility, and successful installs in Claude Code and Codex CLI. Public marketplace install counts were not found.

## Uncertainty Log

- Public install counts for Claude Code plugins, Codex plugins, raw Agent Skills repos, and MCP servers were not found in authoritative sources. Confidence: low, needs human review if private dashboards or marketplace telemetry exist.
- The exact number of public MCP Registry entries on 2026-06-01 was not established. The registry API is paginated and this pass did not complete a full count. Confidence: low.
- Google Gemini Enterprise Skill Registry is preview/pre-GA and appears enterprise/private, not a public ecosystem marketplace. Its long-term relation to open `SKILL.md` repos is unclear. Confidence: medium.
- GitHub search ranking is not exhaustive. The open-source comparison uses known official/high-signal repos plus scoped GitHub searches, with live metadata collected by `gh repo view`; it may miss similarly named repos outside the search terms. Confidence: medium.
- OpenAI GPT Store remains important for ChatGPT distribution, but it is not a direct replacement for Codex skills/plugins based on the cited docs. Confidence: medium.

## References

- Anthropic Claude Code skills: <https://code.claude.com/docs/en/skills>
- Anthropic Claude Code plugins: <https://code.claude.com/docs/en/plugins>
- Anthropic Claude Code plugin marketplaces: <https://code.claude.com/docs/en/plugin-marketplaces>
- Agent Skills specification: <https://agentskills.io/specification>
- OpenAI Codex skills: <https://developers.openai.com/codex/skills>
- OpenAI Codex plugins: <https://developers.openai.com/codex/plugins>
- OpenAI Codex build plugins: <https://developers.openai.com/codex/plugins/build>
- OpenAI GPTs in ChatGPT: <https://help.openai.com/en/articles/8554407>
- OpenAI creating GPTs: <https://help.openai.com/en/articles/8554397-creating-a-gpt>
- OpenAI sharing and publishing GPTs: <https://help.openai.com/en/articles/8798878-building-and-publishing-a-gpt>
- MCP introduction: <https://modelcontextprotocol.io/docs/getting-started/intro>
- MCP specification: <https://modelcontextprotocol.io/specification/2025-06-18>
- MCP Registry: <https://modelcontextprotocol.io/registry/about>
- MCP package types: <https://modelcontextprotocol.io/registry/package-types>
- Google ADK: <https://adk.dev/>
- Gemini Enterprise Skill Registry: <https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/skill-registry>
- GitHub `modelcontextprotocol/servers`: <https://github.com/modelcontextprotocol/servers>
- GitHub `modelcontextprotocol/registry`: <https://github.com/modelcontextprotocol/registry>
- GitHub `anthropics/claude-plugins-official`: <https://github.com/anthropics/claude-plugins-official>
- GitHub `agentskills/agentskills`: <https://github.com/agentskills/agentskills>
- GitHub `wshobson/agents`: <https://github.com/wshobson/agents>
- GitHub `TerminalSkills/skills`: <https://github.com/TerminalSkills/skills>
- GitHub `build000r/skills`: <https://github.com/build000r/skills>
- Hacker News "Agent Skills": <https://news.ycombinator.com/item?id=46871173>
- Hacker News "Skills are quietly becoming the unit of agent knowledge": <https://news.ycombinator.com/item?id=47475832>
