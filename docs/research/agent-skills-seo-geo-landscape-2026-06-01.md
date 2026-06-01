# Agent Skills SEO/GEO Landscape - 2026-06-01

## Scope And Evidence Notes

This report covers search, GEO, and content architecture for the "agent skills / Claude Code workflows / coding-agent plugins" niche. It intentionally complements, rather than repeats, `agent-skill-ecosystem-distribution-2026-06-01.md`: this document is about discoverability, query intent, SERP ownership, AI-citation readiness, and content planning.

Evidence quality:

- Primary sources used: Anthropic Claude Code docs and plugin marketplace pages, OpenAI Codex skills/plugin docs, Agent Skills specification, GitHub repo/topic/search surfaces, Cursor docs, VS Code and Raycast marketplace docs.
- Secondary sources used only where they are themselves ranking/citation competitors: ClaudSkills, SkillMD.ai, skills.md, Firecrawl's SKILL.md explainer, Reddit result surfaces where visible in SERPs.
- Banned sources not used: Backlinko, Ahrefs blog, Neil Patel, Semrush blog.
- Keyword-volume tools were not accessible in this environment. All volume tiers below are marked `low-evidence / inferred` unless tied to public evidence such as GitHub topic counts, repository stars, official marketplace install counts, or repeated SERP density.
- Direct ChatGPT, Perplexity, and Google AI Overview sampling was not accessible from this environment. The GEO table therefore marks those cells `not tested` and substitutes accessible web-search/SERP evidence.

## Executive Summary

The niche is real, but it is still early and fragmented. Exact search volume is not available here, yet multiple current public signals point to rising demand: Anthropic now has first-party Claude Code skills and plugin docs; OpenAI has first-party Codex skills and plugin docs; the GitHub `agent-skills` topic reports thousands of matching public repositories; Anthropic's plugin gallery exposes five-digit install counts for multiple developer plugins; and third-party registries already rank for `SKILL.md`, `Claude Code skills`, and "agent skills" queries. Sources: [Claude Code skills](https://code.claude.com/docs/en/skills), [OpenAI Codex skills](https://developers.openai.com/codex/skills), [GitHub agent-skills topic](https://github.com/topics/agent-skills), [Anthropic plugins gallery](https://claude.com/plugins).

The head terms are hard to displace because official docs and official marketplaces own them. The winnable space is not "what are Claude Code skills?" in isolation; it is workflow-category and implementation-intent content: "Claude Code skills for code review", "skills vs hooks vs plugins", "how to install SKILL.md from GitHub", "best Claude Code workflows for release validation", "Codex skills vs Claude skills", and "agent skills for [engineering task]". These terms have lower direct authority competition and clearer product fit for `build000r/skills`.

Recommendation: invest in GitHub README/repo SEO immediately and build a small docs/content surface only if it is generated from real skill metadata plus hand-written category summaries. Do not launch hundreds of token-swapped pages. The best first move is 5 high-intent content pieces plus README metadata changes, then measure with GitHub referrals, Google Search Console if a docs site is launched, and AI/search citation checks.

Confidence: medium. The demand signal is visible, but exact keyword volume and AI-citation behavior remain unmeasured.

## Keyword Cluster Map

