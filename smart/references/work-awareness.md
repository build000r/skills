# Relevant work awareness

The collector reports declared Beads ownership and observed NTM/tmux locations.
It supplies evidence for judgment. It does not grant a claim, identify an idle
worker, or authorize intervention in another thread.

## Decide whether to collect

Collect when existing work could change the recommendation or its execution:
uncertain ownership, a changed agent landscape, a new write scope, or a decision
that spans repositories. Reuse a recent snapshot when its observed times, scope,
coverage, and known intervening changes fit the decision. Skip collection when
the available evidence suffices. There is no mandatory scan per invocation or
fixed age threshold that makes an observation safe to act on.

## Find the current tool

The current prototype is Skillbox's `scripts/work-status.py`, backed by
`runtime_manager.work_inventory.collect`. It may exist only in a feature
worktree. Resolve the known Skillbox checkout through the active client context,
`SKILLBOX_ROOT`, or the installed SBP wrapper's root resolution. Inspect
`scripts/work-status.py` and `docs/work-inventory.md` there. If absent, inspect
that checkout's registered worktrees with `git worktree list --porcelain` and
look for those same files. Verify the candidate's branch and documentation;
do not choose an arbitrary candidate when several differ. Do not recursively
scan home directories, check out branches, install a tool, or copy the collector
into this skill just to obtain a snapshot.

Set `collector` to the verified script path. Resolve the task's repository root
from its actual directory; do not change cwd to the collector's worktree and
then infer the task from that location. The prototype accepts explicit paths:

```bash
# One repository, including invocation from a subdirectory or linked worktree.
python3 "$collector" --repo "$repo_root" --json

# A task involving known application and service repositories.
python3 "$collector" --repo "$app_repo" --repo "$service_repo" --json

# Workspace-wide prioritization, with the declared inventory selected explicitly.
python3 "$collector" --workspace "$workspace_inventory" --json
```

Assign these variables from verified context before use. Relative paths in a
workspace inventory are relative to its containing directory. The prototype's
no-scope default discovers an ancestor `.bv/workspace.yaml`; avoid that default
for a single-repository question. `--repo` limits tracker reads, while the MVP
still reports all sessions/panes on the local default tmux server.

Do not assume a proposed `sbp work` command is installed. Switch to an SBP front
door only after its installed help/capabilities advertise it and its scope,
JSON, and exit behavior are verified. If the collector cannot be found, use
available task/context evidence and name any decision-relevant gap. Do not
silently repair tools or open native trackers under a read-only claim: even
some native `br` read commands can perform database maintenance.

## Interpret only what matters

- Check scope and per-source coverage before selecting rows. Exit 0 means the
  declared collection completed; exit 1 still contains usable JSON with partial
  or invalid coverage; exit 2 is a usage error. Never discard an exit-1 payload
  or turn a failed source into an empty task list.
- Consider the target repository, declared write scope, related dependencies,
  and the question being answered. Workspace-wide prioritization can justify a
  broader view than a local edit. Do not treat every returned session as a
  conflict or infer relevance from session names alone.
- An in-progress Bead can have no declared owner. An assigned open, blocked, or
  deferred Bead can still reserve relevant work. Inspect the actual task when
  its overlap matters; status alone does not establish the write boundary.
- Pane cwd indicates location, not Bead ownership. The MVP leaves task/pane
  bindings unknown. A quiet pane, absent session, or old task timestamp does
  not release ownership. Remote hosts, other tmux servers, and processes outside
  tmux are not covered by this local snapshot.
- Native tracker formats unsupported by the MVP remain explicitly unavailable.
  Do not substitute a possibly stale JSONL export and call it live evidence.
  Missing relevant ownership evidence limits claims about that scope; unrelated
  failures need not prevent independent analysis or work elsewhere.
- Report the useful observations, their age when material, and relevant unknowns.
  Preserve existing owners. Before acting on a changed write scope, resolve any
  material ownership uncertainty through current evidence or choose independent
  work. Collection alone never authorizes a message, handoff request, interrupt,
  reassignment, or takeover of another session.
