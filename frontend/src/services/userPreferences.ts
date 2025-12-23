export type SupportedLanguage = 'auto' | 'en' | 'zh'

export interface UserPreferences {
  displayName: string
  email?: string
  avatarColor: string
  preferredLanguage: SupportedLanguage
  explainLikeNewDefault: boolean
  defaultTopK: number
  defaultKCite: number
  retentionDays: 30 | 60 | 90
  theme: 'light' | 'high-contrast'
}

export interface ConversationExportMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  createdAt?: string
  citations?: unknown
  diagnostics?: unknown
  lowConfidence?: boolean
}

export interface ConversationExport {
  sessionId: string
  messages: ConversationExportMessage[]
}

export interface ConversationExportPayload {
  exportedAt: string
  sessions: ConversationExport[]
}

const USER_PREFS_STORAGE_KEY = 'rag.user.preferences'
const CONVERSATION_PREFIX = 'rag.conversation.'

export const DEFAULT_USER_PREFERENCES: UserPreferences = {
  displayName: 'Analyst',
  email: undefined,
  avatarColor: '#2563eb',
  preferredLanguage: 'auto',
  explainLikeNewDefault: false,
  defaultTopK: 8,
  defaultKCite: 2,
  retentionDays: 30,
  theme: 'light',
}

const clampInteger = (value: unknown, fallback: number, min: number, max: number) => {
  const parsed = typeof value === 'number' ? value : Number(value)
  if (Number.isNaN(parsed)) return fallback
  return Math.min(Math.max(Math.round(parsed), min), max)
}

export const loadUserPreferences = (): UserPreferences => {
  if (typeof window === 'undefined') {
    return { ...DEFAULT_USER_PREFERENCES }
  }
  try {
    const raw = window.localStorage.getItem(USER_PREFS_STORAGE_KEY)
    if (!raw) {
      return { ...DEFAULT_USER_PREFERENCES }
    }
    const parsed = JSON.parse(raw) as Partial<UserPreferences>
    return {
      displayName: parsed.displayName?.trim() || DEFAULT_USER_PREFERENCES.displayName,
      email: parsed.email,
      avatarColor: parsed.avatarColor || DEFAULT_USER_PREFERENCES.avatarColor,
      preferredLanguage: (parsed.preferredLanguage as SupportedLanguage) || DEFAULT_USER_PREFERENCES.preferredLanguage,
      explainLikeNewDefault: Boolean(parsed.explainLikeNewDefault),
      defaultTopK: clampInteger(parsed.defaultTopK, DEFAULT_USER_PREFERENCES.defaultTopK, 1, 20),
      defaultKCite: clampInteger(parsed.defaultKCite, DEFAULT_USER_PREFERENCES.defaultKCite, 1, 10),
      retentionDays: ([30, 60, 90] as const).includes(parsed.retentionDays as 30 | 60 | 90)
        ? (parsed.retentionDays as 30 | 60 | 90)
        : DEFAULT_USER_PREFERENCES.retentionDays,
      theme: parsed.theme === 'high-contrast' ? 'high-contrast' : DEFAULT_USER_PREFERENCES.theme,
    }
  } catch {
    return { ...DEFAULT_USER_PREFERENCES }
  }
}

export const saveUserPreferences = (preferences: UserPreferences): UserPreferences => {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(USER_PREFS_STORAGE_KEY, JSON.stringify(preferences))
  }
  return preferences
}

export const resetUserPreferences = (): UserPreferences => {
  const defaults = { ...DEFAULT_USER_PREFERENCES }
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(USER_PREFS_STORAGE_KEY, JSON.stringify(defaults))
  }
  return defaults
}

export const exportConversationHistory = (): ConversationExportPayload => {
  const sessions: ConversationExport[] = []
  if (typeof window !== 'undefined') {
    for (let index = 0; index < window.localStorage.length; index += 1) {
      const key = window.localStorage.key(index)
      if (!key || !key.startsWith(CONVERSATION_PREFIX)) {
        continue
      }
      const sessionId = key.slice(CONVERSATION_PREFIX.length)
      try {
        const raw = window.localStorage.getItem(key)
        if (!raw) continue
        const parsed = JSON.parse(raw) as ConversationExportMessage[]
        if (!Array.isArray(parsed)) continue
        sessions.push({ sessionId, messages: parsed })
      } catch {
        continue
      }
    }
  }
  return {
    exportedAt: new Date().toISOString(),
    sessions,
  }
}
