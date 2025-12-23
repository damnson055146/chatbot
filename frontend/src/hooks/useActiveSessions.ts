import { useQuery } from '@tanstack/react-query'
import { fetchActiveSessions, type SessionStatePayload } from '../services/apiClient'

export function useActiveSessions() {
  return useQuery<SessionStatePayload[], Error>({
    queryKey: ['sessions'],
    queryFn: fetchActiveSessions,
    staleTime: 1000 * 30,
  })
}
