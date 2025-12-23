import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChatSidebar } from '../chat/ChatSidebar'
import { ChatMessageBubble } from '../chat/ChatMessageBubble'
import { TypingIndicator } from '../chat/TypingIndicator'
import { ChatComposer } from '../chat/ChatComposer'
import { UserSettingsDrawer } from './UserSettingsDrawer'
import { useUserPreferences } from '../../hooks/useUserPreferences'
import { useActiveSessions } from '../../hooks/useActiveSessions'
import { useSessionState } from '../../hooks/useSessionState'
import { useQueryClient } from '../../hooks/useQueryClient'
import type { ChatMessageModel } from '../chat/types'
import {
  clearStoredSessionId,
  deleteConversationIndexEntry,
  getStoredSessionId,
  loadConversationIndex,
  loadConversationMessages,
  saveConversationIndex,
  saveConversationMessages,
  setStoredSessionId,
  sortConversationEntries,
  type ConversationIndexEntry,
} from '../../state/chatStorage'
import {
  deleteSession,
  postQuery,
  streamQuery,
  uploadAttachment,
  type QueryResponsePayload,
  type SessionStatePayload,
} from '../../services/apiClient'
import type { UserPreferences } from '../../services/userPreferences'
import { ASSISTANT_PROFILE, getAssistantGreeting, getAssistantOpeningStatement } from '../../utils/assistantProfile'
import { AssistantOpening } from '../chat/AssistantOpening'
import type { MessageAttachment } from '../chat/types'

const QUICK_SUGGESTIONS = [
  'Explain the visa timeline for Australia.',
  'Draft a study plan for a UK postgraduate program.',
  'Compare scholarships for EU engineering degrees.',
  'Help me prepare documents for a US F-1 visa.',
]

const DEFAULT_TITLE = 'New conversation'

const randomId = () => {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return Math.random().toString(36).slice(2, 10)
}

const buildWelcomeMessage = (): ChatMessageModel => ({
  id: `welcome-${randomId()}`,
  role: 'assistant',
  content: `${getAssistantGreeting()}! I'm ${ASSISTANT_PROFILE.name}, your ${ASSISTANT_PROFILE.title}. ${getAssistantOpeningStatement()} Tell me what stage you're at and I'll map your next best step.`,
  createdAt: new Date().toISOString(),
})

const deriveConversationTitle = (currentTitle: string | undefined, fallbackQuestion: string) => {
  if (currentTitle && currentTitle !== DEFAULT_TITLE) {
    return currentTitle
  }
  const trimmed = fallbackQuestion.trim()
  if (!trimmed) return DEFAULT_TITLE
  return trimmed.length > 60 ? `${trimmed.slice(0, 57)}…` : trimmed
}

const deriveFallbackTitle = (sessionId: string) => `Session ${sessionId.slice(0, 8)}`

const mergeConversationsWithBackendSessions = (
  existing: ConversationIndexEntry[],
  sessions: SessionStatePayload[],
) => {
  const map = new Map<string, ConversationIndexEntry>()
  for (const entry of existing) {
    map.set(entry.sessionId, entry)
  }
  for (const session of sessions) {
    const sessionId = session.session_id
    const prior = map.get(sessionId)
    const slotCount = session.slot_count ?? Object.keys(session.slots ?? {}).length
    map.set(sessionId, {
      sessionId,
      title: prior?.title ?? deriveFallbackTitle(sessionId),
      pinned: prior?.pinned ?? false,
      archived: prior?.archived ?? false,
      slotCount,
      createdAt: session.created_at ?? prior?.createdAt ?? new Date().toISOString(),
      updatedAt: session.updated_at ?? prior?.updatedAt ?? new Date().toISOString(),
    })
  }
  return sortConversationEntries(Array.from(map.values()))
}

const SUPPORTED_UPLOAD_ACCEPT = 'application/pdf,image/png,image/jpeg,image/webp'
const STREAMING_MODE = (import.meta.env.VITE_STREAMING_MODE ?? 'off').toString().toLowerCase()

