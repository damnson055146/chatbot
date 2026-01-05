from __future__ import annotations

import os
import re
import time
import uuid
from urllib.parse import quote
from datetime import datetime, UTC
from pathlib import Path
from typing import List

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.middleware import Middleware
from fastapi.staticfiles import StaticFiles

from src.agents.rag_agent import answer_query, answer_query_sse
from src.pipelines.ingest import ingest_content
from src.pipelines.ingest_queue import get_ingest_queue, ingest_upload_payload
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
    AdminSourceVerifyResponse,
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
    AdminAssistantOpeningEntry,
    AdminAssistantOpeningResponse,
    AdminAssistantOpeningUpdateRequest,
    AdminAssistantOpeningUpdateResponse,
    AdminAuditResponse,
    AdminAuditEntry,
    AdminEscalationEntry,
    AdminEscalationResponse,
    AdminConversationMessage,
    AdminSessionMessagesResponse,
    AdminSessionSummary,
    AdminUserSummary,
    ConversationMessage,
    ChunkDetail,
    ChunkDetailResponse,
    Document,
    HighlightSpan,
    IndexHealth,
    IngestRequest,
    IngestResponse,
    JobEnqueueResponse,
    QueryRequest,
    QueryResponse,
    RetrievalEvalCaseResult,
    RetrievalEvalRequest,
    RetrievalEvalResponse,
    RerankRequest,
    RerankResponse,
    RerankResult,
    ServiceStatusResponse,
    ServiceStatusMetric,
    SessionListResponse,
    SessionCreateRequest,
    SessionSlotsUpdateRequest,
    SessionStateResponse,
    SessionMetadataUpdateRequest,
    SessionMessagesResponse,
    SlotCatalogResponse,
    SlotSchema,
    UploadInitResponse,
    UploadSignedUrlResponse,
    UploadPreviewResponse,
    UploadCleanupResponse,
    UploadRecord,
    AuthLoginRequest,
    AuthLoginResponse,
    AuthRegisterRequest,
    AuthRegisterResponse,
    AuthMeResponse,
    AuthResetQuestionResponse,
    AuthChangePasswordRequest,
    AuthResetPasswordRequest,
    AuthUpdateResetQuestionRequest,
    AssistantOpeningResponse,
    AssistantProfileResponse,
    AdminAssistantProfileResponse,
    AdminAssistantProfileUpdateRequest,
    AdminAssistantProfileUpdateResponse,
    EscalationRequest,
    EscalationResponse,
    UserProfileUpdateRequest,
    UserProfileResponse,
    AdminIngestUploadRequest,
)
from src.schemas.slots import normalize_slot_name, slot_definitions, update_slot_definitions, _slot_from_dict, serialize_slots, list_slots
from src.utils.env import load_env_file
from src.utils.index_manager import get_index_manager
from src.utils.logging import get_logger
from src.utils.observability import get_metrics, get_service_status_snapshot, time_phase_endpoint
from src.utils.text_extract import extract_text_from_bytes
from src.utils.tracing import configure_tracing
from src.utils.security import (
    Principal,
    assert_admin,
    get_rate_limiter,
    mint_access_token,
    resolve_principal,
)
from src.utils.upload_signing import sign_upload_url, verify_upload_signature
from src.utils.conversation_store import get_conversation_store
from src.utils.session import reset_session_store
from src.utils import siliconflow
from src.utils.opening import (
    ASSISTANT_OPENING_TEMPLATE_IDS,
    coerce_opening_language,
    ensure_assistant_opening_template,
)
from src.utils.opening_defaults import opening_template_description, opening_template_name
from src.utils.prompt_catalog import resolve_fragment, normalize_assistant_prompt, strip_assistant_intro
from src.utils.user_store import (
    authenticate_user,
    create_user,
    normalize_username,
    get_reset_question,
    update_reset_credentials,
    change_password,
    reset_password_with_answer,
)
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
    mark_document_verified,
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
    get_template,
    load_assistant_profile_record,
    save_assistant_profile_record,
    append_audit_log,
    read_audit_logs,
    load_jobs_history,
    get_upload_expiry,
    is_upload_expired,
    load_upload_record,
    purge_expired_uploads,
    save_upload_file,
    save_assistant_avatar,
    UPLOADS_DIR,
    load_escalations,
    append_escalation,
    append_metrics_snapshot,
    load_metrics_history,
    append_status_snapshot,
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


def _resolve_opening_language(request: Request, lang: str | None) -> str:
    raw = (lang or request.headers.get("Accept-Language", "")).strip().lower()
    if raw:
        primary = raw.split(",")[0].strip().lower()
        if primary.startswith("zh"):
            return "zh"
        if primary.startswith("en"):
            return "en"
    return "en"


def _assistant_display_name() -> str:
    record = load_assistant_profile_record()
    profile = record.get("profile") if isinstance(record, dict) else {}
    name = str(profile.get("name") or "").strip()
    return name or "Lumi"


def _normalize_prompt_payload(record: dict, assistant_name: str | None = None) -> dict:
    payload = dict(record)
    name = assistant_name if assistant_name is not None else _assistant_display_name()
    if isinstance(payload.get("content"), str):
        payload["content"] = normalize_assistant_prompt(payload["content"], name, payload.get("language"))
    return payload


def _ensure_default_prompts() -> List[dict]:
    records = load_prompts()
    if records:
        return records
    placeholder = "{assistant_name}"
    defaults = [
        {
            "prompt_id": "system_prompt_en",
            "name": "System Prompt",
            "language": "en",
            "content": resolve_fragment("system_prompt", "en", {"assistant_name": placeholder}),
            "description": "Default system prompt seeded from the prompt catalog.",
            "is_active": True,
        },
        {
            "prompt_id": "system_prompt_zh",
            "name": "System Prompt (zh)",
            "language": "zh",
            "content": resolve_fragment("system_prompt", "zh", {"assistant_name": placeholder}),
            "description": "Default system prompt seeded from the prompt catalog.",
            "is_active": True,
        },
    ]
    for entry in defaults:
        entry["content"], _ = strip_assistant_intro(entry.get("content"))
        upsert_prompt(entry)
    return load_prompts()


def _parse_template_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except Exception:
            return None
    return None

