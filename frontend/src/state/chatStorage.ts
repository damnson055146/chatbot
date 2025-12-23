import type { ChatMessageModel, ConversationSummary } from '../components/chat/types'
import { conversationStorageKey, SESSION_STORAGE_KEY } from './storageKeys'

const CONVERSATION_INDEX_KEY = 'rag.conversation.index'

const safeParse = <T>(value: string | null, fallback: T): T => {
  if (!value) return fallback
  try {
    return JSON.parse(value) as T
  } catch {
    return fallback
  }
}

const readStorage = (key: string): string | null => {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

const writeStorage = (key: string, value: string) => {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // no-op
  }
}

export interface ConversationIndexEntry extends ConversationSummary {
  createdAt: string
}

export const sortConversationEntries = (entries: ConversationIndexEntry[]) => {
  return [...entries].sort((a, b) => {
    if (a.pinned !== b.pinned) {
      return a.pinned ? -1 : 1
    }
    const left = b.updatedAt ?? b.createdAt ?? ''
    const right = a.updatedAt ?? a.createdAt ?? ''
    return left.localeCompare(right)
  })
}

export const loadConversationIndex = (): ConversationIndexEntry[] => {
  const raw = readStorage(CONVERSATION_INDEX_KEY)
  return safeParse<ConversationIndexEntry[]>(raw, [])
}

export const saveConversationIndex = (entries: ConversationIndexEntry[]) => {
  writeStorage(CONVERSATION_INDEX_KEY, JSON.stringify(entries))
}

export const upsertConversationIndex = (
  entry: Omit<ConversationIndexEntry, 'createdAt'> & { createdAt?: string },
) => {
  const createdAt = entry.createdAt ?? new Date().toISOString()
  const index = loadConversationIndex()
  const existingIndex = index.findIndex((item) => item.sessionId === entry.sessionId)
  const normalized: ConversationIndexEntry = {
    ...entry,
    pinned: entry.pinned ?? false,
    archived: entry.archived ?? false,
    slotCount: entry.slotCount ?? 0,
    updatedAt: entry.updatedAt ?? new Date().toISOString(),
    createdAt,
  }

  if (existingIndex >= 0) {
    index[existingIndex] = { ...index[existingIndex], ...normalized }
  } else {
    index.push({ ...normalized })
  }

  const sorted = sortConversationEntries(index)
  saveConversationIndex(sorted)
  return sorted
}

export const deleteConversationIndexEntry = (sessionId: string) => {
  const index = loadConversationIndex().filter((entry) => entry.sessionId !== sessionId)
  saveConversationIndex(index)
  if (typeof window !== 'undefined') {
    try {
      window.localStorage.removeItem(conversationStorageKey(sessionId))
    } catch {
      // ignore
    }
  }
}

export const loadConversationMessages = (sessionId: string): ChatMessageModel[] => {
  const raw = readStorage(conversationStorageKey(sessionId))
  return safeParse<ChatMessageModel[]>(raw, [])
}

export const saveConversationMessages = (sessionId: string, messages: ChatMessageModel[]) => {
  writeStorage(conversationStorageKey(sessionId), JSON.stringify(messages))
}

export const getStoredSessionId = () => readStorage(SESSION_STORAGE_KEY)

export const setStoredSessionId = (sessionId: string) => {
  writeStorage(SESSION_STORAGE_KEY, sessionId)
}

export const clearStoredSessionId = () => {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.removeItem(SESSION_STORAGE_KEY)
  } catch {
    // ignore
  }
}
