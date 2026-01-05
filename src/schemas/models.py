from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict, model_validator


def _now_utc() -> datetime:
    return datetime.now(UTC)


class QueryDiagnostics(BaseModel):
    """Performance and quality diagnostics returned with a query answer."""

    retrieval_ms: float | None = Field(default=None, ge=0, description="Retrieval latency in ms.")
    rerank_ms: float | None = Field(default=None, ge=0, description="Rerank latency in ms.")
    generation_ms: float | None = Field(default=None, ge=0, description="Generation latency in ms.")
    end_to_end_ms: float | None = Field(default=None, ge=0, description="Total latency in ms.")
    low_confidence: bool = Field(default=False, description="True if citations are below the target.")
    citation_coverage: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Normalized citation coverage ratio.",
    )
    review_suggested: bool = Field(default=False, description="True if manual review is suggested.")
    review_reason: str | None = Field(default=None, description="Reason for review suggestion.")


class Document(BaseModel):
    """Metadata for an ingested document within the knowledge corpus."""

    doc_id: str = Field(min_length=1, description="Stable document identifier.")
    source_name: str = Field(min_length=1, description="Human-friendly source title.")
    language: str = Field(default="auto", description="Language code (en/zh/auto).")
    url: Optional[str] = Field(default=None, description="Source URL for provenance.")
    domain: Optional[str] = Field(default=None, description="Domain label (admissions/visa/fees/etc.).")
    freshness: Optional[str] = Field(default=None, description="Declared freshness date string.")
    checksum: Optional[str] = Field(default=None, description="Optional content checksum.")
    version: int = Field(default=1, ge=1, description="Document version number.")
    updated_at: datetime = Field(default_factory=_now_utc, description="Last update timestamp.")
    tags: List[str] = Field(default_factory=list, description="Free-form tags for filtering.")
    extra: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata.")


class ChunkMeta(BaseModel):
    doc_id: str
    chunk_id: str
    page: Optional[int] = None
    section: Optional[str] = None
    para: Optional[int] = None
    start_idx: Optional[int] = None
    end_idx: Optional[int] = None


class HighlightSpan(BaseModel):
    """Inclusive-exclusive span for highlighted text offsets."""

    start: int = Field(ge=0, description="Start offset (inclusive).")
    end: int = Field(ge=0, description="End offset (exclusive).")

    @model_validator(mode="after")
    def validate_span(self):
        if self.end <= self.start:
            raise ValueError("Highlight span end must be greater than start.")
        return self


class ChunkDetail(BaseModel):
    """Full detail for a retrieved chunk used in citation context."""

    chunk_id: str = Field(min_length=1, description="Chunk identifier.")
    doc_id: str = Field(min_length=1, description="Parent document identifier.")
    text: str = Field(description="Chunk text content.")
    start_idx: int = Field(ge=0, description="Start offset in the source document.")
    end_idx: int = Field(ge=0, description="End offset in the source document.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Chunk-level metadata.")
    last_verified_at: datetime | None = Field(
        default=None, description="Timestamp of last verification for the source document."
    )
    highlights: List[HighlightSpan] = Field(
        default_factory=list, description="Highlighted spans for UI emphasis."
    )

    @model_validator(mode="after")
    def validate_ranges(self):
        if self.end_idx < self.start_idx:
            raise ValueError("Chunk end_idx must be greater than or equal to start_idx.")
        return self


class ChunkDetailResponse(BaseModel):
    chunk: ChunkDetail


class Citation(BaseModel):
    """Citation metadata that links an answer to source passages."""

    chunk_id: str = Field(min_length=1, description="Chunk identifier.")
    doc_id: str = Field(min_length=1, description="Parent document identifier.")
    snippet: str = Field(description="Short excerpt for quick display.")
    score: float = Field(description="Rerank score for this citation.")
    source_name: str | None = Field(default=None, description="Human-friendly source name.")
    url: str | None = Field(default=None, description="Source URL for deep linking.")
    domain: str | None = Field(default=None, description="Source domain label.")
    start_char: int | None = Field(default=None, ge=0, description="Start offset in the source document.")
    end_char: int | None = Field(default=None, ge=0, description="End offset in the source document.")
    last_verified_at: datetime | None = Field(
        default=None, description="Timestamp of last verification for the source document."
    )
    highlights: List[HighlightSpan] = Field(
        default_factory=list, description="Highlighted spans for the cited content."
    )

    @model_validator(mode="after")
    def validate_offsets(self):
        if (self.start_char is None) != (self.end_char is None):
            raise ValueError("start_char and end_char must be set together.")
        if self.start_char is not None and self.end_char is not None and self.end_char < self.start_char:
            raise ValueError("end_char must be greater than or equal to start_char.")
        return self


