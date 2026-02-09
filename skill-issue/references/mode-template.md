# Mode Template

Copy this file to `modes/{project-name}.md` and fill in each section. Delete any sections that don't apply.

---

# {Org/Project Name} Mode

## Detection

```
cwd_match: ~/repos/{project-name}
```

## Skill Standards

Naming and structural conventions for skills in this org:

- **Naming pattern**: `{domain}-{action}` (e.g., `pdf-editor`, `deploy-debug`)
- **Required SKILL.md sections**: frontmatter, description, workflow, output
- **Max SKILL.md lines**: 500 (recommended) | custom limit
- **Required frontmatter fields**: name, description, license
- **Required bundled resources**: scripts/ (at least one script) | references/ | none
- **License**: MIT | Apache-2.0 | proprietary | custom (see LICENSE.txt)
- **Allowed tools**: list any tool restrictions in frontmatter

## Publishing Target

Where skills are distributed:

- **Primary**: GitHub org (`github.com/{org}/skills/`) | internal registry | marketplace
- **Package format**: `.skill` (zip) | git submodule | symlink
- **README required**: yes (for public repos) | no (internal only)
- **Changelog required**: yes | no
- **Version scheme**: semver | date-based | none

## Testing

How to validate skills in this org's environment:

- **Validation command**: `python3 scripts/quick_validate.py {skill-path}`
- **Package command**: `python3 scripts/package_skill.py {skill-path}`
- **Manual test**: describe the smoke test (e.g., "invoke the skill with a sample prompt and verify output")
- **CI integration**: GitHub Actions | none
- **Test skill directory**: `~/.claude/skills/` | custom path for testing

## Bundled Resources

Standard scripts, references, or assets every skill in this org should include:

- **Standard scripts**: list any shared utility scripts (e.g., `scripts/common_utils.py`)
- **Standard references**: list any shared reference docs
- **Asset templates**: list any standard asset files (logos, configs)
- **Shared config**: path to org-wide skill config if applicable

## Review Process

How skills are reviewed before publishing:

- **Reviewer**: self | team lead | peer review | automated only
- **Approval workflow**: PR review | Slack approval | none
- **Checklist**: run quick_validate.py, test with real prompt, check line count, verify frontmatter
- **Iteration cadence**: after every real usage | weekly | on publish
