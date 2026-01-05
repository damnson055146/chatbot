import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  DEFAULT_USER_PREFERENCES,
  loadUserPreferences,
  resetUserPreferences,
  saveUserPreferences,
  USER_PREFS_EVENT,
  type UserPreferences,
} from '../services/userPreferences'

export function useUserPreferences() {
  const [preferences, setPreferences] = useState<UserPreferences>(() => loadUserPreferences())

  useEffect(() => {
    if (typeof window === 'undefined') return
    const handleUpdate = (event: Event) => {
      const detail = (event as CustomEvent<UserPreferences>).detail
      setPreferences(detail ?? loadUserPreferences())
    }
    window.addEventListener(USER_PREFS_EVENT, handleUpdate as EventListener)
    return () => window.removeEventListener(USER_PREFS_EVENT, handleUpdate as EventListener)
  }, [])

  const updatePreferences = useCallback((updates: Partial<UserPreferences>) => {
    setPreferences((prev) => {
      const merged = { ...prev, ...updates }
      saveUserPreferences(merged)
      return merged
    })
  }, [])

  const reset = useCallback(() => {
    const defaults = resetUserPreferences()
    setPreferences(defaults)
  }, [])

  const hasCustomizations = useMemo(() => {
    return (
      preferences.avatarColor !== DEFAULT_USER_PREFERENCES.avatarColor ||
      preferences.preferredLanguage !== DEFAULT_USER_PREFERENCES.preferredLanguage ||
      preferences.explainLikeNewDefault !== DEFAULT_USER_PREFERENCES.explainLikeNewDefault ||
      preferences.defaultTopK !== DEFAULT_USER_PREFERENCES.defaultTopK ||
      preferences.defaultKCite !== DEFAULT_USER_PREFERENCES.defaultKCite ||
      preferences.retentionDays !== DEFAULT_USER_PREFERENCES.retentionDays ||
      preferences.theme !== DEFAULT_USER_PREFERENCES.theme
    )
  }, [preferences])

  return { preferences, updatePreferences, resetPreferences: reset, hasCustomizations }
}
