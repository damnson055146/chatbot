export const SESSION_STORAGE_KEY = 'rag.session.id'
export const PINNED_STORAGE_KEY = 'rag.pinned.sessions'

export const conversationStorageKey = (sessionId: string) => `rag.conversation.${sessionId}`
