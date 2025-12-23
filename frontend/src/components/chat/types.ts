export type AttachmentStatus = 'queued' | 'uploading' | 'ready' | 'error'

export interface MessageAttachment {
  clientId: string
  uploadId?: string
  filename: string
  mimeType: string
  sizeBytes: number
  downloadUrl?: string
  status: AttachmentStatus
  error?: string
}

export interface ChatMessageModel {
  id: string
  role: 'user' | 'assistant'
  content: string
  createdAt: string
  citations?: Array<{
    chunk_id: string
    doc_id: string
    snippet: string
    score: number
    source_name?: string
    url?: string
  }>
  diagnostics?: {
    retrieval_ms?: number
    rerank_ms?: number
    generation_ms?: number
    end_to_end_ms?: number
    citation_coverage?: number
    low_confidence?: boolean
  } | null
  lowConfidence?: boolean
  streaming?: boolean
  attachments?: MessageAttachment[]
}

export interface ConversationSummary {
  sessionId: string
  title: string
  updatedAt?: string
  createdAt?: string
  pinned: boolean
  slotCount: number
  archived: boolean
}