class QueryRequest(BaseModel):
    """User query payload for retrieval and generation."""

    question: str = Field(description="User question text.")
    language: str = Field(default="auto", description="Input language (en/zh/auto).")
    slots: Dict[str, Any] = Field(default_factory=dict, description="Slot values to merge into session state.")
    top_k: int = Field(default=8, ge=0, description="Number of chunks to retrieve.")
    k_cite: int = Field(default=2, ge=0, description="Number of citations to include.")
    use_rag: bool = Field(default=True, description="Enable retrieval augmented generation.")
    session_id: Optional[str] = Field(default=None, description="Existing session id to continue.")
    reset_slots: List[str] = Field(default_factory=list, description="Slot names to reset.")
    temperature: float | None = Field(default=None, ge=0.0, le=2.0, description="Sampling temperature.")
    top_p: float | None = Field(default=None, ge=0.0, le=1.0, description="Nucleus sampling probability.")
    max_tokens: int | None = Field(default=None, ge=1, le=4096, description="Max tokens for generation.")
    stop: List[str] = Field(default_factory=list, description="Stop sequences for generation.")
    model: Optional[str] = Field(default=None, description="Override model identifier.")
    explain_like_new: bool = Field(
        default=False, description="If true, reformulate answer for newcomers."
    )
    attachments: List[str] = Field(default_factory=list, description="Upload ids to include as context.")


class QueryResponse(BaseModel):
    """Answer payload returned by the query endpoint."""

    answer: str = Field(description="Generated answer text.")
    citations: List[Citation] = Field(description="Citations supporting the answer.")
    trace_id: str = Field(description="Server trace id for observability.")
    session_id: str = Field(description="Session identifier for follow-up turns.")
    slots: Dict[str, Any] = Field(default_factory=dict, description="Resolved slot values.")
    missing_slots: List[str] = Field(default_factory=list, description="Missing slot names.")
    slot_prompts: Dict[str, str] = Field(default_factory=dict, description="Prompts for missing slots.")
    slot_suggestions: List[str] = Field(default_factory=list, description="User-facing slot suggestions.")
    slot_errors: Dict[str, str] = Field(default_factory=dict, description="Slot validation errors.")
    diagnostics: QueryDiagnostics | None = Field(default=None, description="Performance diagnostics.")
    attachments: List[str] = Field(default_factory=list, description="Attachment upload ids.")


class RerankDocument(BaseModel):
    text: str
    document_id: str | None = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RerankRequest(BaseModel):
    query: str
    documents: List[RerankDocument]
    language: str = Field(default="auto")
    model: str | None = None


class RerankResult(BaseModel):
    index: int
    score: float
    document: RerankDocument


class RerankResponse(BaseModel):
    query: str
    trace_id: str
    results: List[RerankResult]


class MessageAttachmentPayload(BaseModel):
    client_id: str
    filename: str
    mime_type: str
    size_bytes: int
    upload_id: str | None = None
    download_url: str | None = None
    status: str = "ready"
    error: str | None = None