| Cluster | Keyword examples | Volume tier | Intent | SERP difficulty | Current #1 owner / dominant owner | Content gap | Confidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1. Claude Code skills head term | `Claude Code skills`, `Claude skills Claude Code`, `Claude Code SKILL.md` | Medium, low-evidence / inferred from official docs, registries, Reddit density | Informational, navigational | High | Anthropic help/docs. Search showed Anthropic help/docs plus skills registries and community catalogs. | Ecosystem examples and "which skills should I install for real engineering workflows" are underserved. | Medium |
| 2. Claude Code plugins and marketplace | `Claude Code plugins`, `Claude Code plugin marketplace`, `Claude plugin install` | Medium, low-evidence / inferred from Anthropic marketplace install counts | Navigational, transactional | High | Anthropic plugin gallery and Claude Code docs. Anthropic gallery shows many plugins with 10k-80k+ installs. | Third-party plugin catalogs exist, but few explain skills vs plugins vs workflows from a GitHub OSS repo angle. | High for competition; medium for volume |
| 3. How to create/add skills | `how to add skills to Claude Code`, `create Claude Code skill`, `install Claude Code skills` | Low-to-medium, low-evidence / inferred from SERP tutorials and official docs | How-to, implementation | Medium-high | Anthropic docs/help; secondary how-to sites also rank. | A concise GitHub-first install path with `npx skills add build000r/skills` and validation examples could compete below official docs. | Medium |
| 4. SKILL.md / Agent Skills standard | `SKILL.md`, `agent skills specification`, `Agent Skills standard`, `SKILL.md files` | Medium, low-evidence / inferred from current registries and academic/security discussion | Informational, comparative | Medium | Agent Skills spec, skills.md, SkillMD.ai, Firecrawl, GitHub. | The standard is explained, but "production-grade workflow authoring patterns" and "trustworthy skill examples" are weakly covered. | Medium |
| 5. `npx skills add` and GitHub install | `npx skills add`, `install agent skills from GitHub`, `skills add GitHub repo` | Low, low-evidence / inferred from sparse SERPs and Reddit | Transactional, implementation | Low-medium | Skills CLI docs, niche package/project docs, Reddit posts. | Highly winnable if README repeats exact install commands, examples, and package manager variants. | Medium |
| 6. Reusable coding-agent workflows | `coding agent workflows`, `Claude Code workflows`, `agent workflow library`, `reusable agent prompts for developers` | Medium, low-evidence / inferred from Reddit density and official workflow docs | Informational, solution-seeking | Medium | Anthropic workflow docs/help, Reddit, community guides. | "Workflow" SERPs are noisy; a concrete library of repeatable workflows can differentiate from prompt-tip posts. | Medium |
| 7. Skills vs hooks vs plugins vs rules | `Claude Code skills vs hooks`, `Claude Code plugins vs skills`, `Cursor rules vs skills`, `CLAUDE.md vs skills` | Low-to-medium, low-evidence / inferred from SERP discussions | Comparative, implementation | Medium | Official Claude plugin reference, Cursor rules docs, Reddit. | A single cross-agent decision table could rank and earn citations because official docs are split by product. | Medium-high |
| 8. Code review / security skills | `Claude Code code review skill`, `AI code review skill Claude Code`, `Claude Code security skill`, `agent skill code review` | Low-to-medium, low-evidence / inferred from marketplace installs and SERP tutorials | Transactional, workflow-specific | Medium-high | Anthropic code review/product pages, marketplace plugins, Crystl/community skill pages. | A proof-backed "code review skill stack" with exact SKILL.md structure, validation loop, and safety caveats is winnable. | Medium |
| 9. Codex skills / cross-agent skills | `Codex skills`, `OpenAI Codex skills`, `Codex plugins skills`, `Claude Code skills in Codex` | Low-to-medium, low-evidence / inferred from OpenAI docs, `openai/skills` stars | Navigational, comparative | High for head term, medium for comparison | OpenAI docs and `openai/skills`. `gh repo view` on 2026-06-01 showed `openai/skills` at 21,045 stars. | "Portable skills for Claude Code, Codex, Cursor" is under-explained outside platform docs. | Medium |
| 10. Skill registries and marketplaces | `agent skills registry`, `Claude skills marketplace`, `SKILL.md marketplace`, `best Claude Code skills` | Medium, low-evidence / inferred from many indexed registries and catalogs | Commercial investigation, browsing | Medium | ClaudSkills, SkillMD.ai, skills.md, Anthropic plugin gallery, awesome lists. | Existing registries are broad; a curated engineering-workflow catalog with trust/proof metadata can stand out. | Medium |

