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
  "updates": [],
  "metrics": {
    "sessions_seen": 0,
    "llm_calls": 0,
    "suppressed": 0
  }
}
```

## Error Response

```json
{
  "type": "error",
  "id": "req-123",
  "code": "invalid_config",
  "message": "cadence_hot_ms must be between 5000 and 300000"
}
```

