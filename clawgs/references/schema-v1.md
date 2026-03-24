# Clawgs Schema v1

`clawgs extract` emits a single JSON document with `schema_version: "clawgs.v1"`.

## Top-Level Fields

- `schema_version` (`string`): fixed to `"clawgs.v1"`
- `source` (`object`): source metadata
- `snapshot` (`object`): normalized context snapshot
- `stats` (`object`): parse and input metrics
- `generated_at` (`string`): ISO-8601 UTC timestamp
- `raw_events` (`array`, optional): included only with `--include-raw`

## source

- `tool` (`"claude" | "codex"`)
- `path` (`string`): file path used for extraction
- `discovered` (`boolean`): `true` when path came from discovery logic
- `cwd` (`string`): cwd used for discovery/matching

## snapshot

- `user_task` (`string | null`): latest detected user prompt/task
- `current_tool` (`Action | null`): latest detected tool/thinking action
- `token_count` (`number`): latest observed `input_tokens`
- `recent_actions` (`Action[]`): bounded action list, oldest to newest
- `commit_signal` (`CommitSignal`, optional): Codex-only commit-readiness nudge derived from transcript evidence

### Action

- `tool` (`string`): tool or activity label
- `detail` (`string | null`): short normalized detail
- `kind` (`"tool_use" | "text" | "thinking" | "function_call" | "other"`)
- `ts` (`string | null`): timestamp when available in source event

### CommitSignal

- `candidate` (`boolean`): `true` when edits were observed, validation succeeded, the dirty tree was checked, and no commit was seen
- `edited` (`boolean`): `true` when a completed edit action such as `apply_patch` was observed
- `validated` (`boolean`): `true` when a successful test/lint/typecheck command was paired with successful command output
- `dirty_checked` (`boolean`): `true` when the transcript shows a git dirty-tree check
- `commit_seen` (`boolean`): `true` when the transcript shows a git commit command

## stats

- `events_seen` (`number`): successfully parsed JSONL lines
- `malformed_lines_skipped` (`number`): non-JSON lines ignored
- `bytes_read` (`number`): file bytes read

## Example

```json
{
  "schema_version": "clawgs.v1",
  "source": {
    "tool": "codex",
    "path": "/tmp/rollout-abc.jsonl",
    "discovered": false,
    "cwd": "/tmp/project"
  },
  "snapshot": {
    "user_task": "Build a parser",
    "current_tool": {
      "tool": "exec_command",
      "detail": "ls -la",
      "kind": "function_call",
      "ts": null
    },
    "token_count": 1212,
    "recent_actions": [
      {
        "tool": "exec_command",
        "detail": "ls -la",
        "kind": "function_call",
        "ts": null
      }
    ],
    "commit_signal": {
      "candidate": false,
      "edited": false,
      "validated": false,
      "dirty_checked": false,
      "commit_seen": false
    }
  },
  "stats": {
    "events_seen": 4,
    "malformed_lines_skipped": 0,
    "bytes_read": 286
  },
  "generated_at": "2026-02-26T20:11:56Z"
}
```