MAX_UPLOAD_BYTES = int(os.getenv("UPLOAD_MAX_BYTES", str(10 * 1024 * 1024)))
DEFAULT_UPLOAD_RETENTION_DAYS = int(os.getenv("UPLOAD_RETENTION_DAYS", "30"))
ALLOWED_UPLOAD_MIME = {
    "application/pdf",
    "text/markdown",
    "text/plain",
    "image/png",
    "image/jpeg",
    "image/webp",
    "audio/mpeg",
    "audio/mp4",
    "audio/wav",
    "audio/x-wav",
    "audio/webm",
    "audio/ogg",
    "audio/aac",
    "audio/x-m4a",
}

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")


def normalize_source_id(value: str) -> str:
    return "-".join(value.strip().split()).lower()


def _upload_download_url(storage_filename: str) -> str:
    return f"/uploads/{storage_filename}"


def _resolve_retention_days(retention_days: int | None) -> int | None:
    if retention_days is None:
        return DEFAULT_UPLOAD_RETENTION_DAYS
    if retention_days <= 0:
        return None
    return retention_days


def _signed_upload_url(upload_id: str, *, disposition: str):
    return sign_upload_url(
        upload_id,
        base_path=f"/v1/upload/{upload_id}/file",
        disposition=disposition,
    )


def _safe_content_disposition(filename: str, disposition: str) -> str:
    normalized = "inline" if disposition.strip().lower() == "inline" else "attachment"
    if not filename:
        return normalized
    clean_name = filename.replace('"', "'")
    try:
        clean_name.encode("latin-1")
        return f'{normalized}; filename="{clean_name}"'
    except UnicodeEncodeError:
        fallback = re.sub(r"[^A-Za-z0-9._-]", "_", clean_name) or "download"
        return f"{normalized}; filename=\"{fallback}\"; filename*=UTF-8''{quote(clean_name)}"


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


def _rate_limit_identity(principal: Principal | str | None, path: str) -> str:
    if principal is None:
        identity = "anonymous"
    elif isinstance(principal, str):
        identity = principal.strip() or "anonymous"
    else:
        identity = (principal.sub or "anonymous").strip() or "anonymous"
    return f"{identity}:{path}"



def require_user(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    api_key: str | None = Header(default=None, alias="X-API-Key"),
    limiter=Depends(get_rate_limiter),
) -> Principal:
    principal = resolve_principal(authorization=authorization, api_key=api_key)
    limiter.allow(_rate_limit_identity(principal, request.url.path))
    return principal


def require_admin(principal: Principal = Depends(require_user)) -> Principal:
    assert_admin(principal, allow_readonly=True)
    return principal


def require_admin_write(principal: Principal = Depends(require_user)) -> Principal:
    assert_admin(principal, allow_readonly=False)
    return principal


def _can_admin_adjust_rag(principal: Principal) -> bool:
    return principal.role == "admin"


def _sanitize_query_payload(payload: QueryRequest, principal: Principal) -> QueryRequest:
    if _can_admin_adjust_rag(principal):
        return payload
    manager = get_index_manager()
    return payload.model_copy(
        update={
            "top_k": manager.default_top_k,
            "k_cite": manager.default_k_cite,
        }
    )


