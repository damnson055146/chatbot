import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Suspense, useEffect } from 'react'
import { RouterProvider } from 'react-router-dom'
import { AppRouter } from './routes'
import '../index.css'
import { useUserPreferences } from '../hooks/useUserPreferences'
import { i18next } from '../utils/i18n'
import { useTranslation } from 'react-i18next'

const queryClient = new QueryClient()
const SUPPORTED_UI_LANGUAGES = ['en', 'zh']

export function App() {
  const { preferences } = useUserPreferences()
  const { t } = useTranslation()

  useEffect(() => {
    if (typeof document === 'undefined') return
    document.documentElement.dataset.theme = preferences.theme
  }, [preferences.theme])

  useEffect(() => {
    const pref = (preferences.preferredLanguage ?? 'auto').toString().toLowerCase()
    const next = pref === 'auto' ? (navigator.language || 'en').slice(0, 2).toLowerCase() : pref
    const lang = SUPPORTED_UI_LANGUAGES.includes(next) ? next : 'en'
    void i18next.changeLanguage(lang)
  }, [preferences.preferredLanguage])

  return (
    <QueryClientProvider client={queryClient}>
      <Suspense
        fallback={<div className="flex items-center justify-center py-20 text-sm text-slate-500">{t('common.loading')}</div>}
      >
        <RouterProvider router={AppRouter} />
      </Suspense>
    </QueryClientProvider>
  )
}

export default App
