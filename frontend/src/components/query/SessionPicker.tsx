import { useMemo } from 'react'
import { useActiveSessions } from '../../hooks/useActiveSessions'

interface SessionPickerProps {
  currentSessionId?: string
  onSelect: (sessionId: string) => void
}

export function SessionPicker({ currentSessionId, onSelect }: SessionPickerProps) {
  const { data: sessions = [], isLoading, refetch } = useActiveSessions()

  const sortedSessions = useMemo(() => {
    return [...sessions].sort((a, b) => {
      const left = b.updated_at ?? b.created_at ?? ''
      const right = a.updated_at ?? a.created_at ?? ''
      return left.localeCompare(right)
    })
  }, [sessions])

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <header className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">Active sessions</h3>
          <p className="text-xs text-slate-500">Resume an existing conversation tracked by the backend.</p>
        </div>
        <button type="button" className="text-xs font-medium text-brand-primary" onClick={() => void refetch()}>
          Refresh
        </button>
      </header>
      {isLoading ? (
        <p className="text-sm text-slate-500">Loading sessions...</p>
      ) : sortedSessions.length === 0 ? (
        <p className="text-sm text-slate-500">No active sessions detected.</p>
      ) : (
        <ul className="space-y-3 text-sm text-slate-700">
          {sortedSessions.map((session) => (
            <li
              key={session.session_id}
              className={`flex items-center justify-between rounded-md border px-3 py-2 ${
                session.session_id === currentSessionId
                  ? 'border-brand-primary bg-brand-primary/5 text-brand-primary'
                  : 'border-slate-200 bg-slate-50'
              }`}
            >
              <div className="flex flex-col">
                <span className="font-medium">{session.session_id.slice(0, 12)}</span>
                <span className="text-xs text-slate-500">
                  Slots: {session.slot_count ?? Object.keys(session.slots ?? {}).length} ¡¤ TTL:{' '}
                  {session.remaining_ttl_seconds ? `${session.remaining_ttl_seconds}s` : 'n/a'}
                </span>
              </div>
              <button
                type="button"
                className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium"
                onClick={() => onSelect(session.session_id)}
              >
                {session.session_id === currentSessionId ? 'Current' : 'Resume'}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
