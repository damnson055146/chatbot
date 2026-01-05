const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000/v1'

const getFallbackOrigin = () => {
  if (typeof window !== 'undefined' && window.location?.origin) {
    return window.location.origin
  }
  return 'http://localhost'
}

const isAbsoluteUrl = (value: string) => /^[a-z][a-z0-9+.-]*:/i.test(value) || value.startsWith('//')

const getApiBaseUrl = () => {
  try {
    return new URL(API_BASE, getFallbackOrigin())
  } catch {
    return null
  }
}

export const resolveApiUrl = (input?: string | null): string => {
  if (!input) return ''
  const trimmed = input.trim()
  if (!trimmed) return ''
  if (isAbsoluteUrl(trimmed)) return trimmed

  const baseUrl = getApiBaseUrl()
  if (!baseUrl) return trimmed
  if (trimmed.startsWith('/')) {
    return `${baseUrl.origin}${trimmed}`
  }
  try {
    return new URL(trimmed, baseUrl).toString()
  } catch {
    return trimmed
  }
}
