from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, UTC
from pathlib import Path
from typing import List

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from starlette.middleware import Middleware
from fastapi.staticfiles import StaticFiles

from src.agents.rag_agent import answer_query, answer_query_sse
from src.pipelines.ingest import ingest_content
from src.schemas.models import (
    AdminConfigResponse,
    AdminJobHistoryResponse,
    AdminJobEntry,
    AdminRetrievalSettings,
    AdminSlotConfig,
    AdminSource,
    AdminSourceUpsertRequest,
    AdminSourceUpsertResponse,
    AdminSourceDeleteResponse,
    AdminTemplate,
    AdminTemplateUpsertRequest,
    AdminTemplateUpsertResponse,
    AdminTemplateDeleteResponse,
    AdminPrompt,
    AdminPromptUpsertRequest,
    AdminPromptUpsertResponse,
    AdminPromptDeleteResponse,
    AdminUpdateRetrievalRequest,
    AdminUpdateRetrievalResponse,
    AdminUpdateSlotsRequest,
    AdminUpdateSlotsResponse,
    AdminAuditResponse,
    AdminAuditEntry,
    ChunkDetail,
    ChunkDetailResponse,
    Document,
    HighlightSpan,
    IndexHealth,
    IngestRequest,
    IngestResponse,
    QueryRequest,
    QueryResponse,
    ServiceStatusResponse,
    ServiceStatusMetric,
    SessionListResponse,
    SessionStateResponse,
    SlotCatalogResponse,
    SlotSchema,
    UploadInitResponse,
    UploadRecord,
)
from src.schemas.slots import normalize_slot_name, slot_definitions, update_slot_definitions, _slot_from_dict, serialize_slots, list_slots
from src.utils.env import load_env_file
from src.utils.index_manager import get_index_manager
from src.utils.logging import get_logger
from src.utils.observability import get_metrics, get_service_status_snapshot
from src.utils.tracing import configure_tracing
from src.utils.security import get_rate_limiter, verify_api_key, resolve_actor_name
from src.utils.session import get_session_store, reset_session_store
from src.utils.storage import (
    get_document,
    load_chunk_by_id,
    load_manifest,
    load_slots_config,
    save_slots_config,
    serialize_slot_definition,
    save_retrieval_settings,
    upsert_document,
    delete_document,
    load_stop_list,
    save_stop_list,
    load_templates,
    upsert_template,
    delete_template,
    load_prompts,
    upsert_prompt,
    delete_prompt,
    set_active_prompt,
    get_active_prompt,
    append_audit_log,
    read_audit_logs,
    load_jobs_history,
    load_upload_record,
    save_upload_file,
    UPLOADS_DIR,
)

load_env_file()

raw_origins = os.getenv("CORS_ALLOW_ORIGINS", "*")
raw_credentials = os.getenv("CORS_ALLOW_CREDENTIALS", "true")

if raw_origins.strip() == "*":
    cors_origins = ["*"]
else:
    cors_origins = [entry.strip() for entry in raw_origins.split(",") if entry.strip()]

cors_allow_credentials = raw_credentials.strip().lower() in {"1", "true", "yes"}

if cors_origins == ["*"] and cors_allow_credentials:
    cors_allow_credentials = False

cors_middleware = Middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

log = get_logger(__name__)
configure_tracing()

app = FastAPI(title="Study Abroad RAG Assistant API", version="0.1.0", middleware=[cors_middleware])


def _resolve_cors_origin(request_origin: str | None) -> str | None:
    if not request_origin:
        return None
    if cors_origins == ["*"]:
        return "*"
    if request_origin in cors_origins:
        return request_origin
    return None


def _apply_cors_headers(response: Response, request: Request, *, methods: str | None = None) -> None:
    origin = request.headers.get("origin")
    allow_origin = _resolve_cors_origin(origin)
    if allow_origin:
        response.headers["Access-Control-Allow-Origin"] = allow_origin
        if cors_allow_credentials and allow_origin != "*":
            response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers.setdefault("Vary", "Origin")
    if methods:
        response.headers["Access-Control-Allow-Methods"] = methods
    acr_headers = request.headers.get("Access-Control-Request-Headers")
    if acr_headers:
        response.headers["Access-Control-Allow-Headers"] = acr_headers

MAX_UPLOAD_BYTES = int(os.getenv("UPLOAD_MAX_BYTES", str(10 * 1024 * 1024)))
ALLOWED_UPLOAD_MIME = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
}

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")