export function QueryConsolePage() {
  const navigate = useNavigate()
  const { preferences, updatePreferences, resetPreferences, hasCustomizations } = useUserPreferences()
  const queryClient = useQueryClient()
  const { data: backendSessions = [] } = useActiveSessions()
  const [conversations, setConversations] = useState<ConversationIndexEntry[]>([])
  const [activeSessionId, setActiveSessionId] = useState<string | undefined>(undefined)
  const [messages, setMessages] = useState<ChatMessageModel[]>([])
  const [inputValue, setInputValue] = useState('')
  const [searchTerm, setSearchTerm] = useState('')
  const [showArchived, setShowArchived] = useState(false)
  const [isSending, setIsSending] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)
  const [statusBanner, setStatusBanner] = useState<{ tone: 'info' | 'error'; message: string } | null>(null)
  const [isHydrating, setIsHydrating] = useState(true)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [slotPanel, setSlotPanel] = useState<{
    missingSlots: string[]
    slotPrompts: Record<string, string>
    slotErrors: Record<string, string>
    slotSuggestions: string[]
  } | null>(null)
  const [pendingAttachments, setPendingAttachments] = useState<MessageAttachment[]>([])

  const messagesEndRef = useRef<HTMLDivElement | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const activeAbortRef = useRef<AbortController | null>(null)

  const activeConversation = useMemo(
    () => conversations.find((conversation) => conversation.sessionId === activeSessionId),
    [conversations, activeSessionId],
  )

  const { data: sessionState } = useSessionState(activeSessionId)

  const hasUserMessage = messages.some((message) => message.role === 'user')
  const showAssistantOpening = !hasUserMessage
  const visibleMessages = showAssistantOpening
    ? messages.filter((message, index) => !(index === 0 && message.role === 'assistant'))
    : messages

  const persistConversationEntries = useCallback((updater: (entries: ConversationIndexEntry[]) => ConversationIndexEntry[]) => {
    setConversations((prev) => {
      const next = sortConversationEntries(updater(prev))
      saveConversationIndex(next)
      return next
    })
  }, [])

  const createConversation = useCallback(() => {
    const sessionId = randomId()
    const now = new Date().toISOString()
    const welcome = buildWelcomeMessage()
    saveConversationMessages(sessionId, [welcome])
    setConversations((prev) => {
      const nextEntries = sortConversationEntries([
        ...prev,
        {
          sessionId,
          title: DEFAULT_TITLE,
          pinned: false,
          archived: false,
          slotCount: 0,
          updatedAt: now,
          createdAt: now,
        },
      ])
      saveConversationIndex(nextEntries)
      return nextEntries
    })
    setActiveSessionId(sessionId)
    setStoredSessionId(sessionId)
    setMessages([welcome])
    return sessionId
  }, [])

  useEffect(() => {
    const index = sortConversationEntries(loadConversationIndex())
    const storedSessionId = getStoredSessionId()
    const fallbackSession = storedSessionId || index[0]?.sessionId

    const merged = mergeConversationsWithBackendSessions(index, backendSessions)
    setConversations(merged)
    saveConversationIndex(merged)

    if (fallbackSession) {
      setActiveSessionId(fallbackSession)
      setMessages(loadConversationMessages(fallbackSession))
    } else {
      createConversation()
    }
    setIsHydrating(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [createConversation])

  useEffect(() => {
    setConversations((prev) => {
      const merged = mergeConversationsWithBackendSessions(prev, backendSessions)
      saveConversationIndex(merged)
      return merged
    })
    if (!activeSessionId && backendSessions.length > 0) {
      const nextId = backendSessions[0]?.session_id
      if (nextId) {
        setActiveSessionId(nextId)
        setStoredSessionId(nextId)
        const maybeMessages = loadConversationMessages(nextId)
        setMessages(maybeMessages.length > 0 ? maybeMessages : [buildWelcomeMessage()])
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [backendSessions])

  useEffect(() => {
    if (!activeSessionId) return
    saveConversationMessages(activeSessionId, messages)
  }, [activeSessionId, messages])

  useEffect(() => {
    if (!sessionState || !activeSessionId) return
    const slotCount = Object.keys(sessionState.slots ?? {}).length
    persistConversationEntries((entries) =>
      entries.map((entry) =>
        entry.sessionId === activeSessionId
          ? { ...entry, slotCount, updatedAt: sessionState.updated_at ?? new Date().toISOString() }
          : entry,
      ),
    )
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
    if (!messagesEndRef.current || typeof messagesEndRef.current.scrollIntoView !== 'function') {
      return
    }
    messagesEndRef.current.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, isSending])

  const handleSelectConversation = (sessionId: string) => {
    setActiveSessionId(sessionId)
    setStoredSessionId(sessionId)
    const storedMessages = loadConversationMessages(sessionId)
    setMessages(storedMessages.length > 0 ? storedMessages : [buildWelcomeMessage()])
    setInputValue('')
    setMobileSidebarOpen(false)
    setStatusBanner(null)
    setSlotPanel(null)
    setPendingAttachments([])
  }

  const handleCreateConversation = () => {
    createConversation()
  }

  const handleRenameConversation = (sessionId: string, nextTitle: string) => {
    const trimmed = nextTitle.trim()
    if (!trimmed) return
    persistConversationEntries((entries) =>
      entries.map((entry) => (entry.sessionId === sessionId ? { ...entry, title: trimmed } : entry)),
    )
  }

  const handleTogglePin = (sessionId: string) => {
    persistConversationEntries((entries) =>
      entries.map((entry) => (entry.sessionId === sessionId ? { ...entry, pinned: !entry.pinned } : entry)),
    )
  }

  const handleToggleArchive = (sessionId: string) => {
    persistConversationEntries((entries) =>
      entries.map((entry) => (entry.sessionId === sessionId ? { ...entry, archived: !entry.archived } : entry)),
    )
  }

  const handleDeleteConversation = (sessionId: string) => {
    const target = conversations.find((entry) => entry.sessionId === sessionId)
    const shouldDelete =
      typeof window === 'undefined'
        ? true
        : window.confirm(
            `Delete "${target?.title || 'Untitled conversation'}"? This removes it from your browser history.`,
          )
    if (!shouldDelete) {
      return
    }
    deleteSession(sessionId).catch(() => undefined)
    deleteConversationIndexEntry(sessionId)
    queryClient.invalidateQueries({ queryKey: ['sessions'] }).catch(() => undefined)
    let updatedEntries: ConversationIndexEntry[] = []
    setConversations((prev) => {
      const filtered = prev.filter((entry) => entry.sessionId !== sessionId)
      updatedEntries = filtered
      return filtered
    })
    if (sessionId === activeSessionId) {
      if (updatedEntries.length > 0) {
        const nextSessionId = updatedEntries[0].sessionId
        setActiveSessionId(nextSessionId)
        setStoredSessionId(nextSessionId)
        setMessages(loadConversationMessages(nextSessionId))
      } else {
        clearStoredSessionId()
        createConversation()
      }
    }
    setStatusBanner({ tone: 'info', message: 'Conversation deleted.' })
  }

  const handleCopy = (content: string) => {
    if (navigator?.clipboard?.writeText) {
      navigator.clipboard
        .writeText(content)
        .catch(() => setStatusBanner({ tone: 'error', message: 'Unable to copy to clipboard.' }))
    }
  }

  const handleRetry = (message: ChatMessageModel) => {
    setInputValue(message.content)
  }

  const handleStopGenerating = () => {
    const controller = activeAbortRef.current
    if (!controller) return
    controller.abort()
    activeAbortRef.current = null
  }

  const handleUploadClick = () => {
    if (fileInputRef.current) {
      fileInputRef.current.click()
      return
    }
    setStatusBanner({ tone: 'error', message: 'Unable to open file picker.' })
  }

  const handleFileSelected = async (files: FileList | null) => {
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
        const uploaded = await uploadAttachment(file)
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
                  error: error instanceof Error ? error.message : 'Upload failed',
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
    if (!activeSessionId) {
      handleCreateConversation()
      return
    }
    const trimmed = inputValue.trim()
    if (!trimmed) return
    const now = new Date().toISOString()
    const userMessage: ChatMessageModel = {
      id: `user-${randomId()}`,
      role: 'user',
      content: trimmed,
      createdAt: now,
      attachments: pendingAttachments.length > 0 ? pendingAttachments : undefined,
    }
    setMessages((prev) => [...prev, userMessage])
    setInputValue('')
    setIsSending(true)
    setStatusBanner(null)
    const attachmentIds = pendingAttachments
      .filter((item) => item.status === 'ready' && item.uploadId)
      .map((item) => item.uploadId as string)
    setPendingAttachments([])

    try {
      const requestPayload = {
        question: trimmed,
        session_id: activeSessionId,
        language: preferences.preferredLanguage === 'auto' ? undefined : preferences.preferredLanguage,
        explain_like_new: preferences.explainLikeNewDefault,
        top_k: preferences.defaultTopK,
        k_cite: preferences.defaultKCite,
        attachments: attachmentIds,
      }

      if (STREAMING_MODE === 'server') {
        const assistantMessageId = `assistant-stream-${randomId()}`
        const placeholder: ChatMessageModel = {
          id: assistantMessageId,
          role: 'assistant',
          content: '',
          createdAt: new Date().toISOString(),
          citations: [],
          diagnostics: null,
          streaming: true,
        }
        setMessages((prev) => [...prev, placeholder])

        const controller = new AbortController()
        activeAbortRef.current = controller

        const finalize = (response: QueryResponsePayload, question: string) => {
          setMessages((prev) =>
            prev.map((message) =>
              message.id === assistantMessageId
                ? {
                    ...message,
                    content: response.answer || message.content || 'I was unable to craft a response with the provided information.',
                    citations: response.citations,
                    diagnostics: response.diagnostics,
                    lowConfidence: response.diagnostics?.low_confidence,
                    streaming: false,
                  }
                : message,
            ),
          )
          const slotCount = Object.keys(response.slots ?? {}).length
          const derivedTitle = deriveConversationTitle(activeConversation?.title, question)
          persistConversationEntries((entries) =>
            entries.map((entry) =>
              entry.sessionId === activeSessionId
                ? { ...entry, title: derivedTitle, slotCount, updatedAt: new Date().toISOString() }
                : entry,
            ),
          )
          setSlotPanel({
            missingSlots: response.missing_slots ?? [],
            slotPrompts: response.slot_prompts ?? {},
            slotErrors: response.slot_errors ?? {},
            slotSuggestions: response.slot_suggestions ?? [],
          })
          queryClient.invalidateQueries({ queryKey: ['sessions'] }).catch(() => undefined)
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
                finalize(payload, trimmed)
              },
              onError: (payload) => {
                setStatusBanner({
                  tone: 'error',
                  message: payload.message ? String(payload.message) : 'Streaming error',
                })
              },
            },
            controller.signal,
          )
          finalize(response, trimmed)
        } finally {
          activeAbortRef.current = null
        }
      } else {
        const response = await postQuery(requestPayload)
        appendAssistantMessage(response, trimmed)
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        setStatusBanner({ tone: 'info', message: 'Generation stopped.' })
        setMessages((prev) => {
          const last = [...prev].reverse().find((m) => m.role === 'assistant' && m.streaming)
          if (!last) return prev
          return prev.map((m) =>
            m.id === last.id ? { ...m, streaming: false, content: `${m.content}\n\n[Generation stopped]` } : m,
          )
        })
      } else {
      setStatusBanner({
        tone: 'error',
        message: error instanceof Error ? error.message : 'Unable to send message right now.',
      })
      const failure: ChatMessageModel = {
        id: `assistant-error-${randomId()}`,
        role: 'assistant',
        content: 'I ran into an issue while generating a response. Please try again in a moment.',
        createdAt: new Date().toISOString(),
        lowConfidence: true,
      }
      setMessages((prev) => [...prev, failure])
      }
    } finally {
      setIsSending(false)
    }
  }

  const appendAssistantMessage = (response: QueryResponsePayload, question: string) => {
    if (!activeSessionId) return
    const answerMessage: ChatMessageModel = {
      id: `assistant-${randomId()}`,
      role: 'assistant',
      content: response.answer || 'I was unable to craft a response with the provided information.',
      createdAt: new Date().toISOString(),
      citations: response.citations,
      diagnostics: response.diagnostics,
      lowConfidence: response.diagnostics?.low_confidence,
    }
    setMessages((prev) => [...prev, answerMessage])
    const slotCount = Object.keys(response.slots ?? {}).length
    const derivedTitle = deriveConversationTitle(activeConversation?.title, question)
    persistConversationEntries((entries) =>
      entries.map((entry) =>
        entry.sessionId === activeSessionId
          ? { ...entry, title: derivedTitle, slotCount, updatedAt: new Date().toISOString() }
          : entry,
      ),
    )
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

  const handleThemeUpdate = (next: UserPreferences) => {
    updatePreferences(next)
  }

  const hasUploadingAttachment = pendingAttachments.some((item) => item.status === 'uploading' || item.status === 'queued')
  const isSendDisabled = isSending || hasUploadingAttachment || inputValue.trim().length === 0
  const isUploadDisabled = isSending

  const handleWorkspaceNavigate = (label: string) => {
    const normalized = label.trim().toLowerCase()
    switch (normalized) {
      case 'chat':
        navigate('/')
        return
      case 'library':
        navigate('/library')
        return
      case 'explore':
        navigate('/explore')
        return
      default:
        setStatusBanner({ tone: 'info', message: `${label} workspace view is coming soon.` })
        return
    }
  }

  const handleSystemNavigate = (label: string) => {
    const normalized = label.trim().toLowerCase()
    switch (normalized) {
      case 'system status':
        navigate('/admin/status')
        return
      case 'metrics':
        navigate('/admin/metrics')
        return
      case 'sources':
        navigate('/admin/sources')
        return
      case 'audit log':
        navigate('/admin/audit')
        return
      case 'admin console':
        navigate('/admin/status')
        return
      case 'release notes':
        navigate('/release-notes')
        return
      default:
        setStatusBanner({ tone: 'info', message: `${label} panel will be available shortly.` })
        return
    }
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
      onRename={handleRenameConversation}
      onArchiveToggle={handleToggleArchive}
      showArchived={showArchived}
      onToggleArchivedVisibility={() => setShowArchived((prev) => !prev)}
      isLoading={isHydrating}
      onSettings={() => setSettingsOpen(true)}
      onWorkspaceNavigate={handleWorkspaceNavigate}
      onSystemNavigate={handleSystemNavigate}
      onDelete={handleDeleteConversation}
      onCollapseToggle={() => setSidebarCollapsed(true)}
    />
  )

  return (
    <div className="flex min-h-screen bg-[#F7F7F8] text-slate-900">
      {sidebarCollapsed ? (
        <aside className="hidden w-14 shrink-0 border-r border-slate-200 bg-white lg:flex">
          <button
            type="button"
            aria-label="Expand sidebar"
            className="mx-auto mt-4 flex h-8 w-8 items-center justify-center rounded-full border border-slate-200 text-xs text-slate-500 transition hover:border-slate-300"
            onClick={() => setSidebarCollapsed(false)}
          >
            ⟩
          </button>
          <div className="mt-auto flex flex-col items-center gap-6 pb-6 text-[10px] uppercase tracking-[0.4em] text-slate-400">
            <span className="-rotate-90 whitespace-nowrap">Assistant</span>
          </div>
        </aside>
      ) : (
        <aside className="hidden w-[240px] shrink-0 border-r border-slate-200 lg:flex">{sidebar}</aside>
      )}
      {mobileSidebarOpen ? (
        <div className="fixed inset-0 z-40 bg-slate-900/40 backdrop-blur-sm lg:hidden">
          <div className="absolute inset-y-0 left-0 w-64 bg-white shadow-2xl">{sidebar}</div>
          <button
            type="button"
            aria-label="Close sidebar"
            className="absolute inset-0"
            onClick={() => setMobileSidebarOpen(false)}
          />
        </div>
      ) : null}
      <section className="flex flex-1 flex-col">
        <header className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-200 bg-[#F7F7F8]/95 px-4 py-4 backdrop-blur">
          <div>
            <p className="text-[11px] uppercase tracking-[0.4em] text-slate-400">Study Abroad Assistant</p>
            <h1 className="text-xl font-semibold text-slate-900">
              {activeConversation?.title || DEFAULT_TITLE}
            </h1>
            {activeSessionId ? (
              <p className="mt-1 text-[11px] text-slate-400">
                Session: {activeSessionId.slice(0, 12)} · Slots:{' '}
                {sessionState?.slot_count ?? activeConversation?.slotCount ?? 0}
              </p>
            ) : null}
          </div>
          <div className="flex items-center gap-2">
            {sidebarCollapsed ? (
              <button
                type="button"
                className="hidden rounded-full border border-slate-300 px-3 py-1 text-xs font-semibold text-slate-600 hover:border-slate-400 lg:inline-flex"
                onClick={() => setSidebarCollapsed(false)}
              >
                Show sidebar
              </button>
            ) : null}
            <button
              type="button"
              className="rounded-full border border-slate-300 px-3 py-1 text-xs font-semibold text-slate-600 hover:border-slate-400"
              onClick={() => {
                if (!activeSessionId || !activeConversation) return
                const nextTitle = window.prompt('Rename conversation', activeConversation.title)
                if (nextTitle !== null) {
                  handleRenameConversation(activeSessionId, nextTitle)
                }
              }}
            >
              Rename
            </button>
            <button
              type="button"
              className="rounded-full border border-rose-200 px-3 py-1 text-xs font-semibold text-rose-500 hover:border-rose-400"
              onClick={() => {
                if (!activeSessionId) return
                handleDeleteConversation(activeSessionId)
              }}
            >
              Delete
            </button>
            <button
              type="button"
              className="rounded-full border border-slate-300 px-3 py-1 text-xs font-semibold text-slate-600 hover:border-slate-400 lg:hidden"
              onClick={() => setMobileSidebarOpen(true)}
              aria-label="Open navigation"
            >
              Menu
            </button>
          </div>
        </header>
        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 pb-40 pt-6 sm:px-6">
            {slotPanel && (slotPanel.missingSlots.length > 0 || Object.keys(slotPanel.slotErrors).length > 0) ? (
              <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.4em] text-slate-400">Slot guidance</p>
                    <p className="mt-2 text-sm text-slate-700">
                      Share the missing details to get a more precise, grounded answer.
                    </p>
                  </div>
                  <button
                    type="button"
                    className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600 hover:border-slate-300"
                    onClick={() => setSlotPanel(null)}
                  >
                    Dismiss
                  </button>
                </div>

                {slotPanel.missingSlots.length > 0 ? (
                  <div className="mt-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.35em] text-slate-400">Missing</p>
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
                              Use
                            </button>
                          </li>
                        )
                      })}
                    </ul>
                  </div>
                ) : null}

                {Object.keys(slotPanel.slotErrors).length > 0 ? (
                  <div className="mt-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.35em] text-slate-400">Validation</p>
                    <ul className="mt-3 space-y-2">
                      {Object.entries(slotPanel.slotErrors).map(([name, error]) => (
                        <li key={name} className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                          <span className="font-semibold">{name}</span>: {error}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {slotPanel.slotSuggestions.length > 0 ? (
                  <div className="mt-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.35em] text-slate-400">Suggestions</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {slotPanel.slotSuggestions.map((suggestion) => (
                        <button
                          type="button"
                          key={suggestion}
                          className="rounded-full border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 hover:border-slate-400"
                          onClick={() => setInputValue(suggestion)}
                        >
                          {suggestion}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}
            {showAssistantOpening ? (
              <AssistantOpening
                displayName={preferences.displayName}
                suggestions={QUICK_SUGGESTIONS}
                onSuggestionClick={handleSuggestionClick}
              />
            ) : null}
            {!visibleMessages.length && !showAssistantOpening ? (
              <div className="rounded-3xl border border-dashed border-slate-200 bg-white/70 p-6 text-sm text-slate-500">
                Start a conversation to see responses here.
              </div>
            ) : null}
            {visibleMessages.map((message) => (
              <ChatMessageBubble
                key={message.id}
                message={message}
                onCopy={handleCopy}
                onRetry={handleRetry}
                assistantName={ASSISTANT_PROFILE.name}
                userDisplayName={preferences.displayName}
                userAvatarColor={preferences.avatarColor}
              />
            ))}
            {isSending ? (
              <div className="flex items-center justify-between gap-3">
                <div className="flex justify-start">
                  <TypingIndicator />
                </div>
                {STREAMING_MODE === 'server' ? (
                  <button
                    type="button"
                    className="rounded-full border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 shadow-sm hover:border-slate-400"
                    onClick={handleStopGenerating}
                  >
                    Stop generating
                  </button>
                ) : null}
              </div>
            ) : null}
            <div ref={messagesEndRef} />
            {!showAssistantOpening ? (
              <div className="mt-4 flex flex-wrap gap-2">
                {QUICK_SUGGESTIONS.map((suggestion) => (
                  <button
                    type="button"
                    key={suggestion}
                    className="rounded-full border border-slate-200 px-4 py-2 text-sm text-slate-600 transition hover:border-slate-400"
                    onClick={() => handleSuggestionClick(suggestion)}
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            ) : null}
            {statusBanner ? (
              <p className={`text-sm ${statusBanner.tone === 'error' ? 'text-rose-600' : 'text-slate-500'}`}>
                {statusBanner.message}
              </p>
            ) : null}
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
                <p className="text-[11px] font-semibold uppercase tracking-[0.4em] text-slate-400">Pending attachments</p>
                <ul className="mt-3 space-y-2">
                  {pendingAttachments.map((attachment) => (
                    <li
                      key={attachment.clientId}
                      className="flex items-start justify-between gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-slate-800">{attachment.filename}</p>
                        <p className="mt-1 text-xs text-slate-500">
                          {Math.round(attachment.sizeBytes / 1024)} KB · {attachment.mimeType} · {attachment.status}
                          {attachment.error ? ` · ${attachment.error}` : ''}
                        </p>
                      </div>
                      <button
                        type="button"
                        className="shrink-0 rounded-full border border-slate-300 px-3 py-1 text-xs font-semibold text-slate-700 hover:border-slate-400"
                        onClick={() => removePendingAttachment(attachment.clientId)}
                      >
                        Remove
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
          uploadDisabled={isUploadDisabled}
          onUploadClick={handleUploadClick}
          containerClassName="mx-auto w-full max-w-3xl px-4 py-4 sm:px-6"
        />
      </section>
      <UserSettingsDrawer
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onSave={handleThemeUpdate}
        onReset={() => {
          resetPreferences()
        }}
        preferences={preferences}
        hasCustomizations={hasCustomizations}
      />
    </div>
  )
}

export default QueryConsolePage
