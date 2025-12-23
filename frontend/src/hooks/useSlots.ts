import { useQuery } from '@tanstack/react-query'
import { fetchSlotCatalog, type SlotDefinitionPayload } from '../services/apiClient'

export function useSlots(language: string) {
  return useQuery<SlotDefinitionPayload[], Error>({
    queryKey: ['slots', language],
    queryFn: () => fetchSlotCatalog(language === 'auto' ? undefined : language),
    staleTime: 1000 * 60 * 5,
  })
}