def normalize_source_id(value: str) -> str:
    return "-".join(value.strip().split()).lower()


def _upload_download_url(storage_filename: str) -> str:
    return f"/uploads/{storage_filename}"


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    metrics = get_metrics()
    request_id = uuid.uuid4().hex
    start = time.perf_counter()
    if request.method == "OPTIONS":
        response = Response(status_code=204)
        methods = request.headers.get("Access-Control-Request-Method", "GET,POST,PUT,PATCH,DELETE,OPTIONS")
        _apply_cors_headers(response, request, methods=methods)
        if "Access-Control-Allow-Headers" not in response.headers:
            response.headers["Access-Control-Allow-Headers"] = request.headers.get(
                "Access-Control-Request-Headers", "*"
            )
        response.headers.setdefault("Access-Control-Max-Age", "86400")
        duration_ms = (time.perf_counter() - start) * 1000
        metrics.record(request.url.path, duration_ms)
        log.info(
            "api_request",
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
            request_id=request_id,
        )
        response.headers["X-Request-ID"] = request_id
        return response
    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        metrics.record(request.url.path, duration_ms)
        log.error(
            "api_request_failed",
            path=request.url.path,
            duration_ms=duration_ms,
            request_id=request_id,
            error=str(exc),
        )
        raise
    duration_ms = (time.perf_counter() - start) * 1000
    metrics.record(request.url.path, duration_ms)
    _apply_cors_headers(response, request)
    log.info(
        "api_request",
        path=request.url.path,
        status=response.status_code,
        duration_ms=duration_ms,
        request_id=request_id,
    )
    response.headers["X-Request-ID"] = request_id
    return response


def get_manager():
    return get_index_manager()


def _rate_limit_identity(api_key: str | None, path: str) -> str:
    identity = (api_key or 'anonymous').strip() or 'anonymous'
    return f"{identity}:{path}"



def require_auth(
    request: Request,
    api_key: str | None = Header(default=None, alias="X-API-Key"),
    limiter=Depends(get_rate_limiter),
) -> str | None:
    verify_api_key(api_key)
    limiter.allow(_rate_limit_identity(api_key, request.url.path))
    return api_key


def _slot_catalog_payload(language: str | None = None) -> SlotCatalogResponse:
    items = [
        SlotSchema(
            name=slot["name"],
            description=slot["description"],
            required=slot["required"],
            prompt=slot.get("prompt"),
            prompt_zh=slot.get("prompt_zh"),
            value_type=slot["value_type"],
            choices=slot.get("choices"),
            min_value=slot.get("min_value"),
            max_value=slot.get("max_value"),
        )
        for slot in list_slots(language)
    ]
    return SlotCatalogResponse(slots=items)


@app.get("/v1/slots", response_model=SlotCatalogResponse)
def slot_catalog(
    request: Request,
    lang: str | None = Query(default=None, alias="lang"),
    api_key: str | None = Depends(require_auth),
) -> SlotCatalogResponse:
    if lang:
        primary_lang = lang
    else:
        accept_language = request.headers.get("Accept-Language", "en")
        primary_lang = accept_language.split(",")[0].strip() if accept_language else "en"
    return _slot_catalog_payload(primary_lang)


@app.get("/v1/session", response_model=SessionListResponse)
def list_sessions(
    api_key: str | None = Depends(require_auth),
) -> SessionListResponse:
    store = get_session_store()
    return SessionListResponse(sessions=store.list_sessions())


