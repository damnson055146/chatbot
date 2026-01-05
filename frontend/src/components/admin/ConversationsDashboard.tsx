/* NOTE: Conversations review feature is disabled. Remove this block comment to restore it.
import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  fetchAdminConversations,
  fetchAdminConversationMessages,
  fetchAdminUsers,
  type AdminConversationMessagePayload,
  type AdminSessionSummaryPayload,
  type AdminUserSummaryPayload,
} from '../../services/apiClient'

const formatTimestamp = (value?: string | null) => {
  if (!value) return '--'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString()
}

const matchesSearch = (value: string | null | undefined, query: string) =>
  Boolean(value && value.toLowerCase().includes(query))

const ratingLabel = (rating: number, t: (key: string) => string) => {
  if (rating > 0) return t('admin.conversations.feedback.rating.up')
  if (rating < 0) return t('admin.conversations.feedback.rating.down')
  return t('admin.conversations.feedback.rating.neutral')
}

const formatScore = (score: number | null | undefined) =>
  typeof score === 'number' && Number.isFinite(score) ? score.toFixed(2) : '--'

export function ConversationsDashboard() {
  const { t } = useTranslation()
  const [userSearch, setUserSearch] = useState('')
  const [sessionSearch, setSessionSearch] = useState('')
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null)
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null)

  const usersQuery = useQuery<AdminUserSummaryPayload[]>({
    queryKey: ['admin-users'],
    queryFn: () => fetchAdminUsers(200),
    staleTime: 1000 * 30,
  })

  const sessionsQuery = useQuery<AdminSessionSummaryPayload[]>({
    queryKey: ['admin-conversations', selectedUserId],
    queryFn: () => fetchAdminConversations({ userId: selectedUserId ?? undefined, limit: 200 }),
    enabled: Boolean(selectedUserId),
    staleTime: 1000 * 30,
  })

  const messagesQuery = useQuery({
    queryKey: ['admin-conversation-messages', selectedUserId, selectedSessionId],
    queryFn: () => fetchAdminConversationMessages(selectedUserId ?? '', selectedSessionId ?? ''),
    enabled: Boolean(selectedUserId && selectedSessionId),
    staleTime: 1000 * 10,
  })

  useEffect(() => {
    if (selectedUserId || !usersQuery.data?.length) return
    setSelectedUserId(usersQuery.data[0].user_id)
  }, [selectedUserId, usersQuery.data])

  useEffect(() => {
    if (!selectedUserId) return
    if (sessionsQuery.isLoading) return
    if (!sessionsQuery.data?.length) {
      setSelectedSessionId(null)
      return
    }
    if (selectedSessionId && sessionsQuery.data.some((session) => session.session_id === selectedSessionId)) return
    setSelectedSessionId(sessionsQuery.data[0].session_id)
  }, [selectedUserId, selectedSessionId, sessionsQuery.data, sessionsQuery.isLoading])

  const filteredUsers = useMemo(() => {
    const users = usersQuery.data ?? []
    const query = userSearch.trim().toLowerCase()
    if (!query) return users
    return users.filter((user) =>
      [user.user_id, user.display_name ?? '', user.contact_email ?? ''].some((value) =>
        matchesSearch(value, query),
      ),
    )
  }, [userSearch, usersQuery.data])

  const filteredSessions = useMemo(() => {
    const sessions = sessionsQuery.data ?? []
    const query = sessionSearch.trim().toLowerCase()
    if (!query) return sessions
    return sessions.filter((session) =>
      [session.session_id, session.title ?? ''].some((value) => matchesSearch(value, query)),
    )
  }, [sessionSearch, sessionsQuery.data])

  const messages = (messagesQuery.data as { messages?: AdminConversationMessagePayload[] } | undefined)?.messages ?? []

  return (
    <div className="mt-6 grid gap-6 lg:grid-cols-[280px_320px_1fr]">
      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.4em] text-slate-400">{t('admin.conversations.users')}</p>
            <p className="mt-1 text-sm text-slate-600">{filteredUsers.length}</p>
          </div>
          <button
            type="button"
            className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600 hover:border-slate-400"
            onClick={() => void usersQuery.refetch()}
          >
            {t('common.refresh')}
          </button>
        </div>
        <input
          value={userSearch}
          onChange={(event) => setUserSearch(event.target.value)}
          placeholder={t('admin.conversations.search_users')}
          className="mt-4 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-200"
        />
        {usersQuery.isLoading ? (
          <p className="mt-4 text-sm text-slate-500">{t('common.loading')}</p>
        ) : usersQuery.error ? (
          <p className="mt-4 text-sm text-rose-600">{String(usersQuery.error)}</p>
        ) : filteredUsers.length === 0 ? (
          <p className="mt-4 text-sm text-slate-500">{t('admin.conversations.none_users')}</p>
        ) : (
          <ul className="mt-4 space-y-2">
            {filteredUsers.map((user) => {
              const active = selectedUserId === user.user_id
              return (
                <li key={user.user_id}>
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedUserId(user.user_id)
                      setSelectedSessionId(null)
                    }}
                    className={`w-full rounded-xl border px-3 py-3 text-left transition ${
                      active ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-white hover:border-slate-400'
                    }`}
                  >
                    <p className="text-sm font-semibold">
                      {user.display_name || user.user_id}
                    </p>
                    <p className={`mt-1 text-xs ${active ? 'text-white/70' : 'text-slate-500'}`}>
                      {user.contact_email || user.user_id}
                    </p>
                    <p className={`mt-1 text-xs ${active ? 'text-white/70' : 'text-slate-500'}`}>
                      {t('admin.conversations.session_count', { count: user.session_count })}
                    </p>
                    <p className={`mt-1 text-xs ${active ? 'text-white/70' : 'text-slate-500'}`}>
                      {t('admin.conversations.last_active')}: {formatTimestamp(user.last_active_at)}
                    </p>
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.4em] text-slate-400">{t('admin.conversations.sessions')}</p>
            <p className="mt-1 text-sm text-slate-600">{filteredSessions.length}</p>
          </div>
          <button
            type="button"
            className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600 hover:border-slate-400"
            onClick={() => void sessionsQuery.refetch()}
            disabled={!selectedUserId}
          >
            {t('common.refresh')}
          </button>
        </div>
        <input
          value={sessionSearch}
          onChange={(event) => setSessionSearch(event.target.value)}
          placeholder={t('admin.conversations.search_sessions')}
          className="mt-4 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-200"
          disabled={!selectedUserId}
        />
        {!selectedUserId ? (
          <p className="mt-4 text-sm text-slate-500">{t('admin.conversations.select_user')}</p>
        ) : sessionsQuery.isLoading ? (
          <p className="mt-4 text-sm text-slate-500">{t('common.loading')}</p>
        ) : sessionsQuery.error ? (
          <p className="mt-4 text-sm text-rose-600">{String(sessionsQuery.error)}</p>
        ) : filteredSessions.length === 0 ? (
          <p className="mt-4 text-sm text-slate-500">{t('admin.conversations.none_sessions')}</p>
        ) : (
          <ul className="mt-4 space-y-2">
            {filteredSessions.map((session) => {
              const active = selectedSessionId === session.session_id
              return (
                <li key={session.session_id}>
                  <button
                    type="button"
                    onClick={() => setSelectedSessionId(session.session_id)}
                    className={`w-full rounded-xl border px-3 py-3 text-left transition ${
                      active ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-white hover:border-slate-400'
                    }`}
                  >
                    <p className="text-sm font-semibold">{session.title || session.session_id}</p>
                    <p className={`mt-1 text-xs ${active ? 'text-white/70' : 'text-slate-500'}`}>
                      {t('admin.conversations.session.meta', { slots: session.slot_count })}
                    </p>
                    <p className={`mt-1 text-xs ${active ? 'text-white/70' : 'text-slate-500'}`}>
                      {t('admin.conversations.session.updated', { time: formatTimestamp(session.updated_at) })}
                    </p>
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.4em] text-slate-400">{t('admin.conversations.messages')}</p>
            <p className="mt-1 text-sm text-slate-600">{messages.length}</p>
          </div>
          <button
            type="button"
            className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600 hover:border-slate-400"
            onClick={() => void messagesQuery.refetch()}
            disabled={!selectedSessionId}
          >
            {t('common.refresh')}
          </button>
        </div>
        {!selectedSessionId ? (
          <p className="mt-4 text-sm text-slate-500">{t('admin.conversations.none_messages')}</p>
        ) : messagesQuery.isLoading ? (
          <p className="mt-4 text-sm text-slate-500">{t('common.loading')}</p>
        ) : messagesQuery.error ? (
          <p className="mt-4 text-sm text-rose-600">{String(messagesQuery.error)}</p>
        ) : messages.length === 0 ? (
          <p className="mt-4 text-sm text-slate-500">{t('admin.conversations.empty_messages')}</p>
        ) : (
          <div className="mt-4 space-y-4">
            {messages.map((message) => (
              <div key={message.id} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span
                    className={`rounded-full px-3 py-1 text-xs font-semibold ${
                      message.role === 'assistant'
                        ? 'bg-slate-900 text-white'
                        : 'bg-white text-slate-700 border border-slate-200'
                    }`}
                  >
                    {message.role}
                  </span>
                  <span className="text-xs text-slate-500">{formatTimestamp(message.created_at)}</span>
                </div>
                <p className="mt-3 whitespace-pre-wrap text-sm text-slate-700">{message.content}</p>
                <div className="mt-3 flex flex-wrap gap-3 text-xs text-slate-500">
                  <span>{t('admin.conversations.message.citations', { count: message.citations?.length ?? 0 })}</span>
                  <span>{t('admin.conversations.message.attachments', { count: message.attachments?.length ?? 0 })}</span>
                </div>
                {message.citations && message.citations.length > 0 ? (
                  <div className="mt-3">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.35em] text-slate-400">
                      {t('admin.conversations.message.rerank_title')}
                    </p>
                    <ul className="mt-2 space-y-2">
                      {message.citations.map((citation) => (
                        <li
                          key={`${message.id}-${citation.chunk_id}`}
                          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span className="font-semibold text-slate-800">
                              {citation.source_name ?? citation.doc_id}
                            </span>
                            <span>{t('admin.conversations.message.rerank_score', { score: formatScore(citation.score) })}</span>
                          </div>
                          {citation.snippet ? (
                            <p className="mt-1 text-xs text-slate-600">{citation.snippet}</p>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                <div className="mt-3">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.35em] text-slate-400">
                    {t('admin.conversations.feedback.title')}
                  </p>
                  {message.feedback && message.feedback.length > 0 ? (
                    <ul className="mt-2 space-y-2">
                      {message.feedback.map((fb, idx) => (
                        <li key={`${message.id}-fb-${idx}`} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span className="font-semibold text-slate-800">{ratingLabel(fb.rating, t)}</span>
                            <span>{formatTimestamp(fb.submitted_at)}</span>
                          </div>
                          <p className="mt-1 text-slate-600">
                            {t('admin.conversations.feedback.actor')}: {fb.actor || t('common.na')}
                          </p>
                          {fb.comment ? (
                            <p className="mt-1 text-slate-600">
                              {t('admin.conversations.feedback.comment')}: {fb.comment}
                            </p>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-2 text-xs text-slate-500">{t('admin.conversations.feedback.none')}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

export default ConversationsDashboard
*/
