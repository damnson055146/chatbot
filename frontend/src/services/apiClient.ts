import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000/v1'

const buildBaseHeaders = () => {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  const apiKey = import.meta.env.VITE_API_KEY
  if (apiKey) {
    headers['X-API-Key'] = apiKey
  }
  const language = import.meta.env.VITE_DEFAULT_LANGUAGE
  if (language) {
    headers['Accept-Language'] = language
  }
  return headers
}

export const apiClient = axios.create({
  baseURL: API_BASE,
})

apiClient.interceptors.request.use((config) => {
  const apiKey = import.meta.env.VITE_API_KEY
  if (apiKey) {
    config.headers = config.headers ?? {}
    config.headers['X-API-Key'] = apiKey
  }
  const language = import.meta.env.VITE_DEFAULT_LANGUAGE
  if (language) {
    config.headers = config.headers ?? {}
    config.headers['Accept-Language'] = language
  }
  return config
})

export interface CitationPayload {
  chunk_id: string
  doc_id: string
  snippet: string
  score: number
  source_name?: string
  url?: string
}

export interface SlotDefinitionPayload {
  name: string
  description: string
  required: boolean
  prompt?: string
  prompt_zh?: string
  value_type: string
  choices?: string[] | null
  min_value?: number | null
  max_value?: number | null
}

export interface QueryRequestPayload {
  question: string
  language?: string
  slots?: Record<string, unknown>
  session_id?: string
  explain_like_new?: boolean
  top_k?: number
  k_cite?: number
  attachments?: string[]
}

export interface QueryDiagnosticsPayload {
  retrieval_ms?: number
  rerank_ms?: number
  generation_ms?: number
  end_to_end_ms?: number
  low_confidence?: boolean
  citation_coverage?: number
}

export interface QueryResponsePayload {
  answer: string
  citations: CitationPayload[]
  session_id: string
  slots: Record<string, unknown>
  missing_slots?: string[]
  slot_prompts?: Record<string, string>
  slot_suggestions?: string[]
  slot_errors?: Record<string, string>
  diagnostics?: QueryDiagnosticsPayload | null
  attachments?: string[]
}

export interface SlotCatalogResponsePayload {
  slots: SlotDefinitionPayload[]
}

export interface SessionStatePayload {
  session_id: string
  slots: Record<string, unknown>
  slot_errors: Record<string, string>
  language: string
  created_at?: string
  updated_at?: string
  remaining_ttl_seconds?: number | null
  slot_count?: number
}

export interface SessionListResponsePayload {
  sessions: SessionStatePayload[]
}

export interface ServiceStatusMetricPayload {
  name: string
  status: string
  value?: number
  target?: number
  threshold_amber?: number
}

export interface ServiceStatusCategoryPayload {
  name: string
  metrics: ServiceStatusMetricPayload[]
}

export interface ServiceStatusResponsePayload {
  categories: ServiceStatusCategoryPayload[]
  generated_at: string
}

export type MetricsSnapshotPayload = Record<string, unknown>

export interface AdminRetrievalSettingsPayload {
  alpha: number
  top_k: number
  k_cite: number
}

export interface AdminSlotConfigPayload {
  name: string
  description: string
  prompt?: string | null
  prompt_zh?: string | null
  required: boolean
  value_type: string
  choices?: string[] | null
  min_value?: number | null
  max_value?: number | null
}

export interface AdminSourcePayload {
  doc_id: string
  source_name: string
  language: string
  domain?: string | null
  freshness?: string | null
  url?: string | null
  tags?: string[]
  last_updated_at?: string
  description?: string | null
}

export interface AdminConfigPayload {
  sources: AdminSourcePayload[]
  slots: AdminSlotConfigPayload[]
  retrieval: AdminRetrievalSettingsPayload
}

export interface AdminAuditEntryPayload {
  timestamp: string
  action: string
  details: Record<string, unknown>
}

export interface AdminAuditResponsePayload {
  entries: AdminAuditEntryPayload[]
}

export interface UploadResponsePayload {
  upload_id: string
  filename: string
  mime_type: string
  size_bytes: number
  sha256: string
  stored_at: string
  download_url?: string
}

