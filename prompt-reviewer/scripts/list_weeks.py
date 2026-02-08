#!/usr/bin/env python3
"""
List available session weeks across all providers and show backfill status.

Usage:
  list_weeks.py [--provider NAME] [--prompt]

Options:
  --provider NAME   Filter to specific provider (claude, codex, opencode)
  --prompt          Output full backfill prompt for next unreviewed week

Shows:
  - All weeks with session data (Claude, Codex, OpenCode)
  - Which weeks have already been reviewed (from history)
  - Next unreviewed week to backfill

Output is a markdown table ready for copy/paste or piping.
"""

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HISTORY_FILE = Path.home() / ".claude" / "prompt-review-history.jsonl"


def iso_week(dt: datetime) -> str:
    """Return ISO week string like '2025-W03'."""
    return f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"


def has_user_messages(jsonl_path: Path) -> bool:
    """Check if a Claude session file contains any user messages."""
    try:
        with open(jsonl_path, "r") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("type") == "user":
                        return True
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    return False


def scan_claude_weeks(claude_dir: Path) -> dict[str, int]:
    """Scan Claude Code sessions and count by week.

    Only counts files that actually contain user messages,
    not just file-history-snapshot entries.
    """
    weeks = defaultdict(int)
    projects_dir = claude_dir / "projects"
    if not projects_dir.exists():
        return weeks

    for session_file in projects_dir.rglob("*.jsonl"):
        if session_file.name.startswith("agent-"):
            continue
        try:
            # Only count if file has actual user messages
            if not has_user_messages(session_file):
                continue
            mtime = datetime.fromtimestamp(session_file.stat().st_mtime)
            weeks[iso_week(mtime)] += 1
        except Exception:
            continue
    return dict(weeks)


def scan_codex_weeks(codex_dir: Path) -> dict[str, int]:
    """Scan Codex sessions and count by week."""
    weeks = defaultdict(int)
    sessions_dir = codex_dir / "sessions"
    if not sessions_dir.exists():
        return weeks

    for session_file in sessions_dir.rglob("rollout-*.jsonl"):
        try:
            mtime = datetime.fromtimestamp(session_file.stat().st_mtime)
            weeks[iso_week(mtime)] += 1
        except Exception:
            continue
    return dict(weeks)


def scan_opencode_weeks(opencode_state_dir: Path) -> dict[str, int]:
    """Scan OpenCode prompt history and count by week.

    OpenCode stores all prompts in a flat prompt-history.jsonl without timestamps.
    We use the file's mtime to determine which week the data belongs to.
    Returns at most one week (the file's mtime week) with prompt count.
    """
    weeks = defaultdict(int)
    history_file = opencode_state_dir / "prompt-history.jsonl"
    if not history_file.exists():
        return weeks

    try:
        mtime = datetime.fromtimestamp(history_file.stat().st_mtime)
        week = iso_week(mtime)

        # Count prompts in the file
        prompt_count = 0
        with open(history_file) as f:
            for line in f:
                if line.strip():
                    try:
                        entry = json.loads(line)
                        if entry.get("input", "").strip():
                            prompt_count += 1
                    except json.JSONDecodeError:
                        continue

        if prompt_count > 0:
            weeks[week] = prompt_count
    except Exception:
        pass

    return dict(weeks)


def load_reviewed_weeks(provider_filter: str | None = None) -> dict[str, list[str]]:
    """Load weeks that have been reviewed from history file."""
    reviewed = defaultdict(list)
    if not HISTORY_FILE.exists():
        return reviewed

    with open(HISTORY_FILE) as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                week = rec.get("week")
                provider = rec.get("provider") or rec.get("source", "unknown")
                if week:
                    if provider_filter is None or provider == provider_filter:
                        reviewed[week].append(provider)
            except json.JSONDecodeError:
                continue
    return dict(reviewed)


def week_to_dates(week_str: str) -> tuple[str, str]:
    """Convert ISO week string to start/end dates."""
    from datetime import timedelta
    year, week_num = week_str.split("-W")
    year = int(year)
    week_num = int(week_num)
    # ISO week 1 contains Jan 4
    jan4 = datetime(year, 1, 4)
    start_of_week1 = jan4 - timedelta(days=jan4.weekday())
    start_date = start_of_week1 + timedelta(weeks=week_num - 1)
    end_date = start_date + timedelta(days=6)
    return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")


def generate_backfill_prompt(provider: str, week: str, sessions: int) -> str:
    """Generate full backfill prompt for a week."""
    start_date, end_date = week_to_dates(week)
    return f'''You are doing a prompt quality backfill review for week {week} ({provider.capitalize()} sessions).

## Step 1: Extract sessions

Run:
```bash
python3 ~/.claude/skills/prompt-reviewer/scripts/extract_sessions.py \\
  --source {provider} \\
  --since {start_date} \\
  --until {end_date} \\
  --limit 100
```

## Step 2: Score all user prompts

Read ~/.claude/skills/prompt-reviewer/references/scoring-rubric.md.

Score EVERY user prompt (not a sample) on all 9 axes. Compute averages.
Composite = sum(axis averages) / 23

## Step 3: Output the review

```
## Prompt Review - {week} ({provider.capitalize()} Backfill)

**Composite: X.XX / 1.00**
Sessions: N | Prompts: M | Provider: {provider}

### Top 3 Improvements
1. **[Axis]** (X.X/max): [Coaching tip]
   > Example: "[quoted prompt]"
2. ...
3. ...

### What's Working Well
- **[Axis]** (X.X/max): [Positive observation]
```

## Step 4: Save scores (include qualitative insights!)

```bash
python3 ~/.claude/skills/prompt-reviewer/scripts/save_review.py \\
  --composite {{composite}} --sessions {{N}} --prompts {{M}} \\
  --clarity {{avg}} --context {{avg}} --autonomy {{avg}} \\
  --constraints {{avg}} --checkpoints {{avg}} --followup {{avg}} \\
  --collaboration {{avg}} --adaptability {{avg}} --outcome {{avg}} \\
  --source {provider} --provider {provider} --week {week} \\
  --improvements '[{{"axis":"...","score":X.X,"tip":"...","example":"..."}}]' \\
  --strengths '[{{"axis":"...","score":X.X,"observation":"..."}}]'
```

IMPORTANT: Use --week {week} to record the original week, not today's date.

## Step 5: Ask about purging old sessions

After saving, ASK the user if they want to delete the reviewed session files to free disk space.

If they say yes, first show what would be deleted:
```bash
python3 ~/.claude/skills/prompt-reviewer/scripts/purge_sessions.py \\
  --provider {provider} --week {week} --dry-run
```

Then if they confirm, run without --dry-run:
```bash
python3 ~/.claude/skills/prompt-reviewer/scripts/purge_sessions.py \\
  --provider {provider} --week {week}
```

NEVER delete without asking first. The user may want to keep the raw sessions.
'''


