# API Contract Reference

All endpoints use the OpenClaw Approval Feedback API v0.

## Authentication Headers (Machine Auth)

Required headers:

```
X-Tenant-Id: {OPENCLAW_TENANT_ID}
X-Machine-Key-Id: {OPENCLAW_MACHINE_KEY_ID}
X-Machine-Secret: {OPENCLAW_MACHINE_SECRET}
```

Optional header for gateways that do not inject server-side app binding:

```
X-API-Key: {OPENCLAW_API_KEY}
```

## Endpoints

### 1. List Pending Revision Requests

```
GET /v0/agents/{agent_id}/revision-requests?status=pending
```

**Auth:** Machine key with scope `approval_revision.fulfill`
**Agent guard:** Machine key must be bound to `{agent_id}`

**Query params:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `status` | string | `"pending"` | Filter: `pending`, `dispatched`, `fulfilled`, `expired`, `failed` |
| `cursor` | string? | null | Pagination cursor |
| `limit` | int | 50 | 1–200 |

**Response (200):**
```json
{
  "data": {
    "items": [
      {
        "id": "rev-req-uuid",
        "approval_id": "approval-uuid",
        "agent_id": "agent-uuid",
        "status": "pending",
        "trigger_message_ids": ["msg-uuid-1", "msg-uuid-2"],
        "runtime_profile": "openclaw_client_bootstrap",
        "dispatch_mode": "webhook",
        "created_at": "2026-02-24T...",
        "expires_at": "2026-02-24T...",
        "updated_at": "2026-02-24T...",
        "terminal_reason": null,
        "fulfilled_message_id": null
      }
    ],
    "next_cursor": null
  }
}
```

**Errors:**
- `401 MACHINE_KEY_NOT_FOUND` — key ID not found in this tenant/app context
- `401 UNAUTHORIZED` — machine secret is invalid
- `403 MACHINE_KEY_EXPIRED` — key expired; rotate or re-provision
- `403 MACHINE_KEY_REVOKED` — key revoked; provision new key
- `403 APP_BINDING_MISMATCH` — app binding mismatch (`X-API-Key` / gateway binding issue)
- `403 MACHINE_AGENT_MISMATCH` — key bound to different agent

---

### 2. Get Approval Request Detail

```
GET /v0/approval-requests/{approval_id}
```

**Auth:** Machine key OR human governance identity (dual-auth via `require_approval_read_identity`)
**Participant guard:** Viewer must resolve to a participant on the approval with one of:
`approver`, `authorized_user`, `agent_owner`, or `observer`.
**Machine note:** Machine reads are participant-scoped. The machine key (or its effective principal) must be present in `participants`.

**Response (200):**
```json
{
  "data": {
    "id": "approval-uuid",
    "code": "ABC123",
    "agent_id": "agent-uuid",
    "action": "social_reply",
    "resource_type": "social_reply",
    "resource_id": "resource-uuid",
    "status": "pending_review",
    "created_at": "2026-02-24T...",
    "expires_at": "2026-02-25T...",
    "context": {
      "context_type": "social_reply",
      "context_version": "v1",
      "payload": {
        "proposed_reply": "The original suggested reply text...",
        "platform": "twitter",
        "original_post": "..."
      }
    },
    "participants": [
      {
        "principal_type": "agent",
        "principal_id": "agent-uuid",
        "role": "agent_owner"
      },
      {
        "principal_type": "human",
        "principal_id": "user-uuid",
        "role": "approver"
      }
    ],
    "version": 3
  }
}
```

**Errors:**
- `401` — no valid auth
- `403` — viewer is not a participant with view access
- `404 APPROVAL_NOT_FOUND` — invalid approval_id

---

### 3. List Messages (Feedback Thread)

```
GET /v0/approval-requests/{approval_id}/messages
```

**Auth:** Machine key OR human governance identity (dual-auth)
**Participant guard:** Same participant-access requirement as approval detail.
**Machine note:** Same participant-scoped machine read behavior as approval detail.

