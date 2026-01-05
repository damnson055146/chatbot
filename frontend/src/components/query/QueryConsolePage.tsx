import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import axios from 'axios'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ChatSidebar } from '../chat/ChatSidebar'
import { ChatMessageBubble } from '../chat/ChatMessageBubble'
import { TypingIndicator } from '../chat/TypingIndicator'
import { ChatComposer } from '../chat/ChatComposer'
import { ContextRail, type ChunkDetailPayload, type AttachmentPreviewPayload } from '../chat/ContextRail'
import { UserSettingsDrawer } from './UserSettingsDrawer'
import { SlotEditorDrawer } from './SlotEditorDrawer'
import { LanguageSwitcher } from '../layout/LanguageSwitcher'
import { useUserPreferences } from '../../hooks/useUserPreferences'
import { useActiveSessions } from '../../hooks/useActiveSessions'
import { useSessionState } from '../../hooks/useSessionState'
import { useQueryClient } from '../../hooks/useQueryClient'
import type { ChatMessageModel, ConversationSummary } from '../chat/types'
import {
  createSession,
  deleteSession,
  authMe,
  authLogout,
  clearAccessToken,
  isAdminRole,
  fetchAssistantOpening,
  fetchAssistantProfile,
  fetchSessionMessages,
  fetchSlotCatalog,
  fetchUserProfile,
  getAccessToken,
  postQuery,
  streamQuery,
  uploadAttachment,
  updateUserProfile,
  updateSessionMetadata,
  updateSessionSlots,
  fetchChunkDetail,
  fetchUploadPreview,
  createEscalation,
  type AssistantProfilePayload,
  type AssistantOpeningPayload,
  type QueryResponsePayload,
  type SessionStatePayload,
  type SlotDefinitionPayload,
  type ConversationMessagePayload,
  type MessageAttachmentPayload,
} from '../../services/apiClient'
import { DEFAULT_USER_PREFERENCES, type UserPreferences } from '../../services/userPreferences'
import { getAssistantProfile, mergeAssistantProfile } from '../../utils/assistantProfile'
import { AssistantOpening } from '../chat/AssistantOpening'
import type { MessageAttachment } from '../chat/types'
import { useTranslation } from 'react-i18next'

const DEFAULT_TITLE_KEY = 'query.conversation.default_title'
type SessionDialogTarget = { sessionId: string; title?: string | null }

const randomId = () => {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return Math.random().toString(36).slice(2, 10)
}

const mapAttachment = (attachment: MessageAttachmentPayload): MessageAttachment => ({
  clientId: attachment.client_id,
  uploadId: attachment.upload_id ?? undefined,
  filename: attachment.filename,
  mimeType: attachment.mime_type,
  sizeBytes: attachment.size_bytes,
  downloadUrl: attachment.download_url ?? undefined,
  status: (attachment.status as MessageAttachment['status']) ?? 'ready',
  error: attachment.error ?? undefined,
})

const mapMessage = (message: ConversationMessagePayload): ChatMessageModel => ({
  id: message.id,
  role: message.role,
  content: message.content,
  createdAt: message.created_at,
  language: message.language ?? undefined,
  citations: message.citations ?? [],
  diagnostics: message.diagnostics ?? null,
  lowConfidence: message.low_confidence ?? undefined,
  attachments: message.attachments ? message.attachments.map(mapAttachment) : undefined,
})

const mapSession = (session: SessionStatePayload): ConversationSummary => ({
  sessionId: session.session_id,
  title: session.title ?? '',
  pinned: Boolean(session.pinned),
  archived: Boolean(session.archived),
  slotCount: session.slot_count ?? Object.keys(session.slots ?? {}).length,
  createdAt: session.created_at ?? new Date().toISOString(),
  updatedAt: session.updated_at ?? new Date().toISOString(),
})


const SUPPORTED_UPLOAD_ACCEPT = [
  'application/pdf',
  'text/plain',
  'text/markdown',
  'image/png',
  'image/jpeg',
  'image/webp',
  'audio/mpeg',
  'audio/mp4',
  'audio/wav',
  'audio/webm',
  'audio/ogg',
  'audio/aac',
  'audio/x-m4a',
  '.txt',
  '.md',
].join(',')
const STREAMING_MODE = (import.meta.env.VITE_STREAMING_MODE ?? 'off').toString().toLowerCase()
const getErrorMessage = (error: unknown, fallback: string) => {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string' && detail.trim()) {
      return detail
    }
  }
  return error instanceof Error && error.message ? error.message : fallback
}
const isNotFoundError = (error: unknown) => axios.isAxiosError(error) && error.response?.status === 404

