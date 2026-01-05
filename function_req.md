# function_req.md �?Study‑Abroad RAG Assistant (FYP)



> This Functional Requirements document follows well‑recognized SRS guidance (ISO/IEC/IEEE 29148) for structure and clarity. It specifies *what* the system shall do and the quality attributes it shall meet. References are included where relevant to practices in RAG, dialogue management, and Malaysia PDPA compliance.  



---



## 1. Introduction



### 1.1 Purpose

Define the functional and non‑functional requirements for a bilingual (ZH/EN) Study‑Abroad Consultation Assistant that answers policy/process questions with verifiable citations, using a Retrieval‑Augmented Generation (RAG) backend and SiliconFlow API for model inference.



### 1.2 Scope

- Channels: web app (desktop/mobile), later extensible to API/SDK.

- Core: ingest→chunk→index→retrieve→rerank→generate→cite→escalate.

- Users: Students, counsellors, administrators.

- Out‑of‑scope (initial): payments, agentic web‑browsing at runtime, long‑term user profiling beyond session.



### 1.3 References

- ISO/IEC/IEEE 29148 SRS concepts & attributes of good requirements. citeturn0search11turn0search19turn0search6�? 

- Haystack docs/blog (hybrid retrieval, reranking value in RAG). citeturn0search7turn0search12turn0search1�? 

- Dify knowledge base & external sources for RAG prototyping/ops. citeturn0search2turn0search21�? 

- Rasa slots/forms for structured dialogue. citeturn0search3turn0search8�? 

- SiliconFlow Chat Completions API. citeturn0search10turn0search5turn0search18�? 

- Malaysia PDPA (principles; consent, security, retention). citeturn0search4turn0search13turn0search17�?



### 1.4 Definitions

- **RAG**: Retrieve top‑k source chunks to ground LLM answers; return citations.

- **Hybrid retrieval**: BM25 (keyword) + dense embeddings; merge+rank. citeturn0search7�? 

- **Reranking**: Cross‑encoder or LLM ranker reorders retrieved chunks for relevance. citeturn0search1�? 

- **Slot/Form**: Dialogue state fields collected via guided turns. citeturn0search3�?



---



## 2. System Overview



### 2.1 Context

- Data sources: university sites, visa pages, FAQs, PDFs (curated & permitted).

- Components: Ingestion service, Index service (vector + lexical), Query API (FastAPI), Conversation service (optional Rasa), Generation service (SiliconFlow), Admin console (docs, prompts), Observability stack.



### 2.2 High‑Level Flow

1) Ingest & normalize documents �?2) Chunk & embed �?3) Index (dense+lexical) �?4) Query (intent & slot capture) �?5) Retrieve hybrid top‑k �?6) Rerank �?7) Compose prompt with citations �?8) SiliconFlow generate �?9) Post‑processing (citation mapping, translation, safety) �?10) Return answer + sources.



---



## 3. Functional Requirements



### 3.1 Ingestion & Curation �?Status: Completed

FR‑ING�?: The system shall allow authorized users to upload and update documents (PDF, DOCX, HTML, TXT) with language metadata and source URL.  

FR‑ING�?: The system shall normalize text (OCR optional), remove boilerplate, and keep paragraph/page anchors.  

FR‑ING�?: The system shall version each corpus snapshot and support rollback to previous versions.  

FR‑ING�?: The system shall tag documents by domain (admissions/visa/fees/scholarship) and freshness date.



### 3.2 Chunking & Indexing �?Status: Completed

FR‑IDX�?: The system shall split documents into semantically coherent chunks with overlap and store chunk‑level metadata (doc id, page, section).  

FR‑IDX�?: The system shall compute dense embeddings and index them in a vector store; it shall also index lexical terms (BM25 or equivalent) for hybrid search. citeturn0search7�? 

FR‑IDX�?: The system shall maintain index rebuild jobs when corpus changes and complete within SLOs (see §5).  

FR‑IDX�?: The system shall expose an index‑health endpoint (documents, chunks, last build, errors).



### 3.3 Query & Dialogue �?Status: In Progress

FR‑DIA�?: The system shall capture key slots (e.g., target country, degree level, GPA/IELTS, budget, timeframe) via guided prompts/forms before querying. citeturn0search3�? 

