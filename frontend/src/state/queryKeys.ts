export const queryKeys = {
  slots: ['slots'] as const,
  session: (id: string) => ['session', id] as const,
  queryHistory: ['query-history'] as const,
}
