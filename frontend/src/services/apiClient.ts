import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000/v1'

const ACCESS_TOKEN_KEY = 'rag.auth.access_token'

export const getAccessToken = () => {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage.getItem(ACCESS_TOKEN_KEY)
  } catch {
    return null
  }
}

export const setAccessToken = (token: string) => {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(ACCESS_TOKEN_KEY, token)
}

export const clearAccessToken = () => {
  if (typeof window === 'undefined') return
  window.localStorage.removeItem(ACCESS_TOKEN_KEY)
}

const buildBaseHeaders = () => {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  const token = getAccessToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
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
  const token = getAccessToken()
  if (token) {
    config.headers = config.headers ?? {}
    config.headers['Authorization'] = `Bearer ${token}`
  }
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
  last_verified_at?: string | null
}

export interface ChunkDetailResponsePayload {
  chunk: {
    chunk_id: string
    doc_id: string
    text: string
    last_verified_at?: string | null
    highlights?: Array<{ start: number; end: number }>
    metadata?: Record<string, unknown>
  }
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
  use_rag?: boolean
  attachments?: string[]
}

export interface QueryDiagnosticsPayload {
  retrieval_ms?: number
  rerank_ms?: number
  generation_ms?: number
  end_to_end_ms?: number
  low_confidence?: boolean
  citation_coverage?: number
  review_suggested?: boolean
  review_reason?: string | null
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

export interface EscalationRequestPayload {
  session_id: string
  message_id: string
  reason?: string | null
  notes?: string | null
}

export interface EscalationResponsePayload {
  escalation_id: string
  status: string
  created_at: string
  session_id: string
  message_id: string
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
  title?: string | null
  pinned?: boolean
  archived?: boolean
}

export interface SessionCreateRequestPayload {
  title?: string | null
  language?: string | null
}

export interface SessionMetadataUpdateRequestPayload {
  title?: string | null
  pinned?: boolean | null
  archived?: boolean | null
}

export interface MessageAttachmentPayload {
  client_id: string
  filename: string
  mime_type: string
  size_bytes: number
  upload_id?: string | null
  download_url?: string | null
  status?: string
  error?: string | null
}

export interface ConversationMessagePayload {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
  language?: string | null
  citations?: CitationPayload[]
  diagnostics?: QueryDiagnosticsPayload | null
  low_confidence?: boolean | null
  attachments?: MessageAttachmentPayload[]
}

export interface SessionMessagesResponsePayload {
  session_id: string
  messages: ConversationMessagePayload[]
}

export interface SessionListResponsePayload {
  sessions: SessionStatePayload[]
}

export interface SessionSlotsUpdateRequestPayload {
  slots: Record<string, unknown>
  reset_slots?: string[]
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

export interface MetricsHistoryEntryPayload {
  timestamp: string
  snapshot: MetricsSnapshotPayload
}

export interface MetricsHistoryResponsePayload {
  entries: MetricsHistoryEntryPayload[]
}

export interface IndexHealthPayload {
  document_count: number
  chunk_count: number
  last_build_at?: string | null
  errors?: string[]
}

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

export interface AdminUserSummaryPayload {
  user_id: string
  display_name?: string | null
  contact_email?: string | null
  session_count: number
  last_active_at?: string | null
}

export interface AdminSessionSummaryPayload {
  user_id: string
  session_id: string
  title?: string | null
  language: string
  slot_count: number
  pinned: boolean
  archived: boolean
  created_at: string
  updated_at: string
}

export interface AdminConversationMessagePayload extends ConversationMessagePayload {}

export interface AdminSessionMessagesResponsePayload {
  user_id: string
  session_id: string
  messages: AdminConversationMessagePayload[]
}

export interface AdminAuditEntryPayload {
  timestamp: string
  action: string
  details: Record<string, unknown>
}

export interface AdminAuditResponsePayload {
  entries: AdminAuditEntryPayload[]
}

export interface AdminStopListPayload {
  items: string[]
  updated_at: string
}

export interface AssistantOpeningPayload {
  opening?: string | null
  language: string
}

export interface AssistantAvatarPayload {
  accent: string
  base: string
  ring: string
  face: string
  image_url?: string | null
}

export interface AssistantProfilePayload {
  name: string
  avatar: AssistantAvatarPayload
}

export interface AdminAssistantOpeningEntryPayload {
  language: string
  template_id: string
  content?: string | null
  updated_at?: string | null
}

export interface AdminAssistantOpeningResponsePayload {
  entries: AdminAssistantOpeningEntryPayload[]
}

export interface AdminAssistantOpeningUpdateRequestPayload {
  language: string
  content: string
}

export interface AdminAssistantOpeningUpdateResponsePayload {
  entry: AdminAssistantOpeningEntryPayload
  updated_at?: string
}

export interface AdminAssistantProfileResponsePayload {
  profile: AssistantProfilePayload
  updated_at?: string | null
}

export interface AdminAssistantProfileUpdateRequestPayload {
  name?: string
  avatar?: Partial<AssistantAvatarPayload>
}

export interface AdminAssistantProfileUpdateResponsePayload {
  profile: AssistantProfilePayload
  updated_at?: string | null
}

export interface AdminTemplatePayload {
  template_id: string
  name: string
  description?: string | null
  language: string
  category?: string | null
  content: string
  created_at?: string
  updated_at?: string
}

export interface AdminTemplateUpsertRequestPayload {
  template_id: string
  name: string
  content: string
  description?: string | null
  language: string
  category?: string | null
}

export interface AdminTemplateUpsertResponsePayload {
  template: AdminTemplatePayload
}

export interface AdminTemplateDeleteResponsePayload {
  template_id: string
  deleted: boolean
  updated_at: string
}

export interface AdminPromptPayload {
  prompt_id: string
  name: string
  content: string
  description?: string | null
  language: string
  is_active: boolean
  created_at?: string
  updated_at?: string
}

export interface AdminPromptUpsertRequestPayload {
  prompt_id?: string | null
  name: string
  content: string
  description?: string | null
  language: string
  is_active?: boolean
}

export interface AdminPromptUpsertResponsePayload {
  prompt: AdminPromptPayload
}

export interface AdminPromptDeleteResponsePayload {
  prompt_id: string
  deleted: boolean
  updated_at: string
}

export interface AdminUpdateSlotsRequestPayload {
  slots: AdminSlotConfigPayload[]
}

export interface AdminUpdateSlotsResponsePayload {
  slots: AdminSlotConfigPayload[]
  updated_at?: string
}

export interface UploadResponsePayload {
  upload_id: string
  filename: string
  mime_type: string
  size_bytes: number
  sha256: string
  stored_at: string
  download_url?: string
  retention_days?: number | null
  expires_at?: string | null
}

export interface UploadPreviewPayload {
  upload_id: string
  filename: string
  mime_type: string
  size_bytes: number
  preview_url?: string | null
  download_url?: string | null
  text_excerpt?: string | null
  expires_at?: string | null
}

export interface AuthLoginRequestPayload {
  username: string
  password: string
}

export type AuthRole = 'user' | 'admin' | 'admin_readonly'

export const isAdminRole = (role?: AuthRole | null) => role === 'admin' || role === 'admin_readonly'

export interface AuthLoginResponsePayload {
  access_token: string
  token_type: string
  role: AuthRole
}

export interface AuthRegisterRequestPayload {
  username: string
  password: string
  reset_question: string
  reset_answer: string
}

export interface AuthRegisterResponsePayload {
  user_id: string
  username: string
  role: AuthRole
}

export interface AuthMeResponsePayload {
  sub: string
  role: AuthRole
  token_type: string
}

export interface AuthResetQuestionResponsePayload {
  username: string
  reset_question: string
}

export interface AuthChangePasswordRequestPayload {
  current_password: string
  new_password: string
}

export interface AuthResetPasswordRequestPayload {
  username: string
  reset_answer: string
  new_password: string
}

export interface AuthUpdateResetQuestionRequestPayload {
  reset_question: string
  reset_answer: string
}

export interface UserProfilePayload {
  display_name?: string | null
  contact_email?: string | null
  updated_at?: string | null
}

export interface UserProfileUpdatePayload {
  display_name?: string | null
  contact_email?: string | null
}

export const authLogin = async (username: string, password: string) => {
  const { data } = await apiClient.post<AuthLoginResponsePayload>(
    '/auth/login',
    { username, password } satisfies AuthLoginRequestPayload,
  )
  return data
}

export const authRegister = async (
  username: string,
  password: string,
  resetQuestion: string,
  resetAnswer: string,
) => {
  const { data } = await apiClient.post<AuthRegisterResponsePayload>(
    '/auth/register',
    {
      username,
      password,
      reset_question: resetQuestion,
      reset_answer: resetAnswer,
    } satisfies AuthRegisterRequestPayload,
  )
  return data
}

export const authMe = async () => {
  const { data } = await apiClient.get<AuthMeResponsePayload>('/auth/me')
  return data
}

export const authLogout = async () => {
  await apiClient.post('/auth/logout')
}

export const fetchResetQuestion = async (username: string) => {
  const { data } = await apiClient.get<AuthResetQuestionResponsePayload>('/auth/reset-question', {
    params: { username },
  })
  return data
}

export const resetPassword = async (payload: AuthResetPasswordRequestPayload) => {
  await apiClient.post('/auth/reset-password', payload)
}

export const changePassword = async (payload: AuthChangePasswordRequestPayload) => {
  await apiClient.post('/auth/password', payload)
}

export const updateResetQuestion = async (payload: AuthUpdateResetQuestionRequestPayload) => {
  await apiClient.post('/auth/reset-question', payload)
}

export const fetchUserProfile = async () => {
  const { data } = await apiClient.get<UserProfilePayload>('/profile')
  return data
}

export const updateUserProfile = async (payload: UserProfileUpdatePayload) => {
  const { data } = await apiClient.patch<UserProfilePayload>('/profile', payload)
  return data
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

export const createSession = async (payload?: SessionCreateRequestPayload) => {
  const { data } = await apiClient.post<SessionStatePayload>('/session', payload ?? {})
  return data
}

export const updateSessionMetadata = async (sessionId: string, payload: SessionMetadataUpdateRequestPayload) => {
  const { data } = await apiClient.patch<SessionStatePayload>(`/session/${sessionId}`, payload)
  return data
}

export const deleteSession = async (sessionId: string) => {
  await apiClient.delete(`/session/${sessionId}`)
}

export const updateSessionSlots = async (sessionId: string, payload: SessionSlotsUpdateRequestPayload) => {
  const { data } = await apiClient.patch<SessionStatePayload>(`/session/${sessionId}/slots`, payload)
  return data
}

export const fetchSessionMessages = async (sessionId: string) => {
  const { data } = await apiClient.get<SessionMessagesResponsePayload>(`/session/${sessionId}/messages`)
  return data.messages
}

export const fetchServiceStatus = async () => {
  const { data } = await apiClient.get<ServiceStatusResponsePayload>('/status')
  return data
}

export const fetchChunkDetail = async (chunkId: string) => {
  const { data } = await apiClient.get<ChunkDetailResponsePayload>(`/chunks/${encodeURIComponent(chunkId)}`)
  return data
}

export const createEscalation = async (payload: EscalationRequestPayload) => {
  const { data } = await apiClient.post<EscalationResponsePayload>('/escalations', payload)
  return data
}

export const fetchMetricsSnapshot = async () => {
  const { data } = await apiClient.get<MetricsSnapshotPayload>('/metrics')
  return data
}

export const fetchMetricsHistory = async (limit = 30) => {
  const { data } = await apiClient.get<MetricsHistoryResponsePayload>('/metrics/history', { params: { limit } })
  return data.entries
}

export const rebuildIndex = async () => {
  const { data } = await apiClient.post<IndexHealthPayload>('/index/rebuild')
  return data
}

export const fetchAdminConfig = async () => {
  const { data } = await apiClient.get<AdminConfigPayload>('/admin/config')
  return data
}

export const fetchAdminUsers = async (limit?: number) => {
  const { data } = await apiClient.get<AdminUserSummaryPayload[]>('/admin/users', {
    params: limit ? { limit } : undefined,
  })
  return data
}

export const fetchAdminConversations = async ({
  userId,
  limit,
}: {
  userId?: string | null
  limit?: number
}) => {
  const params: Record<string, string | number> = {}
  if (userId) params.user_id = userId
  if (limit) params.limit = limit
  const { data } = await apiClient.get<AdminSessionSummaryPayload[]>('/admin/conversations', {
    params: Object.keys(params).length ? params : undefined,
  })
  return data
}

export const fetchAdminConversationMessages = async (userId: string, sessionId: string) => {
  const { data } = await apiClient.get<AdminSessionMessagesResponsePayload>(
    `/admin/conversations/${encodeURIComponent(userId)}/${encodeURIComponent(sessionId)}/messages`,
  )
  return data
}

export const fetchAdminAudit = async (limit = 100) => {
  const { data } = await apiClient.get<AdminAuditResponsePayload>('/admin/audit', { params: { limit } })
  return data
}

export interface AdminJobEntryPayload {
  job_id: string
  job_type: string
  status: string
  started_at: string
  completed_at?: string | null
  duration_ms?: number | null
  metadata?: Record<string, unknown>
}

export interface AdminJobHistoryPayload {
  jobs: AdminJobEntryPayload[]
}

export const fetchAdminJobs = async (limit = 50) => {
  const { data } = await apiClient.get<AdminJobHistoryPayload>('/admin/jobs', { params: { limit } })
  return data
}

export interface AdminIngestUploadRequestPayload {
  upload_id: string
  source_name?: string | null
  doc_id?: string | null
  language?: string
  domain?: string | null
  freshness?: string | null
  url?: string | null
  tags?: string[]
  max_chars?: number
  overlap?: number
}

export interface IngestResponsePayload {
  doc_id: string
  version: number
  chunk_count: number
  health: IndexHealthPayload
}

export const ingestUpload = async (payload: AdminIngestUploadRequestPayload) => {
  const { data } = await apiClient.post<IngestResponsePayload>('/admin/ingest-upload', payload)
  return data
}

export const ingestUploadUser = async (payload: AdminIngestUploadRequestPayload) => {
  const { data } = await apiClient.post<IngestResponsePayload>('/ingest-upload', payload)
  return data
}

export const fetchAdminStopList = async () => {
  const { data } = await apiClient.get<AdminStopListPayload>('/admin/stop-list')
  return data
}

export const updateAdminStopList = async (items: string[]) => {
  const { data } = await apiClient.post<AdminStopListPayload>('/admin/stop-list', { items })
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

export interface AdminSourceVerifyResponsePayload {
  doc_id: string
  verified_at: string
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

export const verifyAdminSource = async (docId: string) => {
  const { data } = await apiClient.post<AdminSourceVerifyResponsePayload>(`/admin/sources/${encodeURIComponent(docId)}/verify`)
  return data
}

export const fetchAssistantOpening = async (language?: string) => {
  const { data } = await apiClient.get<AssistantOpeningPayload>('/assistant/opening', {
    params: language ? { lang: language } : undefined,
  })
  return data
}

export const fetchAssistantProfile = async () => {
  const { data } = await apiClient.get<AssistantProfilePayload>('/assistant/profile')
  return data
}

export const fetchAdminTemplates = async () => {
  const { data } = await apiClient.get<AdminTemplatePayload[]>('/admin/templates')
  return data
}

export const upsertAdminTemplate = async (payload: AdminTemplateUpsertRequestPayload) => {
  const { data } = await apiClient.post<AdminTemplateUpsertResponsePayload>('/admin/templates', payload)
  return data
}

export const deleteAdminTemplate = async (templateId: string) => {
  const { data } = await apiClient.delete<AdminTemplateDeleteResponsePayload>(
    `/admin/templates/${encodeURIComponent(templateId)}`,
  )
  return data
}

export const fetchAdminPrompts = async () => {
  const { data } = await apiClient.get<AdminPromptPayload[]>('/admin/prompts')
  return data
}

export const upsertAdminPrompt = async (payload: AdminPromptUpsertRequestPayload) => {
  const { data } = await apiClient.post<AdminPromptUpsertResponsePayload>('/admin/prompts', payload)
  return data
}

export const activateAdminPrompt = async (promptId: string) => {
  const { data } = await apiClient.post<AdminPromptUpsertResponsePayload>(`/admin/prompts/${encodeURIComponent(promptId)}/activate`)
  return data
}

export const deleteAdminPrompt = async (promptId: string) => {
  const { data } = await apiClient.delete<AdminPromptDeleteResponsePayload>(`/admin/prompts/${encodeURIComponent(promptId)}`)
  return data
}

export const updateAdminRetrieval = async (payload: Partial<AdminRetrievalSettingsPayload>) => {
  const { data } = await apiClient.post<AdminRetrievalSettingsPayload>('/admin/retrieval', payload)
  return data
}

export const updateAdminSlots = async (payload: AdminUpdateSlotsRequestPayload) => {
  const { data } = await apiClient.post<AdminUpdateSlotsResponsePayload>('/admin/slots', payload)
  return data
}

export const fetchAdminAssistantOpening = async () => {
  const { data } = await apiClient.get<AdminAssistantOpeningResponsePayload>('/admin/assistant/opening')
  return data
}

export const updateAdminAssistantOpening = async (payload: AdminAssistantOpeningUpdateRequestPayload) => {
  const { data } = await apiClient.post<AdminAssistantOpeningUpdateResponsePayload>('/admin/assistant/opening', payload)
  return data
}

export const fetchAdminAssistantProfile = async () => {
  const { data } = await apiClient.get<AdminAssistantProfileResponsePayload>('/admin/assistant/profile')
  return data
}

export const updateAdminAssistantProfile = async (payload: AdminAssistantProfileUpdateRequestPayload) => {
  const { data } = await apiClient.post<AdminAssistantProfileUpdateResponsePayload>('/admin/assistant/profile', payload)
  return data
}

export const uploadAdminAssistantAvatar = async (file: File) => {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await apiClient.post<AdminAssistantProfileUpdateResponsePayload>('/admin/assistant/avatar', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export const uploadAttachment = async (file: File, retentionDays?: number, purpose?: 'chat' | 'rag') => {
  const formData = new FormData()
  formData.append('file', file)
  const params: Record<string, number | string> = {}
  if (retentionDays) {
    params.retention_days = retentionDays
  }
  if (purpose) {
    params.purpose = purpose
  }
  const { data } = await apiClient.post<UploadResponsePayload>('/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    params: Object.keys(params).length > 0 ? params : undefined,
  })
  return data
}

export const fetchUploadPreview = async (uploadId: string) => {
  const { data } = await apiClient.get<UploadPreviewPayload>(`/upload/${encodeURIComponent(uploadId)}/preview`)
  return data
}