## SERP Landscape Summary

Official documentation owns the highest-authority head terms. Anthropic's skills page says skills extend Claude by adding `SKILL.md` instructions and that Claude Code skills follow the open Agent Skills standard; it also documents personal, project, and plugin skill locations. OpenAI's Codex docs describe skills as packages of instructions, resources, and optional scripts that build on the same open standard. Sources: [Claude Code skills](https://code.claude.com/docs/en/skills), [OpenAI Codex skills](https://developers.openai.com/codex/skills), [Agent Skills specification](https://agentskills.io/specification).

Plugin and marketplace queries are even more authority-heavy. Anthropic's plugin gallery is a live, crawlable marketplace with visible install counts, and the Claude Code docs define marketplaces as git-backed catalogs with `marketplace.json`, GitHub shorthand sources, sparse checkout support, and validation rules. Codex plugin docs similarly define `.codex-plugin/plugin.json` with optional `skills/`, hooks, MCP config, apps/connectors, and assets. Sources: [Anthropic plugins gallery](https://claude.com/plugins), [Claude plugin marketplaces](https://code.claude.com/docs/en/plugin-marketplaces), [Codex build plugins](https://developers.openai.com/codex/plugins/build).

The non-official SERP is already forming around registries and catalogs, not isolated blog posts. ClaudSkills positions itself as an open `SKILL.md` registry and reports 76,000+ skills; SkillMD.ai reports 111,000+ agent skills; skills.md positions itself as an API-based skill marketplace with 200+ skills and cross-agent support. These numbers are vendor claims, but their pages are ranking and therefore matter as search competitors. Sources: [ClaudSkills](https://claudskills.com/), [SkillMD.ai](https://skillmd.ai/), [skills.md](https://skills.md/).

GitHub itself is a major discovery layer. On 2026-06-01, GitHub's `agent-skills` topic page reported 5,860 public matching repositories and showed high-star, keyword-rich repos that include terms such as `agent-skills`, `claude-code`, `codex-cli`, `cursor`, `workflows`, and `claude-code-plugins`. Separately, `gh search repos "Claude Code plugins"` surfaced `anthropics/claude-plugins-official`, `jeremylongshore/claude-code-plugins-plus-skills`, `ccplugins/awesome-claude-code-plugins`, and other active catalogs. Source: [GitHub agent-skills topic](https://github.com/topics/agent-skills).

Anthropic's official authority is not an insurmountable barrier for `build000r/skills`, but it makes a generic "Claude Code skills" page a weak primary bet. The opportunity is to become the practical implementation source that official docs do not try to be: an opinionated engineering workflow catalog with runnable install commands, trust notes, task-specific pages, compatibility notes for Claude/Codex/Cursor, and examples showing before/after agent behavior.

## GEO / AI-Citation Opportunity

Direct AI-search sampling status: ChatGPT browsing/citation surfaces, Perplexity answer pages, and Google AI Overview UI were not accessible from this environment. Cells below are marked `not tested`; the substitute evidence column records accessible SERP/search sources collected on 2026-06-01.

| Query string | ChatGPT top citation | Perplexity top citation | Google AI Overview source | Accessible SERP / source evidence | Gap for `build000r/skills` | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| `Claude Code skills library` | not tested | not tested | not tested | Anthropic docs, ClaudSkills, SkillsMD, GitHub catalogs surfaced. | Publish a concise "Claude Code skills library for engineering workflows" page with install commands and a category map. | Medium |
| `best Claude Code workflows` | not tested | not tested | not tested | Reddit/community discussions and Anthropic workflow docs dominate accessible results. | Create a proof-oriented "best workflows" page with concrete Beads/review/release/security workflows, not vague tips. | Medium |
| `how to add skills to Claude Code` | not tested | not tested | not tested | Anthropic docs/help and secondary how-to pages appear. | Win long-tail with exact GitHub install, local symlink, validation, and troubleshooting snippets. | Medium-high |
| `reusable agent prompts for developers` | not tested | not tested | not tested | Results are broad and not tightly owned by official docs. | Reframe as "reusable agent workflows, not prompt snippets" and point to concrete `SKILL.md` examples. | Medium |
| `Claude Code skills vs hooks vs plugins` | not tested | not tested | not tested | Claude plugin reference, Cursor rules docs, Reddit discussions, hook guides surfaced. | Build a comparison matrix across Claude skills, plugins, hooks, `CLAUDE.md`, Codex skills, and Cursor rules. | Medium-high |
| `Codex skills vs Claude Code skills` | not tested | not tested | not tested | OpenAI Codex docs, Claude docs, Agent Skills spec, `openai/skills` repo. | A cross-platform portability guide can cite both official docs and show one skill working across runtimes. | Medium |
| `Claude Code code review skill` | not tested | not tested | not tested | Marketplace plugins, Crystl skill page, Reddit examples, Anthropic code review coverage. | Publish a code-review skill page with bug-finding rubric, validation loop, and safety boundaries. | Medium |
| `agent skills registry` | not tested | not tested | not tested | GitHub topic page, ClaudSkills, SkillMD.ai, skills.md, Agent Skills spec. | Do not compete as a general registry; compete as a curated engineering-workflow library with trust/proof metadata. | Medium |

AI-citation hypothesis: answer engines are likely to cite official docs for definitions and install mechanics, then cite structured registries or GitHub repos for examples. `build000r/skills` can become citable if pages expose dated, source-backed, self-contained passages: definition, compatibility table, install command, category list, trust model, and "last verified" metadata.

## Programmatic SEO Viability

Recommendation: go, but only as a constrained, quality-gated program. Confidence: medium.

The viable shape is not a broad mass of generated pages. The viable shape is 10-20 category pages generated from real repo metadata and then hand-edited for unique value: `code-review`, `release-validation`, `deep-research`, `commit`, `deployment`, `frontend-ui`, `seo`, `skill-authoring`, `multi-agent-coordination`, and `ops`. Each page should contain the exact install command, included skills, who it is for, when not to use it, trust/safety notes, a short runnable example, and links to source files. This mirrors marketplace/category patterns that already rank: Anthropic plugin listings with install counts, ClaudSkills category/tag pages, SkillMD.ai category pages, GitHub topic pages, VS Code Marketplace pages, and Raycast extension store pages. Sources: [Anthropic plugins gallery](https://claude.com/plugins), [ClaudSkills](https://claudskills.com/), [SkillMD.ai](https://skillmd.ai/), [GitHub agent-skills topic](https://github.com/topics/agent-skills), [VS Code Extension Marketplace docs](https://code.visualstudio.com/docs/configure/extensions/extension-marketplace), [Raycast extensions manual](https://manual.raycast.com/extensions).

The no-go version is "one page per skill" with thin token-swapped copy. That would compete poorly with GitHub source pages and could create low-value scaled pages. If a standalone docs site is built, launch with a small number of canonical category pages and a generated index, not a page for every skill until there is evidence that category pages are getting impressions.

Go/no-go: **Go for README SEO plus a small category-page pilot; no-go for broad one-page-per-skill PSEO until GSC or GitHub referral data proves demand.** Confidence: medium because exact search volume and AI-citation data are still missing.

## Competitor Content Gap Map

| Competitor/source | Topics covered | Traffic/engagement evidence | Gap the skills repo could fill | Confidence |
| --- | --- | --- | --- | --- |
| Anthropic Claude Code docs | Skills, plugins, hooks, marketplaces, install locations, validation | Official docs rank for head terms; plugin gallery shows five-digit install counts on many developer plugins. | Practical OSS workflow catalog and cross-skill engineering recipes. | High |
| Anthropic plugin gallery | Discoverable plugins for Claude Code/Cowork, verified badges, installs | Public install counts include many 10k+ and some 50k+ developer-oriented plugins. | Not a neutral cross-agent skill library; `build000r/skills` can target Claude + Codex + Cursor portability. | High |
| OpenAI Codex docs and `openai/skills` | Codex skills, plugins, official skill catalog | `gh repo view` on 2026-06-01 showed `openai/skills` at 21,045 stars. | Codex docs do not explain Claude/Cursor portability or GitHub-first workflow catalogs. | High |
| Agent Skills spec | Standard structure, progressive disclosure, validation | Spec is authoritative and cited by official Claude/OpenAI docs. | Does not provide opinionated GTM, workflow-category, or engineering-use-case pages. | High |
| ClaudSkills | Massive searchable Claude skills catalog, tags, categories, install app | Site claims 76,633+ skills and 7,522+ adjacent tools. | Broad catalog, not curated proof-first engineering workflows. | Medium |
| SkillMD.ai | Discover/create SKILL.md files, rankings, categories | Site claims 111,469+ skills and category counts. | Generated/broad marketplace feel; opportunity for trusted, source-controlled workflow docs. | Medium |
| skills.md | API-based remote skills marketplace | Site claims 200+ skills, 17 categories, multi-agent support. | Remote API model differs from git-native OSS install; content gap around local trust and inspectability. | Medium |
| GitHub topic/search results | Repos tagged `agent-skills`, `claude-code`, `codex-cli`, `workflows` | GitHub topic page reported 5,860 matching public repos on 2026-06-01; high-star topic owners dominate. | `build000r/skills` has weak metadata right now: `gh repo view` showed 4 stars, 0 watchers, no topics, and description "a very particular set of skills". | High |
| wshobson/agents | Multi-harness plugin marketplace across Claude Code, Codex CLI, Cursor, OpenCode, Gemini | `gh repo view` on 2026-06-01 showed 36,231 stars and rich repo topics. | Competes on breadth; `build000r/skills` can compete on operator-grade workflows and proof discipline. | Medium-high |
| Cursor rules docs | Reusable `.cursor/rules` instructions for Agent | Official Cursor docs rank for "rules" and adjacent reusable-instruction queries. | Crosswalk page: Cursor rules vs Agent Skills vs Claude skills vs Codex skills. | Medium |

## GitHub SEO Recommendations

1. Replace the repo description with a keyword-rich but honest phrase: `Reusable Agent Skills (SKILL.md) for Claude Code, Codex, Cursor, and engineering workflows`. Rationale: current GitHub description is memorable but does not match discovery terms.
2. Add GitHub topics: `agent-skills`, `claude-code`, `codex-cli`, `cursor`, `skill-md`, `ai-agents`, `coding-agents`, `developer-tools`, `workflows`, `claude-code-skills`, `codex-skills`. Rationale: GitHub topic pages are ranking and topic metadata is visible in GitHub search.
3. Add a first-screen keyword block in README with exact query phrases: `Claude Code skills`, `Codex skills`, `SKILL.md`, `agent workflow library`, `npx skills add build000r/skills`, and `coding agent workflows`. Rationale: the README currently explains the repo well but underuses the exact search vocabulary.
4. Add a README "Skill Categories" table that maps categories to top skills and target use cases: code review, release validation, deep research, commits, deployment, UI, SEO/GEO, multi-agent coordination, skill authoring. Rationale: category text creates indexable anchors for long-tail workflow queries.
5. Add a "Compatibility" table for Claude Code, Codex, Cursor, and raw filesystem installs, with links to official docs. Rationale: cross-agent portability is a content gap and likely AI-citation hook.
6. Add a "Trust And Safety" section: inspect before install, skill-specific licensing, no hidden generated artifacts, supporting files, validation commands, and how to audit `SKILL.md`. Rationale: security/trust is appearing in SERPs and will matter for citations.
7. Add exact install snippets for `--all`, one skill, and one category bundle near the top and repeat them in category pages. Rationale: `npx skills add` is a low-competition transactional query.
8. Add badges or compact status lines for catalog count, supported agents, and last verified date. Rationale: AI citation systems prefer current, extractable facts.
9. Add a generated `docs/research/` index from this and the Round-1 report. Rationale: research pages are currently discoverable only by path, not as a coherent public evidence surface.

## Prioritized Content Calendar

| Rank | Title/topic | Format | Target keyword cluster | Expected traffic/citation potential | Effort | Confidence |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | Claude Code Skills vs Plugins vs Hooks vs CLAUDE.md: Which Extension Surface To Use | Docs/blog comparison matrix | Cluster 7 | High citation potential because official docs are split and Reddit questions are active. | Medium | Medium-high |
| 2 | A Practical Claude Code Skills Library For Engineering Workflows | README section plus docs landing page | Clusters 1, 6, 10 | Medium traffic, high product fit; strongest repo-homepage match. | Low-medium | Medium |
| 3 | How To Install Agent Skills From GitHub With `npx skills add` | How-to doc with troubleshooting | Clusters 3, 5 | Lower volume but high intent and low competition. | Low | Medium |
| 4 | Portable Agent Skills: One `SKILL.md` Workflow Across Claude Code, Codex, And Cursor | Technical guide | Clusters 4, 7, 9 | Medium citation potential; strong cross-platform gap. | Medium | Medium |
| 5 | Claude Code Skills For Code Review: A Proof-First Workflow Stack | Category landing page plus example skill walkthrough | Clusters 6, 8 | Medium traffic; high conversion to repo installs because code review is a concrete pain point. | Medium | Medium |

## Source Log

- Anthropic Claude Code skills: <https://code.claude.com/docs/en/skills>
- Anthropic Claude Code plugins reference: <https://code.claude.com/docs/en/plugins-reference>
- Anthropic Claude Code plugin marketplaces: <https://code.claude.com/docs/en/plugin-marketplaces>
- Anthropic plugins gallery: <https://claude.com/plugins>
- OpenAI Codex skills: <https://developers.openai.com/codex/skills>
- OpenAI Codex plugins: <https://developers.openai.com/codex/plugins>
- OpenAI Codex build plugins: <https://developers.openai.com/codex/plugins/build>
- OpenAI skills catalog: <https://github.com/openai/skills>
- Agent Skills specification: <https://agentskills.io/specification>
- GitHub `agent-skills` topic: <https://github.com/topics/agent-skills>
- GitHub `build000r/skills`: <https://github.com/build000r/skills>
- GitHub `wshobson/agents`: <https://github.com/wshobson/agents>
- ClaudSkills: <https://claudskills.com/>
- SkillMD.ai: <https://skillmd.ai/>
- skills.md: <https://skills.md/>
- Firecrawl SKILL.md explainer: <https://www.firecrawl.dev/blog/agent-skills>
- Cursor rules docs: <https://docs.cursor.com/context/rules-for-ai>
- VS Code Extension Marketplace docs: <https://code.visualstudio.com/docs/configure/extensions/extension-marketplace>
- Raycast extensions manual: <https://manual.raycast.com/extensions>
- Raycast store preparation docs: <https://developers.raycast.com/basics/prepare-an-extension-for-store>

## Residual Evidence Gaps

- Exact keyword volume was not available. Search-volume tiers should be refreshed with Google Keyword Planner, Search Console, or a rank-tracker export before large content investment.
- ChatGPT, Perplexity, and Google AI Overview citation surfaces were not directly testable from this environment. The GEO table uses accessible web/SERP substitutes and should be refreshed by a logged-in browser run or manual sampling.
- GitHub search and topic pages are dynamic. Star counts, topic counts, and rankings are snapshots from 2026-06-01 and may drift quickly.
- Anthropic plugin install counts are public on the gallery, but exact methodology and update cadence are not documented on the page.