**Query params:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `cursor` | string? | null | Pagination cursor |
| `limit` | int | 50 | 1–200 |

**Response (200):**
```json
{
  "data": {
    "approval_id": "approval-uuid",
    "messages": [
      {
        "id": "msg-uuid",
        "approval_id": "approval-uuid",
        "author_type": "human",
        "author_id": "user-uuid",
        "author_name": "Jane",
        "message_type": "feedback",
        "content": "Make this more casual",
        "original_content": null,
        "edited_content": null,
        "created_at": "2026-02-24T...",
        "sequence": 1,
        "reaction": { "up": 0, "down": 0, "viewer_vote": null }
      },
      {
        "id": "msg-uuid-2",
        "approval_id": "approval-uuid",
        "author_type": "machine",
        "author_id": "machine-key-id",
        "author_name": null,
        "message_type": "edit_diff",
        "content": "Made tone more casual",
        "original_content": null,
        "edited_content": "Hey! Thanks for reaching out...",
        "created_at": "2026-02-24T...",
        "sequence": 2,
        "reaction": { "up": 1, "down": 0, "viewer_vote": "up" }
      }
    ],
    "next_cursor": null
  }
}
```

**Message types:**
- `feedback` — human feedback text
- `edit_diff` — machine revision with `edited_content`
- `system` — system-generated messages

---

### 3a. Timeline

```
GET /v0/approval-requests/{approval_id}/timeline
```

**Auth:** Machine key OR human governance identity (dual-auth via `require_approval_read_identity`)
**Participant guard:** Same participant-access requirement as approval detail.
**Machine note:** Same participant-scoped machine read behavior as approval detail.

**Query params:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `cursor` | string? | null | Pagination cursor |
| `limit` | int | 50 | 1–200 |

**Errors:**
- `403 NOT_AUTHORIZED` — viewer is not a participant
- `404 APPROVAL_NOT_FOUND` — invalid approval_id

---

### 3b. Approval Reaction Summary

```
GET /v0/approval-requests/{approval_id}/reaction-summary
```

**Auth:** Machine key OR human governance identity (dual-auth via `require_approval_read_identity`)
**Participant guard:** Same participant-access requirement as approval detail.
**Machine note:** Same participant-scoped machine read behavior as approval detail.

---

### 3c. Message Reaction Summary

```
GET /v0/approval-requests/{approval_id}/messages/{message_id}/reaction-summary
```

**Auth:** Machine key OR human governance identity (dual-auth via `require_approval_read_identity`)
**Participant guard:** Same participant-access requirement as approval detail.
**Machine note:** Same participant-scoped machine read behavior as approval detail.

---

### 4. Feedback Digest

```
GET /v0/agents/{agent_id}/feedback-digest?limit=100
```

**Auth:** Machine key with scope `agent_feedback_digest.read`, or legacy agent identity
**Agent guard:** Machine key must be bound to `{agent_id}`

**Query params:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `cursor` | string? | null | Pagination cursor |
| `limit` | int | 100 | 1–500 |
| `context_type` | string? | null | Filter by context type |

**Response (200):**
```json
{
  "data": {
    "agent_id": "agent-uuid",
    "items": [
      {
        "approval_id": "approval-uuid",
        "status": "approved",
        "context_type": "social_reply",
        "feedback_count": 2,
        "latest_feedback_at": "2026-02-24T..."
      }
    ],
    "next_cursor": null
  }
}
```

---

### 5. Fulfill Revision Request

```
POST /v0/approval-requests/{approval_id}/messages/fulfill
```

**Auth:** Machine key only (via `require_machine_governance_identity`)
**Scope:** `approval_revision.fulfill`
**Agent guard:** Enforced internally by the service layer