FR‑DIA�?: The system shall support both free‑text Q&A and structured checklists (e.g., “documents required�?.  

FR‑DIA�?: The system shall support bilingual input/output (ZH/EN) and permit language switch mid‑session.  

FR‑DIA�?: The system shall persist per‑session slots and allow user correction (“edit my IELTS to 6.5�?.



### 3.4 Retrieval & Reranking �?Status: Completed

FR‑RET�?: The system shall retrieve top‑k chunks via **hybrid retrieval** (dense+lexical) and merge results. citeturn0search7�? 

FR‑RET�?: The system shall apply a reranker to reorder candidates for maximum relevance (cross‑encoder/LLM). citeturn0search1�? 

FR‑RET�?: The system shall return at least `k_cite` chunks sufficient to support cited answers.  

FR‑RET�?: The system shall degrade gracefully if the reranker is unavailable (fall back to dense or lexical only).





### 3.5 Advanced conversational Conversational UX -- Status: Planned
FR-UX1 *(Completed Dec 2025)*: The frontend shall implement a three-pane layout (conversation list, transcript, context rail) with responsive slide-over behavior for tablet/mobile viewports (>=1280px fixed, 768-1279px collapsible, <768px stacked).  
FR-UX2 *(Completed Dec 2025)*: The system shall support streaming responses via Server-Sent Events when the client calls `POST /v1/query?stream=true` with `Accept: text/event-stream`, emitting `chunk`, `citations`, `completed`, and `error` events as defined in docs/frontend.md.  
FR-UX3 *(Completed Dec 2025)*: While streaming, the UI shall render token-level updates with a persistent "Stop generating" control that aborts the outstanding HTTP request and shows an inline "[Generation stopped]" notice.  
FR-UX4 *(Completed Dec 2025; auth sync pending)*: Conversation management shall include pin/unpin, rename, search, archive, and soft delete capabilities, persisting state per authenticated user once auth is enabled; unauthenticated sessions shall continue to store state locally.  
FR-UX5 *(Partially completed Dec 2025; richer rail pending)*: Each assistant message shall display timestamp, language badge, low-confidence indicator (based on `diagnostics.low_confidence`), and inline citation badges that open detailed cards in the context rail.  
FR-UX6 *(Completed Dec 2025)*: Users shall be able to submit per-message feedback (thumbs up/down with optional comment) to a feedback endpoint for analytics.  
FR-UX7 *(Completed Dec 2025)*: The composer shall expose advanced controls (language, explain-like-new, `top_k`, `k_cite`) via a collapsible panel, support keyboard shortcuts (Ctrl/Cmd+Enter submit, Shift+Enter newline), and display backend-provided slot suggestion chips.  
FR-UX8: The UI shall offer a user settings drawer to configure preferred language, default retrieval parameters, retention window, and theme; these preferences must sync with authenticated profiles when auth becomes available and fall back to local storage otherwise.  
FR-UX9 *(Partially completed Dec 2025)*: Accessibility requirements include a high-contrast theme option, ARIA live regions for streaming updates, focus-visible styles for all interactive elements, and WCAG-compliant color contrast.  

### 3.5 Generation & Post‑Processing �?Status: In Progress

FR‑GEN�?: The system shall call **SiliconFlow Chat Completions** with controllable parameters (model, temperature, top_p, max_tokens, stop). citeturn0search10turn0search5�? 

FR‑GEN�?: The system shall construct prompts that include user slots, top‑n chunks, and citation markers.  

FR‑GEN�?: The system shall map model references back to canonical citations (URL, title, section).  

FR‑GEN�?: The system shall support streaming tokens and handle API errors/retries with backoff. citeturn0search10�? 

FR‑GEN�? *(Completed Oct 2025)*: The system shall support bilingual output and optional “explain like I’m new�?reformulation.



### 3.6 Citation & Verification �?Status: In Progress

FR‑CIT�?: Every final answer shall include clickable citations (at least 1; typically 2�?) that resolve to source passages.  

FR‑CIT‑2 *(Completed Dec 2025)*: The system shall provide a “view quoted passage” toggle with highlighting at chunk granularity.  

FR‑CIT�?: The system shall show “last verified on <date>�?for time‑sensitive policies and allow manual re‑verify.



### 3.7 Admin & Governance �?Status: In Progress

FR-ADM-1 *(Completed Dec 2025)*: Admin users shall manage sources, prompts, slot schema, retrieval settings, and stop-list.

FR-ADM-2 *(Completed Dec 2025)*: Admin shall view ingestion/index job history, failures, and re-run jobs.

FR-ADM-3 *(Completed Dec 2025)*: Admin shall define answer templates for common tasks (eligibility, documents, timelines).

FR-ADM-4: Admin shall export audit logs (queries, citations served, errors) with privacy safeguards (see §6). *(审计写入+导出 `/v1/admin/audit` 已上线�?*



### 3.8 Observability & Ops �?Status: In Progress

FR‑OBS�? *(Completed Oct 2025)*: The system shall record latency metrics for: retrieval, rerank, generation, and end‑to‑end.  

FR‑OBS�? *(Completed Oct 2025)*: The system shall record quality counters: empty retrieval, low‑confidence answer, citation coverage.  

FR‑OBS�? *(Completed Oct 2025)*: The system shall provide a red/amber/green service dashboard and alert rules on major SLO breaches.



### 3.10 Document & Media Uploads -- Status: Planned
FR-UP1: End users shall attach PDF and image files (JPEG/PNG/WebP, up to 10 MB each) through the chat composer; the UI must show progress (queued, uploading, scanned, attached) and allow removal before submission.  
FR-UP2: The frontend shall request short-lived signed URLs, upload files directly to storage, then call the backend with metadata (filename, mime type, sha256, page count) so ingestion/OCR pipelines can run.  
FR-UP3: All uploads shall pass antivirus and PII scans as described in IR_TP055146; audit logs must record uploader identity, purpose, retention selection, and counsellor access history.  
FR-UP4: Attachments shall appear inside the context rail with previews (page thumbnails or extracted slot hints) so counsellors can reference them mid-session.  
FR-UP5: Retention defaults to 30 days unless the user explicitly opts to save artefacts; deletion requests shall purge hot storage, backups, and analytics copies.  

### 3.9 Internationalization & Accessibility �?Status: Not Started

FR‑I18N *(In Progress Dec 2025)*: All UI strings shall be localized (ZH/EN) with a single source of truth.  

FR‑A11Y *(In Progress Dec 2025)*: The web app shall be keyboard navigable and meet basic contrast/ARIA guidelines.



---



## 4. External Interfaces



### 4.1 API (FastAPI) �?Status: In Progress

- `POST /api/query` �?body: { text, lang, slots? } �?returns: { answer, citations[], diagnostics }  

- `POST /api/ingest` �?body: { file/url, meta } �?returns: { doc_id }  

- `POST /api/reindex` �?body: { scope } �?returns: { job_id }  

- `GET /api/health` �?returns: status, build info, index metrics.



### 4.2 SiliconFlow �?Status: Completed

- Endpoint: `POST /v1/chat/completions` (Bearer auth). Controls: `model`, `temperature`, `top_p`, `stop`, `stream`, etc. Error/429 handling with retry/backoff. citeturn0search10turn0search5�?



### 4.3 Admin UI �?Status: Not Started

- Source CRUD, prompt editor, slot schema editor, feature flags (reranker on/off), dashboards.



---



## 5. Non‑Functional Requirements (NFRs)



### 5.1 Performance & SLOs �?Status: In Progress

- P50/P95 latencies (desktop on campus network):  

  - Retrieval �?300/800 ms; Rerank �?300/900 ms; Generation first token �?1.5/3 s; E2E �?3/7 s.  

- Index builds: incremental update < 10 min for 5k pages; full rebuild overnight windows.

> Rationale: Hybrid retrieval + rerank improves relevance; streaming/composable pipeline controls tail latency. citeturn0search7turn0search1�?



### 5.2 Reliability & Availability

- 99.5% monthly availability for query path; graceful degradation (no reranker �?still answer with warnings).  

- Idempotent ingest jobs; at‑least‑once reindex with dedupe.



### 5.3 Security & Privacy (PDPA)

- Consent & notice for any personal data in conversations; store minimal necessary data.  

- Security principle: protect personal data from loss/misuse/unauthorized access.  

- Retention principle: do not keep data longer than necessary; configurable retention (e.g., 30/90 days). citeturn0search13turn0search17�? 

- Log redaction; no sensitive fields in analytics.  

- Access control: role‑based (admin/counsellor/viewer); API keys rotated and least‑privilege.  

- Data residency: choose region‑appropriate storage if required by institution policy.  

- Third‑party: SiliconFlow & other services documented with DPAs where applicable.  

> Background: Malaysia PDPA in force; follow 7 principles (notice/choice, disclosure, security, retention, data integrity, access). citeturn0search4turn0search17�?



### 5.4 Maintainability & Modularity -- Status: In Progress

- Components (ingest/index/query/rerank/generate) deployable independently.  

- Configuration via ENV/`configs/*.yaml`; no secrets in repo.  

- Manifest, prompt, and document lookup caches reduce disk churn; multi-worker persistence deemed out of scope for the current release.  



### 5.5 Observability -- Status: In Progress

- Delivered ingestion phase timers and reranker counter metrics (2025-11-02).  

- Metrics: latency, error rate, empty-hit rate, rerank coverage, citation count, API retries.  

- Reranker resilience telemetry: `rerank_retry::*`, `rerank_circuit::*`, `rerank_fallback::*` expose retry counts, circuit state, and fallback frequency for dashboards.  

- Tracing: request id spans through retrieval��rerank��generation.  

- Logs: structured JSON with correlation ids.  

- Next: publish dashboard templates and OTLP tracing runbooks (metrics exporter deferred).  



### 5.6 Compatibility �?Status: Not Started

- Browsers: latest Chrome/Edge/Safari/Firefox; responsive mobile web.  

- API stability: semantic versioning for public endpoints.



---



## 6. Data Requirements �?Status: In Progress



DR�?: Store only necessary session data (query text, slots, selected citations, minimal diagnostics).  

DR�?: Pseudonymize session ids; purge per retention policy; allow export/delete upon request. citeturn0search13�? 

DR�?: Content store keeps original docs, chunked texts, embeddings, and metadata with versioning.  

DR�?: Maintain provenance for every chunk (URL, title, section, timestamp).



---



## 7. Constraints, Assumptions, Dependencies



- **Constraints**: budget (cloud API usage), institutional firewalls, content licenses; rely on SiliconFlow availability limits. citeturn0search10�? 

- **Assumptions**: curated sources are permitted for indexing; admins keep corpus up‑to‑date.  

- **Dependencies**: vector DB (Milvus/Qdrant/FAISS), lexical index, object storage; Rasa optional for guided forms. citeturn0search3�? 

- **Prototype Support**: Dify used for prototyping/ops integration where helpful. citeturn0search2�?



---



## 8. Acceptance Criteria (Samples)



- Given an eligibility query with complete slots, the system returns an answer �?5 s with �?2 citations linking to the correct passages.  

- When reranker is disabled, the system still returns a grounded answer with a “reduced‑confidence�?banner.  

- For a changed policy (updated doc), a nightly refresh reflects new content and citations within 24 h.  

- Admin can upload a new PDF, trigger reindex, and see it cited in results.  

- PDPA: a user can request deletion of their session data; system confirms purge within SLA.

- Streaming queries invoked with `/v1/query?stream=true` emit incremental tokens within 0.5 s, and the client stop button cancels the stream without leaving orphaned tasks.  

- Pinned or archived conversations remain available after page refresh for authenticated users (server persistence) and for the current browser when unauthenticated.

- Uploaded PDFs/images show scans completed state before submission, are referenceable in the context rail, and honor the default 30-day retention (auto purge upon delete requests).



---



## 9. Test Plan Outline �?Status: In Progress



- Unit: ingestion parsers, chunker, retriever, reranker mock, citation mapper.  

- Integration: end‑to‑end query with stubbed SiliconFlow, then with live key (rate‑limited).  

- Data QA: citation targets match passages; broken links alerting.  

- NFR: latency benchmarks with corpora sizes (S/M/L); chaos tests for reranker outage.  

- Security: authZ, rate‑limit, log redaction, retention purge jobs.



---



## 10. Roadmap & Milestones (suggested) �?Status: In Progress



- M1 (Week 1�?): Corpus curation + ingest pipeline; baseline dense retrieval; SiliconFlow integration.  

- M2 (Week 3�?): Hybrid retrieval + citations; bilingual UI; admin basics.  

- M3 (Week 5�?): Reranker + observability; PDPA data controls; nightly refresh.  

- M4 (Week 7�?): Guided forms/slots; quality review; UX polish; pilot.  



---



## 11. Traceability



| Req ID | Feature | Tests | Notes |

|---|---|---|---|

| FR‑RET�? | Hybrid retrieval | `tests/integration/test_query_hybrid.py::test_topk` | BM25 + dense merge |

| FR‑RET�? | Reranker | `tests/integration/test_rerank.py::test_ordering` | Cross‑encoder/LLM |

| FR‑GEN�? | SiliconFlow call | `tests/unit/test_gen.py::test_params` | params/stream/errors |

| FR‑CIT�? | Citations | `tests/integration/test_citation.py::test_links` | chunk anchors |

| NFR‑PERF | Latency | bench scripts | P95 gates |



---



## 12. Open Questions



- Which countries/programs are priority at launch?  

- Exact retention window defaults (30 vs 90 days)?  

- Require login for students or anonymous sessions suffice?  

- Which reranker (model choice) and cost budget per 1k queries?  





