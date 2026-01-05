# HTTP API Reference

The FastAPI service at `src/agents/http_api.py` exposes endpoints that mirror the CLI/RAG workflow.

Run locally:

```bash
uvicorn src.agents.http_api:app --reload
```

## Authentication

- If `API_AUTH_TOKEN` is configured, clients must provide **`X-API-Key: <token>`** (or a valid Bearer JWT via `/v1/auth/login`).
- Roles: `user`, `admin`, `admin_readonly`. Admin endpoints require admin privileges; read-only admins can call admin GET endpoints only.
- API key access is treated as full admin for bootstrap/dev.

IR compatibility: unversioned endpoints `/ingest`, `/query`, `/answer` alias the `/v1/*` routes. `/reran` maps to `/v1/reran` (rerank only).

---

## POST /v1/auth/register
Registers a new user account (username + password + reset question/answer). Only `user` role is permitted.

## POST /v1/auth/login
Login (JWT) for UI clients. Requires username + password unless using admin password.

## GET /v1/auth/me
Returns current principal.

## POST /v1/auth/logout
Clears client session (stateless; clients should delete local token).

## GET /v1/auth/reset-question
Returns the reset question for a username (used during password reset flow).

## POST /v1/auth/reset-password
Resets a password using username + reset answer + new password.

## POST /v1/auth/password
Changes password for the current logged-in user.

## POST /v1/auth/reset-question
Updates the reset question + answer for the current logged-in user.

---

## POST /v1/ingest
Uploads corpus content (text/markdown) and triggers index rebuild.
URL ingestion is not supported; use uploaded documents instead.

## POST /v1/upload
Uploads a file (PDF/text/image/audio) and returns an `upload_id` plus download URL.
Admin-only.
Image OCR is applied during preview/ingest for PNG/JPEG/WEBP uploads (Qwen/Qwen3-VL-32B-Instruct via SiliconFlow).
Audio uploads (MP3/WAV/MP4/WEBM/OGG) are transcribed during ingest.
Optional query params:
- `retention_days` (defaults to `UPLOAD_RETENTION_DAYS`; `0` disables expiry)
- `purpose` (`chat` for session-only attachments, `rag` for knowledge base ingestion)

## GET /v1/upload/{upload_id}
Returns upload metadata and download URL.

## GET /v1/upload/{upload_id}/signed
Returns short-lived signed URLs for downloading/previewing the upload.

## GET /v1/upload/{upload_id}/preview
Returns preview metadata, a signed preview URL, and an optional text excerpt.

## GET /v1/upload/{upload_id}/file
Signed download/preview endpoint (expects `exp`, `sig`, and `disposition` query params).

## POST /v1/ingest-upload
Ingests a previously uploaded file and triggers index rebuild. Only uploads with purpose `rag` are eligible. Image uploads are OCR’d (Qwen/Qwen3-VL-32B-Instruct) and audio uploads are transcribed before chunking.
Admin-only.
URL ingestion is not supported; only uploaded documents are accepted.

Optional async mode:
- `POST /v1/ingest-upload?async=true` returns a `202` with `JobEnqueueResponse`.
- Use `/v1/admin/jobs` to track queued/running/completed jobs.

## POST /v1/query
Submits a question and returns grounded answer + citations + diagnostics.

Request (`QueryRequest`) key fields:
- `question`, `language`, `slots`, `session_id`, `reset_slots`, `top_k`, `k_cite`, `use_rag`
- Generation controls: `temperature`, `top_p`, `max_tokens`, `stop`, `model`
- `explain_like_new` (beginner-friendly phrasing)
- `attachments`: upload IDs whose OCR/STT text is merged into the question; if images are present the server attempts a multimodal model

Response includes:
- `answer`
- `citations[]` with `highlights[]`
- `diagnostics` (`retrieval_ms`, `rerank_ms`, `generation_ms`, `end_to_end_ms`, `low_confidence`, `citation_coverage`)
Notes:
- Citations are always derived from indexed RAG chunks (attachments only influence the query context).