**Request body:**
```json
{
  "content": "Made tone more casual per user feedback",
  "message_type": "edit_diff",
  "edited_content": "Hey! Thanks for reaching out. Here's what I think...",
  "revision_request_id": "rev-req-uuid",
  "expected_version": 3,
  "idempotency_key": "unique-uuid-per-attempt"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `content` | string | yes | Brief description of the edit |
| `message_type` | string | no | `edit_diff` (default) or `comment` |
| `edited_content` | string | conditional | Required only when `message_type=edit_diff` |
| `revision_request_id` | string | yes | Links fulfillment to the revision request |
| `expected_version` | int | yes | Approval version for optimistic concurrency |
| `idempotency_key` | string | yes | 1–128 chars, non-blank, deduplicate retries |

**Response (201):**
```json
{
  "data": {
    "id": "msg-uuid",
    "approval_id": "approval-uuid",
    "author_type": "machine",
    "author_id": "machine-key-id",
    "message_type": "edit_diff",
    "content": "Made tone more casual per user feedback",
    "edited_content": "Hey! Thanks for reaching out...",
    "created_at": "2026-02-24T...",
    "sequence": 3
  }
}
```

**Errors:**
- `400 VALIDATION_ERROR` — missing `revision_request_id`
- `400 EDIT_DIFF_INVALID` — missing `edited_content` for `edit_diff`
- `400 REVISION_FULFILLMENT_MESSAGE_TYPE_INVALID` — `message_type` not one of `edit_diff`/`comment`
- `401 MACHINE_KEY_NOT_FOUND` — key ID not found in this tenant/app context
- `401 UNAUTHORIZED` — machine secret is invalid
- `403 MACHINE_KEY_EXPIRED` — key expired
- `403 MACHINE_KEY_REVOKED` — key revoked
- `403 APP_BINDING_MISMATCH` — app binding mismatch (`X-API-Key` / gateway binding issue)
- `403 MACHINE_AGENT_MISMATCH` — machine key not bound to this approval's agent
- `404 APPROVAL_NOT_FOUND` — invalid approval_id
- `409 VERSION_CONFLICT` — `expected_version` doesn't match current; re-fetch and retry
- `409 REVISION_REQUEST_STALE` — revision request is no longer open (already fulfilled/closed)
- `409 IDEMPOTENCY_CONFLICT` — idempotency key reused with different payload fingerprint

---

### 6. Create Instruction Proposal

```
POST /v0/instruction-proposals
```

**Auth:** Machine key only (via `require_machine_governance_identity`)
**Scope:** `instruction_proposal.create`
**Agent guard:** Machine key's bound `agent_id` is used as the proposal's agent_id

**Request body:**
```json
{
  "scope": "agent",
  "title": "Be funnier in replies",
  "summary": "Multiple users asked for a more humorous tone across 3 revisions",
  "approval_id": null,
  "target_ref": null,
  "evidence_ref": "rev-abc123-deadbeef",
  "payload": {
    "instruction": "Use more humor and casual tone in social replies"
  },
  "idempotency_key": "unique-uuid-per-attempt"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `scope` | string | yes | Proposal scope: `"agent"`, `"skill"`, `"agent_skill"` (max 64 chars) |
| `title` | string | yes | Short title (1–256 chars) |
| `summary` | string | yes | Description of the proposed change (1–2000 chars) |
| `payload` | object | yes | The instruction delta (arbitrary JSON) |
| `idempotency_key` | string | yes | 1–128 chars, non-blank, deduplicate retries |
| `approval_id` | string? | no | Link to triggering approval if applicable |
| `target_ref` | string? | no | Target reference (max 256 chars) |
| `evidence_ref` | string? | no | Evidence reference like revision request ID (max 512 chars) |

**Response (201):**
```json
{
  "data": {
    "id": "ip-agent-test-a1b2c3d4",
    "agent_id": "agent-uuid",
    "approval_id": null,
    "status": "proposed",
    "scope": "agent",
    "target_ref": null,
    "title": "Be funnier in replies",
    "summary": "Multiple users asked for a more humorous tone",
    "evidence_ref": "rev-abc123-deadbeef",
    "payload": {
      "instruction": "Use more humor and casual tone in social replies"
    },
    "created_at": "2026-02-25T...",
    "decided_at": null
  }
}
```

**Errors:**
- `401 MACHINE_KEY_NOT_FOUND` — key ID not found in this tenant/app context
- `401 UNAUTHORIZED` — machine secret is invalid
- `403 MACHINE_KEY_EXPIRED` — key expired
- `403 MACHINE_KEY_REVOKED` — key revoked
- `403 APP_BINDING_MISMATCH` — app binding mismatch (`X-API-Key` / gateway binding issue)
- `403 MACHINE_SCOPE_DENIED` — key missing `instruction_proposal.create` scope
- `409 IDEMPOTENCY_CONFLICT` — same key reused with different payload fingerprint

---

## Example: Full Cycle (curl)

**IMPORTANT:** Never store auth headers in a bash variable — quoting breaks. Always write each `-H` flag inline. Always append `-w "\nHTTP_STATUS:%{http_code}"` to capture status codes.

```bash
# Source env vars first
set -a && source .claude/agents/<agent-id>.env && set +a

# 1. List pending revisions
curl -s -w "\nHTTP_STATUS:%{http_code}" \
  -H "X-Tenant-Id: ${OPENCLAW_TENANT_ID}" \
  -H "X-Machine-Key-Id: ${OPENCLAW_MACHINE_KEY_ID}" \
  -H "X-Machine-Secret: ${OPENCLAW_MACHINE_SECRET}" \
  "${OPENCLAW_API_URL}/v0/agents/${OPENCLAW_AGENT_ID}/revision-requests?status=pending"

# 2. Get approval detail
curl -s -w "\nHTTP_STATUS:%{http_code}" \
  -H "X-Tenant-Id: ${OPENCLAW_TENANT_ID}" \
  -H "X-Machine-Key-Id: ${OPENCLAW_MACHINE_KEY_ID}" \
  -H "X-Machine-Secret: ${OPENCLAW_MACHINE_SECRET}" \
  "${OPENCLAW_API_URL}/v0/approval-requests/${APPROVAL_ID}"

# 3. Get feedback thread
curl -s -w "\nHTTP_STATUS:%{http_code}" \
  -H "X-Tenant-Id: ${OPENCLAW_TENANT_ID}" \
  -H "X-Machine-Key-Id: ${OPENCLAW_MACHINE_KEY_ID}" \
  -H "X-Machine-Secret: ${OPENCLAW_MACHINE_SECRET}" \
  "${OPENCLAW_API_URL}/v0/approval-requests/${APPROVAL_ID}/messages"

# 4. Get feedback digest
curl -s -w "\nHTTP_STATUS:%{http_code}" \
  -H "X-Tenant-Id: ${OPENCLAW_TENANT_ID}" \
  -H "X-Machine-Key-Id: ${OPENCLAW_MACHINE_KEY_ID}" \
  -H "X-Machine-Secret: ${OPENCLAW_MACHINE_SECRET}" \
  "${OPENCLAW_API_URL}/v0/agents/${OPENCLAW_AGENT_ID}/feedback-digest?limit=100"

# 5. Fulfill revision (check for 201!)
curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST \
  -H "X-Tenant-Id: ${OPENCLAW_TENANT_ID}" \
  -H "X-Machine-Key-Id: ${OPENCLAW_MACHINE_KEY_ID}" \
  -H "X-Machine-Secret: ${OPENCLAW_MACHINE_SECRET}" \
  -H "Content-Type: application/json" \
  "${OPENCLAW_API_URL}/v0/approval-requests/${APPROVAL_ID}/messages/fulfill" \
  -d "{
    \"content\": \"Adjusted tone per feedback\",
    \"edited_content\": \"Updated reply text here...\",
    \"revision_request_id\": \"${REV_REQ_ID}\",
    \"expected_version\": ${VERSION},
    \"idempotency_key\": \"$(uuidgen)\"
  }"
```