@app.get("/v1/session/{session_id}", response_model=SessionStateResponse)
def session_detail(
    session_id: str,
    api_key: str | None = Depends(require_auth),
) -> SessionStateResponse:
    store = get_session_store()
    payload = store.export(session_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return payload


@app.delete("/v1/session/{session_id}", status_code=204)
def session_delete(
    session_id: str,
    api_key: str | None = Depends(require_auth),
) -> Response:
    store = get_session_store()
    if store.get(session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    store.clear(session_id)
    return Response(status_code=204)


@app.post("/v1/query")
async def query_endpoint(
    request: Request,
    payload: QueryRequest,
    stream: bool = Query(default=False),
    api_key: str | None = Depends(require_auth),
):
    if stream:
        accept = request.headers.get("Accept", "")
        if "text/event-stream" not in accept:
            raise HTTPException(status_code=406, detail="Streaming requires Accept: text/event-stream")
        return StreamingResponse(answer_query_sse(payload), media_type="text/event-stream")
    return await answer_query(payload)


@app.post("/v1/upload", response_model=UploadInitResponse)
async def upload_media(
    file: UploadFile = File(...),
    purpose: str = "chat",
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> UploadInitResponse:
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file is not allowed")
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 10 MB limit")
    mime_type = (file.content_type or "application/octet-stream").lower()
    if mime_type not in ALLOWED_UPLOAD_MIME:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    uploader = resolve_actor_name(x_api_key)
    record = save_upload_file(
        filename=file.filename or "upload",
        content=contents,
        mime_type=mime_type,
        purpose=purpose,
        uploader=uploader,
    )
    download_url = _upload_download_url(record.storage_filename)
    return UploadInitResponse(
        upload_id=record.upload_id,
        filename=record.filename,
        mime_type=record.mime_type,
        size_bytes=record.size_bytes,
        sha256=record.sha256,
        stored_at=record.stored_at,
        download_url=download_url,
    )


@app.get("/v1/upload/{upload_id}", response_model=UploadRecord)
def upload_detail(upload_id: str):
    record = load_upload_record(upload_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    record.download_url = _upload_download_url(record.storage_filename)
    return record


@app.post("/v1/ingest", response_model=IngestResponse)
async def ingest_endpoint(
    request: IngestRequest,
    manager=Depends(get_manager),
    api_key: str | None = Depends(require_auth),
) -> IngestResponse:
    result = ingest_content(
        request.content,
        source_name=request.source_name,
        doc_id=request.doc_id,
        language=request.language,
        domain=request.domain,
        freshness=request.freshness,
        url=request.url,
        tags=request.tags,
        max_chars=request.max_chars,
        overlap=request.overlap,
    )
    manager.rebuild()
    health = manager.health()
    return IngestResponse(
        doc_id=result.document.doc_id,
        version=result.document.version,
        chunk_count=result.chunk_count,
        health=health,
    )


@app.get("/v1/index/health", response_model=IndexHealth)
def index_health(
    manager=Depends(get_manager),
    api_key: str | None = Depends(require_auth),
) -> IndexHealth:
    return manager.health()


@app.post("/v1/index/rebuild", response_model=IndexHealth)
def index_rebuild(
    manager=Depends(get_manager),
    api_key: str | None = Depends(require_auth),
) -> IndexHealth:
    manager.rebuild()
    return manager.health()


@app.get("/v1/chunks/{chunk_id}", response_model=ChunkDetailResponse)
def chunk_detail(
    chunk_id: str,
    api_key: str | None = Depends(require_auth),
) -> ChunkDetailResponse:
    chunk = load_chunk_by_id(chunk_id)
    if chunk is None:
        raise HTTPException(status_code=404, detail="Chunk not found")
    document = get_document(chunk.doc_id)
    last_verified_at = document.updated_at if document else None
    metadata = dict(chunk.metadata)
    metadata.setdefault("doc_id", chunk.doc_id)
    highlight_start = metadata.get("highlight_start")
    highlight_end = metadata.get("highlight_end")
    if highlight_start is None or highlight_end is None:
        highlight_start = chunk.start_idx
        highlight_end = chunk.end_idx
    detail = ChunkDetail(
        chunk_id=chunk.chunk_id,
        doc_id=chunk.doc_id,
        text=chunk.text,
        start_idx=chunk.start_idx,
        end_idx=chunk.end_idx,
        metadata=metadata,
        last_verified_at=last_verified_at,
        highlights=[HighlightSpan(start=highlight_start, end=highlight_end)],
    )
    return ChunkDetailResponse(chunk=detail)


@app.get("/v1/admin/config", response_model=AdminConfigResponse)
def admin_config(
    api_key: str | None = Depends(require_auth),
) -> AdminConfigResponse:
    docs = load_manifest()
    if docs:
        sources = [
            AdminSource(
                doc_id=doc.doc_id,
                source_name=doc.source_name,
                language=doc.language,
                domain=doc.domain,
                freshness=doc.freshness,
                url=doc.url,
                tags=doc.tags,
                last_updated_at=doc.updated_at,
            )
            for doc in docs
        ]
    else:
        sources = _fallback_sources_from_jobs()
    slot_configs = [
        AdminSlotConfig(
            name=slot.name,
            description=slot.description,
            prompt=slot.prompt,
            prompt_zh=getattr(slot, "prompt_zh", None),
            required=slot.required,
            value_type=slot.value_type,
            choices=slot.choices,
            min_value=slot.min_value,
            max_value=slot.max_value,
        )
        for slot in slot_definitions()
    ]
    manager = get_index_manager()
    retrieval = AdminRetrievalSettings(
        alpha=manager.alpha,
        top_k=manager.default_top_k,
        k_cite=manager.default_k_cite,
    )
    return AdminConfigResponse(sources=sources, slots=slot_configs, retrieval=retrieval)


@app.post("/v1/admin/retrieval", response_model=AdminUpdateRetrievalResponse)
def admin_update_retrieval(
    payload: AdminUpdateRetrievalRequest,
    api_key: str | None = Depends(require_auth),
) -> AdminUpdateRetrievalResponse:
    manager = get_index_manager()
    manager.configure(alpha=payload.alpha, top_k=payload.top_k, k_cite=payload.k_cite)
    save_retrieval_settings(
        {
            "alpha": manager.alpha,
            "top_k": manager.default_top_k,
            "k_cite": manager.default_k_cite,
        }
    )
    append_audit_log(
        {
            "action": "update_retrieval",
            "alpha": manager.alpha,
            "top_k": manager.default_top_k,
            "k_cite": manager.default_k_cite,
            "actor": resolve_actor_name(api_key),
        }
    )
    return AdminUpdateRetrievalResponse(
        alpha=manager.alpha,
        top_k=manager.default_top_k,
        k_cite=manager.default_k_cite,
    )


@app.post("/v1/admin/slots", response_model=AdminUpdateSlotsResponse)
def admin_update_slots(
    payload: AdminUpdateSlotsRequest,
    api_key: str | None = Depends(require_auth),
) -> AdminUpdateSlotsResponse:
    if not payload.slots:
        raise HTTPException(status_code=400, detail="At least one slot must be provided")

    definitions = []
    seen: set[str] = set()
    for slot_cfg in payload.slots:
        data = slot_cfg.model_dump()
        name = normalize_slot_name(data.get("name", ""))
        if not name:
            raise HTTPException(status_code=400, detail="Slot name is required")
        if name in seen:
            raise HTTPException(status_code=400, detail=f"Duplicate slot name: {name}")
        data["name"] = name
        definition = _slot_from_dict(data)
        if definition is None:
            raise HTTPException(status_code=400, detail=f"Invalid slot definition for: {name}")
        definitions.append(definition)
        seen.add(name)

    update_slot_definitions(definitions)
    save_slots_config(serialize_slots(definitions))
    reset_session_store()
    append_audit_log(
        {
            "action": "update_slots",
            "slot_count": len(definitions),
            "actor": resolve_actor_name(api_key),
        }
    )

    updated_slots = [
        AdminSlotConfig(
            name=slot.name,
            description=slot.description,
            prompt=slot.prompt,
            prompt_zh=getattr(slot, "prompt_zh", None),
            required=slot.required,
            value_type=slot.value_type,
            choices=slot.choices,
            min_value=slot.min_value,
            max_value=slot.max_value,
        )
        for slot in slot_definitions()
    ]
    return AdminUpdateSlotsResponse(slots=updated_slots)


@app.get("/v1/metrics")
def metrics_snapshot(
    api_key: str | None = Depends(require_auth),
):
    metrics = get_metrics().snapshot()
    session_count = len(get_session_store().list_sessions())
    diagnostics = metrics.setdefault("diagnostics", {})
    sessions_block = diagnostics.setdefault("sessions", {})
    sessions_block["active"] = session_count
    return metrics


@app.get("/v1/status", response_model=ServiceStatusResponse)
def service_status(
    api_key: str | None = Depends(require_auth),
) -> ServiceStatusResponse:
    metrics = get_metrics()
    snapshot = get_service_status_snapshot(metrics.snapshot())
    return snapshot


@app.get("/v1/admin/audit", response_model=AdminAuditResponse)
def admin_audit(
    limit: int = 100,
    api_key: str | None = Depends(require_auth),
) -> AdminAuditResponse:
    raw_entries = read_audit_logs(limit=limit)
    entries = []
    for item in raw_entries:
        timestamp_raw = item.get("timestamp")
        action = item.get("action", "unknown")
        details = {k: v for k, v in item.items() if k not in {"timestamp", "action"}}
        try:
            parsed_timestamp = datetime.fromisoformat(timestamp_raw) if isinstance(timestamp_raw, str) else timestamp_raw
        except Exception:
            parsed_timestamp = datetime.now(UTC)
        entries.append(AdminAuditEntry(timestamp=parsed_timestamp, action=action, details=details))
    return AdminAuditResponse(entries=entries)




def _fallback_sources_from_jobs(limit: int = 50) -> List[AdminSource]:
    entries = load_jobs_history(limit=limit)
    seen: dict[str, AdminSource] = {}
    for job in entries:
        if job.get("job_type") != "ingest":
            continue
        metadata = job.get("metadata") or {}
        doc_id = str(job.get("doc_id") or metadata.get("doc_id") or metadata.get("source_name") or "unknown")
        if doc_id in seen:
            continue
        source_name = metadata.get("source_name") or doc_id
        language = metadata.get("language") or "en"
        domain = metadata.get("domain")
        freshness = metadata.get("freshness")
        url = metadata.get("url")
        tags = metadata.get("tags") or []
        seen[doc_id] = AdminSource(
            doc_id=doc_id,
            source_name=str(source_name),
            language=str(language),
            domain=domain,
            freshness=freshness,
            url=url,
            tags=list(tags) if isinstance(tags, list) else [],
            last_updated_at=datetime.now(UTC),
            description=metadata.get("description"),
        )
    return list(seen.values())

@app.get("/v1/admin/sources", response_model=List[AdminSource])
def admin_sources_list(
    api_key: str | None = Depends(require_auth),
):
    docs = load_manifest()
    sources = [
        AdminSource(
            doc_id=doc.doc_id,
            source_name=doc.source_name,
            language=doc.language,
            domain=doc.domain,
            freshness=doc.freshness,
            url=doc.url,
            tags=doc.tags,
            last_updated_at=doc.updated_at,
            description=doc.extra.get("description") if doc.extra else None,
        )
        for doc in docs
    ]
    return sources


@app.post("/v1/admin/sources", response_model=AdminSourceUpsertResponse)
def admin_sources_upsert(
    payload: AdminSourceUpsertRequest,
    api_key: str | None = Depends(require_auth),
) -> AdminSourceUpsertResponse:
    doc_id = normalize_source_id(payload.doc_id)
    document = Document(
        doc_id=doc_id,
        source_name=payload.source_name,
        language=payload.language,
        domain=payload.domain,
        freshness=payload.freshness,
        url=payload.url,
        tags=payload.tags,
        extra={"description": payload.description} if payload.description else {},
    )
    updated = upsert_document(document)
    append_audit_log(
        {
            "action": "admin_source_upsert",
            "doc_id": updated.doc_id,
            "actor": resolve_actor_name(api_key),
        }
    )
    return AdminSourceUpsertResponse(
        source=AdminSource(
            doc_id=updated.doc_id,
            source_name=updated.source_name,
            language=updated.language,
            domain=updated.domain,
            freshness=updated.freshness,
            url=updated.url,
            tags=updated.tags,
            last_updated_at=updated.updated_at,
            description=updated.extra.get("description") if updated.extra else None,
        )
    )


@app.delete("/v1/admin/sources/{doc_id}", response_model=AdminSourceDeleteResponse)
def admin_sources_delete(
    doc_id: str,
    api_key: str | None = Depends(require_auth),
) -> AdminSourceDeleteResponse:
    normalized = normalize_source_id(doc_id)
    deleted = delete_document(normalized)
    append_audit_log(
        {
            "action": "admin_source_delete",
            "doc_id": normalized,
            "deleted": deleted,
            "actor": resolve_actor_name(api_key),
        }
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Source not found")
    return AdminSourceDeleteResponse(doc_id=normalized, deleted=True)


@app.get("/v1/admin/stop-list")
def admin_stop_list(
    api_key: str | None = Depends(require_auth),
):
    items = load_stop_list()
    return {"items": items, "updated_at": datetime.now(UTC)}


@app.post("/v1/admin/stop-list")
def admin_stop_list_update(
    payload: dict,
    api_key: str | None = Depends(require_auth),
):
    items = payload.get("items", [])
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="items must be a list of strings")
    cleaned = [str(item).strip() for item in items if str(item).strip()]
    save_stop_list(cleaned)
    append_audit_log(
        {
            "action": "update_stop_list",
            "count": len(cleaned),
            "actor": resolve_actor_name(api_key),
        }
    )
    return {"items": cleaned, "updated_at": datetime.now(UTC)}


@app.get("/v1/admin/jobs", response_model=AdminJobHistoryResponse)
def admin_jobs(
    limit: int = 50,
    api_key: str | None = Depends(require_auth),
) -> AdminJobHistoryResponse:
    records = load_jobs_history(limit=limit)
    entries = []
    for item in records:
        try:
            started = datetime.fromisoformat(item.get("started_at"))
        except Exception:
            started = datetime.now(UTC)
        completed_raw = item.get("completed_at")
        completed = None
        if completed_raw:
            try:
                completed = datetime.fromisoformat(completed_raw)
            except Exception:
                completed = None
        entries.append(
            AdminJobEntry(
                job_id=item.get("job_id", "unknown"),
                job_type=item.get("job_type", "unknown"),
                status=item.get("status", "unknown"),
                started_at=started,
                completed_at=completed,
                duration_ms=item.get("duration_ms"),
                metadata={k: v for k, v in item.items() if k not in {"job_id", "job_type", "status", "started_at", "completed_at", "duration_ms"}},
            )
        )
    return AdminJobHistoryResponse(jobs=entries)


@app.get("/v1/admin/templates", response_model=List[AdminTemplate])
def admin_templates_list(
    api_key: str | None = Depends(require_auth),
):
    records = load_templates()
    templates = [AdminTemplate(**record) for record in records]
    return templates


@app.post("/v1/admin/templates", response_model=AdminTemplateUpsertResponse)
def admin_templates_upsert(
    payload: AdminTemplateUpsertRequest,
    api_key: str | None = Depends(require_auth),
) -> AdminTemplateUpsertResponse:
    record = upsert_template(payload.model_dump())
    append_audit_log(
        {
            "action": "admin_template_upsert",
            "template_id": record["template_id"],
            "actor": resolve_actor_name(api_key),
        }
    )
    return AdminTemplateUpsertResponse(template=AdminTemplate(**record))


@app.delete("/v1/admin/templates/{template_id}", response_model=AdminTemplateDeleteResponse)
def admin_templates_delete(
    template_id: str,
    api_key: str | None = Depends(require_auth),
) -> AdminTemplateDeleteResponse:
    deleted = delete_template(template_id)
    append_audit_log(
        {
            "action": "admin_template_delete",
            "template_id": template_id,
            "deleted": deleted,
            "actor": resolve_actor_name(api_key),
        }
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Template not found")
    return AdminTemplateDeleteResponse(template_id=template_id, deleted=True)


@app.get("/v1/admin/prompts", response_model=List[AdminPrompt])
def admin_prompts_list(
    api_key: str | None = Depends(require_auth),
):
    records = load_prompts()
    prompts = [AdminPrompt(**record) for record in records]
    return prompts


@app.post("/v1/admin/prompts", response_model=AdminPromptUpsertResponse)
def admin_prompts_upsert(
    payload: AdminPromptUpsertRequest,
    api_key: str | None = Depends(require_auth),
) -> AdminPromptUpsertResponse:
    record = upsert_prompt(payload.model_dump())
    append_audit_log(
        {
            "action": "admin_prompt_upsert",
            "prompt_id": record["prompt_id"],
            "actor": resolve_actor_name(api_key),
        }
    )
    return AdminPromptUpsertResponse(prompt=AdminPrompt(**record))


@app.post("/v1/admin/prompts/{prompt_id}/activate", response_model=AdminPromptUpsertResponse)
def admin_prompts_activate(
    prompt_id: str,
    api_key: str | None = Depends(require_auth),
) -> AdminPromptUpsertResponse:
    record = set_active_prompt(prompt_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Prompt not found")
    append_audit_log(
        {
            "action": "admin_prompt_activate",
            "prompt_id": prompt_id,
            "actor": resolve_actor_name(api_key),
        }
    )
    return AdminPromptUpsertResponse(prompt=AdminPrompt(**record))


@app.delete("/v1/admin/prompts/{prompt_id}", response_model=AdminPromptDeleteResponse)
def admin_prompts_delete(
    prompt_id: str,
    api_key: str | None = Depends(require_auth),
) -> AdminPromptDeleteResponse:
    deleted = delete_prompt(prompt_id)
    append_audit_log(
        {
            "action": "admin_prompt_delete",
            "prompt_id": prompt_id,
            "deleted": deleted,
            "actor": resolve_actor_name(api_key),
        }
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return AdminPromptDeleteResponse(prompt_id=prompt_id, deleted=True)


