import { useQuery } from '@tanstack/react-query'
import { fetchServiceStatus, type ServiceStatusResponsePayload } from '../services/apiClient'

export function useServiceStatus() {
  return useQuery<ServiceStatusResponsePayload, Error>({
    queryKey: ['service-status'],
    queryFn: fetchServiceStatus,
    staleTime: 1000 * 60,
  })
}