def main():
    parser = argparse.ArgumentParser(description="List available session weeks")
    parser.add_argument("--provider", help="Filter to specific provider")
    parser.add_argument("--prompt", action="store_true",
                        help="Output full backfill prompt for next unreviewed week")
    args = parser.parse_args()

    home = Path.home()

    # Scan all providers
    claude_weeks = scan_claude_weeks(home / ".claude")
    codex_weeks = scan_codex_weeks(home / ".codex")
    opencode_weeks = scan_opencode_weeks(home / ".local" / "state" / "opencode")

    # Load reviewed weeks
    reviewed = load_reviewed_weeks(args.provider)

    # Combine all weeks
    all_weeks = set(claude_weeks.keys()) | set(codex_weeks.keys()) | set(opencode_weeks.keys())

    if not all_weeks:
        print("No session data found.")
        return

    # Sort weeks chronologically
    sorted_weeks = sorted(all_weeks)

    # Find first unreviewed week per provider
    next_unreviewed = {}
    for week in sorted_weeks:
        if claude_weeks.get(week, 0) > 0 and "claude" not in next_unreviewed:
            if week not in reviewed or "claude" not in reviewed[week]:
                next_unreviewed["claude"] = week
        if codex_weeks.get(week, 0) > 0 and "codex" not in next_unreviewed:
            if week not in reviewed or "codex" not in reviewed[week]:
                next_unreviewed["codex"] = week
        if opencode_weeks.get(week, 0) > 0 and "opencode" not in next_unreviewed:
            if week not in reviewed or "opencode" not in reviewed[week]:
                next_unreviewed["opencode"] = week

    # Determine which provider to use for backfill
    target_provider = args.provider if args.provider else None
    week_counts = {"claude": claude_weeks, "codex": codex_weeks, "opencode": opencode_weeks}

    # If --prompt flag, just output the full prompt and exit
    if args.prompt:
        if target_provider and target_provider in next_unreviewed:
            week = next_unreviewed[target_provider]
            count = week_counts[target_provider].get(week, 0)
            print(generate_backfill_prompt(target_provider, week, count))
        elif next_unreviewed:
            # Pick first available
            first_provider = min(next_unreviewed.keys())
            week = next_unreviewed[first_provider]
            count = week_counts[first_provider].get(week, 0)
            print(generate_backfill_prompt(first_provider, week, count))
        else:
            print("All weeks have been reviewed!")
        return

    # Print summary table
    print("## Session Weeks Available\n")
    print("| Week | Claude | Codex | OpenCode | Reviewed |")
    print("|------|--------|-------|----------|----------|")

    for week in sorted_weeks:
        claude_n = claude_weeks.get(week, 0)
        codex_n = codex_weeks.get(week, 0)
        opencode_n = opencode_weeks.get(week, 0)

        # Filter if requested
        if args.provider:
            if args.provider == "claude" and claude_n == 0:
                continue
            if args.provider == "codex" and codex_n == 0:
                continue
            if args.provider == "opencode" and opencode_n == 0:
                continue

        reviewed_providers = reviewed.get(week, [])
        reviewed_str = ", ".join(sorted(set(reviewed_providers))) if reviewed_providers else "—"

        claude_str = str(claude_n) if claude_n else "—"
        codex_str = str(codex_n) if codex_n else "—"
        opencode_str = str(opencode_n) if opencode_n else "—"

        print(f"| {week} | {claude_str} | {codex_str} | {opencode_str} | {reviewed_str} |")

    print("")

    # Print next actions
    if next_unreviewed:
        print("### Next to Backfill\n")
        for provider, week in sorted(next_unreviewed.items()):
            count = week_counts[provider].get(week, 0)
            print(f"- **{provider}**: {week} ({count} sessions)")
        print("")

        # Generate the command for the first one
        first_provider = target_provider if target_provider in next_unreviewed else min(next_unreviewed.keys())
        first_week = next_unreviewed[first_provider]
        start_date, end_date = week_to_dates(first_week)

        print("### Backfill Command\n")
        print("```bash")
        print(f"python3 ~/.claude/skills/prompt-reviewer/scripts/extract_sessions.py \\")
        print(f"  --source {first_provider} \\")
        print(f"  --since {start_date} \\")
        print(f"  --until {end_date} \\")
        print(f"  --limit 100")
        print("```")
    else:
        print("All weeks have been reviewed!")


if __name__ == "__main__":
    main()
