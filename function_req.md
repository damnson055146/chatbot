# function_req.md â€?Studyâ€‘Abroad RAG Assistant (FYP)



> This Functional Requirements document follows wellâ€‘recognized SRS guidance (ISO/IEC/IEEE 29148) for structure and clarity. It specifies *what* the system shall do and the quality attributes it shall meet. References are included where relevant to practices in RAG, dialogue management, and Malaysia PDPA compliance.  



---



## 1. Introduction



### 1.1 Purpose

Define the functional and nonâ€‘functional requirements for a bilingual (ZH/EN) Studyâ€‘Abroad Consultation Assistant that answers policy/process questions with verifiable citations, using a Retrievalâ€‘Augmented Generation (RAG) backend and SiliconFlow API for model inference.



### 1.2 Scope

- Channels: web app (desktop/mobile), later extensible to API/SDK.

- Core: ingestâ†’chunkâ†’indexâ†’retrieveâ†’rerankâ†’generateâ†’citeâ†’escalate.

- Users: Students, counsellors, administrators.

- Outâ€‘ofâ€‘scope (initial): payments, agentic webâ€‘browsing at runtime, longâ€‘term user profiling beyond session.



### 1.3 References

- ISO/IEC/IEEE 29148 SRS concepts & attributes of good requirements. îˆ€citeîˆ‚turn0search11îˆ‚turn0search19îˆ‚turn0search6îˆ? 

- Haystack docs/blog (hybrid retrieval, reranking value in RAG). îˆ€citeîˆ‚turn0search7îˆ‚turn0search12îˆ‚turn0search1îˆ? 

- Dify knowledge base & external sources for RAG prototyping/ops. îˆ€citeîˆ‚turn0search2îˆ‚turn0search21îˆ? 

- Rasa slots/forms for structured dialogue. îˆ€citeîˆ‚turn0search3îˆ‚turn0search8îˆ? 

- SiliconFlow Chat Completions API. îˆ€citeîˆ‚turn0search10îˆ‚turn0search5îˆ‚turn0search18îˆ? 

- Malaysia PDPA (principles; consent, security, retention). îˆ€citeîˆ‚turn0search4îˆ‚turn0search13îˆ‚turn0search17îˆ?



### 1.4 Definitions

- **RAG**: Retrieve topâ€‘k source chunks to ground LLM answers; return citations.

- **Hybrid retrieval**: BM25 (keyword) + dense embeddings; merge+rank. îˆ€citeîˆ‚turn0search7îˆ? 

- **Reranking**: Crossâ€‘encoder or LLM ranker reorders retrieved chunks for relevance. îˆ€citeîˆ‚turn0search1îˆ? 

- **Slot/Form**: Dialogue state fields collected via guided turns. îˆ€citeîˆ‚turn0search3îˆ?



---



## 2. System Overview



### 2.1 Context

- Data sources: university sites, visa pages, FAQs, PDFs (curated & permitted).

- Components: Ingestion service, Index service (vector + lexical), Query API (FastAPI), Conversation service (optional Rasa), Generation service (SiliconFlow), Admin console (docs, prompts), Observability stack.



### 2.2 Highâ€‘Level Flow

1) Ingest & normalize documents â†?2) Chunk & embed â†?3) Index (dense+lexical) â†?4) Query (intent & slot capture) â†?5) Retrieve hybrid topâ€‘k â†?6) Rerank â†?7) Compose prompt with citations â†?8) SiliconFlow generate â†?9) Postâ€‘processing (citation mapping, translation, safety) â†?10) Return answer + sources.



---



## 3. Functional Requirements



### 3.1 Ingestion & Curation â€?Status: Completed

FRâ€‘INGâ€?: The system shall allow authorized users to upload and update documents (PDF, DOCX, HTML, TXT) with language metadata and source URL.  

FRâ€‘INGâ€?: The system shall normalize text (OCR optional), remove boilerplate, and keep paragraph/page anchors.  

FRâ€‘INGâ€?: The system shall version each corpus snapshot and support rollback to previous versions.  

