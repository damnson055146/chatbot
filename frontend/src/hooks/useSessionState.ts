import { useQuery } from '@tanstack/react-query'
import { fetchSessionState, type SessionStatePayload } from '../services/apiClient'

export function useSessionState(sessionId: string | undefined, scope?: string) {
  return useQuery<SessionStatePayload, Error>({
    queryKey: ['session', scope ?? 'default', sessionId],
    queryFn: () => fetchSessionState(sessionId as string),
    enabled: Boolean(sessionId),
    staleTime: 1000 * 60,
  })
}