class ConversationMessage(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime
    language: str | None = None
    citations: List[Citation] = Field(default_factory=list)
    diagnostics: QueryDiagnostics | None = None
    low_confidence: bool | None = None
    attachments: List[MessageAttachmentPayload] = Field(default_factory=list)


class SessionMessagesResponse(BaseModel):
    session_id: str
    messages: List[ConversationMessage]


class AdminConversationMessage(ConversationMessage):
    pass


class AdminSessionMessagesResponse(BaseModel):
    user_id: str
    session_id: str
    messages: List[AdminConversationMessage]


class AdminUserSummary(BaseModel):
    user_id: str
    display_name: str | None = None
    contact_email: str | None = None
    session_count: int
    last_active_at: datetime | None = None


class AdminSessionSummary(BaseModel):
    user_id: str
    session_id: str
    title: str | None = None
    language: str = "auto"
    slot_count: int = 0
    pinned: bool = False
    archived: bool = False
    created_at: datetime
    updated_at: datetime


class RetrievalEvalCase(BaseModel):
    query: str
    relevant_doc_ids: List[str] = Field(default_factory=list)
    relevant_chunk_ids: List[str] = Field(default_factory=list)


class RetrievalEvalRequest(BaseModel):
    cases: List[RetrievalEvalCase] = Field(default_factory=list)
    top_k: int = Field(default=8, ge=1, le=50)
    return_details: bool = False


class RetrievalEvalCaseResult(BaseModel):
    query: str
    match_type: str
    recall_at_k: float
    mrr: float
    relevant_count: int
    retrieved_ids: List[str] = Field(default_factory=list)
    matched_ids: List[str] = Field(default_factory=list)


class RetrievalEvalResponse(BaseModel):
    top_k: int
    total_cases: int
    evaluated_cases: int
    skipped_cases: int
    recall_at_k: float
    mrr: float
    cases: List[RetrievalEvalCaseResult] = Field(default_factory=list)


class UploadRecord(BaseModel):
    """Persisted metadata for an uploaded file."""

    upload_id: str = Field(min_length=1, description="Upload identifier.")
    filename: str = Field(min_length=1, description="Original filename.")
    storage_filename: str = Field(min_length=1, description="Stored filename on disk.")
    mime_type: str = Field(min_length=1, description="Detected MIME type.")
    size_bytes: int = Field(ge=0, description="File size in bytes.")
    sha256: str = Field(min_length=1, description="SHA256 checksum of stored content.")
    stored_at: datetime = Field(default_factory=_now_utc, description="Upload timestamp.")
    purpose: str = Field(default="chat", description="Usage context for the upload.")
    uploader: str | None = Field(default=None, description="Uploader identifier (if available).")
    download_url: str | None = Field(default=None, description="Optional download URL.")
    retention_days: int | None = Field(default=None, ge=0, description="Retention window in days.")
    expires_at: datetime | None = Field(default=None, description="Expiry timestamp for retention.")

    @model_validator(mode="after")
    def validate_expiry(self):
        if self.expires_at and self.expires_at < self.stored_at:
            raise ValueError("expires_at must be on or after stored_at.")
        return self


class UploadInitResponse(BaseModel):
    upload_id: str
    filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    stored_at: datetime
    download_url: str | None = None
    retention_days: int | None = None
    expires_at: datetime | None = None


class UploadSignedUrlResponse(BaseModel):
    upload_id: str
    download_url: str
    preview_url: str | None = None
    expires_at: datetime


class UploadPreviewResponse(BaseModel):
    upload_id: str
    filename: str
    mime_type: str
    size_bytes: int
    preview_url: str | None = None
    download_url: str | None = None
    text_excerpt: str | None = None
    expires_at: datetime | None = None


class UploadCleanupResponse(BaseModel):
    deleted: int
    skipped: int
    expired_ids: List[str] = Field(default_factory=list)


class SlotSchema(BaseModel):
    name: str
    description: str
    required: bool = False
    prompt: Optional[str] = None
    prompt_zh: Optional[str] = None
    value_type: str = "string"
    choices: List[str] | None = None
    min_value: float | None = None
    max_value: float | None = None


class SlotCatalogResponse(BaseModel):
    slots: List[SlotSchema]


class SessionStateResponse(BaseModel):
    """Session snapshot returned to clients."""

    session_id: str = Field(description="Session identifier.")
    slots: Dict[str, Any] = Field(default_factory=dict, description="Current slot values.")
    slot_errors: Dict[str, str] = Field(default_factory=dict, description="Slot validation errors.")
    language: str = Field(default="auto", description="Session language.")
    created_at: datetime = Field(description="Session creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")
    remaining_ttl_seconds: int | None = Field(
        default=None, ge=0, description="Remaining TTL in seconds."
    )
    slot_count: int = Field(default=0, ge=0, description="Number of filled slots.")
    title: str | None = Field(default=None, description="Session title.")
    pinned: bool = Field(default=False, description="Pinned session flag.")
    archived: bool = Field(default=False, description="Archived session flag.")


class SessionListResponse(BaseModel):
    sessions: List[SessionStateResponse]

class SessionSlotsUpdateRequest(BaseModel):
    slots: Dict[str, Any] = Field(default_factory=dict)
    reset_slots: List[str] = Field(default_factory=list)


class SessionCreateRequest(BaseModel):
    title: str | None = None
    language: str | None = None


class SessionMetadataUpdateRequest(BaseModel):
    title: str | None = None
    pinned: bool | None = None
    archived: bool | None = None



class IndexHealth(BaseModel):
    document_count: int
    chunk_count: int
    last_build_at: Optional[datetime] = None
    errors: List[str] = Field(default_factory=list)


class IngestRequest(BaseModel):
    source_name: str
    content: str
    doc_id: Optional[str] = None
    language: str = "auto"
    domain: Optional[str] = None
    freshness: Optional[str] = None
    url: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    max_chars: int = 800
    overlap: int = 120


class IngestResponse(BaseModel):
    doc_id: str
    version: int
    chunk_count: int
    health: IndexHealth


class BulkIngestItem(BaseModel):
    source_name: str
    content: str | None = None
    path: str | None = None
    doc_id: str | None = None
    language: str = "auto"
    domain: str | None = None
    freshness: str | None = None
    url: str | None = None
    tags: List[str] = Field(default_factory=list)
    max_chars: int = 800
    overlap: int = 120
    extra: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_content_source(self):
        if bool(self.content) == bool(self.path):
            raise ValueError("Provide exactly one of content or path for bulk ingestion.")
        return self


class BulkIngestRequest(BaseModel):
    documents: List[BulkIngestItem] = Field(default_factory=list)


class AdminSource(BaseModel):
    doc_id: str
    source_name: str
    language: str
    domain: str | None = None
    freshness: str | None = None
    url: str | None = None
    tags: List[str] = Field(default_factory=list)
    last_updated_at: datetime
    description: str | None = None


class AdminSourceUpsertRequest(BaseModel):
    doc_id: str
    source_name: str
    language: str
    domain: str | None = None
    freshness: str | None = None
    url: str | None = None
    tags: List[str] = Field(default_factory=list)
    description: str | None = None


class AdminSourceUpsertResponse(BaseModel):
    source: AdminSource
    updated_at: datetime = Field(default_factory=_now_utc)


class AdminSourceDeleteResponse(BaseModel):
    doc_id: str
    deleted: bool
    updated_at: datetime = Field(default_factory=_now_utc)


class AdminSourceVerifyResponse(BaseModel):
    doc_id: str
    verified_at: datetime
    updated_at: datetime = Field(default_factory=_now_utc)


class AdminSlotConfig(BaseModel):
    name: str
    description: str = ""
    prompt: str | None = None
    prompt_zh: str | None = None
    required: bool = False
    value_type: str = "string"
    choices: List[str] | None = None
    min_value: float | None = None
    max_value: float | None = None


class AdminRetrievalSettings(BaseModel):
    alpha: float = Field(default=0.5, ge=0.0, le=1.0)
    top_k: int = Field(default=8, ge=1, le=50)
    k_cite: int = Field(default=2, ge=1, le=10)


class AdminConfigResponse(BaseModel):
    sources: List[AdminSource] = Field(default_factory=list)
    slots: List[AdminSlotConfig] = Field(default_factory=list)
    retrieval: AdminRetrievalSettings


class AdminUpdateRetrievalRequest(AdminRetrievalSettings):
    pass


class AdminUpdateRetrievalResponse(AdminRetrievalSettings):
    updated_at: datetime = Field(default_factory=_now_utc)


class AdminUpdateSlotsRequest(BaseModel):
    slots: List[AdminSlotConfig]


class AdminUpdateSlotsResponse(BaseModel):
    slots: List[AdminSlotConfig]
    updated_at: datetime = Field(default_factory=_now_utc)


class AdminAssistantOpeningEntry(BaseModel):
    language: str
    template_id: str
    content: str | None = None
    updated_at: datetime | None = None


class AdminAssistantOpeningResponse(BaseModel):
    entries: List[AdminAssistantOpeningEntry]


class AdminAssistantOpeningUpdateRequest(BaseModel):
    language: str
    content: str


class AdminAssistantOpeningUpdateResponse(BaseModel):
    entry: AdminAssistantOpeningEntry
    updated_at: datetime = Field(default_factory=_now_utc)


class AdminAuditEntry(BaseModel):
    timestamp: datetime
    action: str
    details: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class AdminAuditResponse(BaseModel):
    entries: List[AdminAuditEntry]


class EscalationRequest(BaseModel):
    session_id: str
    message_id: str
    reason: str | None = None
    notes: str | None = None


class EscalationResponse(BaseModel):
    escalation_id: str
    status: str
    created_at: datetime
    session_id: str
    message_id: str


class AdminEscalationEntry(BaseModel):
    escalation_id: str
    status: str
    reason: str | None = None
    notes: str | None = None
    created_at: datetime
    user_id: str
    session_id: str
    message_id: str
    message: ConversationMessage | None = None
    conversation: List[ConversationMessage] = Field(default_factory=list)


class AdminEscalationResponse(BaseModel):
    entries: List[AdminEscalationEntry]


class ServiceStatusMetric(BaseModel):
    name: str
    status: str
    value: float | None = None
    target: float | None = None
    threshold_amber: float | None = None
    threshold_red: float | None = None


class ServiceStatusCategory(BaseModel):
    name: str
    metrics: List[ServiceStatusMetric] = Field(default_factory=list)


class ServiceStatusResponse(BaseModel):
    categories: List[ServiceStatusCategory] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=_now_utc)


