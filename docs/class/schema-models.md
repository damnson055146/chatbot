# Schema Models Class Diagram (PlantUML)

```plantuml
@startuml
hide empty members
skinparam classAttributeIconSize 0
left to right direction

package "schemas.query" {
  class QueryDiagnostics {
    +retrieval_ms: Float [0..1]
    +rerank_ms: Float [0..1]
    +generation_ms: Float [0..1]
    +end_to_end_ms: Float [0..1]
    +low_confidence: Boolean
    +citation_coverage: Float [0..1]
    +review_suggested: Boolean
    +review_reason: String [0..1]
  }

  class Document {
    +doc_id: String
    +source_name: String
    +language: String
    +url: String [0..1]
    +domain: String [0..1]
    +freshness: String [0..1]
    +checksum: String [0..1]
    +version: Integer
    +updated_at: DateTime
    +tags: List<String>
    +extra: Map<String, Any>
  }

  class ChunkMeta {
    +doc_id: String
    +chunk_id: String
    +page: Integer [0..1]
    +section: String [0..1]
    +para: Integer [0..1]
    +start_idx: Integer [0..1]
    +end_idx: Integer [0..1]
  }

  class HighlightSpan {
    +start: Integer
    +end: Integer
  }

  class ChunkDetail {
    +chunk_id: String
    +doc_id: String
    +text: String
    +start_idx: Integer
    +end_idx: Integer
    +metadata: Map<String, Any>
    +last_verified_at: DateTime [0..1]
    +highlights: List<HighlightSpan>
  }

  class ChunkDetailResponse {
    +chunk: ChunkDetail
  }

  class Citation {
    +chunk_id: String
    +doc_id: String
    +snippet: String
    +score: Float
    +source_name: String [0..1]
    +url: String [0..1]
    +domain: String [0..1]
    +start_char: Integer [0..1]
    +end_char: Integer [0..1]
    +last_verified_at: DateTime [0..1]
    +highlights: List<HighlightSpan>
  }

  class QueryRequest {
    +question: String
    +language: String
    +slots: Map<String, Any>
    +top_k: Integer
    +k_cite: Integer
    +use_rag: Boolean
    +session_id: String [0..1]
    +reset_slots: List<String>
    +temperature: Float [0..1]
    +top_p: Float [0..1]
    +max_tokens: Integer [0..1]
    +stop: List<String>
    +model: String [0..1]
    +explain_like_new: Boolean
    +attachments: List<String>
  }

  class QueryResponse {
    +answer: String
    +citations: List<Citation>
    +trace_id: String
    +session_id: String
    +slots: Map<String, Any>
    +missing_slots: List<String>
    +slot_prompts: Map<String, String>
    +slot_suggestions: List<String>
    +slot_errors: Map<String, String>
    +diagnostics: QueryDiagnostics [0..1]
    +attachments: List<String>
  }
}

package "schemas.rerank" {
  class RerankDocument {
    +text: String
    +document_id: String [0..1]
    +metadata: Map<String, Any>
  }

  class RerankRequest {
    +query: String
    +documents: List<RerankDocument>
    +language: String
    +model: String [0..1]
  }

  class RerankResult {
    +index: Integer
    +score: Float
    +document: RerankDocument
  }

  class RerankResponse {
    +query: String
    +trace_id: String
    +results: List<RerankResult>
  }
}

package "schemas.conversation" {
  class MessageAttachmentPayload {
    +client_id: String
    +filename: String
    +mime_type: String
    +size_bytes: Integer
    +upload_id: String [0..1]
    +download_url: String [0..1]
    +status: String
    +error: String [0..1]
  }

  class ConversationMessage {
    +id: String
    +role: String
    +content: String
    +created_at: DateTime
    +language: String [0..1]
    +citations: List<Citation>
    +diagnostics: QueryDiagnostics [0..1]
    +low_confidence: Boolean [0..1]
    +attachments: List<MessageAttachmentPayload>
  }

  class SessionMessagesResponse {
    +session_id: String
    +messages: List<ConversationMessage>
  }

  class AdminConversationMessage {
  }

  class AdminSessionMessagesResponse {
    +user_id: String
    +session_id: String
    +messages: List<AdminConversationMessage>
  }

  class AdminUserSummary {
    +user_id: String
    +display_name: String [0..1]
    +contact_email: String [0..1]
    +session_count: Integer
    +last_active_at: DateTime [0..1]
  }

  class AdminSessionSummary {
    +user_id: String
    +session_id: String
    +title: String [0..1]
    +language: String
    +slot_count: Integer
    +pinned: Boolean
    +archived: Boolean
    +created_at: DateTime
    +updated_at: DateTime
  }

  class EscalationRequest {
    +session_id: String
    +message_id: String
    +reason: String [0..1]
    +notes: String [0..1]
  }

  class EscalationResponse {
    +escalation_id: String
    +status: String
    +created_at: DateTime
    +session_id: String
    +message_id: String
  }

  class AdminEscalationEntry {
    +escalation_id: String
    +status: String
    +reason: String [0..1]
    +notes: String [0..1]
    +created_at: DateTime
    +user_id: String
    +session_id: String
    +message_id: String
    +message: ConversationMessage [0..1]
    +conversation: List<ConversationMessage>
  }

  class AdminEscalationResponse {
    +entries: List<AdminEscalationEntry>
  }
}

package "schemas.session" {
  class SessionStateResponse {
    +session_id: String
    +slots: Map<String, Any>
    +slot_errors: Map<String, String>
    +language: String
    +created_at: DateTime
    +updated_at: DateTime
    +remaining_ttl_seconds: Integer [0..1]
    +slot_count: Integer
    +title: String [0..1]
    +pinned: Boolean
    +archived: Boolean
  }

  class SessionListResponse {
    +sessions: List<SessionStateResponse>
  }

  class SessionSlotsUpdateRequest {
    +slots: Map<String, Any>
    +reset_slots: List<String>
  }

  class SessionCreateRequest {
    +title: String [0..1]
    +language: String [0..1]
  }

  class SessionMetadataUpdateRequest {
    +title: String [0..1]
    +pinned: Boolean [0..1]
    +archived: Boolean [0..1]
  }

  class UserProfileUpdateRequest {
    +display_name: String [0..1]
    +contact_email: String [0..1]
  }

  class UserProfileResponse {
    +display_name: String [0..1]
    +contact_email: String [0..1]
    +updated_at: DateTime [0..1]
  }
}

package "schemas.slots" {
  class SlotSchema {
    +name: String
    +description: String
    +required: Boolean
    +prompt: String [0..1]
    +prompt_zh: String [0..1]
    +value_type: String
    +choices: List<String>
    +min_value: Float [0..1]
    +max_value: Float [0..1]
  }

  class SlotCatalogResponse {
    +slots: List<SlotSchema>
  }
}

package "schemas.ingest" {
  class IndexHealth {
    +document_count: Integer
    +chunk_count: Integer
    +last_build_at: DateTime [0..1]
    +errors: List<String>
  }

  class IngestRequest {
    +source_name: String
    +content: String
    +doc_id: String [0..1]
    +language: String
    +domain: String [0..1]
    +freshness: String [0..1]
    +url: String [0..1]
    +tags: List<String>
    +max_chars: Integer
    +overlap: Integer
  }

  class IngestResponse {
    +doc_id: String
    +version: Integer
    +chunk_count: Integer
    +health: IndexHealth
  }

  class BulkIngestItem {
    +source_name: String
    +content: String [0..1]
    +path: String [0..1]
    +doc_id: String [0..1]
    +language: String
    +domain: String [0..1]
    +freshness: String [0..1]
    +url: String [0..1]
    +tags: List<String>
    +max_chars: Integer
    +overlap: Integer
    +extra: Map<String, Any>
  }

  class BulkIngestRequest {
    +documents: List<BulkIngestItem>
  }

  class UploadRecord {
    +upload_id: String
    +filename: String
    +storage_filename: String
    +mime_type: String
    +size_bytes: Integer
    +sha256: String
    +stored_at: DateTime
    +purpose: String
    +uploader: String [0..1]
    +download_url: String [0..1]
    +retention_days: Integer [0..1]
    +expires_at: DateTime [0..1]
  }

  class UploadInitResponse {
    +upload_id: String
    +filename: String
    +mime_type: String
    +size_bytes: Integer
    +sha256: String
    +stored_at: DateTime
    +download_url: String [0..1]
    +retention_days: Integer [0..1]
    +expires_at: DateTime [0..1]
  }

  class UploadSignedUrlResponse {
    +upload_id: String
    +download_url: String
    +preview_url: String [0..1]
    +expires_at: DateTime
  }

  class UploadPreviewResponse {
    +upload_id: String
    +filename: String
    +mime_type: String
    +size_bytes: Integer
    +preview_url: String [0..1]
    +download_url: String [0..1]
    +text_excerpt: String [0..1]
    +expires_at: DateTime [0..1]
  }

  class UploadCleanupResponse {
    +deleted: Integer
    +skipped: Integer
    +expired_ids: List<String>
  }

  class AdminIngestUploadRequest {
    +upload_id: String
    +source_name: String [0..1]
    +doc_id: String [0..1]
    +language: String
    +domain: String [0..1]
    +freshness: String [0..1]
    +url: String [0..1]
    +tags: List<String>
    +max_chars: Integer
    +overlap: Integer
  }
}

package "schemas.retrieval_eval" {
  class RetrievalEvalCase {
    +query: String
    +relevant_doc_ids: List<String>
    +relevant_chunk_ids: List<String>
  }

  class RetrievalEvalRequest {
    +cases: List<RetrievalEvalCase>
    +top_k: Integer
    +return_details: Boolean
  }

  class RetrievalEvalCaseResult {
    +query: String
    +match_type: String
    +recall_at_k: Float
    +mrr: Float
    +relevant_count: Integer
    +retrieved_ids: List<String>
    +matched_ids: List<String>
  }

  class RetrievalEvalResponse {
    +top_k: Integer
    +total_cases: Integer
    +evaluated_cases: Integer
    +skipped_cases: Integer
    +recall_at_k: Float
    +mrr: Float
    +cases: List<RetrievalEvalCaseResult>
  }
}

package "schemas.admin" {
  class AdminSource {
    +doc_id: String
    +source_name: String
    +language: String
    +domain: String [0..1]
    +freshness: String [0..1]
    +url: String [0..1]
    +tags: List<String>
    +last_updated_at: DateTime
    +description: String [0..1]
  }

  class AdminSourceUpsertRequest {
    +doc_id: String
    +source_name: String
    +language: String
    +domain: String [0..1]
    +freshness: String [0..1]
    +url: String [0..1]
    +tags: List<String>
    +description: String [0..1]
  }

  class AdminSourceUpsertResponse {
    +source: AdminSource
    +updated_at: DateTime
  }

  class AdminSourceDeleteResponse {
    +doc_id: String
    +deleted: Boolean
    +updated_at: DateTime
  }

  class AdminSourceVerifyResponse {
    +doc_id: String
    +verified_at: DateTime
    +updated_at: DateTime
  }

  class AdminSlotConfig {
    +name: String
    +description: String
    +prompt: String [0..1]
    +prompt_zh: String [0..1]
    +required: Boolean
    +value_type: String
    +choices: List<String>
    +min_value: Float [0..1]
    +max_value: Float [0..1]
  }

  class AdminRetrievalSettings {
    +alpha: Float
    +top_k: Integer
    +k_cite: Integer
  }

  class AdminConfigResponse {
    +sources: List<AdminSource>
    +slots: List<AdminSlotConfig>
    +retrieval: AdminRetrievalSettings
  }

  class AdminUpdateRetrievalRequest

  class AdminUpdateRetrievalResponse {
    +updated_at: DateTime
  }

  class AdminUpdateSlotsRequest {
    +slots: List<AdminSlotConfig>
  }

  class AdminUpdateSlotsResponse {
    +slots: List<AdminSlotConfig>
    +updated_at: DateTime
  }

  class AdminAssistantOpeningEntry {
    +language: String
    +template_id: String
    +content: String [0..1]
    +updated_at: DateTime [0..1]
  }

  class AdminAssistantOpeningResponse {
    +entries: List<AdminAssistantOpeningEntry>
  }

  class AdminAssistantOpeningUpdateRequest {
    +language: String
    +content: String
  }

  class AdminAssistantOpeningUpdateResponse {
    +entry: AdminAssistantOpeningEntry
    +updated_at: DateTime
  }

  class AdminAuditEntry {
    +timestamp: DateTime
    +action: String
    +details: Map<String, Any>
  }

  class AdminAuditResponse {
    +entries: List<AdminAuditEntry>
  }

  class AdminJobEntry {
    +job_id: String
    +job_type: String
    +status: String
    +started_at: DateTime
    +completed_at: DateTime [0..1]
    +duration_ms: Float [0..1]
    +metadata: Map<String, Any>
  }

  class AdminJobHistoryResponse {
    +jobs: List<AdminJobEntry>
  }

  class JobEnqueueResponse {
    +job_id: String
    +job_type: String
    +status: String
    +queued_at: DateTime
    +attempts: Integer
    +max_attempts: Integer
  }

  class AdminTemplate {
    +template_id: String
    +name: String
    +description: String [0..1]
    +language: String
    +category: String [0..1]
    +content: String
    +created_at: DateTime
    +updated_at: DateTime
  }

  class AdminTemplateUpsertRequest {
    +template_id: String
    +name: String
    +content: String
    +description: String [0..1]
    +language: String
    +category: String [0..1]
  }

  class AdminTemplateUpsertResponse {
    +template: AdminTemplate
  }

  class AdminTemplateDeleteResponse {
    +template_id: String
    +deleted: Boolean
    +updated_at: DateTime
  }

  class AdminPrompt {
    +prompt_id: String
    +name: String
    +content: String
    +description: String [0..1]
    +language: String
    +is_active: Boolean
    +created_at: DateTime
    +updated_at: DateTime
  }

  class AdminPromptUpsertRequest {
    +prompt_id: String [0..1]
    +name: String
    +content: String
    +description: String [0..1]
    +language: String
    +is_active: Boolean
  }

  class AdminPromptUpsertResponse {
    +prompt: AdminPrompt
  }

  class AdminPromptDeleteResponse {
    +prompt_id: String
    +deleted: Boolean
    +updated_at: DateTime
  }

  class AdminAssistantProfileResponse {
    +profile: AssistantProfileResponse
    +updated_at: DateTime [0..1]
  }

  class AdminAssistantProfileUpdateRequest {
    +name: String [0..1]
    +avatar: AssistantAvatarUpdate [0..1]
  }

  class AdminAssistantProfileUpdateResponse {
    +profile: AssistantProfileResponse
    +updated_at: DateTime
  }
}

package "schemas.auth" {
  class AuthLoginRequest {
    +username: String [0..1]
    +password: String [0..1]
  }

  class AuthLoginResponse {
    +access_token: String
    +token_type: String
    +role: String
  }

  class AuthRegisterRequest {
    +username: String
    +password: String
    +reset_question: String
    +reset_answer: String
  }

  class AuthRegisterResponse {
    +user_id: String
    +username: String
    +role: String
  }

  class AuthMeResponse {
    +sub: String
    +role: String
    +token_type: String
  }

  class AuthResetQuestionResponse {
    +username: String
    +reset_question: String
  }

  class AuthChangePasswordRequest {
    +current_password: String
    +new_password: String
  }

  class AuthResetPasswordRequest {
    +username: String
    +reset_answer: String
    +new_password: String
  }

  class AuthUpdateResetQuestionRequest {
    +reset_question: String
    +reset_answer: String
  }
}

package "schemas.assistant" {
  class AssistantOpeningResponse {
    +opening: String [0..1]
    +language: String
  }

  class AssistantAvatarConfig {
    +accent: String
    +base: String
    +ring: String
    +face: String
    +image_url: String [0..1]
  }

  class AssistantProfileResponse {
    +name: String
    +avatar: AssistantAvatarConfig
  }

  class AssistantAvatarUpdate {
    +accent: String [0..1]
    +base: String [0..1]
    +ring: String [0..1]
    +face: String [0..1]
    +image_url: String [0..1]
  }
}

package "schemas.status" {
  class ServiceStatusMetric {
    +name: String
    +status: String
    +value: Float [0..1]
    +target: Float [0..1]
    +threshold_amber: Float [0..1]
    +threshold_red: Float [0..1]
  }

  class ServiceStatusCategory {
    +name: String
    +metrics: List<ServiceStatusMetric>
  }

  class ServiceStatusResponse {
    +categories: List<ServiceStatusCategory>
    +generated_at: DateTime
  }
}

QueryResponse "1" o-- "*" Citation : citations
QueryResponse "1" o-- "0..1" QueryDiagnostics : diagnostics
Citation "1" o-- "*" HighlightSpan : highlights
ChunkDetail "1" o-- "*" HighlightSpan : highlights
ChunkDetailResponse "1" o-- "1" ChunkDetail : chunk

RerankRequest "1" o-- "*" RerankDocument : documents
RerankResult "1" o-- "1" RerankDocument : document
RerankResponse "1" o-- "*" RerankResult : results

ConversationMessage "1" o-- "*" Citation : citations
ConversationMessage "1" o-- "0..1" QueryDiagnostics : diagnostics
ConversationMessage "1" o-- "*" MessageAttachmentPayload : attachments
AdminConversationMessage --|> ConversationMessage
SessionMessagesResponse "1" o-- "*" ConversationMessage : messages
AdminSessionMessagesResponse "1" o-- "*" AdminConversationMessage : messages

AdminEscalationEntry "0..1" o-- "1" ConversationMessage : message
AdminEscalationEntry "1" o-- "*" ConversationMessage : conversation
AdminEscalationResponse "1" o-- "*" AdminEscalationEntry : entries

SessionListResponse "1" o-- "*" SessionStateResponse : sessions
SlotCatalogResponse "1" o-- "*" SlotSchema : slots
IngestResponse "1" o-- "1" IndexHealth : health
BulkIngestRequest "1" o-- "*" BulkIngestItem : documents

RetrievalEvalRequest "1" o-- "*" RetrievalEvalCase : cases
RetrievalEvalResponse "1" o-- "*" RetrievalEvalCaseResult : cases

AdminSourceUpsertResponse "1" o-- "1" AdminSource : source
AdminConfigResponse "1" o-- "*" AdminSource : sources
AdminConfigResponse "1" o-- "*" AdminSlotConfig : slots
AdminConfigResponse "1" o-- "1" AdminRetrievalSettings : retrieval
AdminUpdateRetrievalRequest --|> AdminRetrievalSettings
AdminUpdateRetrievalResponse --|> AdminRetrievalSettings
AdminUpdateSlotsRequest "1" o-- "*" AdminSlotConfig : slots
AdminUpdateSlotsResponse "1" o-- "*" AdminSlotConfig : slots
AdminAssistantOpeningResponse "1" o-- "*" AdminAssistantOpeningEntry : entries
AdminAssistantOpeningUpdateResponse "1" o-- "1" AdminAssistantOpeningEntry : entry
AdminAuditResponse "1" o-- "*" AdminAuditEntry : entries
AdminJobHistoryResponse "1" o-- "*" AdminJobEntry : jobs
AdminTemplateUpsertResponse "1" o-- "1" AdminTemplate : template
AdminPromptUpsertResponse "1" o-- "1" AdminPrompt : prompt

AssistantProfileResponse "1" o-- "1" AssistantAvatarConfig : avatar
AdminAssistantProfileResponse "1" o-- "1" AssistantProfileResponse : profile
AdminAssistantProfileUpdateRequest "0..1" o-- "1" AssistantAvatarUpdate : avatar
AdminAssistantProfileUpdateResponse "1" o-- "1" AssistantProfileResponse : profile

ServiceStatusCategory "1" o-- "*" ServiceStatusMetric : metrics
ServiceStatusResponse "1" o-- "*" ServiceStatusCategory : categories
@enduml
```
