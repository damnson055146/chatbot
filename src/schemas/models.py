from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from pydantic import ConfigDict


def _now_utc() -> datetime:
    return datetime.now(UTC)


class QueryDiagnostics(BaseModel):
    retrieval_ms: float | None = None
    rerank_ms: float | None = None
    generation_ms: float | None = None
    end_to_end_ms: float | None = None
    low_confidence: bool = False
    citation_coverage: float | None = None


class Document(BaseModel):
    """Metadata for an ingested document within the knowledge corpus."""

    doc_id: str
    source_name: str
    language: str = Field(default="auto", description="language code: en/zh/auto")
    url: Optional[str] = None
    domain: Optional[str] = None  # admissions/visa/fees/scholarship
    freshness: Optional[str] = None  # date string
    checksum: Optional[str] = None
    version: int = Field(default=1, ge=1)
    updated_at: datetime = Field(default_factory=_now_utc)
    tags: List[str] = Field(default_factory=list)
    extra: Dict[str, str] = Field(default_factory=dict, description="Arbitrary metadata")


class ChunkMeta(BaseModel):
    doc_id: str
    chunk_id: str
    page: Optional[int] = None
    section: Optional[str] = None
    para: Optional[int] = None
    start_idx: Optional[int] = None
    end_idx: Optional[int] = None


class HighlightSpan(BaseModel):
    start: int
    end: int


class ChunkDetail(BaseModel):
    chunk_id: str
    doc_id: str
    text: str
    start_idx: int
    end_idx: int
    metadata: Dict[str, Any] = Field(default_factory=dict)
    last_verified_at: datetime | None = None
    highlights: List[HighlightSpan] = Field(default_factory=list)


class ChunkDetailResponse(BaseModel):
    chunk: ChunkDetail


class Citation(BaseModel):
    chunk_id: str
    doc_id: str
    snippet: str
    score: float
    source_name: str | None = None
    url: str | None = None
    domain: str | None = None
    start_char: int | None = None
    end_char: int | None = None
    last_verified_at: datetime | None = None
    highlights: List[HighlightSpan] = Field(default_factory=list)


class QueryRequest(BaseModel):
    question: str
    language: str = Field(default="auto")
    slots: Dict[str, Any] = Field(default_factory=dict)
    top_k: int = 8
    k_cite: int = 2
    session_id: Optional[str] = None
    reset_slots: List[str] = Field(default_factory=list)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, ge=1, le=4096)
    stop: List[str] = Field(default_factory=list)
    model: Optional[str] = None
    explain_like_new: bool = Field(default=False, description="If true, reformulate answer for newcomers")
    attachments: List[str] = Field(default_factory=list)


class QueryResponse(BaseModel):
    answer: str
    citations: List[Citation]
    trace_id: str
    session_id: str
    slots: Dict[str, Any] = Field(default_factory=dict)
    missing_slots: List[str] = Field(default_factory=list)
    slot_prompts: Dict[str, str] = Field(default_factory=dict)
    slot_suggestions: List[str] = Field(default_factory=list)
    slot_errors: Dict[str, str] = Field(default_factory=dict)
    diagnostics: QueryDiagnostics | None = None
    attachments: List[str] = Field(default_factory=list)


class UploadRecord(BaseModel):
    upload_id: str
    filename: str
    storage_filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    stored_at: datetime = Field(default_factory=_now_utc)
    purpose: str = "chat"
    uploader: str | None = None
    download_url: str | None = None


class UploadInitResponse(BaseModel):
    upload_id: str
    filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    stored_at: datetime
    download_url: str | None = None


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
    session_id: str
    slots: Dict[str, Any] = Field(default_factory=dict)
    slot_errors: Dict[str, str] = Field(default_factory=dict)
    language: str = "auto"
    created_at: datetime
    updated_at: datetime
    remaining_ttl_seconds: int | None = None
    slot_count: int = 0


class SessionListResponse(BaseModel):
    sessions: List[SessionStateResponse]



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


class AdminAuditEntry(BaseModel):
    timestamp: datetime
    action: str
    details: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class AdminAuditResponse(BaseModel):
    entries: List[AdminAuditEntry]


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
    prompt_id: str
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

