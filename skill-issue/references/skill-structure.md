# Skill Structure & Progressive Disclosure

## Table of Contents

- [What Skills Provide](#what-skills-provide)
- [Anatomy of a Skill](#anatomy-of-a-skill)
  - [SKILL.md](#skillmd)
  - [Scripts](#scripts-scripts)
  - [References](#references-references)
  - [Assets](#assets-assets)
  - [What NOT to Include](#what-not-to-include)
- [Progressive Disclosure](#progressive-disclosure)
  - [Three-Level Loading](#three-level-loading)
  - [Pattern 1: High-Level Guide with References](#pattern-1-high-level-guide-with-references)
  - [Pattern 2: Domain-Specific Organization](#pattern-2-domain-specific-organization)
  - [Pattern 3: Conditional Details](#pattern-3-conditional-details)

---

## What Skills Provide

1. **Specialized workflows** — Multi-step procedures for specific domains
2. **Tool integrations** — Instructions for working with specific file formats or APIs
3. **Domain expertise** — Company-specific knowledge, schemas, business logic
4. **Bundled resources** — Scripts, references, and assets for complex and repetitive tasks

## Anatomy of a Skill

```
skill-name/
├── SKILL.md (required)
│   ├── YAML frontmatter (name, description)
│   └── Markdown instructions
└── Bundled Resources (optional)
    ├── scripts/          - Executable code (Python/Bash/etc.)
    ├── references/       - Documentation loaded into context as needed
    └── assets/           - Files used in output (templates, icons, fonts)
```

### SKILL.md

- **Frontmatter** (YAML): Required `name` and `description`, plus optional `license`, `allowed-tools`, `metadata`. The `name` and `description` determine when the skill triggers — be clear and comprehensive.
- **Body** (Markdown): Instructions and guidance. Only loaded AFTER the skill triggers.

### Scripts (`scripts/`)

Executable code for tasks requiring deterministic reliability or that are repeatedly rewritten.

- **When to include**: Same code rewritten repeatedly, or deterministic reliability needed
- **Example**: `scripts/rotate_pdf.py` for PDF rotation
- **Benefits**: Token efficient, deterministic, can execute without loading into context
- Scripts may still need to be read by the agent for patching or environment-specific adjustments

### References (`references/`)

Documentation loaded as needed into context.

- **When to include**: Documentation the agent should reference while working
- **Examples**: Database schemas, API docs, domain knowledge, company policies
- **Benefits**: Keeps SKILL.md lean, loaded only when needed
- If files are large (>10k words), include grep search patterns in SKILL.md
- **Avoid duplication**: Information lives in SKILL.md OR references, not both. Prefer references for detailed information.

### Assets (`assets/`)

Files used in output, not loaded into context.

- **When to include**: Files that will be used in the final output
- **Examples**: `assets/logo.png`, `assets/slides.pptx`, `assets/frontend-template/`
- **Benefits**: Separates output resources from documentation

### What NOT to Include

Only include files that directly support the skill's functionality. Do NOT create:

- INSTALLATION_GUIDE.md, QUICK_REFERENCE.md, CHANGELOG.md, or similar auxiliary files
- Setup/testing procedures, user-facing documentation, or process history

**Exception**: README.md for GitHub publishing (for human discoverability, not for the agent). See `references/publishing.md`.

## Progressive Disclosure

### Three-Level Loading

1. **Metadata (name + description)** — Always in context (~100 words)
2. **SKILL.md body** — When skill triggers (<5k words)
3. **Bundled resources** — As needed (unlimited; scripts can execute without reading into context)

Keep SKILL.md under 500 lines. Split to reference files when approaching this limit. Reference them clearly from SKILL.md so the agent knows they exist and when to use them.

**Key principle:** When a skill supports multiple variations, keep only the core workflow and selection guidance in SKILL.md. Move variant-specific details into reference files.

### Pattern 1: High-Level Guide with References

```markdown
# PDF Processing

## Quick start
Extract text with pdfplumber:
[code example]

## Advanced features
- **Form filling**: See [FORMS.md](FORMS.md) for complete guide
- **API reference**: See [REFERENCE.md](REFERENCE.md) for all methods
```

The agent loads FORMS.md or REFERENCE.md only when needed.

### Pattern 2: Domain-Specific Organization

Organize by domain to avoid loading irrelevant context:

```
bigquery-skill/
├── SKILL.md (overview and navigation)
└── references/
    ├── finance.md
    ├── sales.md
    └── product.md
```

When a user asks about sales, the agent only reads `sales.md`. Same pattern works for framework variants (aws.md, gcp.md, azure.md).

### Pattern 3: Conditional Details

```markdown
# DOCX Processing

## Creating documents
Use docx-js for new documents. See [DOCX-JS.md](DOCX-JS.md).

## Editing documents
For simple edits, modify the XML directly.
**For tracked changes**: See [REDLINING.md](REDLINING.md)
```

**Guidelines:**
- Keep references one level deep from SKILL.md (no nested references)
- For files >100 lines, include a table of contents at the top