export function QueryConsolePage() {
  const { t, i18n } = useTranslation()
  const assistantBase = useMemo(() => getAssistantProfile(t), [t])
  const defaultTitle = useMemo(() => String(t(DEFAULT_TITLE_KEY)), [t])
  const navigate = useNavigate()
  const { preferences, updatePreferences, resetPreferences, hasCustomizations } = useUserPreferences()
  const queryClient = useQueryClient()
  const accessToken = getAccessToken()
  const hasApiKey = Boolean(import.meta.env.VITE_API_KEY)
  const authQuery = useQuery({
    queryKey: ['authMe'],
    queryFn: authMe,
    enabled: Boolean(accessToken),
    retry: false,
    staleTime: 1000 * 60,
  })
  const canAdminWrite = authQuery.data?.role === 'admin'
  const canViewCitationSources = isAdminRole(authQuery.data?.role)
  const canViewAdminConsole = isAdminRole(authQuery.data?.role)
  const canUpload = Boolean(accessToken) || hasApiKey
  const canAdjustRetrieval = canAdminWrite
  const sessionScope = accessToken ? authQuery.data?.sub ?? 'pending' : hasApiKey ? 'api-key' : 'public'
  const sessionsEnabled = Boolean(accessToken) || hasApiKey
  const { data: backendSessions = [], isLoading: sessionsLoading } = useActiveSessions(sessionScope, sessionsEnabled)
  const isHydrating = sessionsLoading
  const conversations = useMemo(() => backendSessions.map(mapSession), [backendSessions])
  const [activeSessionId, setActiveSessionId] = useState<string | undefined>(undefined)
  const [messages, setMessages] = useState<ChatMessageModel[]>([])
  const [, setIsLoadingMessages] = useState(false)
  const [inputValue, setInputValue] = useState('')
  const [searchTerm, setSearchTerm] = useState('')
  const [showArchived, setShowArchived] = useState(false)
  const [isSending, setIsSending] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [slotEditorOpen, setSlotEditorOpen] = useState(false)
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)
  const [statusBanner, setStatusBanner] = useState<{ tone: 'info' | 'error'; message: string } | null>(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    if (typeof window === 'undefined') return false
    return !window.matchMedia('(min-width: 1280px)').matches
  })
  const [dragActive, setDragActive] = useState(false)
  const [slotPanel, setSlotPanel] = useState<{
    missingSlots: string[]
    slotPrompts: Record<string, string>
    slotErrors: Record<string, string>
    slotSuggestions: string[]
  } | null>(null)
  const [slotCoachHiddenKey, setSlotCoachHiddenKey] = useState<string | null>(null)
  const [pendingAttachments, setPendingAttachments] = useState<MessageAttachment[]>([])
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [messageControls, setMessageControls] = useState<{
    language: 'auto' | 'en' | 'zh'
    explainLikeNew: boolean
    topK: number
    kCite: number
    useRag: boolean
  }>(() => ({
    language: 'auto',
    explainLikeNew: false,
    topK: 8,
    kCite: 2,
    useRag: true,
  }))
  const [contextOpen, setContextOpen] = useState(false)
  const [contextTitle, setContextTitle] = useState<string | undefined>(undefined)
  const [contextChunk, setContextChunk] = useState<ChunkDetailPayload | null>(null)
  const [contextAttachment, setContextAttachment] = useState<AttachmentPreviewPayload | null>(null)
  const [contextCitationScore, setContextCitationScore] = useState<number | null>(null)
  const [contextLoading, setContextLoading] = useState(false)
  const [contextError, setContextError] = useState<string | null>(null)
  const [logoutConfirmOpen, setLogoutConfirmOpen] = useState(false)
  const [renameDialogOpen, setRenameDialogOpen] = useState(false)
  const [renameTarget, setRenameTarget] = useState<SessionDialogTarget | null>(null)
  const [renameDraft, setRenameDraft] = useState('')
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<SessionDialogTarget | null>(null)

  const messagesEndRef = useRef<HTMLDivElement | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const activeAbortRef = useRef<AbortController | null>(null)
  const suppressAutoLoadSessionIdRef = useRef<string | null>(null)
  const suppressAutoSelectRef = useRef(false)
  const createSessionRef = useRef<Promise<string | null> | null>(null)
  const dragCounterRef = useRef(0)
  const sessionScopeRef = useRef<string | null>(null)

  const activeConversation = useMemo(
    () => conversations.find((conversation) => conversation.sessionId === activeSessionId),
    [conversations, activeSessionId],
  )

  const sessionStateQuery = useSessionState(activeSessionId, sessionScope)
  const sessionState = sessionStateQuery.data
  const resolveConversationTitle = (title?: string | null) => {
    const trimmed = (title ?? '').trim()
    return trimmed || t('query.conversation.untitled')
  }

  const getSessionTitle = (sessionId: string) => {
    const entry = conversations.find((conversation) => conversation.sessionId === sessionId)
    if (entry?.title && entry.title.trim()) return entry.title
    if (sessionId === activeSessionId && sessionState?.title) return sessionState.title ?? ''
    return ''
  }

  const openRenameDialog = (sessionId: string, title?: string | null) => {
    const resolvedTitle = (title ?? '').trim() ? title : getSessionTitle(sessionId)
    setRenameTarget({ sessionId, title: resolvedTitle ?? '' })
    setRenameDraft(resolveConversationTitle(resolvedTitle))
    setRenameDialogOpen(true)
    setDeleteDialogOpen(false)
  }

  const openDeleteDialog = (sessionId: string, title?: string | null) => {
    const resolvedTitle = (title ?? '').trim() ? title : getSessionTitle(sessionId)
    setDeleteTarget({ sessionId, title: resolvedTitle ?? '' })
    setDeleteDialogOpen(true)
    setRenameDialogOpen(false)
  }

  const closeRenameDialog = () => {
    setRenameDialogOpen(false)
    setRenameTarget(null)
    setRenameDraft('')
  }

  const closeDeleteDialog = () => {
    setDeleteDialogOpen(false)
    setDeleteTarget(null)
  }
  const slotCatalogLanguage = useMemo(() => {
    const sessionLanguage = sessionState?.language
    if (sessionLanguage && sessionLanguage !== 'auto') return sessionLanguage
    const preferred = preferences.preferredLanguage
    if (preferred && preferred !== 'auto') return preferred
    return undefined
  }, [sessionState?.language, preferences.preferredLanguage])
  const slotCatalogQuery = useQuery<SlotDefinitionPayload[], Error>({
    queryKey: ['slot-catalog', slotCatalogLanguage ?? 'auto'],
    queryFn: () => fetchSlotCatalog(slotCatalogLanguage),
    staleTime: 1000 * 60,
  })
  const profileQuery = useQuery({
    queryKey: ['userProfile'],
    queryFn: fetchUserProfile,
    enabled: Boolean(accessToken),
    staleTime: 1000 * 60,
  })
  const openingLanguage = useMemo(() => {
    if (preferences.preferredLanguage && preferences.preferredLanguage !== 'auto') {
      return preferences.preferredLanguage
    }
    const raw = (i18n.language ?? '').toLowerCase()
    if (raw.startsWith('zh')) return 'zh'
    return 'en'
  }, [preferences.preferredLanguage, i18n.language])
  const openingQuery = useQuery<AssistantOpeningPayload, Error>({
    queryKey: ['assistant-opening', openingLanguage],
    queryFn: () => fetchAssistantOpening(openingLanguage),
    staleTime: 1000 * 60 * 10,
  })
  const assistantProfileQuery = useQuery<AssistantProfilePayload, Error>({
    queryKey: ['assistant-profile'],
    queryFn: fetchAssistantProfile,
    staleTime: 1000 * 60 * 10,
  })
  const assistant = useMemo(
    () => mergeAssistantProfile(assistantBase, assistantProfileQuery.data ?? null),
    [assistantBase, assistantProfileQuery.data],
  )
  const openingStatement = openingQuery.data?.opening?.trim() || undefined
  const slotDefinitions = slotCatalogQuery.data ?? []
  const slotPromptLookup = useMemo(() => {
    const lookup: Record<string, string> = {}
    for (const slot of slotDefinitions) {
      if (slot.prompt) {
        lookup[slot.name] = slot.prompt
      } else if (slot.description) {
        lookup[slot.name] = slot.description
      }
    }
    return lookup
  }, [slotDefinitions])
  const requiredSlotNames = useMemo(() => slotDefinitions.filter((slot) => slot.required).map((slot) => slot.name), [slotDefinitions])
  const slotOrder = useMemo(() => {
    const order: Record<string, number> = {}
    slotDefinitions.forEach((slot, index) => {
      order[slot.name] = index
    })
    return order
  }, [slotDefinitions])
  const orderedMissingSlots = useMemo(() => {
    if (!slotPanel?.missingSlots) return []
    return [...slotPanel.missingSlots].sort((a, b) => (slotOrder[a] ?? 999) - (slotOrder[b] ?? 999))
  }, [slotPanel?.missingSlots, slotOrder])
  const slotCoachKey = useMemo(() => orderedMissingSlots.join('|'), [orderedMissingSlots])
  const slotCoachSlot = orderedMissingSlots[0]
  const slotCoachPrompt = slotCoachSlot
    ? slotPanel?.slotPrompts?.[slotCoachSlot] ?? slotPromptLookup[slotCoachSlot] ?? slotCoachSlot
    : ''
  const slotCoachVisible = Boolean(slotCoachSlot) && slotCoachHiddenKey !== slotCoachKey

  const hasUserMessage = messages.some((message) => message.role === 'user')
  const showAssistantOpening = !hasUserMessage
  const visibleMessages = showAssistantOpening
    ? messages.filter((message, index) => !(index === 0 && message.role === 'assistant'))
    : messages
  const floatingSuggestions = useMemo(() => {
    const base = slotPanel?.slotSuggestions ?? []
    const seen = new Set<string>()
    return base.reduce<string[]>((acc, suggestion) => {
      if (acc.length >= 3) {
        return acc
      }
      const trimmed = suggestion.trim()
      if (!trimmed || seen.has(trimmed)) {
        return acc
      }
      seen.add(trimmed)
      acc.push(trimmed)
      return acc
    }, [])
  }, [slotPanel?.slotSuggestions])
  const showFloatingSuggestions = !showAssistantOpening && floatingSuggestions.length === 3

  const computeMissingSlots = useCallback(
    (slots: Record<string, unknown>) => {
      if (requiredSlotNames.length === 0) return []
      return requiredSlotNames.filter((name) => {
        const value = slots?.[name]
        if (value === null || value === undefined) return true
        if (typeof value === 'string') {
          return value.trim().length === 0
        }
        return false
      })
    },
    [requiredSlotNames],
  )

  const loadMessages = useCallback(
    async (sessionId: string) => {
      setIsLoadingMessages(true)
      try {
        const payload = await fetchSessionMessages(sessionId)
        setMessages(payload.map(mapMessage))
      } catch (error) {
        setMessages([])
        if (isNotFoundError(error)) {
          setActiveSessionId(undefined)
          setSlotPanel(null)
          setPendingAttachments([])
          setStatusBanner(null)
        } else {
          setStatusBanner({ tone: 'error', message: error instanceof Error ? error.message : t('query.errors.send_failed') })
        }
      } finally {
        setIsLoadingMessages(false)
      }
    },
    [t],
  )

  const createConversation = useCallback(async () => {
    if (createSessionRef.current) {
      return createSessionRef.current
    }
    const task = (async () => {
      try {
        const session = await createSession({})
        suppressAutoSelectRef.current = false
        suppressAutoLoadSessionIdRef.current = session.session_id
        setActiveSessionId(session.session_id)
        setMessages([])
        setSlotPanel(null)
        setPendingAttachments([])
        queryClient.invalidateQueries({ queryKey: ['sessions'] }).catch(() => undefined)
        return session.session_id
      } catch (error) {
        setStatusBanner({ tone: 'error', message: error instanceof Error ? error.message : t('query.errors.send_failed') })
        return null
      }
    })()
    createSessionRef.current = task
    try {
      return await task
    } finally {
      createSessionRef.current = null
    }
  }, [queryClient, t])

  useEffect(() => {
    if (!sessionScope || sessionScopeRef.current === sessionScope) return
    sessionScopeRef.current = sessionScope
    suppressAutoLoadSessionIdRef.current = null
    suppressAutoSelectRef.current = false
    setActiveSessionId(undefined)
    setMessages([])
    setSlotPanel(null)
    setPendingAttachments([])
    setStatusBanner(null)
    queryClient.removeQueries({ queryKey: ['sessions'] })
    queryClient.removeQueries({ queryKey: ['session'] })
  }, [queryClient, sessionScope])

  useEffect(() => {
    if (activeSessionId || sessionsLoading || suppressAutoSelectRef.current) return
    if (backendSessions.length > 0) {
      const nextId = backendSessions[0]?.session_id
      if (nextId) {
        setActiveSessionId(nextId)
      }
    }
  }, [activeSessionId, backendSessions, sessionsLoading])

  useEffect(() => {
    if (!activeSessionId) return
    if (suppressAutoLoadSessionIdRef.current) {
      if (suppressAutoLoadSessionIdRef.current === activeSessionId) {
        suppressAutoLoadSessionIdRef.current = null
        return
      }
      suppressAutoLoadSessionIdRef.current = null
    }
    void loadMessages(activeSessionId)
  }, [activeSessionId, loadMessages])

  useEffect(() => {
    if (!activeSessionId || !sessionStateQuery.error) return
    if (!isNotFoundError(sessionStateQuery.error)) return
    setActiveSessionId(undefined)
    setMessages([])
    setSlotPanel(null)
    setPendingAttachments([])
    setStatusBanner(null)
  }, [activeSessionId, sessionStateQuery.error])

  useEffect(() => {
    if (!sessionState || !activeSessionId) return
    if (Object.keys(sessionState.slot_errors ?? {}).length > 0) {
      setSlotPanel((prev) => ({
        missingSlots: prev?.missingSlots ?? [],
        slotPrompts: prev?.slotPrompts ?? {},
        slotErrors: sessionState.slot_errors ?? {},
        slotSuggestions: prev?.slotSuggestions ?? [],
      }))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionState, activeSessionId])

  useEffect(() => {
    if (!slotCoachKey) return
    if (slotCoachHiddenKey && slotCoachHiddenKey !== slotCoachKey) {
      setSlotCoachHiddenKey(null)
    }
  }, [slotCoachHiddenKey, slotCoachKey])

  useEffect(() => {
    if (!messagesEndRef.current || typeof messagesEndRef.current.scrollIntoView !== 'function') {
      return
    }
    messagesEndRef.current.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, isSending])

  useLayoutEffect(() => {
    if (typeof window === 'undefined' || typeof document === 'undefined') return
    const previousBodyOverflow = document.body.style.overflow
    const previousHtmlOverflow = document.documentElement.style.overflow
    const previousRestoration = window.history?.scrollRestoration
    if (window.history && 'scrollRestoration' in window.history) {
      window.history.scrollRestoration = 'manual'
    }
    document.body.style.overflow = 'hidden'
    document.documentElement.style.overflow = 'hidden'
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' })
    document.body.scrollTop = 0
    document.documentElement.scrollTop = 0
    const raf = window.requestAnimationFrame(() => {
      window.scrollTo({ top: 0, left: 0, behavior: 'auto' })
      document.body.scrollTop = 0
      document.documentElement.scrollTop = 0
    })
    return () => {
      window.cancelAnimationFrame(raf)
      document.body.style.overflow = previousBodyOverflow
      document.documentElement.style.overflow = previousHtmlOverflow
      if (window.history && 'scrollRestoration' in window.history && previousRestoration) {
        window.history.scrollRestoration = previousRestoration
      }
    }
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') return
    const media = window.matchMedia('(min-width: 1280px)')
    const syncSidebar = () => {
      if (!media.matches) {
        setSidebarCollapsed(true)
      }
    }
    syncSidebar()
    if (typeof media.addEventListener === 'function') {
      media.addEventListener('change', syncSidebar)
      return () => media.removeEventListener('change', syncSidebar)
    }
    media.addListener(syncSidebar)
    return () => media.removeListener(syncSidebar)
  }, [])

  useEffect(() => {
    if (!profileQuery.data) return
    const nextDisplayName = profileQuery.data.display_name?.trim() || DEFAULT_USER_PREFERENCES.displayName
    const nextEmail = profileQuery.data.contact_email?.trim() || undefined
    if (nextDisplayName === preferences.displayName && nextEmail === preferences.email) return
    updatePreferences({ displayName: nextDisplayName, email: nextEmail })
  }, [profileQuery.data, preferences.displayName, preferences.email, updatePreferences])

  useEffect(() => {
    setMessageControls((prev) => ({
      language: (preferences.preferredLanguage as 'auto' | 'en' | 'zh') ?? 'auto',
      explainLikeNew: preferences.explainLikeNewDefault,
      topK: preferences.defaultTopK,
      kCite: preferences.defaultKCite,
      useRag: prev.useRag ?? true,
    }))
  }, [preferences.preferredLanguage, preferences.explainLikeNewDefault, preferences.defaultTopK, preferences.defaultKCite])

  const handleSelectConversation = (sessionId: string) => {
    if (sessionId === activeSessionId) return
    suppressAutoSelectRef.current = false
    setActiveSessionId(sessionId)
    setMessages([])
    setInputValue('')
    setMobileSidebarOpen(false)
    setStatusBanner(null)
    setSlotPanel(null)
    setPendingAttachments([])
  }

  const handleCreateConversation = () => {
    suppressAutoSelectRef.current = true
    setActiveSessionId(undefined)
    setMessages([])
    setInputValue('')
    setMobileSidebarOpen(false)
    setStatusBanner(null)
    setSlotPanel(null)
    setPendingAttachments([])
  }

  const applySessionUpdate = (updated: SessionStatePayload) => {
    queryClient.setQueryData<SessionStatePayload[]>(['sessions'], (prev) => {
      if (!prev) return prev
      let matched = false
      const next = prev.map((session) => {
        if (session.session_id !== updated.session_id) return session
        matched = true
        return { ...session, ...updated }
      })
      return matched ? next : [updated, ...next]
    })
    queryClient.setQueryData(['session', updated.session_id], updated)
  }

  const applyOptimisticSessionPatch = (sessionId: string, patch: Partial<SessionStatePayload>) => {
    const base = backendSessions.find((session) => session.session_id === sessionId)
    if (!base) return null
    const optimistic: SessionStatePayload = {
      ...base,
      ...patch,
      updated_at: new Date().toISOString(),
    }
    applySessionUpdate(optimistic)
    return base
  }

  const handleRenameConversation = (sessionId: string, nextTitle: string) => {
    const trimmed = nextTitle.trim()
    if (!trimmed) return
    const previous = applyOptimisticSessionPatch(sessionId, { title: trimmed })
    updateSessionMetadata(sessionId, { title: trimmed })
      .then((updated) => {
        applySessionUpdate(updated)
        return queryClient.invalidateQueries({ queryKey: ['sessions'] })
      })
      .catch((error) => {
        if (previous) applySessionUpdate(previous)
        setStatusBanner({ tone: 'error', message: getErrorMessage(error, t('query.errors.send_failed')) })
      })
  }

  const handleTogglePin = (sessionId: string) => {
    const target = conversations.find((entry) => entry.sessionId === sessionId)
    if (!target) return
    const previous = applyOptimisticSessionPatch(sessionId, { pinned: !target.pinned })
    updateSessionMetadata(sessionId, { pinned: !target.pinned })
      .then((updated) => {
        applySessionUpdate(updated)
        return queryClient.invalidateQueries({ queryKey: ['sessions'] })
      })
      .catch((error) => {
        if (previous) applySessionUpdate(previous)
        setStatusBanner({ tone: 'error', message: getErrorMessage(error, t('query.errors.send_failed')) })
      })
  }

  const handleToggleArchive = (sessionId: string) => {
    const target = conversations.find((entry) => entry.sessionId === sessionId)
    if (!target) return
    const previous = applyOptimisticSessionPatch(sessionId, { archived: !target.archived })
    updateSessionMetadata(sessionId, { archived: !target.archived })
      .then((updated) => {
        applySessionUpdate(updated)
        return queryClient.invalidateQueries({ queryKey: ['sessions'] })
      })
      .catch((error) => {
        if (previous) applySessionUpdate(previous)
        setStatusBanner({ tone: 'error', message: getErrorMessage(error, t('query.errors.send_failed')) })
      })
  }

  const handleDeleteConversation = async (sessionId: string) => {
    try {
      await deleteSession(sessionId)
      await queryClient.invalidateQueries({ queryKey: ['sessions'] })
    } catch (error) {
      setStatusBanner({ tone: 'error', message: getErrorMessage(error, t('query.errors.send_failed')) })
      return false
    }

    const remaining = conversations.filter((entry) => entry.sessionId !== sessionId)
    if (sessionId === activeSessionId) {
      if (remaining.length > 0) {
        suppressAutoSelectRef.current = false
        setActiveSessionId(remaining[0].sessionId)
      } else {
        suppressAutoSelectRef.current = true
        setActiveSessionId(undefined)
        setMessages([])
        setInputValue('')
        setSlotPanel(null)
        setPendingAttachments([])
      }
    }
    setStatusBanner({ tone: 'info', message: t('query.conversation.deleted') })
    return true
  }

  const handleCopy = (content: string) => {
    if (navigator?.clipboard?.writeText) {
      navigator.clipboard
        .writeText(content)
        .catch(() => setStatusBanner({ tone: 'error', message: t('query.errors.copy_failed') }))
    }
  }

  const handleCitationClick = async (
    citation: NonNullable<ChatMessageModel['citations']>[number],
    message: ChatMessageModel,
  ) => {
    void message
    setContextOpen(true)
    setContextLoading(true)
    setContextError(null)
    setContextChunk(null)
    setContextAttachment(null)
    setContextCitationScore(typeof citation.score === 'number' ? citation.score : null)
    setContextTitle(citation.source_name ?? citation.doc_id)
    try {
      const response = await fetchChunkDetail(citation.chunk_id)
      setContextChunk({
        chunk_id: response.chunk.chunk_id,
        doc_id: response.chunk.doc_id,
        text: response.chunk.text,
        last_verified_at: response.chunk.last_verified_at,
        highlights: response.chunk.highlights,
        metadata: response.chunk.metadata,
      })
    } catch (error) {
      setContextError(error instanceof Error ? error.message : t('chat.loading_passage'))
    } finally {
      setContextLoading(false)
    }
  }

  const handleAttachmentPreview = async (attachment: MessageAttachment) => {
    if (!attachment.uploadId) return
    setContextOpen(true)
    setContextLoading(true)
    setContextError(null)
    setContextChunk(null)
    setContextAttachment(null)
    setContextCitationScore(null)
    setContextTitle(attachment.filename)
    try {
      const preview = await fetchUploadPreview(attachment.uploadId)
      setContextAttachment({
        upload_id: preview.upload_id,
        filename: preview.filename,
        mime_type: preview.mime_type,
        size_bytes: preview.size_bytes,
        preview_url: preview.preview_url,
        download_url: preview.download_url,
        text_excerpt: preview.text_excerpt,
        expires_at: preview.expires_at,
      })
    } catch (error) {
      setContextError(error instanceof Error ? error.message : t('chat.attachment.preview_unavailable'))
    } finally {
      setContextLoading(false)
    }
  }

  const handleRetry = (message: ChatMessageModel) => {
    setInputValue(message.content)
  }

  const handleEscalate = async (message: ChatMessageModel) => {
    if (!activeSessionId) {
      setStatusBanner({ tone: 'error', message: t('chat.review_request_failed') })
      return
    }
    const reason = message.diagnostics?.review_reason ?? (message.lowConfidence ? 'low_confidence' : 'user_request')
    try {
      await createEscalation({
        session_id: activeSessionId,
        message_id: message.id,
        reason,
      })
      setStatusBanner({ tone: 'info', message: t('chat.review_requested') })
    } catch (error) {
      setStatusBanner({ tone: 'error', message: error instanceof Error ? error.message : t('chat.review_request_failed') })
    }
  }

  const handleStopGenerating = () => {
    const controller = activeAbortRef.current
    if (!controller) return
    controller.abort()
    activeAbortRef.current = null
    setIsStreaming(false)
  }

  const handleUploadClick = () => {
    if (!canUpload) return
    if (fileInputRef.current) {
      fileInputRef.current.click()
      return
    }
    setStatusBanner({ tone: 'error', message: t('query.errors.file_picker_failed') })
  }

  const isFileDrag = (event: React.DragEvent) => {
    const types = event.dataTransfer?.types
    return types ? Array.from(types).includes('Files') : false
  }

  const handleDragEnter = (event: React.DragEvent) => {
    if (!canUpload || !isFileDrag(event)) return
    event.preventDefault()
    dragCounterRef.current += 1
    setDragActive(true)
  }

  const handleDragOver = (event: React.DragEvent) => {
    if (!canUpload || !isFileDrag(event)) return
    event.preventDefault()
    event.dataTransfer.dropEffect = 'copy'
  }

  const handleDragLeave = (event: React.DragEvent) => {
    if (!canUpload || !isFileDrag(event)) return
    event.preventDefault()
    dragCounterRef.current = Math.max(0, dragCounterRef.current - 1)
    if (dragCounterRef.current === 0) {
      setDragActive(false)
    }
  }

  const handleDrop = (event: React.DragEvent) => {
    if (!canUpload || !isFileDrag(event)) return
    event.preventDefault()
    dragCounterRef.current = 0
    setDragActive(false)
    const files = event.dataTransfer.files
    if (files && files.length > 0) {
      void handleFileSelected(files)
    }
  }

  const handleFileSelected = async (files: FileList | null) => {
    if (!canUpload) return
    if (!files || files.length === 0) return
    const list = Array.from(files)
    setStatusBanner(null)

    for (const file of list) {
      const clientId = `att-${randomId()}`
      const base: MessageAttachment = {
        clientId,
        filename: file.name,
        mimeType: file.type || 'application/octet-stream',
        sizeBytes: file.size,
        status: 'uploading',
      }
      setPendingAttachments((prev) => [...prev, base])

      try {
        const uploaded = await uploadAttachment(file, preferences.retentionDays, 'chat')
        setPendingAttachments((prev) =>
          prev.map((item) =>
            item.clientId === clientId
              ? {
                  ...item,
                  uploadId: uploaded.upload_id,
                  downloadUrl: uploaded.download_url,
                  status: 'ready',
                }
              : item,
          ),
        )
      } catch (error) {
        setPendingAttachments((prev) =>
          prev.map((item) =>
            item.clientId === clientId
              ? {
                  ...item,
                  status: 'error',
                  error: getErrorMessage(error, t('query.errors.upload_failed')),
                }
              : item,
          ),
        )
      }
    }
  }

  const removePendingAttachment = (clientId: string) => {
    setPendingAttachments((prev) => prev.filter((item) => item.clientId !== clientId))
  }

  const handleSend = async () => {
    const trimmed = inputValue.trim()
    if (!trimmed) return
    let sessionId = activeSessionId
    if (!sessionId) {
      sessionId = await createConversation()
      if (!sessionId) return
    }
    const now = new Date().toISOString()
    const userMessage: ChatMessageModel = {
      id: `user-${randomId()}`,
      role: 'user',
      content: trimmed,
      createdAt: now,
      language: preferences.preferredLanguage,
      attachments: canUpload && pendingAttachments.length > 0 ? pendingAttachments : undefined,
    }
    setMessages((prev) => [...prev, userMessage])
    setInputValue('')
    setIsSending(true)
    setIsStreaming(false)
    setStatusBanner(null)
    const attachmentIds = canUpload
      ? pendingAttachments
          .filter((item) => item.status === 'ready' && item.uploadId)
          .map((item) => item.uploadId as string)
      : []
    setPendingAttachments([])

    try {
      const profileSlots: Record<string, unknown> = {}
      const displayName = preferences.displayName.trim()
      if (displayName && displayName !== DEFAULT_USER_PREFERENCES.displayName) {
        profileSlots.student_name = displayName
      }
      const email = preferences.email?.trim()
      if (email) {
        profileSlots.contact_email = email
      }
      const requestPayload = {
        question: trimmed,
        session_id: sessionId,
        language: messageControls.language === 'auto' ? undefined : messageControls.language,
        explain_like_new: messageControls.explainLikeNew,
        use_rag: messageControls.useRag,
        ...(canAdjustRetrieval ? { top_k: messageControls.topK, k_cite: messageControls.kCite } : {}),
        ...(canUpload ? { attachments: attachmentIds } : {}),
        slots: Object.keys(profileSlots).length > 0 ? profileSlots : undefined,
      }

      if (STREAMING_MODE === 'server') {
        setIsStreaming(true)
        const assistantMessageId = `assistant-stream-${randomId()}`
        const placeholder: ChatMessageModel = {
          id: assistantMessageId,
          role: 'assistant',
          content: '',
          createdAt: new Date().toISOString(),
          language: requestPayload.language ?? preferences.preferredLanguage,
          citations: [],
          diagnostics: null,
          streaming: true,
        }
        setMessages((prev) => [...prev, placeholder])

        const controller = new AbortController()
        activeAbortRef.current = controller

        const finalize = (response: QueryResponsePayload) => {
          setMessages((prev) =>
            prev.map((message) =>
              message.id === assistantMessageId
                ? {
                    ...message,
                    content: response.answer || message.content || t('query.assistant.no_answer'),
                    citations: response.citations,
                    diagnostics: response.diagnostics,
                    lowConfidence: response.diagnostics?.low_confidence,
                    streaming: false,
                  }
                : message,
            ),
          )
          setSlotPanel({
            missingSlots: response.missing_slots ?? [],
            slotPrompts: response.slot_prompts ?? {},
            slotErrors: response.slot_errors ?? {},
            slotSuggestions: response.slot_suggestions ?? [],
          })
          queryClient.invalidateQueries({ queryKey: ['sessions'] }).catch(() => undefined)
          setIsStreaming(false)
        }

        try {
          const response = await streamQuery(
            requestPayload,
            {
              onChunk: (payload) => {
                const delta = payload.delta ?? ''
                if (!delta) return
                setMessages((prev) =>
                  prev.map((message) =>
                    message.id === assistantMessageId ? { ...message, content: message.content + delta } : message,
                  ),
                )
              },
              onCitations: (payload) => {
                setMessages((prev) =>
                  prev.map((message) =>
                    message.id === assistantMessageId
                      ? {
                          ...message,
                          citations: Array.isArray(payload.citations) ? (payload.citations as any) : message.citations,
                          diagnostics: payload.diagnostics ? (payload.diagnostics as any) : message.diagnostics,
                        }
                      : message,
                  ),
                )
                setSlotPanel({
                  missingSlots: (payload.missing_slots as string[]) ?? [],
                  slotPrompts: (payload.slot_prompts as Record<string, string>) ?? {},
                  slotErrors: (payload.slot_errors as Record<string, string>) ?? {},
                  slotSuggestions: (payload.slot_suggestions as string[]) ?? [],
                })
              },
              onCompleted: (payload) => {
                finalize(payload)
              },
              onError: (payload) => {
                setStatusBanner({
                  tone: 'error',
                  message: payload.message ? String(payload.message) : t('query.streaming_error'),
                })
              },
            },
            controller.signal,
          )
          finalize(response)
        } finally {
          activeAbortRef.current = null
          setIsStreaming(false)
        }
      } else {
        setIsStreaming(false)
        const response = await postQuery(requestPayload)
        appendAssistantMessage(response)
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        setIsStreaming(false)
        const stopNotice = t('chat.generation_stopped')
        setStatusBanner({ tone: 'info', message: stopNotice })
        setMessages((prev) => {
          const last = [...prev].reverse().find((m) => m.role === 'assistant' && m.streaming)
          if (!last) return prev
          return prev.map((m) =>
            m.id === last.id
              ? { ...m, streaming: false, content: `${m.content}\n\n[${stopNotice}]` }
              : m,
          )
        })
      } else {
      setStatusBanner({
        tone: 'error',
        message: error instanceof Error ? error.message : t('query.errors.send_failed'),
      })
      const failure: ChatMessageModel = {
        id: `assistant-error-${randomId()}`,
        role: 'assistant',
        content: t('query.assistant.error_reply'),
        createdAt: new Date().toISOString(),
        lowConfidence: true,
      }
      setMessages((prev) => [...prev, failure])
      }
    } finally {
      setIsSending(false)
      setIsStreaming(false)
    }
  }

  const appendAssistantMessage = (response: QueryResponsePayload) => {
    const answerMessage: ChatMessageModel = {
      id: `assistant-${randomId()}`,
      role: 'assistant',
      content: response.answer || t('query.assistant.no_answer'),
      createdAt: new Date().toISOString(),
      language: preferences.preferredLanguage,
      citations: response.citations,
      diagnostics: response.diagnostics,
      lowConfidence: response.diagnostics?.low_confidence,
    }
    setMessages((prev) => [...prev, answerMessage])
    setSlotPanel({
      missingSlots: response.missing_slots ?? [],
      slotPrompts: response.slot_prompts ?? {},
      slotErrors: response.slot_errors ?? {},
      slotSuggestions: response.slot_suggestions ?? [],
    })
    queryClient.invalidateQueries({ queryKey: ['sessions'] }).catch(() => undefined)
  }

  const handleSuggestionClick = (suggestion: string) => {
    setInputValue(suggestion)
  }

  const handleThemeUpdate = async (next: UserPreferences) => {
    updatePreferences(next)
    try {
      await updateUserProfile({
        display_name: next.displayName?.trim() || null,
        contact_email: next.email?.trim() || null,
      })
    } catch (error) {
      setStatusBanner({
        tone: 'error',
        message: error instanceof Error ? error.message : t('settings.save_failed'),
      })
    }
  }

  const handlePreferencesReset = async () => {
    resetPreferences()
    try {
      await updateUserProfile({ display_name: null, contact_email: null })
    } catch (error) {
      setStatusBanner({
        tone: 'error',
        message: error instanceof Error ? error.message : t('settings.save_failed'),
      })
    }
  }

  const handleHeaderLogout = async () => {
    setStatusBanner(null)
    setLogoutConfirmOpen(false)
    try {
      if (accessToken) {
        await authLogout()
      }
    } catch (error) {
      setStatusBanner({
        tone: 'error',
        message: error instanceof Error ? error.message : t('settings.sign_out_failed'),
      })
      return
    } finally {
      clearAccessToken()
      queryClient.invalidateQueries({ queryKey: ['authMe'] }).catch(() => undefined)
    }
    navigate('/login')
  }

  const handleSlotSave = async (payload: { slots: Record<string, unknown>; reset_slots: string[] }) => {
    if (!activeSessionId) return
    setStatusBanner(null)
    try {
      const updated = await updateSessionSlots(activeSessionId, payload)
      queryClient.setQueryData(['session', activeSessionId], updated)
      const nextMissing = computeMissingSlots(updated.slots ?? {})
      const nextErrors = updated.slot_errors ?? {}
      if (nextMissing.length === 0 && Object.keys(nextErrors).length === 0) {
        setSlotPanel(null)
      } else {
        setSlotPanel((prev) => ({
          missingSlots: nextMissing,
          slotPrompts: Object.keys(slotPromptLookup).length > 0 ? slotPromptLookup : prev?.slotPrompts ?? {},
          slotErrors: nextErrors,
          slotSuggestions: prev?.slotSuggestions ?? [],
        }))
      }
      queryClient.invalidateQueries({ queryKey: ['sessions'] }).catch(() => undefined)
      setStatusBanner({ tone: 'info', message: t('query.slots_updated') })
    } catch (error) {
      setStatusBanner({
        tone: 'error',
        message: error instanceof Error ? error.message : t('query.slots_update_failed'),
      })
      throw error
    }
  }

  const hasUploadingAttachment = pendingAttachments.some((item) => item.status === 'uploading' || item.status === 'queued')
  const isSendDisabled = isSending || hasUploadingAttachment || inputValue.trim().length === 0
  const isUploadDisabled = isSending || !canUpload
  const renameDisabled = renameDraft.trim().length === 0
  const deleteTitle = resolveConversationTitle(deleteTarget?.title)

  const handleWorkspaceNavigate = (key: string) => {
    switch (key) {
      case 'nav.chat':
        setMobileSidebarOpen(false)
        setStatusBanner(null)
        navigate('/')
        return
      default:
        setStatusBanner({ tone: 'info', message: t('query.workspace_coming_soon', { label: t(key) }) })
        return
    }
  }

  const handleSystemNavigate = (key: string) => {
    switch (key) {
      case 'nav.admin_console':
        if (!canViewAdminConsole) {
          return
        }
        setMobileSidebarOpen(false)
        setStatusBanner(null)
        navigate('/admin/config')
        return
      default:
        setStatusBanner({ tone: 'info', message: t('query.panel_coming_soon', { label: t(key) }) })
        return
    }
  }

  const handleExpandSidebar = () => {
    if (typeof window !== 'undefined') {
      const isDesktop = window.matchMedia('(min-width: 1280px)').matches
      if (!isDesktop) {
        setMobileSidebarOpen(true)
        return
      }
    }
    setSidebarCollapsed(false)
  }

  const handleCollapseSidebar = () => {
    setSidebarCollapsed(true)
    setMobileSidebarOpen(false)
  }

  const sidebar = (
    <ChatSidebar
      conversations={conversations}
      activeSessionId={activeSessionId}
      searchTerm={searchTerm}
      onSearchChange={setSearchTerm}
      onSelect={handleSelectConversation}
      onCreateNew={handleCreateConversation}
      onTogglePin={handleTogglePin}
      onRenameRequest={(conversation) => openRenameDialog(conversation.sessionId, conversation.title)}
      onArchiveToggle={handleToggleArchive}
      showArchived={showArchived}
      onToggleArchivedVisibility={() => setShowArchived((prev) => !prev)}
      isLoading={isHydrating}
      onSettings={() => setSettingsOpen(true)}
      onWorkspaceNavigate={handleWorkspaceNavigate}
      onSystemNavigate={handleSystemNavigate}
      onDelete={(sessionId) => openDeleteDialog(sessionId)}
      onCollapseToggle={handleCollapseSidebar}
      showAdminConsole={canViewAdminConsole}
    />
  )

  return (
    <div className="flex h-[var(--app-height)] overflow-hidden">
      {sidebarCollapsed ? (
        <aside className="flex w-14 shrink-0 border-r border-slate-200 bg-white xl:flex">
          <button
            type="button"
            aria-label={t('query.sidebar.expand_aria')}
            className="mx-auto mt-4 flex h-8 w-8 items-center justify-center rounded-full border border-slate-200 text-xs text-slate-500 transition hover:border-slate-300"
            onClick={handleExpandSidebar}
          >
            ⟩
          </button>
          <div className="mt-auto flex flex-col items-center gap-6 pb-6 text-[10px] uppercase tracking-[0.4em] text-slate-400">
            <span className="-rotate-90 whitespace-nowrap">{assistant.name}</span>
          </div>
        </aside>
      ) : (
        <aside className="hidden w-[240px] shrink-0 border-r border-slate-200 xl:flex">{sidebar}</aside>
      )}
      {mobileSidebarOpen ? (
        <div className="fixed inset-0 z-40 bg-slate-900/40 backdrop-blur-sm xl:hidden">
          <button
            type="button"
            aria-label={t('query.sidebar.close_aria')}
            className="absolute inset-0 z-10"
            onClick={() => setMobileSidebarOpen(false)}
          />
          <div
            className="absolute inset-y-0 left-0 z-20 w-64 bg-white shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            {sidebar}
          </div>
        </div>
      ) : null}
      <section
        className="relative flex min-h-0 min-w-0 flex-1 flex-col xl:flex-row"
        onDragEnter={handleDragEnter}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {dragActive ? (
          <div className="pointer-events-none absolute inset-0 z-30 flex items-center justify-center bg-slate-900/10">
            <div className="rounded-3xl border border-slate-200 bg-white/90 px-6 py-4 text-sm font-semibold text-slate-700 shadow-sm">
              {t('chat.drop_files')}
            </div>
          </div>
        ) : null}
        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <header className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-200 bg-[#F7F7F8]/95 px-4 py-4 backdrop-blur">
          <div className="min-w-0">
            <p className="text-[11px] uppercase tracking-[0.4em] text-slate-400">{t('app.title')}</p>
            <h1 className="truncate text-xl font-semibold text-slate-900">
              {activeConversation?.title || defaultTitle}
            </h1>
            {activeSessionId ? (
              <p className="mt-1 truncate text-[11px] text-slate-400">
                {t('query.header.session')}: {activeSessionId.slice(0, 12)} · {t('query.header.slots')}:{' '}
                {sessionState?.slot_count ?? activeConversation?.slotCount ?? 0}
              </p>
            ) : null}
          </div>
          <div className="flex items-center gap-2">
            {sidebarCollapsed ? (
              <button
                type="button"
                className="hidden rounded-full border border-slate-300 px-3 py-1 text-xs font-semibold text-slate-600 hover:border-slate-400 lg:inline-flex"
                onClick={handleExpandSidebar}
              >
                {t('query.sidebar.show')}
              </button>
            ) : null}
            {activeSessionId ? (
              <button
                type="button"
                className="rounded-full border border-slate-300 px-3 py-1 text-xs font-semibold text-slate-600 hover:border-slate-400"
                onClick={() => setSlotEditorOpen(true)}
              >
                {t('query.slots_edit')}
              </button>
            ) : null}
            <button
              type="button"
              className="rounded-full border border-slate-300 px-3 py-1 text-xs font-semibold text-slate-600 hover:border-slate-400"
              onClick={() => {
                if (!activeSessionId) return
                openRenameDialog(activeSessionId, activeConversation?.title ?? sessionState?.title)
              }}
            >
              {t('sidebar.action.rename')}
            </button>
            <button
              type="button"
              className="rounded-full border border-rose-200 px-3 py-1 text-xs font-semibold text-rose-500 hover:border-rose-400"
              onClick={() => {
                if (!activeSessionId) return
                openDeleteDialog(activeSessionId, activeConversation?.title ?? sessionState?.title)
              }}
            >
              {t('common.delete')}
            </button>
            <button
              type="button"
              className="rounded-full border border-slate-300 px-3 py-1 text-xs font-semibold text-slate-600 hover:border-slate-400 xl:hidden"
              onClick={() => setMobileSidebarOpen(true)}
              aria-label={t('query.sidebar.open_aria')}
            >
              {t('query.menu')}
            </button>
            <button
              type="button"
              className="rounded-full border border-slate-300 px-3 py-1 text-xs font-semibold text-slate-600 hover:border-slate-400"
              onClick={() => setAdvancedOpen((prev) => !prev)}
              aria-expanded={advancedOpen}
              aria-controls="composer-advanced-controls"
            >
              {t('query.controls')}
            </button>
            {accessToken ? (
              <button
                type="button"
                className="rounded-full border border-rose-200 px-3 py-1 text-xs font-semibold text-rose-600 hover:border-rose-300"
                onClick={() => setLogoutConfirmOpen(true)}
              >
                {t('settings.sign_out')}
              </button>
            ) : null}
            <LanguageSwitcher />
          </div>
        </header>
        <div className="flex-1 overflow-y-auto overscroll-contain">
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 pb-40 pt-6 sm:px-6">
            {slotPanel && (slotPanel.missingSlots.length > 0 || Object.keys(slotPanel.slotErrors).length > 0) ? (
              <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.4em] text-slate-400">{t('query.slot_guidance_title')}</p>
                    <p className="mt-2 text-sm text-slate-700">
                      {t('query.slot_guidance_help')}
                    </p>
                  </div>
                  <button
                    type="button"
                    className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600 hover:border-slate-300"
                    onClick={() => setSlotPanel(null)}
                  >
                    {t('query.dismiss')}
                  </button>
                </div>

                {slotCoachVisible ? (
                  <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-xs font-semibold uppercase tracking-[0.35em] text-slate-400">{t('query.slot_coach_title')}</p>
                        <div className="mt-2 flex items-center gap-2 text-xs text-slate-600">
                          <span className="rounded-full bg-white px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-slate-700">
                            {slotCoachSlot}
                          </span>
                          {slotCoachSlot && requiredSlotNames.includes(slotCoachSlot) ? (
                            <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-amber-700">
                              {t('query.slot_coach_required')}
                            </span>
                          ) : null}
                        </div>
                        <p className="mt-2 text-sm text-slate-700">{slotCoachPrompt}</p>
                        <p className="mt-1 text-xs text-slate-500">
                          {t('query.slot_coach_step', { step: 1, total: orderedMissingSlots.length })}
                        </p>
                      </div>
                      <div className="flex shrink-0 flex-wrap gap-2">
                        <button
                          type="button"
                          className="rounded-full border border-slate-300 bg-white px-3 py-1 text-xs font-semibold text-slate-700 hover:border-slate-400"
                          onClick={() => setInputValue(slotCoachPrompt)}
                        >
                          {t('query.slot_coach_use')}
                        </button>
                        <button
                          type="button"
                          className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600 hover:border-slate-300"
                          onClick={() => setSlotCoachHiddenKey(slotCoachKey)}
                        >
                          {t('query.slot_coach_skip')}
                        </button>
                      </div>
                    </div>
                  </div>
                ) : null}

                {slotPanel.missingSlots.length > 0 ? (
                  <div className="mt-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.35em] text-slate-400">{t('query.missing')}</p>
                    <ul className="mt-3 space-y-2">
                      {slotPanel.missingSlots.map((name) => {
                        const prompt = slotPanel.slotPrompts?.[name] ?? name
                        return (
                          <li key={name} className="flex items-start justify-between gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
                            <div className="min-w-0">
                              <p className="text-xs font-semibold text-slate-700">{name}</p>
                              <p className="mt-1 text-sm text-slate-600">{prompt}</p>
                            </div>
                            <button
                              type="button"
                              className="shrink-0 rounded-full border border-slate-300 px-3 py-1 text-xs font-semibold text-slate-700 hover:border-slate-400"
                              onClick={() => setInputValue(prompt)}
                            >
                              {t('common.use')}
                            </button>
                          </li>
                        )
                      })}
                    </ul>
                  </div>
                ) : null}

                {Object.keys(slotPanel.slotErrors).length > 0 ? (
                  <div className="mt-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.35em] text-slate-400">{t('query.validation_heading')}</p>
                    <ul className="mt-3 space-y-2">
                      {Object.entries(slotPanel.slotErrors).map(([name, error]) => (
                        <li key={name} className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                          <span className="font-semibold">{name}</span>: {error}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}

              </div>
            ) : null}
            {showAssistantOpening ? (
              <AssistantOpening
                assistant={assistant}
                displayName={preferences.displayName}
                suggestions={[]}
                onSuggestionClick={handleSuggestionClick}
                openingStatement={openingStatement}
              />
            ) : null}
            {!visibleMessages.length && !showAssistantOpening ? (
              <div className="rounded-3xl border border-dashed border-slate-200 bg-white/70 p-6 text-sm text-slate-500">
                {t('query.conversation.start_prompt')}
              </div>
            ) : null}
            {visibleMessages.map((message) => (
              <ChatMessageBubble
                key={message.id}
                message={message}
                onCopy={handleCopy}
                onRetry={handleRetry}
                onCitationClick={handleCitationClick}
                onAttachmentPreview={handleAttachmentPreview}
                onEscalate={handleEscalate}
                showCitationSources={canViewCitationSources}
                assistantName={assistant.name}
                assistantAvatar={assistant.avatar}
                userDisplayName={preferences.displayName}
                userAvatarColor={preferences.avatarColor}
              />
            ))}
            {isSending ? (
              <div className="flex items-center justify-between gap-3">
                <div className="flex justify-start">
                  <TypingIndicator />
                </div>
              </div>
            ) : null}
            {statusBanner ? (
              <p
                role="status"
                aria-live="polite"
                className={`text-sm ${statusBanner.tone === 'error' ? 'text-rose-600' : 'text-slate-500'}`}
              >
                {statusBanner.message}
              </p>
            ) : null}
            {showFloatingSuggestions ? (
              <div className="sticky bottom-4 z-10">
                <div className="rounded-[28px] border border-slate-200 bg-white/90 px-3 py-3 shadow-sm backdrop-blur">
                  <div className="grid gap-2 sm:grid-cols-3">
                    {floatingSuggestions.map((suggestion) => (
                      <button
                        type="button"
                        key={suggestion}
                        className="w-full rounded-full border border-slate-200 bg-white px-4 py-2 text-sm text-slate-600 transition hover:border-slate-400"
                        onClick={() => handleSuggestionClick(suggestion)}
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            ) : null}
            <div ref={messagesEndRef} />
          </div>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          accept={SUPPORTED_UPLOAD_ACCEPT}
          multiple
          onChange={(event) => {
            void handleFileSelected(event.target.files)
            event.target.value = ''
          }}
        />
        {pendingAttachments.length > 0 ? (
          <div className="border-t border-slate-200 bg-[#F7F7F8]">
            <div className="mx-auto w-full max-w-3xl px-4 py-3 sm:px-6">
              <div className="rounded-3xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.4em] text-slate-400">{t('query.pending_attachments')}</p>
                <ul className="mt-3 space-y-2">
                  {pendingAttachments.map((attachment) => (
                    <li
                      key={attachment.clientId}
                      className="flex items-start justify-between gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-slate-800">{attachment.filename}</p>
                        <p className="mt-1 text-xs text-slate-500">
                          {Math.round(attachment.sizeBytes / 1024)} KB · {attachment.mimeType} · {t(`query.attachments.status.${attachment.status}`)}
                          {attachment.error ? ` · ${attachment.error}` : ''}
                        </p>
                      </div>
                      <button
                        type="button"
                        className="shrink-0 rounded-full border border-slate-300 px-3 py-1 text-xs font-semibold text-slate-700 hover:border-slate-400"
                        onClick={() => removePendingAttachment(attachment.clientId)}
                      >
                        {t('common.remove')}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        ) : null}
        <ChatComposer
          value={inputValue}
          onChange={setInputValue}
          onSubmit={handleSend}
          disabled={isSendDisabled}
          isStreaming={isStreaming}
          uploadDisabled={isUploadDisabled}
          onUploadClick={handleUploadClick}
          onStop={handleStopGenerating}
          containerClassName="mx-auto w-full max-w-3xl px-4 py-4 sm:px-6"
        />
        {advancedOpen ? (
          <div id="composer-advanced-controls" className="border-t border-slate-200 bg-white">
            <div className="mx-auto w-full max-w-3xl px-4 py-4 sm:px-6">
              <div className="rounded-3xl border border-slate-200 bg-slate-50 px-4 py-4">
                <p className="text-[11px] font-semibold uppercase tracking-[0.4em] text-slate-400">{t('query.controls_help')}</p>
                <div className="mt-4 grid gap-4 sm:grid-cols-2">
                  <label className="text-sm text-slate-600">
                    <span className="text-xs uppercase tracking-wide text-slate-500">{t('query.language')}</span>
                    <select
                      value={messageControls.language}
                      onChange={(event) =>
                        setMessageControls((prev) => ({
                          ...prev,
                          language: event.target.value as 'auto' | 'en' | 'zh',
                        }))
                      }
                      className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus-visible:ring focus-visible:ring-slate-300"
                    >
                      <option value="auto">{t('settings.language.auto')}</option>
                      <option value="en">{t('settings.language.en')}</option>
                      <option value="zh">{t('settings.language.zh')}</option>
                    </select>
                  </label>
                  <label className="text-sm text-slate-600">
                    <span className="text-xs uppercase tracking-wide text-slate-500">{t('query.explain_like_new')}</span>
                    <div className="mt-2 flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={messageControls.explainLikeNew}
                        onChange={(event) => setMessageControls((prev) => ({ ...prev, explainLikeNew: event.target.checked }))}
                      />
                      <span className="text-sm text-slate-700">{t('common.active')}</span>
                    </div>
                  </label>
                  <label className="text-sm text-slate-600">
                    <span className="text-xs uppercase tracking-wide text-slate-500">{t('query.use_rag')}</span>
                    <div className="mt-2 flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={messageControls.useRag}
                        onChange={(event) => setMessageControls((prev) => ({ ...prev, useRag: event.target.checked }))}
                      />
                      <span className="text-sm text-slate-700">{messageControls.useRag ? t('common.active') : t('common.off')}</span>
                    </div>
                  </label>
                  {canAdjustRetrieval && messageControls.useRag ? (
                    <label className="text-sm text-slate-600">
                      <span className="text-xs uppercase tracking-wide text-slate-500">{t('query.top_k')}</span>
                      <input
                        type="number"
                        min={1}
                        max={20}
                        value={messageControls.topK}
                        onChange={(event) =>
                          setMessageControls((prev) => ({ ...prev, topK: Number(event.target.value) || prev.topK }))
                        }
                        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus-visible:ring focus-visible:ring-slate-300"
                      />
                    </label>
                  ) : null}
                  {canAdjustRetrieval && messageControls.useRag ? (
                    <label className="text-sm text-slate-600">
                      <span className="text-xs uppercase tracking-wide text-slate-500">{t('query.k_cite')}</span>
                      <input
                        type="number"
                        min={1}
                        max={10}
                        value={messageControls.kCite}
                        onChange={(event) =>
                          setMessageControls((prev) => ({ ...prev, kCite: Number(event.target.value) || prev.kCite }))
                        }
                        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus-visible:ring focus-visible:ring-slate-300"
                      />
                    </label>
                  ) : null}
                </div>
                <p className="mt-3 text-xs text-slate-500">{t('query.shortcuts')}</p>
              </div>
            </div>
          </div>
        ) : null}
        </div>
        <ContextRail
          isOpen={contextOpen}
          title={contextTitle}
          isLoading={contextLoading}
          error={contextError}
          chunk={contextChunk}
          attachment={contextAttachment}
          citationScore={contextCitationScore}
          onClose={() => {
            setContextOpen(false)
            setContextChunk(null)
            setContextAttachment(null)
            setContextCitationScore(null)
            setContextTitle(undefined)
            setContextError(null)
          }}
        />
      </section>
      <UserSettingsDrawer
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onSave={handleThemeUpdate}
        onReset={handlePreferencesReset}
        preferences={preferences}
        hasCustomizations={hasCustomizations}
      />
      <SlotEditorDrawer
        isOpen={slotEditorOpen}
        onClose={() => setSlotEditorOpen(false)}
        onSave={handleSlotSave}
        sessionId={activeSessionId}
        slotDefinitions={slotDefinitions}
        slots={sessionState?.slots ?? {}}
        slotErrors={sessionState?.slot_errors ?? {}}
      />
      <div
        className={`fixed inset-0 z-50 flex items-center justify-center px-4 transition ${
          renameDialogOpen ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0'
        }`}
      >
        <button
          type="button"
          className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm"
          onClick={closeRenameDialog}
          aria-label={t('common.close')}
        />
        <div className="relative w-full max-w-sm rounded-3xl border border-slate-200 bg-white p-6 shadow-xl">
          <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-500">{t('sidebar.action.rename')}</p>
          <h3 className="mt-3 text-lg font-semibold text-slate-900">{t('query.conversation.rename_prompt')}</h3>
          <form
            className="mt-4 space-y-4"
            onSubmit={(event) => {
              event.preventDefault()
              if (!renameTarget || renameDisabled) return
              handleRenameConversation(renameTarget.sessionId, renameDraft)
              closeRenameDialog()
            }}
          >
            <label className="block text-sm text-slate-600">
              <span className="text-xs uppercase tracking-wide text-slate-500">{t('sidebar.action.rename')}</span>
              <input
                type="text"
                value={renameDraft}
                onChange={(event) => setRenameDraft(event.target.value)}
                className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-700 focus:outline-none focus-visible:ring focus-visible:ring-slate-300"
              />
            </label>
            <div className="flex items-center justify-end gap-3">
              <button
                type="button"
                className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-600 hover:border-slate-300"
                onClick={closeRenameDialog}
              >
                {t('common.cancel')}
              </button>
              <button
                type="submit"
                disabled={renameDisabled}
                className="rounded-full bg-slate-900 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
              >
                {t('common.save')}
              </button>
            </div>
          </form>
        </div>
      </div>
      <div
        className={`fixed inset-0 z-50 flex items-center justify-center px-4 transition ${
          deleteDialogOpen ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0'
        }`}
      >
        <button
          type="button"
          className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm"
          onClick={closeDeleteDialog}
          aria-label={t('common.close')}
        />
        <div className="relative w-full max-w-sm rounded-3xl border border-slate-200 bg-white p-6 shadow-xl">
          <p className="text-xs font-semibold uppercase tracking-[0.3em] text-rose-500">{t('common.delete')}</p>
          <h3 className="mt-3 text-lg font-semibold text-slate-900">
            {t('query.conversation.delete_confirm', { title: deleteTitle })}
          </h3>
          <div className="mt-6 flex items-center justify-end gap-3">
            <button
              type="button"
              className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-600 hover:border-slate-300"
              onClick={closeDeleteDialog}
            >
              {t('common.cancel')}
            </button>
            <button
              type="button"
              disabled={!deleteTarget}
              className="rounded-full bg-rose-500 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-rose-600 disabled:cursor-not-allowed disabled:bg-rose-300"
              onClick={() => {
                if (!deleteTarget) return
                void (async () => {
                  const success = await handleDeleteConversation(deleteTarget.sessionId)
                  if (success) {
                    closeDeleteDialog()
                  }
                })()
              }}
            >
              {t('common.delete')}
            </button>
          </div>
        </div>
      </div>
      <div
        className={`fixed inset-0 z-50 flex items-center justify-center px-4 transition ${
          logoutConfirmOpen ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0'
        }`}
      >
        <button
          type="button"
          className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm"
          onClick={() => setLogoutConfirmOpen(false)}
          aria-label={t('common.close')}
        />
        <div className="relative w-full max-w-sm rounded-3xl border border-slate-200 bg-white p-6 shadow-xl">
          <p className="text-xs font-semibold uppercase tracking-[0.3em] text-rose-500">{t('settings.sign_out')}</p>
          <h3 className="mt-3 text-lg font-semibold text-slate-900">{t('settings.sign_out_confirm')}</h3>
          <div className="mt-6 flex items-center justify-end gap-3">
            <button
              type="button"
              className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-600 hover:border-slate-300"
              onClick={() => setLogoutConfirmOpen(false)}
            >
              {t('common.cancel')}
            </button>
            <button
              type="button"
              className="rounded-full bg-rose-500 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-rose-600"
              onClick={() => void handleHeaderLogout()}
            >
              {t('settings.sign_out')}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default QueryConsolePage
