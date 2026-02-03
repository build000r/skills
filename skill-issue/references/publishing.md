# Publishing Skills for Maximum Reach

Guide for publishing skills to marketplaces like [skills.sh](https://skills.sh) and maximizing downloads.

## How Ranking Works

Skills.sh ranks by **install count** via anonymous telemetry from `npx skills add`. More installs = higher ranking. This creates a flywheel: visible skills get more installs.

## Naming for Discoverability

### Patterns from Top Skills

| Pattern | Example | Why it works |
|---------|---------|--------------|
| `[domain]-[action]-er` | `prompt-reviewer` | Clear function, `-er` suffix common |
| `[tool]-best-practices` | `react-best-practices` | Searchable, implies authority |
| `[format]-[action]` | `pdf-editor` | File type + verb |
| `[platform]-[capability]` | `vercel-deploy` | Platform association |

### Naming Rules

- **Lowercase with hyphens**: `my-skill-name`
- **Two searchable keywords**: Users search "prompt" + "review" not "huml"
- **Avoid clever acronyms**: `prompt-reviewer` beats `huml` (Human-User-Model Liaison)
- **Match mental models**: `code-review` not `source-analyzer`

### Test Your Name

Ask: "If someone needed this, what would they search for?"

## GitHub Repository Structure

For skills.sh listing, you need a **public GitHub repo**:

```
my-skill/
├── SKILL.md              # Required
├── scripts/              # Your scripts
├── references/           # Your references
├── my-skill.zip          # Required for skills.sh
├── README.md             # Required for GitHub (see below)
├── LICENSE               # Recommended (MIT, Apache 2.0)
└── .gitignore            # Exclude TODO.md, __pycache__, etc.
```

### README.md for GitHub

**Exception to the "no README" rule**: GitHub repos need a README for visibility. This is for humans browsing GitHub, not for Claude.

```markdown
# skill-name

One-line description matching your SKILL.md description.

## Install

\`\`\`bash
npx skills add username/skill-name
\`\`\`

## What it does

- Bullet 1
- Bullet 2
- Bullet 3

## Example

\`\`\`
> /skill-name do the thing
[example output]
\`\`\`

## License

MIT
```

### The .zip Package

Skills.sh requires a `.zip` file in your repo root:

```bash
cd my-skill
zip -r my-skill.zip SKILL.md scripts/ references/
# Don't include README.md, .gitignore, TODO.md in the zip
```

## What Makes Skills Go Viral

Based on [Vercel's 20k installs in 6 hours](https://jpcaparas.medium.com/vercel-just-launched-skills-sh-and-it-already-has-20k-installs-c07e6da7e29e):

### 1. Solve Real Pain Points

Top skills address universal frustrations:
- `react-best-practices` - "Stop making the same React mistakes"
- `web-design-guidelines` - "100+ UI/UX rules in one place"

### 2. Have Executable Scripts

From [HN discussion](https://news.ycombinator.com/item?id=46697908):
> "If your 'skill' doesn't come with scripts/executables, it's just a fancy slash command."

Scripts differentiate your skill from a prompt.

### 3. Cross-Platform Compatibility

Skills that work across multiple tools get more installs:
- Claude Code
- GitHub Copilot
- Cursor
- VS Code
- OpenCode

Test on multiple platforms if possible.

### 4. Promotion Drives Downloads

Downloads drive ranking. Ranking drives visibility. Visibility drives downloads.

**Promotion checklist:**
- [ ] Tweet/X with demo GIF
- [ ] Post in Claude Discord
- [ ] Submit to [awesome-claude-skills](https://github.com/travisvn/awesome-claude-skills)
- [ ] Post on relevant subreddits
- [ ] Write a blog post / tutorial
- [ ] Make a YouTube demo

## Pre-Publish Checklist

### Required
- [ ] Searchable name (two keywords)
- [ ] Public GitHub repo
- [ ] `.zip` package in repo root
- [ ] README.md with install command
- [ ] LICENSE file

### Recommended
- [ ] Demo GIF in README
- [ ] At least one executable script
- [ ] Tested on Claude Code
- [ ] Clear trigger phrases in description

### Promotion
- [ ] Social media announcement
- [ ] Community submissions
- [ ] Blog/tutorial content

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Clever/acronym name | Use searchable keywords |
| No scripts, just docs | Add executable automation |
| No .zip file | Package for skills.sh |
| No README | Add for GitHub visibility |
| No promotion | Downloads don't happen automatically |