class AdminJobEntry(BaseModel):
    job_id: str
    job_type: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: float | None = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AdminJobHistoryResponse(BaseModel):
    jobs: List[AdminJobEntry]


class JobEnqueueResponse(BaseModel):
    job_id: str
    job_type: str
    status: str
    queued_at: datetime
    attempts: int = 0
    max_attempts: int = 0


class AdminTemplate(BaseModel):
    template_id: str
    name: str
    description: str | None = None
    language: str = "en"
    category: str | None = None
    content: str
    created_at: datetime = Field(default_factory=_now_utc)
    updated_at: datetime = Field(default_factory=_now_utc)


class AdminTemplateUpsertRequest(BaseModel):
    template_id: str
    name: str
    content: str
    description: str | None = None
    language: str = "en"
    category: str | None = None


class AdminTemplateUpsertResponse(BaseModel):
    template: AdminTemplate


class AdminTemplateDeleteResponse(BaseModel):
    template_id: str
    deleted: bool
    updated_at: datetime = Field(default_factory=_now_utc)


class AdminPrompt(BaseModel):
    prompt_id: str
    name: str
    content: str
    description: str | None = None
    language: str = "en"
    is_active: bool = False
    created_at: datetime = Field(default_factory=_now_utc)
    updated_at: datetime = Field(default_factory=_now_utc)


