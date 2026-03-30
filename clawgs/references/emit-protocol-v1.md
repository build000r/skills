# Clawgs Emit Protocol v1

`clawgs emit --stdio` speaks line-delimited JSON (`NDJSON`) over stdin/stdout.

## Startup

On boot, the daemon writes:

```json
{"type":"hello","protocol":"clawgs.emit.v1","engine_version":"0.1.0"}
```

## Request

Send one `sync` object per line:

```json
{
  "type": "sync",
  "id": "req-123",
  "now": "2026-02-26T21:00:00Z",
  "config": {
    "enabled": true,
    "model": "",
    "cadence_hot_ms": 15000,
    "cadence_warm_ms": 45000,
    "cadence_cold_ms": 120000,
    "agent_prompt": null,
    "terminal_prompt": null
  },
  "sessions": []
}
```

## Success Response

```json
{
  "type": "sync_result",
  "id": "req-123",
  "stream_instance_id": "stream-1",
  "updates": [
    {
      "session_id": "sess-1",
      "stream_instance_id": "stream-1",
      "emission_seq": 7,
      "thought": "Validating fallback handling",
      "token_count": 144379,
      "context_limit": 256000,
      "thought_state": "holding",
      "thought_source": "llm",
      "objective_changed": false,
      "bubble_precedence": "thought_first",
      "at": "2026-03-29T21:00:00Z",
      "objective_fingerprint": "obj-123",
      "rest_state": "active",
      "commit_candidate": false,
      "timing": {
        "run_started_at": "2026-03-29T20:52:14Z",
        "run_elapsed_ms": 466000,
        "idle_elapsed_ms": 1200
      },
      "cues": {
        "cadence_tier": "warm",
        "cadence_ms": 45000,
        "next_llm_eligible_at": "2026-03-29T21:00:30Z",
        "context_source": "transcript"
      }
    }
  ],
  "metrics": {
    "sessions_seen": 1,
    "llm_calls": 1,
    "suppressed": 0
  }
}
```

### Update Fields

- `timing.run_started_at`: start of the current active run.
- `timing.run_finished_at`: present only after the run has stopped and the elapsed timer is frozen.
- `timing.run_elapsed_ms`: live elapsed time while active, frozen elapsed time while stopped.
- `timing.idle_elapsed_ms`: milliseconds since the pane last showed activity.
- `cues.cadence_tier`: current cadence bucket, one of `hot`, `warm`, or `cold`.
- `cues.cadence_ms`: minimum milliseconds between eligible LLM emits for the current cadence tier.
- `cues.next_llm_eligible_at`: next wall-clock time when a fresh LLM emit may run.
- `cues.context_source`: whether the status came from transcript context or terminal-only context.

## Error Response

```json
{
  "type": "error",
  "id": "req-123",
  "code": "invalid_config",
  "message": "cadence_hot_ms must be between 5000 and 300000"
}
```