FRâ€‘INGâ€?: The system shall tag documents by domain (admissions/visa/fees/scholarship) and freshness date.



### 3.2 Chunking & Indexing â€?Status: Completed

FRâ€‘IDXâ€?: The system shall split documents into semantically coherent chunks with overlap and store chunkâ€‘level metadata (doc id, page, section).  

FRâ€‘IDXâ€?: The system shall compute dense embeddings and index them in a vector store; it shall also index lexical terms (BM25 or equivalent) for hybrid search. îˆ€citeîˆ‚turn0search7îˆ? 

FRâ€‘IDXâ€?: The system shall maintain index rebuild jobs when corpus changes and complete within SLOs (see Â§5).  

FRâ€‘IDXâ€?: The system shall expose an indexâ€‘health endpoint (documents, chunks, last build, errors).



### 3.3 Query & Dialogue â€?Status: In Progress

FRâ€‘DIAâ€?: The system shall capture key slots (e.g., target country, degree level, GPA/IELTS, budget, timeframe) via guided prompts/forms before querying. îˆ€citeîˆ‚turn0search3îˆ? 

FRâ€‘DIAâ€?: The system shall support both freeâ€‘text Q&A and structured checklists (e.g., â€œdocuments requiredâ€?.  

FRâ€‘DIAâ€?: The system shall support bilingual input/output (ZH/EN) and permit language switch midâ€‘session.  

FRâ€‘DIAâ€?: The system shall persist perâ€‘session slots and allow user correction (â€œedit my IELTS to 6.5â€?.



### 3.4 Retrieval & Reranking â€?Status: Completed

FRâ€‘RETâ€?: The system shall retrieve topâ€‘k chunks via **hybrid retrieval** (dense+lexical) and merge results. îˆ€citeîˆ‚turn0search7îˆ? 

FRâ€‘RETâ€?: The system shall apply a reranker to reorder candidates for maximum relevance (crossâ€‘encoder/LLM). îˆ€citeîˆ‚turn0search1îˆ? 

FRâ€‘RETâ€?: The system shall return at least `k_cite` chunks sufficient to support cited answers.  

FRâ€‘RETâ€?: The system shall degrade gracefully if the reranker is unavailable (fall back to dense or lexical only).





### 3.5 Advanced conversational Conversational UX -- Status: Planned
FR-UX1: The frontend shall implement a three-pane layout (conversation list, transcript, context rail) with responsive slide-over behavior for tablet/mobile viewports (>=1280px fixed, 768-1279px collapsible, <768px stacked).  
FR-UX2: The system shall support streaming responses via Server-Sent Events when the client calls `POST /v1/query?stream=true` with `Accept: text/event-stream`, emitting `chunk`, `citations`, `completed`, and `error` events as defined in docs/frontend.md.  
FR-UX3: While streaming, the UI shall render token-level updates with a persistent "Stop generating" control that aborts the outstanding HTTP request and shows an inline "[Generation stopped]" notice.  
FR-UX4: Conversation management shall include pin/unpin, rename, search, archive, and soft delete capabilities, persisting state per authenticated user once auth is enabled; unauthenticated sessions shall continue to store state locally.  
FR-UX5: Each assistant message shall display timestamp, language badge, low-confidence indicator (based on `diagnostics.low_confidence`), and inline citation badges that open detailed cards in the context rail.  
FR-UX6: Users shall be able to submit per-message feedback (thumbs up/down with optional comment) to a feedback endpoint for analytics.  
FR-UX7: The composer shall expose advanced controls (language, explain-like-new, `top_k`, `k_cite`) via a collapsible panel, support keyboard shortcuts (Ctrl/Cmd+Enter submit, Shift+Enter newline), and display backend-provided slot suggestion chips.  
FR-UX8: The UI shall offer a user settings drawer to configure preferred language, default retrieval parameters, retention window, and theme; these preferences must sync with authenticated profiles when auth becomes available and fall back to local storage otherwise.  
FR-UX9: Accessibility requirements include a high-contrast theme option, ARIA live regions for streaming updates, focus-visible styles for all interactive elements, and WCAG-compliant color contrast.  

### 3.5 Generation & Postâ€‘Processing â€?Status: In Progress

FRâ€‘GENâ€?: The system shall call **SiliconFlow Chat Completions** with controllable parameters (model, temperature, top_p, max_tokens, stop). îˆ€citeîˆ‚turn0search10îˆ‚turn0search5îˆ? 

FRâ€‘GENâ€?: The system shall construct prompts that include user slots, topâ€‘n chunks, and citation markers.  

FRâ€‘GENâ€?: The system shall map model references back to canonical citations (URL, title, section).  

FRâ€‘GENâ€?: The system shall support streaming tokens and handle API errors/retries with backoff. îˆ€citeîˆ‚turn0search10îˆ? 

FRâ€‘GENâ€? *(Completed Oct 2025)*: The system shall support bilingual output and optional â€œexplain like Iâ€™m newâ€?reformulation.



### 3.6 Citation & Verification â€?Status: In Progress

FRâ€‘CITâ€?: Every final answer shall include clickable citations (at least 1; typically 2â€?) that resolve to source passages.  

FRâ€‘CITâ€?: The system shall provide a â€œview quoted passageâ€?toggle with highlighting at chunk granularity.  

FRâ€‘CITâ€?: The system shall show â€œlast verified on <date>â€?for timeâ€‘sensitive policies and allow manual reâ€‘verify.



### 3.7 Admin & Governance â€?Status: In Progress

FR-ADM-1 *(Completed Oct 2025)*: Admin users shall manage sources, prompts, slot schema, retrieval settings, and stop-list. *(Retrieval/slot write APIså®Œæˆï¼›sources/stop-list/promptç®¡ç†ä»å¾…å®ç°ã€?*

FR-ADM-2: Admin shall view ingestion/index job history, failures, and re-run jobs.

FR-ADM-3: Admin shall define answer templates for common tasks (eligibility, documents, timelines).

FR-ADM-4: Admin shall export audit logs (queries, citations served, errors) with privacy safeguards (see Â§6). *(å®¡è®¡å†™å…¥+å¯¼å‡º `/v1/admin/audit` å·²ä¸Šçº¿ã€?*



### 3.8 Observability & Ops â€?Status: In Progress

FRâ€‘OBSâ€? *(Completed Oct 2025)*: The system shall record latency metrics for: retrieval, rerank, generation, and endâ€‘toâ€‘end.  

FRâ€‘OBSâ€? *(Completed Oct 2025)*: The system shall record quality counters: empty retrieval, lowâ€‘confidence answer, citation coverage.  

FRâ€‘OBSâ€? *(Completed Oct 2025)*: The system shall provide a red/amber/green service dashboard and alert rules on major SLO breaches.



### 3.10 Document & Media Uploads -- Status: Planned
FR-UP1: End users shall attach PDF and image files (JPEG/PNG/WebP, up to 10 MB each) through the chat composer; the UI must show progress (queued, uploading, scanned, attached) and allow removal before submission.  
FR-UP2: The frontend shall request short-lived signed URLs, upload files directly to storage, then call the backend with metadata (filename, mime type, sha256, page count) so ingestion/OCR pipelines can run.  
FR-UP3: All uploads shall pass antivirus and PII scans as described in IR_TP055146; audit logs must record uploader identity, purpose, retention selection, and counsellor access history.  
FR-UP4: Attachments shall appear inside the context rail with previews (page thumbnails or extracted slot hints) so counsellors can reference them mid-session.  
FR-UP5: Retention defaults to 30 days unless the user explicitly opts to save artefacts; deletion requests shall purge hot storage, backups, and analytics copies.  

### 3.9 Internationalization & Accessibility â€?Status: Not Started

FRâ€‘I18Nâ€?: All UI strings shall be localized (ZH/EN) with a single source of truth.  

FRâ€‘A11Yâ€?: The web app shall be keyboard navigable and meet basic contrast/ARIA guidelines.



---



## 4. External Interfaces



### 4.1 API (FastAPI) â€?Status: In Progress

- `POST /api/query` â€?body: { text, lang, slots? } â†?returns: { answer, citations[], diagnostics }  

- `POST /api/ingest` â€?body: { file/url, meta } â†?returns: { doc_id }  

- `POST /api/reindex` â€?body: { scope } â†?returns: { job_id }  

- `GET /api/health` â€?returns: status, build info, index metrics.



### 4.2 SiliconFlow â€?Status: Completed

- Endpoint: `POST /v1/chat/completions` (Bearer auth). Controls: `model`, `temperature`, `top_p`, `stop`, `stream`, etc. Error/429 handling with retry/backoff. îˆ€citeîˆ‚turn0search10îˆ‚turn0search5îˆ?



### 4.3 Admin UI â€?Status: Not Started

- Source CRUD, prompt editor, slot schema editor, feature flags (reranker on/off), dashboards.



---



## 5. Nonâ€‘Functional Requirements (NFRs)



### 5.1 Performance & SLOs â€?Status: In Progress

- P50/P95 latencies (desktop on campus network):  

  - Retrieval â‰?300/800 ms; Rerank â‰?300/900 ms; Generation first token â‰?1.5/3 s; E2E â‰?3/7 s.  

- Index builds: incremental update < 10 min for 5k pages; full rebuild overnight windows.

> Rationale: Hybrid retrieval + rerank improves relevance; streaming/composable pipeline controls tail latency. îˆ€citeîˆ‚turn0search7îˆ‚turn0search1îˆ?



### 5.2 Reliability & Availability

- 99.5% monthly availability for query path; graceful degradation (no reranker â†?still answer with warnings).  

- Idempotent ingest jobs; atâ€‘leastâ€‘once reindex with dedupe.



### 5.3 Security & Privacy (PDPA)

- Consent & notice for any personal data in conversations; store minimal necessary data.  

- Security principle: protect personal data from loss/misuse/unauthorized access.  

- Retention principle: do not keep data longer than necessary; configurable retention (e.g., 30/90 days). îˆ€citeîˆ‚turn0search13îˆ‚turn0search17îˆ? 

- Log redaction; no sensitive fields in analytics.  

- Access control: roleâ€‘based (admin/counsellor/viewer); API keys rotated and leastâ€‘privilege.  

- Data residency: choose regionâ€‘appropriate storage if required by institution policy.  

- Thirdâ€‘party: SiliconFlow & other services documented with DPAs where applicable.  

> Background: Malaysia PDPA in force; follow 7 principles (notice/choice, disclosure, security, retention, data integrity, access). îˆ€citeîˆ‚turn0search4îˆ‚turn0search17îˆ?



### 5.4 Maintainability & Modularity -- Status: In Progress

- Components (ingest/index/query/rerank/generate) deployable independently.  

- Configuration via ENV/`configs/*.yaml`; no secrets in repo.  

- Manifest, prompt, and document lookup caches reduce disk churn; multi-worker persistence deemed out of scope for the current release.  



### 5.5 Observability -- Status: In Progress

- Delivered ingestion phase timers and reranker counter metrics (2025-11-02).  

- Metrics: latency, error rate, empty-hit rate, rerank coverage, citation count, API retries.  

- Reranker resilience telemetry: `rerank_retry::*`, `rerank_circuit::*`, `rerank_fallback::*` expose retry counts, circuit state, and fallback frequency for dashboards.  

- Tracing: request id spans through retrieval¡úrerank¡úgeneration.  

- Logs: structured JSON with correlation ids.  

- Next: publish dashboard templates and OTLP tracing runbooks (metrics exporter deferred).  



### 5.6 Compatibility â€?Status: Not Started

- Browsers: latest Chrome/Edge/Safari/Firefox; responsive mobile web.  

- API stability: semantic versioning for public endpoints.



---



## 6. Data Requirements â€?Status: In Progress



DRâ€?: Store only necessary session data (query text, slots, selected citations, minimal diagnostics).  

DRâ€?: Pseudonymize session ids; purge per retention policy; allow export/delete upon request. îˆ€citeîˆ‚turn0search13îˆ? 

DRâ€?: Content store keeps original docs, chunked texts, embeddings, and metadata with versioning.  

DRâ€?: Maintain provenance for every chunk (URL, title, section, timestamp).



---



## 7. Constraints, Assumptions, Dependencies



- **Constraints**: budget (cloud API usage), institutional firewalls, content licenses; rely on SiliconFlow availability limits. îˆ€citeîˆ‚turn0search10îˆ? 

- **Assumptions**: curated sources are permitted for indexing; admins keep corpus upâ€‘toâ€‘date.  

- **Dependencies**: vector DB (Milvus/Qdrant/FAISS), lexical index, object storage; Rasa optional for guided forms. îˆ€citeîˆ‚turn0search3îˆ? 

- **Prototype Support**: Dify used for prototyping/ops integration where helpful. îˆ€citeîˆ‚turn0search2îˆ?



---



## 8. Acceptance Criteria (Samples)



- Given an eligibility query with complete slots, the system returns an answer â‰?5 s with â‰?2 citations linking to the correct passages.  

- When reranker is disabled, the system still returns a grounded answer with a â€œreducedâ€‘confidenceâ€?banner.  

- For a changed policy (updated doc), a nightly refresh reflects new content and citations within 24 h.  

- Admin can upload a new PDF, trigger reindex, and see it cited in results.  

- PDPA: a user can request deletion of their session data; system confirms purge within SLA.

- Streaming queries invoked with `/v1/query?stream=true` emit incremental tokens within 0.5 s, and the client stop button cancels the stream without leaving orphaned tasks.  

- Pinned or archived conversations remain available after page refresh for authenticated users (server persistence) and for the current browser when unauthenticated.

- Uploaded PDFs/images show scans completed state before submission, are referenceable in the context rail, and honor the default 30-day retention (auto purge upon delete requests).



---



## 9. Test Plan Outline â€?Status: In Progress



- Unit: ingestion parsers, chunker, retriever, reranker mock, citation mapper.  

- Integration: endâ€‘toâ€‘end query with stubbed SiliconFlow, then with live key (rateâ€‘limited).  

- Data QA: citation targets match passages; broken links alerting.  

- NFR: latency benchmarks with corpora sizes (S/M/L); chaos tests for reranker outage.  

- Security: authZ, rateâ€‘limit, log redaction, retention purge jobs.



---



## 10. Roadmap & Milestones (suggested) â€?Status: In Progress



- M1 (Week 1â€?): Corpus curation + ingest pipeline; baseline dense retrieval; SiliconFlow integration.  

- M2 (Week 3â€?): Hybrid retrieval + citations; bilingual UI; admin basics.  

- M3 (Week 5â€?): Reranker + observability; PDPA data controls; nightly refresh.  

- M4 (Week 7â€?): Guided forms/slots; quality review; UX polish; pilot.  



---



## 11. Traceability



| Req ID | Feature | Tests | Notes |

|---|---|---|---|

| FRâ€‘RETâ€? | Hybrid retrieval | `tests/integration/test_query_hybrid.py::test_topk` | BM25 + dense merge |

| FRâ€‘RETâ€? | Reranker | `tests/integration/test_rerank.py::test_ordering` | Crossâ€‘encoder/LLM |

| FRâ€‘GENâ€? | SiliconFlow call | `tests/unit/test_gen.py::test_params` | params/stream/errors |

| FRâ€‘CITâ€? | Citations | `tests/integration/test_citation.py::test_links` | chunk anchors |

| NFRâ€‘PERF | Latency | bench scripts | P95 gates |



---



## 12. Open Questions



- Which countries/programs are priority at launch?  

- Exact retention window defaults (30 vs 90 days)?  

- Require login for students or anonymous sessions suffice?  

- Which reranker (model choice) and cost budget per 1k queries?  