class AdminPromptUpsertRequest(BaseModel):
    prompt_id: str | None = None
    name: str
    content: str
    description: str | None = None
    language: str = "en"
    is_active: bool = False


class AdminPromptUpsertResponse(BaseModel):
    prompt: AdminPrompt


class AdminPromptDeleteResponse(BaseModel):
    prompt_id: str
    deleted: bool
    updated_at: datetime = Field(default_factory=_now_utc)


class AuthLoginRequest(BaseModel):
    """MVP login request: only a single admin password is supported.

    - password == AUTH_ADMIN_PASSWORD -> role=admin
    - password == AUTH_ADMIN_READONLY_PASSWORD -> role=admin_readonly
    - otherwise -> role=user (requires registered account)
    """

    username: str | None = None
    password: str | None = None


class AuthLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


class AuthRegisterRequest(BaseModel):
    username: str
    password: str
    reset_question: str
    reset_answer: str


class AuthRegisterResponse(BaseModel):
    user_id: str
    username: str
    role: str


class AuthMeResponse(BaseModel):
    sub: str
    role: str
    token_type: str = "bearer"


class AuthResetQuestionResponse(BaseModel):
    username: str
    reset_question: str


class AuthChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class AuthResetPasswordRequest(BaseModel):
    username: str
    reset_answer: str
    new_password: str


class AuthUpdateResetQuestionRequest(BaseModel):
    reset_question: str
    reset_answer: str


class AssistantOpeningResponse(BaseModel):
    opening: str | None = None
    language: str


class AssistantAvatarConfig(BaseModel):
    accent: str = Field(default="#2563eb")
    base: str = Field(default="#e0f2ff")
    ring: str = Field(default="#bfdbfe")
    face: str = Field(default="#0f172a")
    image_url: str | None = None


class AssistantProfileResponse(BaseModel):
    name: str = Field(default="Lumi")
    avatar: AssistantAvatarConfig = Field(default_factory=AssistantAvatarConfig)


class AssistantAvatarUpdate(BaseModel):
    accent: str | None = None
    base: str | None = None
    ring: str | None = None
    face: str | None = None
    image_url: str | None = None


class AdminAssistantProfileResponse(BaseModel):
    profile: AssistantProfileResponse
    updated_at: datetime | None = None


class AdminAssistantProfileUpdateRequest(BaseModel):
    name: str | None = None
    avatar: AssistantAvatarUpdate | None = None


class AdminAssistantProfileUpdateResponse(BaseModel):
    profile: AssistantProfileResponse
    updated_at: datetime = Field(default_factory=_now_utc)


class UserProfileUpdateRequest(BaseModel):
    display_name: str | None = None
    contact_email: str | None = None


class UserProfileResponse(BaseModel):
    display_name: str | None = None
    contact_email: str | None = None
    updated_at: datetime | None = None


class AdminIngestUploadRequest(BaseModel):
    upload_id: str
    source_name: str | None = None
    doc_id: str | None = None
    language: str = "auto"
    domain: str | None = None
    freshness: str | None = None
    url: str | None = None
    tags: List[str] = Field(default_factory=list)
    max_chars: int = 800
    overlap: int = 120