@app.post("/v1/auth/login", response_model=AuthLoginResponse)
def auth_login(payload: AuthLoginRequest) -> AuthLoginResponse:
    admin_password = os.getenv("AUTH_ADMIN_PASSWORD", "").strip()
    readonly_password = os.getenv("AUTH_ADMIN_READONLY_PASSWORD", "").strip()
    username = (payload.username or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    raw_password = payload.password or ""
    if not raw_password:
        raise HTTPException(status_code=400, detail="Password is required")
    if admin_password and raw_password == admin_password:
        role = "admin"
    elif readonly_password and raw_password == readonly_password:
        role = "admin_readonly"
    else:
        account = authenticate_user(username, raw_password)
        if account is None:
            raise HTTPException(status_code=401, detail="Invalid username or password")
        role = account.role
        username = account.username
    token = mint_access_token(sub=normalize_username(username), role=role)
    return AuthLoginResponse(access_token=token, role=role)


@app.post("/v1/auth/register", response_model=AuthRegisterResponse, status_code=201)
def auth_register(payload: AuthRegisterRequest) -> AuthRegisterResponse:
    username = (payload.username or "").strip()
    password = payload.password or ""
    reset_question = (payload.reset_question or "").strip()
    reset_answer = payload.reset_answer or ""
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    if not password:
        raise HTTPException(status_code=400, detail="Password is required")
    try:
        account = create_user(
            username,
            password,
            reset_question=reset_question,
            reset_answer=reset_answer,
            role="user",
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 400
        if "exists" in detail.lower():
            status_code = 409
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return AuthRegisterResponse(user_id=account.user_id, username=account.username, role=account.role)


@app.get("/v1/auth/me", response_model=AuthMeResponse)
def auth_me(principal: Principal = Depends(require_user)) -> AuthMeResponse:
    return AuthMeResponse(sub=principal.sub, role=principal.role)


@app.post("/v1/auth/logout", status_code=204)
def auth_logout(principal: Principal = Depends(require_user)) -> Response:
    return Response(status_code=204)


@app.get("/v1/auth/reset-question", response_model=AuthResetQuestionResponse)
def auth_reset_question(username: str = Query(default="")) -> AuthResetQuestionResponse:
    cleaned = (username or "").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Username is required")
    question = get_reset_question(cleaned)
    if not question:
        raise HTTPException(status_code=404, detail="Reset question not configured")
    return AuthResetQuestionResponse(username=normalize_username(cleaned), reset_question=question)


@app.post("/v1/auth/password", status_code=204)
def auth_change_password(
    payload: AuthChangePasswordRequest,
    principal: Principal = Depends(require_user),
) -> Response:
    try:
        change_password(
            principal.sub,
            current_password=payload.current_password or "",
            new_password=payload.new_password or "",
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 400
        if "not found" in detail.lower():
            status_code = 404
        elif "incorrect" in detail.lower():
            status_code = 401
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return Response(status_code=204)


@app.post("/v1/auth/reset-password", status_code=204)
def auth_reset_password(payload: AuthResetPasswordRequest) -> Response:
    try:
        reset_password_with_answer(
            payload.username,
            reset_answer=payload.reset_answer or "",
            new_password=payload.new_password or "",
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 400
        if "not found" in detail.lower():
            status_code = 404
        elif "incorrect" in detail.lower():
            status_code = 401
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return Response(status_code=204)


@app.post("/v1/auth/reset-question", status_code=204)
def auth_update_reset_question(
    payload: AuthUpdateResetQuestionRequest,
    principal: Principal = Depends(require_user),
) -> Response:
    try:
        update_reset_credentials(
            principal.sub,
            reset_question=payload.reset_question or "",
            reset_answer=payload.reset_answer or "",
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 400
        if "not found" in detail.lower():
            status_code = 404
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return Response(status_code=204)


@app.get("/v1/assistant/opening", response_model=AssistantOpeningResponse)
def assistant_opening(
    request: Request,
    lang: str | None = Query(default=None),
) -> AssistantOpeningResponse:
    language = _resolve_opening_language(request, lang)
    record = ensure_assistant_opening_template(language)
    content = record.get("content")
    opening = str(content).strip() if content is not None else None
    return AssistantOpeningResponse(opening=opening, language=language)


@app.get("/v1/assistant/profile", response_model=AssistantProfileResponse)
def assistant_profile(principal: Principal = Depends(require_user)) -> AssistantProfileResponse:
    record = load_assistant_profile_record()
    profile = record.get("profile", {})
    return AssistantProfileResponse(**profile)


@app.get("/v1/admin/assistant/profile", response_model=AdminAssistantProfileResponse)
def admin_assistant_profile(
    principal: Principal = Depends(require_admin),
) -> AdminAssistantProfileResponse:
    record = load_assistant_profile_record()
    profile = record.get("profile", {})
    updated_at = _parse_template_datetime(record.get("updated_at"))
    return AdminAssistantProfileResponse(profile=AssistantProfileResponse(**profile), updated_at=updated_at)


@app.post("/v1/admin/assistant/profile", response_model=AdminAssistantProfileUpdateResponse)
def admin_assistant_profile_update(
    payload: AdminAssistantProfileUpdateRequest,
    principal: Principal = Depends(require_admin_write),
) -> AdminAssistantProfileUpdateResponse:
    record = load_assistant_profile_record()
    profile = dict(record.get("profile", {}))
    updates = payload.model_dump(exclude_unset=True)
    updated = False

    if "name" in updates:
        name = (updates.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Assistant name is required")
        profile["name"] = name
        updated = True

    avatar_updates = updates.get("avatar")
    if isinstance(avatar_updates, dict):
        avatar = dict(profile.get("avatar") or {})
        for key in ("accent", "base", "ring", "face", "image_url"):
            if key not in avatar_updates:
                continue
            value = avatar_updates.get(key)
            if key == "image_url":
                if value is None:
                    avatar.pop("image_url", None)
                    updated = True
                    continue
                cleaned = str(value).strip()
                if cleaned:
                    avatar["image_url"] = cleaned
                else:
                    avatar.pop("image_url", None)
                updated = True
                continue
            if value is None:
                continue
            cleaned = str(value).strip()
            if not cleaned:
                raise HTTPException(status_code=400, detail=f"Avatar color '{key}' is required")
            avatar[key] = cleaned
            updated = True
        if avatar:
            profile["avatar"] = avatar

    if not updated:
        record = load_assistant_profile_record()
        profile = record.get("profile", {})
        updated_at = _parse_template_datetime(record.get("updated_at"))
        return AdminAssistantProfileUpdateResponse(
            profile=AssistantProfileResponse(**profile),
            updated_at=updated_at or datetime.now(UTC),
        )

    saved = save_assistant_profile_record(profile)
    append_audit_log(
        {
            "action": "assistant_profile_update",
            "actor": principal.actor,
        }
    )
    updated_at = _parse_template_datetime(saved.get("updated_at"))
    return AdminAssistantProfileUpdateResponse(
        profile=AssistantProfileResponse(**saved.get("profile", {})),
        updated_at=updated_at or datetime.now(UTC),
    )


@app.post("/v1/admin/assistant/avatar", response_model=AdminAssistantProfileUpdateResponse)
def admin_assistant_avatar_upload(
    file: UploadFile = File(...),
    principal: Principal = Depends(require_admin_write),
) -> AdminAssistantProfileUpdateResponse:
    if not file.content_type:
        raise HTTPException(status_code=400, detail="Avatar content type is required")
    try:
        contents = file.file.read()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Unable to read avatar file") from exc
    if not contents:
        raise HTTPException(status_code=400, detail="Avatar file is empty")
    try:
        record = save_assistant_avatar(contents, mime_type=file.content_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    profile_record = load_assistant_profile_record()
    profile = dict(profile_record.get("profile", {}))
    avatar = dict(profile.get("avatar") or {})
    version = int(datetime.now(UTC).timestamp())
    avatar["image_url"] = f"{record['url']}?v={version}"
    profile["avatar"] = avatar
    saved = save_assistant_profile_record(profile)
    append_audit_log(
        {
            "action": "assistant_avatar_update",
            "actor": principal.actor,
        }
    )
    updated_at = _parse_template_datetime(saved.get("updated_at"))
    return AdminAssistantProfileUpdateResponse(
        profile=AssistantProfileResponse(**saved.get("profile", {})),
        updated_at=updated_at or datetime.now(UTC),
    )


@app.get("/v1/profile", response_model=UserProfileResponse)
def user_profile(principal: Principal = Depends(require_user)) -> UserProfileResponse:
    store = get_conversation_store()
    return store.get_profile(principal.sub)


@app.patch("/v1/profile", response_model=UserProfileResponse)
def update_profile(
    payload: UserProfileUpdateRequest,
    principal: Principal = Depends(require_user),
) -> UserProfileResponse:
    updates = payload.model_dump(exclude_unset=True)
    store = get_conversation_store()
    if not updates:
        return store.get_profile(principal.sub)
    return store.update_profile(principal.sub, updates)


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
    principal: Principal = Depends(require_user),
) -> SlotCatalogResponse:
    if lang:
        primary_lang = lang
    else:
        accept_language = request.headers.get("Accept-Language", "en")
        primary_lang = accept_language.split(",")[0].strip() if accept_language else "en"
    return _slot_catalog_payload(primary_lang)


@app.get("/v1/session", response_model=SessionListResponse)
def list_sessions(
    principal: Principal = Depends(require_user),
) -> SessionListResponse:
    store = get_conversation_store()
    return SessionListResponse(sessions=store.list_sessions(principal.sub))


@app.post("/v1/session", response_model=SessionStateResponse)
def create_session(
    payload: SessionCreateRequest,
    principal: Principal = Depends(require_user),
) -> SessionStateResponse:
    store = get_conversation_store()
    return store.create_session(
        principal.sub,
        title=payload.title,
        language=payload.language,
    )


@app.get("/v1/session/{session_id}", response_model=SessionStateResponse)
def session_detail(
    session_id: str,
    principal: Principal = Depends(require_user),
) -> SessionStateResponse:
    store = get_conversation_store()
    payload = store.get_session(principal.sub, session_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return payload


@app.delete("/v1/session/{session_id}", status_code=204)
def session_delete(
    session_id: str,
    principal: Principal = Depends(require_user),
) -> Response:
    store = get_conversation_store()
    if store.get_session(principal.sub, session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    store.delete_session(principal.sub, session_id)
    return Response(status_code=204)


@app.patch("/v1/session/{session_id}", response_model=SessionStateResponse)
def session_update_metadata(
    session_id: str,
    payload: SessionMetadataUpdateRequest,
    principal: Principal = Depends(require_user),
) -> SessionStateResponse:
    store = get_conversation_store()
    updated = store.update_session_metadata(
        principal.sub,
        session_id,
        title=payload.title,
        pinned=payload.pinned,
        archived=payload.archived,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return updated


@app.patch("/v1/session/{session_id}/slots", response_model=SessionStateResponse)
def session_update_slots(
    session_id: str,
    payload: SessionSlotsUpdateRequest,
    principal: Principal = Depends(require_user),
) -> SessionStateResponse:
    store = get_conversation_store()
    response = store.upsert_session(
        principal.sub,
        session_id=session_id,
        language="auto",
        slot_updates=payload.slots,
        reset_slots=payload.reset_slots,
    )
    return response


@app.get("/v1/session/{session_id}/messages", response_model=SessionMessagesResponse)
def session_messages(
    session_id: str,
    principal: Principal = Depends(require_user),
) -> SessionMessagesResponse:
    store = get_conversation_store()
    if store.get_session(principal.sub, session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = store.list_messages(principal.sub, session_id)
    return SessionMessagesResponse(session_id=session_id, messages=messages)


@app.get("/v1/admin/users", response_model=List[AdminUserSummary])
def admin_users(
    limit: int | None = Query(default=None, ge=1),
    principal: Principal = Depends(require_admin),
) -> List[AdminUserSummary]:
    store = get_conversation_store()
    entries = store.list_users(limit=limit)
    return [
        AdminUserSummary(
            user_id=str(entry.get("user_id", "")),
            display_name=entry.get("display_name"),
            contact_email=entry.get("contact_email"),
            session_count=int(entry.get("session_count") or 0),
            last_active_at=entry.get("last_active_at"),
        )
        for entry in entries
    ]


@app.get("/v1/admin/conversations", response_model=List[AdminSessionSummary])
def admin_conversations(
    user_id: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1),
    principal: Principal = Depends(require_admin),
) -> List[AdminSessionSummary]:
    store = get_conversation_store()
    records = store.list_sessions_admin(user_id=user_id, limit=limit)
    return [AdminSessionSummary(**record) for record in records]


@app.get("/v1/admin/conversations/{user_id}/{session_id}/messages", response_model=AdminSessionMessagesResponse)
def admin_conversation_messages(
    user_id: str,
    session_id: str,
    principal: Principal = Depends(require_admin),
) -> AdminSessionMessagesResponse:
    store = get_conversation_store()
    messages = store.list_messages_admin(user_id, session_id)
    admin_messages = [AdminConversationMessage(**dict(message)) for message in messages]
    return AdminSessionMessagesResponse(user_id=user_id, session_id=session_id, messages=admin_messages)


@app.post("/v1/query")
async def query_endpoint(
    request: Request,
    payload: QueryRequest,
    stream: bool = Query(default=False),
    principal: Principal = Depends(require_user),
):
    payload = _sanitize_query_payload(payload, principal)
    if stream:
        accept = request.headers.get("Accept", "")
        if "text/event-stream" not in accept:
            raise HTTPException(status_code=406, detail="Streaming requires Accept: text/event-stream")
        return StreamingResponse(
            answer_query_sse(request, payload, user_id=principal.sub), media_type="text/event-stream"
        )
    return await answer_query(payload, user_id=principal.sub)


@app.post("/query")
async def query_endpoint_ir(
    request: Request,
    payload: QueryRequest,
    stream: bool = Query(default=False),
    principal: Principal = Depends(require_user),
):
    """IR compatibility endpoint (unversioned)."""
    return await query_endpoint(request, payload, stream=stream, principal=principal)


@app.post("/answer")
async def answer_endpoint_ir(
    request: Request,
    payload: QueryRequest,
    stream: bool = Query(default=False),
    principal: Principal = Depends(require_user),
):
    """IR compatibility endpoint (unversioned)."""
    return await query_endpoint(request, payload, stream=stream, principal=principal)


@app.post("/v1/reran", response_model=RerankResponse)
async def reran_endpoint(
    payload: RerankRequest,
    principal: Principal = Depends(require_user),
) -> RerankResponse:
    trace_id = uuid.uuid4().hex
    documents = payload.documents
    if not documents:
        return RerankResponse(query=payload.query, trace_id=trace_id, results=[])

    metrics = get_metrics()
    with time_phase_endpoint(metrics, "rerank", "/v1/reran"):
        scores = await siliconflow.rerank_async(
            payload.query,
            [doc.text for doc in documents],
            model=payload.model,
            trace_id=trace_id,
            language=payload.language,
        )

    score_map = {idx: float(score) for idx, score in scores}
    ranked_indices = sorted(
        range(len(documents)),
        key=lambda idx: (score_map.get(idx, float("-inf")), -idx),
        reverse=True,
    )
    results = [
        RerankResult(index=idx, score=score_map.get(idx, 0.0), document=documents[idx])
        for idx in ranked_indices
    ]

    return RerankResponse(query=payload.query, trace_id=trace_id, results=results)


@app.post("/reran", response_model=RerankResponse)
async def reran_endpoint_ir(
    payload: RerankRequest,
    principal: Principal = Depends(require_user),
):
    """IR compatibility endpoint (unversioned)."""
    return await reran_endpoint(payload, principal=principal)


@app.post("/v1/upload", response_model=UploadInitResponse)
async def upload_media(
    file: UploadFile = File(...),
    purpose: str = Query(default="chat"),
    retention_days: int | None = Query(default=None, ge=0),
    principal: Principal = Depends(require_user),
) -> UploadInitResponse:
    normalized_purpose = purpose.strip().lower() if purpose else "chat"
    if normalized_purpose not in {"chat", "rag"}:
        raise HTTPException(status_code=400, detail="Unsupported upload purpose")
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file is not allowed")
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 10 MB limit")
    mime_type = (file.content_type or "application/octet-stream").lower()
    if mime_type not in ALLOWED_UPLOAD_MIME:
        filename = (file.filename or "").lower()
        if filename.endswith(".pdf"):
            mime_type = "application/pdf"
        elif filename.endswith(".txt"):
            mime_type = "text/plain"
        elif filename.endswith(".md") or filename.endswith(".markdown"):
            mime_type = "text/markdown"
        elif filename.endswith(".jpg") or filename.endswith(".jpeg"):
            mime_type = "image/jpeg"
        elif filename.endswith(".png"):
            mime_type = "image/png"
        elif filename.endswith(".webp"):
            mime_type = "image/webp"
        elif filename.endswith(".mp3"):
            mime_type = "audio/mpeg"
        elif filename.endswith(".m4a"):
            mime_type = "audio/x-m4a"
        elif filename.endswith(".mp4"):
            mime_type = "audio/mp4"
        elif filename.endswith(".webm"):
            mime_type = "audio/webm"
        elif filename.endswith(".wav"):
            mime_type = "audio/wav"
        elif filename.endswith(".ogg"):
            mime_type = "audio/ogg"
        elif filename.endswith(".aac"):
            mime_type = "audio/aac"
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type")
    uploader = principal.actor
    resolved_retention_days = _resolve_retention_days(retention_days)
    record = save_upload_file(
        filename=file.filename or "upload",
        content=contents,
        mime_type=mime_type,
        purpose=normalized_purpose,
        uploader=uploader,
        retention_days=resolved_retention_days,
    )
    download_url = _signed_upload_url(record.upload_id, disposition="attachment").url
    return UploadInitResponse(
        upload_id=record.upload_id,
        filename=record.filename,
        mime_type=record.mime_type,
        size_bytes=record.size_bytes,
        sha256=record.sha256,
        stored_at=record.stored_at,
        download_url=download_url,
        retention_days=record.retention_days,
        expires_at=record.expires_at,
    )



@app.post("/v1/escalations", response_model=EscalationResponse)
def create_escalation(
    payload: EscalationRequest,
    principal: Principal = Depends(require_user),
) -> EscalationResponse:
    store = get_conversation_store()
    messages = store.list_messages(principal.sub, payload.session_id)
    if not messages:
        raise HTTPException(status_code=404, detail="Session not found")
    message = next((entry for entry in messages if entry.get("id") == payload.message_id), None)
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    record = append_escalation(
        {
            "user_id": principal.sub,
            "session_id": payload.session_id,
            "message_id": payload.message_id,
            "reason": payload.reason or "user_request",
            "notes": payload.notes,
            "message": message,
            "conversation": messages[-30:],
        }
    )
    return EscalationResponse(
        escalation_id=str(record.get("escalation_id", "")),
        status=str(record.get("status", "pending")),
        created_at=_parse_template_datetime(record.get("created_at")) or datetime.now(UTC),
        session_id=payload.session_id,
        message_id=payload.message_id,
    )


@app.get("/v1/upload/{upload_id}", response_model=UploadRecord)
def upload_detail(
    upload_id: str,
    principal: Principal = Depends(require_user),
):
    record = load_upload_record(upload_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    if is_upload_expired(record, default_retention_days=DEFAULT_UPLOAD_RETENTION_DAYS):
        raise HTTPException(status_code=410, detail="Upload has expired")
    if record.retention_days is None:
        record.retention_days = DEFAULT_UPLOAD_RETENTION_DAYS
    record.expires_at = get_upload_expiry(record, default_retention_days=DEFAULT_UPLOAD_RETENTION_DAYS)
    record.download_url = _signed_upload_url(record.upload_id, disposition="attachment").url
    return record


@app.get("/v1/upload/{upload_id}/signed", response_model=UploadSignedUrlResponse)
def upload_signed_urls(
    upload_id: str,
    principal: Principal = Depends(require_user),
) -> UploadSignedUrlResponse:
    record = load_upload_record(upload_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    if is_upload_expired(record, default_retention_days=DEFAULT_UPLOAD_RETENTION_DAYS):
        raise HTTPException(status_code=410, detail="Upload has expired")
    download = _signed_upload_url(upload_id, disposition="attachment")
    preview = _signed_upload_url(upload_id, disposition="inline")
    return UploadSignedUrlResponse(
        upload_id=upload_id,
        download_url=download.url,
        preview_url=preview.url,
        expires_at=download.expires_at,
    )


@app.get("/v1/upload/{upload_id}/preview", response_model=UploadPreviewResponse)
def upload_preview(
    upload_id: str,
    principal: Principal = Depends(require_user),
) -> UploadPreviewResponse:
    record = load_upload_record(upload_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    if is_upload_expired(record, default_retention_days=DEFAULT_UPLOAD_RETENTION_DAYS):
        raise HTTPException(status_code=410, detail="Upload has expired")
    download = _signed_upload_url(upload_id, disposition="attachment")
    preview = _signed_upload_url(upload_id, disposition="inline")
    text_excerpt = None
    try:
        preview_max_chars = int(os.getenv("UPLOAD_PREVIEW_MAX_CHARS", "1000"))
    except ValueError:
        preview_max_chars = 1000
    preview_max_chars = max(0, preview_max_chars)
    if record.mime_type.startswith("text/") or record.mime_type in {
        "application/json",
        "application/pdf",
    } or record.mime_type.startswith("image/"):
        upload_path = UPLOADS_DIR / record.storage_filename
        if upload_path.exists():
            try:
                extracted = extract_text_from_bytes(
                    content=upload_path.read_bytes(),
                    mime_type=record.mime_type,
                    filename=record.filename,
                )
                text_excerpt = extracted.text[:preview_max_chars]
            except HTTPException as exc:
                log.warning("upload_preview_extract_failed", upload_id=upload_id, error=str(exc.detail))
    expires_at = get_upload_expiry(record, default_retention_days=DEFAULT_UPLOAD_RETENTION_DAYS)
    return UploadPreviewResponse(
        upload_id=upload_id,
        filename=record.filename,
        mime_type=record.mime_type,
        size_bytes=record.size_bytes,
        preview_url=preview.url,
        download_url=download.url,
        text_excerpt=text_excerpt,
        expires_at=expires_at,
    )


@app.get("/v1/upload/{upload_id}/file")
def upload_file(
    upload_id: str,
    exp: int = Query(..., ge=1),
    sig: str = Query(..., min_length=10),
    disposition: str = Query(default="attachment"),
) -> FileResponse:
    if not verify_upload_signature(upload_id, exp=exp, sig=sig, disposition=disposition):
        raise HTTPException(status_code=403, detail="Invalid or expired signature")
    record = load_upload_record(upload_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    if is_upload_expired(record, default_retention_days=DEFAULT_UPLOAD_RETENTION_DAYS):
        raise HTTPException(status_code=410, detail="Upload has expired")
    upload_path = UPLOADS_DIR / record.storage_filename
    if not upload_path.exists():
        raise HTTPException(status_code=404, detail="Upload file missing on disk")
    headers = {"Content-Disposition": _safe_content_disposition(record.filename or "", disposition)}
    return FileResponse(path=upload_path, media_type=record.mime_type, headers=headers)


@app.post("/v1/admin/uploads/cleanup", response_model=UploadCleanupResponse)
def admin_upload_cleanup(
    dry_run: bool = Query(default=False),
    principal: Principal = Depends(require_admin_write),
) -> UploadCleanupResponse:
    result = purge_expired_uploads(
        default_retention_days=DEFAULT_UPLOAD_RETENTION_DAYS,
        dry_run=dry_run,
    )
    append_audit_log(
        {
            "action": "upload_cleanup",
            "deleted": result.get("deleted", 0),
            "skipped": result.get("skipped", 0),
            "expired_ids": result.get("expired_ids", []),
            "dry_run": dry_run,
            "actor": principal.actor,
        }
    )
    return UploadCleanupResponse(**result)


@app.post("/v1/ingest", response_model=IngestResponse)
async def ingest_endpoint(
    request: IngestRequest,
    manager=Depends(get_manager),
    principal: Principal = Depends(require_admin_write),
) -> IngestResponse:
    if request.url:
        raise HTTPException(status_code=400, detail="URL ingestion is not supported; upload documents instead")
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


@app.post("/ingest", response_model=IngestResponse)
async def ingest_endpoint_ir(
    request: IngestRequest,
    manager=Depends(get_manager),
    principal: Principal = Depends(require_admin_write),
) -> IngestResponse:
    """IR compatibility endpoint (unversioned)."""
    return await ingest_endpoint(request, manager=manager, principal=principal)


@app.post("/v1/admin/ingest-upload", response_model=IngestResponse | JobEnqueueResponse)
async def admin_ingest_upload(
    payload: AdminIngestUploadRequest,
    principal: Principal = Depends(require_admin_write),
    async_ingest: bool = Query(default=False, alias="async"),
) -> IngestResponse | JobEnqueueResponse:
    if async_ingest:
        job = get_ingest_queue().enqueue_upload(payload, actor=principal.actor, audit=True)
        return JSONResponse(status_code=202, content=job.model_dump(mode="json"))
    return ingest_upload_payload(payload, actor=principal.actor, audit=True)


@app.post("/v1/ingest-upload", response_model=IngestResponse | JobEnqueueResponse)
async def ingest_upload(
    payload: AdminIngestUploadRequest,
    principal: Principal = Depends(require_admin_write),
    async_ingest: bool = Query(default=False, alias="async"),
) -> IngestResponse | JobEnqueueResponse:
    """Ingestion for uploaded files (admin-only)."""

    if async_ingest:
        job = get_ingest_queue().enqueue_upload(payload, actor=principal.actor, audit=False)
        return JSONResponse(status_code=202, content=job.model_dump(mode="json"))
    return ingest_upload_payload(payload, actor=principal.actor, audit=False)


@app.get("/v1/index/health", response_model=IndexHealth)
def index_health(
    manager=Depends(get_manager),
    principal: Principal = Depends(require_admin),
) -> IndexHealth:
    return manager.health()


@app.post("/v1/index/rebuild", response_model=IndexHealth)
def index_rebuild(
    manager=Depends(get_manager),
    principal: Principal = Depends(require_admin_write),
) -> IndexHealth:
    manager.rebuild()
    return manager.health()


@app.get("/v1/chunks/{chunk_id}", response_model=ChunkDetailResponse)
def chunk_detail(
    chunk_id: str,
    principal: Principal = Depends(require_user),
) -> ChunkDetailResponse:
    chunk = load_chunk_by_id(chunk_id)
    if chunk is None:
        raise HTTPException(status_code=404, detail="Chunk not found")
    document = get_document(chunk.doc_id)
    last_verified_at = document.updated_at if document else None
    verified_raw = (document.extra or {}).get("verified_at") if document else None
    if isinstance(verified_raw, str):
        try:
            last_verified_at = datetime.fromisoformat(verified_raw)
        except Exception:
            pass
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
    principal: Principal = Depends(require_admin),
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


@app.get("/v1/admin/assistant/opening", response_model=AdminAssistantOpeningResponse)
def admin_assistant_opening(
    principal: Principal = Depends(require_admin),
) -> AdminAssistantOpeningResponse:
    entries: List[AdminAssistantOpeningEntry] = []
    for language in ("en", "zh"):
        record = ensure_assistant_opening_template(language)
        entries.append(
            AdminAssistantOpeningEntry(
                language=language,
                template_id=record.get("template_id", ASSISTANT_OPENING_TEMPLATE_IDS[language]),
                content=record.get("content"),
                updated_at=_parse_template_datetime(record.get("updated_at")),
            )
        )
    return AdminAssistantOpeningResponse(entries=entries)


@app.post("/v1/admin/assistant/opening", response_model=AdminAssistantOpeningUpdateResponse)
def admin_assistant_opening_update(
    payload: AdminAssistantOpeningUpdateRequest,
    principal: Principal = Depends(require_admin_write),
) -> AdminAssistantOpeningUpdateResponse:
    language = coerce_opening_language(payload.language, default=None)
    if not language or language not in ASSISTANT_OPENING_TEMPLATE_IDS:
        raise HTTPException(status_code=400, detail="Unsupported language")
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Opening content is required")

    record = get_template(ASSISTANT_OPENING_TEMPLATE_IDS[language]) or {}
    updated = upsert_template(
        {
            "template_id": ASSISTANT_OPENING_TEMPLATE_IDS[language],
            "name": record.get("name") or opening_template_name(language),
            "language": language,
            "category": record.get("category") or "assistant",
            "description": record.get("description") or opening_template_description(language),
            "content": content,
        }
    )
    append_audit_log(
        {
            "action": "assistant_opening_update",
            "template_id": updated.get("template_id"),
            "language": language,
            "actor": principal.actor,
        }
    )
    entry = AdminAssistantOpeningEntry(
        language=language,
        template_id=updated.get("template_id", ASSISTANT_OPENING_TEMPLATE_IDS[language]),
        content=updated.get("content"),
        updated_at=_parse_template_datetime(updated.get("updated_at")),
    )
    return AdminAssistantOpeningUpdateResponse(entry=entry)


@app.post("/v1/admin/retrieval", response_model=AdminUpdateRetrievalResponse)
def admin_update_retrieval(
    payload: AdminUpdateRetrievalRequest,
    principal: Principal = Depends(require_admin_write),
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
            "actor": principal.actor,
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
    principal: Principal = Depends(require_admin_write),
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
            "actor": principal.actor,
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


@app.post("/v1/admin/eval/retrieval", response_model=RetrievalEvalResponse)
def admin_eval_retrieval(
    payload: RetrievalEvalRequest,
    principal: Principal = Depends(require_admin_write),
) -> RetrievalEvalResponse:
    manager = get_index_manager()
    metrics = get_metrics()
    cases = payload.cases or []
    results: List[RetrievalEvalCaseResult] = []
    evaluated = 0
    skipped = 0
    recall_sum = 0.0
    mrr_sum = 0.0

    for case in cases:
        relevant_doc_ids = {doc_id for doc_id in case.relevant_doc_ids if doc_id}
        relevant_chunk_ids = {chunk_id for chunk_id in case.relevant_chunk_ids if chunk_id}
        if relevant_chunk_ids:
            match_type = "chunk"
            relevant_set = relevant_chunk_ids
        else:
            match_type = "doc"
            relevant_set = relevant_doc_ids

        if not relevant_set:
            skipped += 1
            if payload.return_details:
                results.append(
                    RetrievalEvalCaseResult(
                        query=case.query,
                        match_type=match_type,
                        recall_at_k=0.0,
                        mrr=0.0,
                        relevant_count=0,
                        retrieved_ids=[],
                        matched_ids=[],
                    )
                )
            continue

        retrieved = manager.query(case.query, top_k=payload.top_k)
        if match_type == "chunk":
            retrieved_ids = [item.chunk_id for item in retrieved]
        else:
            retrieved_ids = []
            for item in retrieved:
                doc_id = item.meta.get("doc_id")
                if not doc_id:
                    doc_id = item.chunk_id.split("-", 1)[0]
                retrieved_ids.append(doc_id)

        matched = [rid for rid in retrieved_ids if rid in relevant_set]
        recall = len(set(matched)) / max(len(relevant_set), 1)
        mrr = 0.0
        for idx, rid in enumerate(retrieved_ids, start=1):
            if rid in relevant_set:
                mrr = 1.0 / idx
                break

        recall_sum += recall
        mrr_sum += mrr
        evaluated += 1

        if payload.return_details:
            results.append(
                RetrievalEvalCaseResult(
                    query=case.query,
                    match_type=match_type,
                    recall_at_k=recall,
                    mrr=mrr,
                    relevant_count=len(relevant_set),
                    retrieved_ids=retrieved_ids,
                    matched_ids=matched,
                )
            )

    avg_recall = recall_sum / evaluated if evaluated else 0.0
    avg_mrr = mrr_sum / evaluated if evaluated else 0.0
    if evaluated:
        metrics.record_retrieval_eval(avg_recall, avg_mrr, payload.top_k)

    append_audit_log(
        {
            "action": "admin_eval_retrieval",
            "actor": principal.actor,
            "total_cases": len(cases),
            "evaluated_cases": evaluated,
            "skipped_cases": skipped,
            "top_k": payload.top_k,
            "recall_at_k": avg_recall,
            "mrr": avg_mrr,
        }
    )

    return RetrievalEvalResponse(
        top_k=payload.top_k,
        total_cases=len(cases),
        evaluated_cases=evaluated,
        skipped_cases=skipped,
        recall_at_k=avg_recall,
        mrr=avg_mrr,
        cases=results if payload.return_details else [],
    )


@app.get("/v1/metrics")
def metrics_snapshot(
    principal: Principal = Depends(require_user),
):
    metrics = get_metrics()
    snapshot = metrics.snapshot()
    session_count = get_conversation_store().count_sessions()
    diagnostics = snapshot.setdefault("diagnostics", {})
    sessions_block = diagnostics.setdefault("sessions", {})
    sessions_block["active"] = session_count
    metrics.record_snapshot(snapshot)
    append_metrics_snapshot(snapshot)
    return snapshot


@app.get("/v1/metrics/history")
def metrics_history(
    limit: int = 30,
    principal: Principal = Depends(require_admin),
):
    entries = load_metrics_history(limit=limit)
    if not entries:
        metrics = get_metrics()
        entries = metrics.history(limit=limit)
    return {"entries": entries}


@app.get("/v1/status", response_model=ServiceStatusResponse)
def service_status(
    principal: Principal = Depends(require_user),
) -> ServiceStatusResponse:
    metrics = get_metrics()
    snapshot = get_service_status_snapshot(metrics.snapshot())
    append_status_snapshot(snapshot.model_dump(mode="json"))
    return snapshot


@app.get("/v1/admin/audit", response_model=AdminAuditResponse)
def admin_audit(
    limit: int = 100,
    principal: Principal = Depends(require_admin),
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


@app.get("/v1/admin/escalations", response_model=AdminEscalationResponse)
def admin_escalations(
    limit: int = 50,
    principal: Principal = Depends(require_admin),
) -> AdminEscalationResponse:
    records = load_escalations(limit=limit)
    entries: List[AdminEscalationEntry] = []
    for record in records:
        raw_message = record.get("message")
        message = None
        if isinstance(raw_message, dict):
            try:
                message = ConversationMessage(**raw_message)
            except Exception:
                message = None
        conversation = []
        for entry in record.get("conversation", []) or []:
            if not isinstance(entry, dict):
                continue
            try:
                conversation.append(ConversationMessage(**entry))
            except Exception:
                continue
        created_raw = record.get("created_at")
        try:
            created_at = datetime.fromisoformat(created_raw) if isinstance(created_raw, str) else datetime.now(UTC)
        except Exception:
            created_at = datetime.now(UTC)
        entries.append(
            AdminEscalationEntry(
                escalation_id=str(record.get("escalation_id", "")),
                status=str(record.get("status", "pending")),
                reason=record.get("reason"),
                notes=record.get("notes"),
                created_at=created_at,
                user_id=str(record.get("user_id", "")),
                session_id=str(record.get("session_id", "")),
                message_id=str(record.get("message_id", "")),
                message=message,
                conversation=conversation,
            )
        )
    return AdminEscalationResponse(entries=entries)




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
    principal: Principal = Depends(require_admin),
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
    principal: Principal = Depends(require_admin_write),
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
            "actor": principal.actor,
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
    principal: Principal = Depends(require_admin_write),
) -> AdminSourceDeleteResponse:
    normalized = normalize_source_id(doc_id)
    deleted = delete_document(normalized)
    append_audit_log(
        {
            "action": "admin_source_delete",
            "doc_id": normalized,
            "deleted": deleted,
            "actor": principal.actor,
        }
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Source not found")
    try:
        manager = get_index_manager()
        manager.rebuild()
    except Exception as exc:
        log.error("index_rebuild_after_source_delete_failed", doc_id=normalized, error=str(exc))
    return AdminSourceDeleteResponse(doc_id=normalized, deleted=True)


@app.post("/v1/admin/sources/{doc_id}/verify", response_model=AdminSourceVerifyResponse)
def admin_sources_verify(
    doc_id: str,
    principal: Principal = Depends(require_admin_write),
) -> AdminSourceVerifyResponse:
    updated = mark_document_verified(normalize_source_id(doc_id), actor=principal.actor)
    if not updated:
        raise HTTPException(status_code=404, detail="Source not found")
    verified_raw = (updated.extra or {}).get("verified_at")
    try:
        verified_at = datetime.fromisoformat(verified_raw) if isinstance(verified_raw, str) else updated.updated_at
    except Exception:
        verified_at = updated.updated_at
    append_audit_log(
        {
            "action": "admin_source_verify",
            "doc_id": updated.doc_id,
            "actor": principal.actor,
        }
    )
    return AdminSourceVerifyResponse(doc_id=updated.doc_id, verified_at=verified_at)


@app.get("/v1/admin/stop-list")
def admin_stop_list(
    principal: Principal = Depends(require_admin),
):
    items = load_stop_list()
    return {"items": items, "updated_at": datetime.now(UTC)}


@app.post("/v1/admin/stop-list")
def admin_stop_list_update(
    payload: dict,
    principal: Principal = Depends(require_admin_write),
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
            "actor": principal.actor,
        }
    )
    return {"items": cleaned, "updated_at": datetime.now(UTC)}


@app.get("/v1/admin/jobs", response_model=AdminJobHistoryResponse)
def admin_jobs(
    limit: int = 50,
    principal: Principal = Depends(require_admin),
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
    principal: Principal = Depends(require_admin),
):
    records = load_templates()
    templates = [AdminTemplate(**record) for record in records]
    return templates


@app.post("/v1/admin/templates", response_model=AdminTemplateUpsertResponse)
def admin_templates_upsert(
    payload: AdminTemplateUpsertRequest,
    principal: Principal = Depends(require_admin_write),
) -> AdminTemplateUpsertResponse:
    record = upsert_template(payload.model_dump())
    append_audit_log(
        {
            "action": "admin_template_upsert",
            "template_id": record["template_id"],
            "actor": principal.actor,
        }
    )
    return AdminTemplateUpsertResponse(template=AdminTemplate(**record))


@app.delete("/v1/admin/templates/{template_id}", response_model=AdminTemplateDeleteResponse)
def admin_templates_delete(
    template_id: str,
    principal: Principal = Depends(require_admin_write),
) -> AdminTemplateDeleteResponse:
    deleted = delete_template(template_id)
    append_audit_log(
        {
            "action": "admin_template_delete",
            "template_id": template_id,
            "deleted": deleted,
            "actor": principal.actor,
        }
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Template not found")
    return AdminTemplateDeleteResponse(template_id=template_id, deleted=True)


@app.get("/v1/admin/prompts", response_model=List[AdminPrompt])
def admin_prompts_list(
    principal: Principal = Depends(require_admin),
):
    records = _ensure_default_prompts()
    assistant_name = _assistant_display_name()
    prompts = []
    for record in records:
        prompts.append(AdminPrompt(**_normalize_prompt_payload(record, assistant_name)))
    return prompts


@app.post("/v1/admin/prompts", response_model=AdminPromptUpsertResponse)
def admin_prompts_upsert(
    payload: AdminPromptUpsertRequest,
    principal: Principal = Depends(require_admin_write),
) -> AdminPromptUpsertResponse:
    data = payload.model_dump()
    content, removed = strip_assistant_intro(data.get("content"))
    if removed:
        data["content"] = content
    record = upsert_prompt(data)
    append_audit_log(
        {
            "action": "admin_prompt_upsert",
            "prompt_id": record["prompt_id"],
            "actor": principal.actor,
        }
    )
    return AdminPromptUpsertResponse(prompt=AdminPrompt(**_normalize_prompt_payload(record)))


@app.post("/v1/admin/prompts/{prompt_id}/activate", response_model=AdminPromptUpsertResponse)
def admin_prompts_activate(
    prompt_id: str,
    principal: Principal = Depends(require_admin_write),
) -> AdminPromptUpsertResponse:
    record = set_active_prompt(prompt_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Prompt not found")
    append_audit_log(
        {
            "action": "admin_prompt_activate",
            "prompt_id": prompt_id,
            "actor": principal.actor,
        }
    )
    return AdminPromptUpsertResponse(prompt=AdminPrompt(**_normalize_prompt_payload(record)))


@app.delete("/v1/admin/prompts/{prompt_id}", response_model=AdminPromptDeleteResponse)
def admin_prompts_delete(
    prompt_id: str,
    principal: Principal = Depends(require_admin_write),
) -> AdminPromptDeleteResponse:
    deleted = delete_prompt(prompt_id)
    append_audit_log(
        {
            "action": "admin_prompt_delete",
            "prompt_id": prompt_id,
            "deleted": deleted,
            "actor": principal.actor,
        }
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return AdminPromptDeleteResponse(prompt_id=prompt_id, deleted=True)
