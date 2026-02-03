---
name: skill-issue
description: Create, update, and package Claude Code skills. Use when asked to "create a skill", "make a skill", "new skill", "skill template", "design a skill", "build a skill", or when working with SKILL.md files, frontmatter, bundled resources (scripts/, references/, assets/), or .skill packaging. Also triggers on "how do I make a skill", "skill best practices", "skill structure", or requests to extend Claude's capabilities with reusable workflows.
license: Complete terms in LICENSE.txt
---

# Skill Creator

Create effective Claude Code skills: modular packages that extend Claude with specialized workflows, domain expertise, and reusable tools.

## Core Principles

### Concise is Key

The context window is a public good. Only add context Claude doesn't already have. Challenge each piece: "Does this paragraph justify its token cost?"

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

The skill is for another Claude instance. Include non-obvious procedural knowledge, domain-specific details, and reusable assets.

#### Consult Design Pattern Guides

- **Multi-step processes**: Read references/workflows.md
- **Consistent output formats**: Read references/output-patterns.md
- **Complete example**: Read references/example-minimal-skill.md
- **Publishing**: Read references/publishing.md

#### Handling API Keys and Secrets

Never hardcode API keys. Use `$ENV_VAR` references in curl/script templates and document the required variable.

Users should set keys in their shell profile (`~/.zshrc` or `~/.bash_profile`):

```bash
export MY_API_KEY="your-key-here"
```

**Known issue:** The `env` field in `~/.claude/settings.json` does not reliably expand variables in Bash tool commands. Shell profile exports work correctly.

In SKILL.md, document requirements like:

```markdown
## Prerequisites
Add to `~/.zshrc`: `export MY_API_KEY="your-key"`
```

#### Local Development with Symlinks

Store skill source in a version-controlled repo, symlink into `~/.claude/skills/` for Claude to discover:

```bash
cp -r ~/.claude/skills/my-skill ~/repos/skills/my-skill
rm -r ~/.claude/skills/my-skill
ln -s ~/repos/skills/my-skill ~/.claude/skills/my-skill
```

The marketplace plugin version (if installed) takes precedence over `~/.claude/skills/` — use a different name to avoid conflicts.

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

### Step 6: Iterate

1. Use the skill on real tasks
2. Notice struggles or inefficiencies
3. Update SKILL.md or bundled resources
4. Test again

### Step 7: Publish (Optional)

1. Create a public GitHub repo
2. Add a README.md (for humans, not Claude)
3. Add a `.zip` package: `zip -r skill-name.zip SKILL.md scripts/ references/`
4. Promote to drive downloads (downloads = ranking)

**Read `references/publishing.md`** for the complete checklist and promotion strategies.
