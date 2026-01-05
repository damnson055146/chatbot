import { useQuery } from '@tanstack/react-query'
import { fetchActiveSessions, type SessionStatePayload } from '../services/apiClient'

const EMPTY_SESSIONS: SessionStatePayload[] = []

export function useActiveSessions(scope?: string, enabled = true) {
  return useQuery<SessionStatePayload[], Error>({
    queryKey: ['sessions', scope ?? 'default'],
    queryFn: fetchActiveSessions,
    staleTime: 1000 * 30,
    placeholderData: EMPTY_SESSIONS,
    enabled,
  })
}
