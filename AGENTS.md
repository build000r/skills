<!-- br-agent-instructions-v1 -->

---

## Beads Workflow Integration

This project uses [beads_rust](https://github.com/Dicklesworthstone/beads_rust) (`br`) for issue tracking. Issues are stored in `.beads/` and tracked in git.

### Essential Commands

```bash
# View ready issues (open, unblocked, not deferred)
br ready --json

# List and search
br list --status=open --json # All open issues
br show <id> --json          # Full issue details with dependencies
br search "keyword" --json   # Full-text search

# Create and update
br create "..." --description "..." --type task --priority 2 --json
br update <id> --claim --json
br update <id> -s blocked --notes "blocked reason" --json
br close <id> --reason "Completed" --suggest-next --json

# Sync with git
br sync --flush-only --json  # Export DB to JSONL
br status --json            # Check status
```

### Workflow Pattern

1. **Start**: Run `br ready --json` to find actionable work
2. **Claim**: Use `br update <id> --claim --json`
3. **Work**: Implement the task
4. **Complete**: Use `br close <id> --reason "..." --suggest-next --json`
5. **Sync**: Always run `br sync --flush-only --json` at session end

### Key Concepts

- **Dependencies**: Issues can block other issues. `br ready` shows only open, unblocked work.
- **Priority**: P0=critical, P1=high, P2=medium, P3=low, P4=backlog (use numbers 0-4, not words)
- **Types**: task, bug, feature, epic, chore, docs, question
- **Blocking**: `br dep add <issue> <depends-on>` to add dependencies

### Session Protocol

**Before ending any session, run this checklist:**

```bash
git status              # Check what changed
git add <files>         # Stage code changes
br sync --flush-only --json # Export beads changes to JSONL
git commit -m "..."     # Commit everything
git push                # Push to remote
```

### Best Practices

- Check `br ready --json` at session start to find available work
- Claim with `br update <id> --claim --json`; close with `br close --suggest-next --json`
- Create new issues with `br create` when you discover tasks
- Use descriptive titles and set appropriate priority/type
- Always sync before ending session

<!-- end-br-agent-instructions -->