export const postQuery = async (payload: QueryRequestPayload, signal?: AbortSignal) => {
  const { data } = await apiClient.post<QueryResponsePayload>('/query', payload, { signal })
  return data
}

export interface QueryStreamCallbacks {
  onChunk?: (payload: { delta?: string; session_id?: string; trace_id?: string }) => void
  onCitations?: (
    payload: Partial<Pick<QueryResponsePayload, 'citations' | 'diagnostics' | 'slots' | 'missing_slots' | 'slot_prompts' | 'slot_errors' | 'slot_suggestions'>> &
      Record<string, unknown>,
  ) => void
  onCompleted?: (payload: QueryResponsePayload) => void
  onError?: (payload: { message?: string; code?: string }) => void
}

const parseSseEvent = (block: string) => {
  const lines = block.split(/\r?\n/)
  let eventName = ''
  const dataLines: string[] = []
  for (const line of lines) {
    if (line.startsWith('event:')) {
      eventName = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trim())
    }
  }
  return { eventName, data: dataLines.join('\n') }
}

export const streamQuery = async (
  payload: QueryRequestPayload,
  callbacks: QueryStreamCallbacks = {},
  signal?: AbortSignal,
) => {
  const headers = {
    ...buildBaseHeaders(),
    Accept: 'text/event-stream',
    'Cache-Control': 'no-cache',
  }

  const response = await fetch(`${API_BASE}/query?stream=true`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
    signal,
  })

  if (!response.ok || !response.body) {
    throw new Error(`Streaming request failed with status ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  const aggregate: QueryResponsePayload = {
    answer: '',
    citations: [],
    session_id: payload.session_id ?? '',
    slots: {},
    missing_slots: [],
    slot_prompts: {},
    slot_errors: {},
    slot_suggestions: [],
    diagnostics: null,
    attachments: payload.attachments,
  }

  return new Promise<QueryResponsePayload>((resolve, reject) => {
    const finish = (result?: QueryResponsePayload) => {
      reader.cancel().catch(() => undefined)
      resolve(result ?? aggregate)
    }

    const fail = (error: unknown) => {
      reader.cancel().catch(() => undefined)
      reject(error)
    }

    const processEvent = (rawBlock: string) => {
      if (!rawBlock.trim()) return
      const { eventName, data } = parseSseEvent(rawBlock)
      if (!eventName) return
      let parsed: any = null
      if (data) {
        try {
          parsed = JSON.parse(data)
        } catch {
          parsed = null
        }
      }
      switch (eventName) {
        case 'chunk': {
          const delta = typeof parsed?.delta === 'string' ? parsed.delta : ''
          if (delta) {
            aggregate.answer += delta
            callbacks.onChunk?.(parsed ?? {})
          }
          if (typeof parsed?.session_id === 'string') {
            aggregate.session_id = parsed.session_id
          }
          break
        }
        case 'citations': {
          if (Array.isArray(parsed?.citations)) {
            aggregate.citations = parsed.citations
          }
          if (parsed?.diagnostics) {
            aggregate.diagnostics = parsed.diagnostics
          }
          if (parsed?.slots) {
            aggregate.slots = parsed.slots
          }
          if (Array.isArray(parsed?.missing_slots)) {
            aggregate.missing_slots = parsed.missing_slots
          }
          if (parsed?.slot_prompts) {
            aggregate.slot_prompts = parsed.slot_prompts
          }
          if (parsed?.slot_errors) {
            aggregate.slot_errors = parsed.slot_errors
          }
          if (Array.isArray(parsed?.slot_suggestions)) {
            aggregate.slot_suggestions = parsed.slot_suggestions
          }
          callbacks.onCitations?.(parsed ?? {})
          break
        }
        case 'completed': {
          if (typeof parsed?.answer === 'string') {
            aggregate.answer = parsed.answer
          }
          if (typeof parsed?.session_id === 'string') {
            aggregate.session_id = parsed.session_id
          }
          if (parsed?.diagnostics) {
            aggregate.diagnostics = parsed.diagnostics
          }
          if (parsed?.slots) {
            aggregate.slots = parsed.slots
          }
          if (Array.isArray(parsed?.missing_slots)) {
            aggregate.missing_slots = parsed.missing_slots
          }
          if (parsed?.slot_prompts) {
            aggregate.slot_prompts = parsed.slot_prompts
          }
          if (parsed?.slot_errors) {
            aggregate.slot_errors = parsed.slot_errors
          }
          if (Array.isArray(parsed?.slot_suggestions)) {
            aggregate.slot_suggestions = parsed.slot_suggestions
          }
          callbacks.onCompleted?.(aggregate)
          finish(aggregate)
          break
        }
        case 'error': {
          callbacks.onError?.(parsed ?? {})
          fail(new Error(parsed?.message ?? 'Streaming error'))
          break
        }
        default:
          break
      }
    }

    const pump = (): void => {
      reader
        .read()
        .then(({ value, done }) => {
          if (done) {
            const remaining = buffer + decoder.decode(new Uint8Array(), { stream: false })
            if (remaining.trim()) {
              processEvent(remaining)
            }
            finish(aggregate)
            return
          }
          buffer += decoder.decode(value ?? new Uint8Array(), { stream: true })
          let boundary = buffer.indexOf('\n\n')
          while (boundary !== -1) {
            const chunk = buffer.slice(0, boundary)
            buffer = buffer.slice(boundary + 2)
            processEvent(chunk)
            boundary = buffer.indexOf('\n\n')
          }
          pump()
        })
        .catch((error) => {
          if (signal?.aborted) {
            fail(new DOMException('Aborted', 'AbortError'))
            return
          }
          fail(error)
        })
    }

    pump()
  })
}

export const fetchSlotCatalog = async (language?: string) => {
  const { data } = await apiClient.get<SlotCatalogResponsePayload>('/slots', {
    params: language ? { lang: language } : undefined,
  })
  return data.slots
}

export const fetchSessionState = async (sessionId: string) => {
  const { data } = await apiClient.get<SessionStatePayload>(`/session/${sessionId}`)
  return data
}

export const fetchActiveSessions = async () => {
  const { data } = await apiClient.get<SessionListResponsePayload>('/session')
  return data.sessions
}

export const deleteSession = async (sessionId: string) => {
  await apiClient.delete(`/session/${sessionId}`)
}

export const fetchServiceStatus = async () => {
  const { data } = await apiClient.get<ServiceStatusResponsePayload>('/status')
  return data
}

export const fetchMetricsSnapshot = async () => {
  const { data } = await apiClient.get<MetricsSnapshotPayload>('/metrics')
  return data
}

export const fetchAdminConfig = async () => {
  const { data } = await apiClient.get<AdminConfigPayload>('/admin/config')
  return data
}

export const fetchAdminAudit = async (limit = 100) => {
  const { data } = await apiClient.get<AdminAuditResponsePayload>('/admin/audit', { params: { limit } })
  return data
}

export const fetchAdminSources = async () => {
  const { data } = await apiClient.get<AdminSourcePayload[]>('/admin/sources')
  return data
}

export interface AdminSourceUpsertRequestPayload {
  doc_id: string
  source_name: string
  language: string
  domain?: string | null
  freshness?: string | null
  url?: string | null
  tags?: string[]
  description?: string | null
}

export interface AdminSourceUpsertResponsePayload {
  source: AdminSourcePayload
  updated_at: string
}

export interface AdminSourceDeleteResponsePayload {
  doc_id: string
  deleted: boolean
  updated_at: string
}

export const upsertAdminSource = async (payload: AdminSourceUpsertRequestPayload) => {
  const { data } = await apiClient.post<AdminSourceUpsertResponsePayload>('/admin/sources', payload)
  return data
}

export const deleteAdminSource = async (docId: string) => {
  const { data } = await apiClient.delete<AdminSourceDeleteResponsePayload>(`/admin/sources/${encodeURIComponent(docId)}`)
  return data
}

export const updateAdminRetrieval = async (payload: Partial<AdminRetrievalSettingsPayload>) => {
  const { data } = await apiClient.post<AdminRetrievalSettingsPayload>('/admin/retrieval', payload)
  return data
}

export const uploadAttachment = async (file: File) => {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await apiClient.post<UploadResponsePayload>('/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}
