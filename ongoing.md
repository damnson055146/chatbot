# Ongoing Tasks

> Updated: 2025-12-29
> Scope: P0 alignment tasks from `p0.md`.

## P0 Backlog
- [x] Image OCR ingestion pipeline
  - Accept image MIME types in upload/ingest
  - OCR to text + metadata (page, confidence)
  - Store extracted text for chunking/indexing
  - Error handling when OCR fails
  - Update user/admin UI copy for OCR support
  - Tests for image upload -> ingest -> query

- [x] Audio STT ingestion pipeline
  - Accept audio MIME types in upload/ingest
  - Speech-to-text (IR: FunAudioLLM) -> transcript + timestamps
  - Store transcript for chunking/indexing
  - Error handling when STT fails
  - Tests for audio upload -> ingest -> query

- [x] Multimodal query path
  - /v1/query accepts attachments and merges OCR/STT text with user question
  - Multimodal LLM routing for image+text (IR: GLM-4.1V / Qwen2.5-VL)
  - Citations still derived from RAG chunks
  - Streaming behavior preserved for multimodal responses

- [x] Model stack alignment to IR
  - Default embed/rerank models set to Qwen3-Embedding-8B + Qwen3-Reranker-8B
  - Add config/env toggles for multimodal chat models
  - Update docs to reflect IR model choices and fallbacks

- [x] Documentation + acceptance checks
  - docs/api.md: include multimodal upload/query notes
  - docs/development_compilation.md: update limitations section
  - Add a minimal P0 acceptance checklist (OCR/STT happy path + failure path)

## Follow-up
- [x] Require login for chat and disable anonymous auth by default.
- [x] Persist account-level profile (display name/email) and apply as slot defaults.
- [x] Export conversation history from backend sessions/messages.
- [x] Align backend route names with IR doc (`/ingest`, `/query`, `/answer`, `/reran`) and implement `/reran` rerank behavior.

## IR Gaps (Pending)
- [x] Replace in-memory index + JSON storage with FAISS for vectors and SQLite for metadata.
- [x] Implement chunk-aware sentence/clause segmentation (beyond paragraph slicing).
- [x] Add bulk ingestion CLI with schema validation.
- [x] Build counsellor dashboard for conversation oversight + feedback loops (admin view).
- [x] Add recall@k / MRR monitoring and evaluation hooks.
- [x] Wire upload retention controls (client to API) for privacy defaults.

## Validation
- [x] python -m pytest -q tests/unit/utils/test_security.py tests/integration/test_http_api.py tests/integration/test_query_smoke.py tests/integration/test_query_streaming.py
- [x] npm test -- --run (frontend)
- [x] python -m pytest -q tests/unit/test_observability.py tests/integration/test_http_api.py
- [x] python -m pytest -q tests/unit/test_storage_cache.py tests/unit/test_ingest_pipeline.py tests/unit/test_index_manager.py
- [x] python -m pytest -q tests/unit/test_chunking.py tests/unit/test_ingest_pipeline.py tests/unit/test_index_manager.py tests/integration/test_query_smoke.py tests/integration/test_rerank_circuit.py
- [x] python -m pytest -q tests/unit/test_cli_bulk_ingest.py
