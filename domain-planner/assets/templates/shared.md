# {slice_name} API Contract

> Shared contract between frontend and backend. **LOCKED** after approval.

---

## User Stories

### US-1: [Story Title]

As a **[role]**, I need to **[action]**, so that **[outcome]**.

**Acceptance:**
- [ ] [Criterion 1]
- [ ] [Criterion 2]

**Test Scenarios:**
- [ ] [Happy path] → 200/201
- [ ] [Validation failure] → 400 VALIDATION_FAILED
- [ ] [Not found] → 404 NOT_FOUND
- [ ] [Not authorized] → 403 NOT_AUTHORIZED

---

### US-2: [Story Title]

<!-- Repeat format -->

---

## API Endpoints

### GET /v1/{slice_name}

**Purpose:** [Description]

**Auth:** [Required auth level]

**Query Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `filter` | string | No | Filter by status |

**Response 200:**
```json
{
  "items": [
    {
      "id": "uuid",
      "name": "string",
      "created_at": "2025-01-01T00:00:00Z"
    }
  ],
  "total": 1
}
```

---

### POST /v1/{slice_name}

**Purpose:** [Description]

**Auth:** [Required auth level]

**Request Body:**
```json
{
  "name": "string (required)",
  "description": "string (optional)"
}
```

**Response 201:**
```json
{
  "id": "uuid",
  "name": "string",
  "created_at": "2025-01-01T00:00:00Z"
}
```

**Response 400:**
```json
{ "detail": "VALIDATION_FAILED" }
```

---

## Error Codes

| Code | HTTP | When |
|------|------|------|
| `NOT_AUTHENTICATED` | 403 | Missing authentication |
| `NOT_AUTHORIZED` | 403 | User doesn't own resource |
| `NOT_FOUND` | 404 | Resource doesn't exist |
| `VALIDATION_FAILED` | 400 | Invalid input |
| `ALREADY_EXISTS` | 409 | Duplicate record |

---

## Runtime & Backpressure Contract

> Required for performance-critical slices.

### Stream/Realtime Semantics

- Transport for hot-path events: [binary/json/mixed]
- Replay behavior on reconnect: [window and truncation contract]
- Backpressure behavior: [drop/queue/reject semantics + error codes]

### Performance Acceptance Criteria

- [ ] [SLO target] with [load assumption] and measurable test.
- [ ] [Queue/buffer bound] and overload behavior documented.
- [ ] [Polling fallback behavior] defined only for degraded channel states.

---

## Business Rules

### Rule 1: [Name]

[Description of when/how this rule applies]

---

## Sign-Off Checklist

- [ ] User stories reviewed with acceptance criteria
- [ ] API endpoints defined with full request/response shapes
- [ ] Error codes documented
- [ ] Test scenarios for each user story
- [ ] **CONTRACT LOCKED** - changes require discussion
