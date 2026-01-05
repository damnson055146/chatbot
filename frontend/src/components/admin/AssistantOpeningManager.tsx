import { useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  fetchAdminAssistantOpening,
  updateAdminAssistantOpening,
  type AdminAssistantOpeningEntryPayload,
  type AdminAssistantOpeningResponsePayload,
} from '../../services/apiClient'

const OPENING_LANGUAGES = [
  { key: 'en', labelKey: 'admin.opening.language.en' },
  { key: 'zh', labelKey: 'admin.opening.language.zh' },
]

export function AssistantOpeningManager({ readOnly = false }: { readOnly?: boolean }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [status, setStatus] = useState<{ tone: 'info' | 'error'; message: string } | null>(null)

  const openingQuery = useQuery<AdminAssistantOpeningResponsePayload, Error>({
    queryKey: ['admin-assistant-opening'],
    queryFn: fetchAdminAssistantOpening,
    staleTime: 1000 * 30,
  })

  const entryByLanguage = useMemo(() => {
    const lookup: Record<string, AdminAssistantOpeningEntryPayload> = {}
    for (const entry of openingQuery.data?.entries ?? []) {
      lookup[entry.language] = entry
    }
    return lookup
  }, [openingQuery.data])

  useEffect(() => {
    if (!openingQuery.data) return
    setDrafts((prev) => {
      const next = { ...prev }
      for (const language of OPENING_LANGUAGES) {
        next[language.key] = entryByLanguage[language.key]?.content ?? ''
      }
      return next
    })
  }, [openingQuery.data, entryByLanguage])

  const handleSave = async (language: string) => {
    if (readOnly) return
    setStatus(null)
    try {
      await updateAdminAssistantOpening({
        language,
        content: drafts[language] ?? '',
      })
      await queryClient.invalidateQueries({ queryKey: ['admin-assistant-opening'] })
      setStatus({ tone: 'info', message: t('admin.opening.status.saved') })
    } catch (error) {
      setStatus({
        tone: 'error',
        message: error instanceof Error ? error.message : t('admin.opening.error.save'),
      })
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-sm font-semibold text-slate-900">{t('admin.opening.title')}</h3>
        <p className="mt-1 text-xs text-slate-500">{t('admin.opening.subtitle')}</p>
        {status ? (
          <p className={`mt-2 text-xs ${status.tone === 'error' ? 'text-rose-600' : 'text-slate-500'}`}>
            {status.message}
          </p>
        ) : null}
        {openingQuery.error ? (
          <p className="mt-2 text-xs text-rose-600">{openingQuery.error.message}</p>
        ) : null}
      </div>

      {OPENING_LANGUAGES.map((language) => {
        const entry = entryByLanguage[language.key]
        const updatedAt = entry?.updated_at ? new Date(entry.updated_at).toLocaleString() : null
        return (
          <div key={language.key} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.35em] text-slate-400">
                  {t(language.labelKey)}
                </p>
                {updatedAt ? (
                  <p className="mt-1 text-xs text-slate-500">{t('admin.opening.updated_at', { time: updatedAt })}</p>
                ) : null}
              </div>
              <button
                type="button"
                className="rounded-full border border-slate-300 bg-white px-3 py-1 text-xs font-semibold text-slate-700 hover:border-slate-400 disabled:cursor-not-allowed disabled:opacity-50"
                onClick={() => void handleSave(language.key)}
                disabled={readOnly || openingQuery.isLoading}
              >
                {t('admin.opening.save')}
              </button>
            </div>
            <label className="mt-4 block text-sm text-slate-600">
              <span className="text-xs uppercase tracking-wide text-slate-500">{t('admin.opening.field.content')}</span>
              <textarea
                value={drafts[language.key] ?? ''}
                onChange={(event) => setDrafts((prev) => ({ ...prev, [language.key]: event.target.value }))}
                className="mt-2 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-200"
                rows={4}
                disabled={readOnly || openingQuery.isLoading}
              />
            </label>
          </div>
        )
      })}
    </div>
  )
}

export default AssistantOpeningManager