## POST /v1/reran
Reranks candidate documents for a query and returns scored ordering.

Request (`RerankRequest`) key fields:
- `query`, `documents[]` (each document includes `text` plus optional `document_id` and `metadata`)
- Optional: `language`, `model`

Response includes:
- `results[]` with `index`, `score`, and the original `document`
- `trace_id`

## GET /v1/slots
Returns slot catalog.

## GET /v1/session
Lists active sessions.

## GET /v1/session/{session_id}
Gets a session state.

## DELETE /v1/session/{session_id}
Deletes a session.

## PATCH /v1/session/{session_id}/slots
Updates slot values for a session (supports `slots` + `reset_slots`).

---

## GET /v1/index/health
Returns index health snapshot.

## POST /v1/index/rebuild
Forces an index rebuild.

## GET /v1/chunks/{chunk_id}
Returns chunk text, metadata, and `highlights[]` spans for UI passage display.

## Streaming: POST /v1/query?stream=true
If the client sends `Accept: text/event-stream` and calls `POST /v1/query?stream=true`, the server responds as SSE and emits:
- `event: citations` with citation payload
- `event: chunk` with `{ "delta": "..." }`
- `event: completed` with a full `QueryResponse` payload
- `event: error` with `{ "message": "..." }`

### Stop generating (client abort)
To stop generation, the client should **abort/close the SSE HTTP request** (e.g., `AbortController.abort()` in browsers).
The server detects disconnect and **stops streaming immediately**, closing the upstream SiliconFlow stream.

## POST /v1/feedback
Submit per-message feedback for analytics.

Request:
- `session_id`
- `message_id`
- `rating`: `-1 | 0 | 1`
- `comment` (optional)

---

## GET /v1/metrics
Aggregated request metrics:
- per-endpoint counters
- `phases` latency block
- `diagnostics` counters
- `status` traffic-light summaries
Additional diagnostics (when eval runs are recorded):
- `retrieval_recall_avg`, `retrieval_mrr_avg`, `retrieval_eval_k`

## GET /v1/metrics/history
Admin-only metrics history. Returns recent snapshots captured when `/v1/metrics` or `/v1/metrics/history` is called.
Query params:
- `limit` (default 30)

## GET /v1/status
Structured service status digest (latency/quality categories).

---

## Admin APIs

## GET /v1/admin/config
Returns an operator snapshot (sources, slots, retrieval defaults).

## GET /v1/admin/audit
Returns audit log entries.

## GET /v1/admin/jobs
Returns ingest/index job history.

## GET /v1/admin/users
Lists user accounts with session counts and last active timestamp.

## GET /v1/admin/conversations
Lists sessions with optional filters.
Query params:
- `user_id`
- `limit`

## GET /v1/admin/conversations/{user_id}/{session_id}/messages
Returns full message history for the specified user/session (admin view).

## POST /v1/admin/uploads/cleanup
Purges expired uploads (retention cleanup).
Query params:
- `dry_run` (true to return IDs only without deleting)

## POST /v1/admin/ingest-upload
Admin-only ingestion of an uploaded file.

Optional async mode:
- `POST /v1/admin/ingest-upload?async=true` returns a `202` with `JobEnqueueResponse`.

## POST /v1/admin/eval/retrieval
Runs retrieval evaluation with recall@k and MRR for the provided cases.

## Sources
- `GET /v1/admin/sources`
- `POST /v1/admin/sources`
- `DELETE /v1/admin/sources/{doc_id}`
- `POST /v1/admin/sources/{doc_id}/verify` (manual re-verify; updates citation `last_verified_at`)

## Stop-list
- `GET /v1/admin/stop-list`
- `POST /v1/admin/stop-list`

## Templates
- `GET /v1/admin/templates`
- `POST /v1/admin/templates`
- `DELETE /v1/admin/templates/{template_id}`

## Prompts
- `GET /v1/admin/prompts`
- `POST /v1/admin/prompts`
- `POST /v1/admin/prompts/{prompt_id}/activate`
- `DELETE /v1/admin/prompts/{prompt_id}`
