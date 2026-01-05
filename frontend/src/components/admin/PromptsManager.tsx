import { useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  activateAdminPrompt,
  deleteAdminPrompt,
  fetchAdminPrompts,
  upsertAdminPrompt,
  type AdminPromptPayload,
  type AdminPromptUpsertRequestPayload,
} from '../../services/apiClient'

const emptyDraft = (): AdminPromptUpsertRequestPayload => ({
  prompt_id: '',
  name: '',
  language: 'en',
  content: '',
  description: '',
  is_active: false,
})

export function PromptsManager({ readOnly = false }: { readOnly?: boolean }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [draft, setDraft] = useState<AdminPromptUpsertRequestPayload>(emptyDraft)
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState<{ tone: 'info' | 'error'; message: string } | null>(null)

  const promptsQuery = useQuery<AdminPromptPayload[], Error>({
    queryKey: ['admin-prompts'],
    queryFn: fetchAdminPrompts,
    staleTime: 1000 * 15,
  })

  const prompts = promptsQuery.data ?? []
  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase()
    if (!term) return prompts
    return prompts.filter((p) => `${p.prompt_id} ${p.name} ${p.language} ${p.description ?? ''}`.toLowerCase().includes(term))
  }, [prompts, search])

  const selected = useMemo(
    () => (selectedId ? prompts.find((p) => p.prompt_id === selectedId) ?? null : null),
    [prompts, selectedId],
  )

  const loadDraft = (prompt: AdminPromptPayload | null) => {
    if (!prompt) {
      setDraft(emptyDraft())
      return
    }
    setDraft({
      prompt_id: prompt.prompt_id,
      name: prompt.name,
      language: prompt.language,
      content: prompt.content,
      description: prompt.description ?? '',
      is_active: prompt.is_active,
    })
  }

  const onSelect = (id: string) => {
    setSelectedId(id)
    loadDraft(prompts.find((p) => p.prompt_id === id) ?? null)
    setStatus(null)
  }

  const onNew = () => {
    setSelectedId(null)
    loadDraft(null)
    setStatus(null)
  }

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['admin-prompts'] })
    await queryClient.invalidateQueries({ queryKey: ['admin-config'] })
  }

  const save = async () => {
    if (readOnly) return
    if (!draft.name.trim() || !draft.language.trim() || !draft.content.trim()) {
      setStatus({ tone: 'error', message: t('admin.prompts.error.required') })
      return
    }
    setBusy(true)
    setStatus(null)
    try {
      const trimmedPromptId = draft.prompt_id.trim()
      const payload: AdminPromptUpsertRequestPayload = {
        ...(trimmedPromptId ? { prompt_id: trimmedPromptId } : {}),
        name: draft.name.trim(),
        language: draft.language.trim(),
        content: draft.content,
        description: draft.description?.trim() || null,
        is_active: Boolean(draft.is_active),
      }
      const res = await upsertAdminPrompt(payload)
      await refresh()
      setSelectedId(res.prompt.prompt_id)
      loadDraft(res.prompt)
      setStatus({ tone: 'info', message: t('admin.prompts.status.saved', { id: res.prompt.prompt_id }) })
    } catch (e) {
      setStatus({ tone: 'error', message: e instanceof Error ? e.message : t('admin.prompts.error.save') })
    } finally {
      setBusy(false)
    }
  }

  const activate = async (promptId: string) => {
    if (readOnly) return
    setBusy(true)
    setStatus(null)
    try {
      await activateAdminPrompt(promptId)
      await refresh()
      setStatus({ tone: 'info', message: t('admin.prompts.status.activated', { id: promptId }) })
    } catch (e) {
      setStatus({ tone: 'error', message: e instanceof Error ? e.message : t('admin.prompts.error.activate') })
    } finally {
      setBusy(false)
    }
  }

  const remove = async (promptId: string) => {
    if (readOnly) return
    const ok = typeof window === 'undefined' ? true : window.confirm(t('admin.prompts.delete_confirm', { id: promptId }))
    if (!ok) return
    setBusy(true)
    setStatus(null)
    try {
      await deleteAdminPrompt(promptId)
      await refresh()
      if (selectedId === promptId) onNew()
      setStatus({ tone: 'info', message: t('admin.prompts.status.deleted', { id: promptId }) })
    } catch (e) {
      setStatus({ tone: 'error', message: e instanceof Error ? e.message : t('admin.prompts.error.delete') })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mt-6 grid gap-6 lg:grid-cols-2">
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-900">{t('admin.prompts.title')}</h3>
            <p className="mt-1 text-xs text-slate-500">{t('admin.prompts.subtitle')}</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="rounded-full border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:border-slate-400"
              onClick={() => void promptsQuery.refetch()}
              disabled={promptsQuery.isLoading}
            >
              {t('common.refresh')}
            </button>
            <button
              type="button"
              className="rounded-full bg-slate-900 px-4 py-2 text-xs font-semibold text-white hover:bg-slate-800"
              onClick={onNew}
              disabled={readOnly}
            >
              {t('common.new')}
            </button>
          </div>
        </div>

        <div className="mt-4">
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('admin.prompts.search_placeholder')}
            className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-slate-200"
          />
        </div>

        {promptsQuery.isLoading ? <p className="mt-4 text-sm text-slate-500">{t('common.loading')}</p> : null}
        {promptsQuery.error ? <p className="mt-4 text-sm text-rose-600">{promptsQuery.error.message}</p> : null}

        <ul className="mt-4 space-y-2">
          {filtered.map((p) => {
            const active = p.prompt_id === selectedId
            return (
              <li key={p.prompt_id}>
                <button
                  type="button"
                  className={`flex w-full items-start justify-between rounded-xl border px-4 py-3 text-left ${
                    active ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-white text-slate-900 hover:border-slate-300'
                  }`}
                  onClick={() => onSelect(p.prompt_id)}
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold">{p.name}</p>
                    <p className={`mt-1 text-xs ${active ? 'text-white/70' : 'text-slate-500'}`}>
                      {p.prompt_id} · {p.language} {p.is_active ? `· ${t('common.active')}` : ''}
                    </p>
                  </div>
                  <span className={`text-xs ${active ? 'text-white/70' : 'text-slate-400'}`}>›</span>
                </button>
              </li>
            )
          })}
          {filtered.length === 0 && !promptsQuery.isLoading ? (
            <li className="rounded-xl border border-dashed border-slate-200 bg-white px-4 py-6 text-center text-sm text-slate-500">
              {t('admin.prompts.none')}
            </li>
          ) : null}
        </ul>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-900">
              {selected ? t('admin.prompts.edit_title', { id: selected.prompt_id }) : t('admin.prompts.create_title')}
            </h3>
            <p className="mt-1 text-xs text-slate-500">{t('admin.prompts.active_hint')}</p>
          </div>
          <button
            type="button"
            className="rounded-full border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:border-slate-400"
            onClick={() => loadDraft(selected)}
            disabled={busy || readOnly}
          >
            {t('common.revert')}
          </button>
        </div>

        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Field label={t('admin.prompts.field.language')}>
              <select
                value={draft.language}
                onChange={(e) => setDraft((prev) => ({ ...prev, language: e.target.value }))}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                disabled={busy || readOnly}
              >
                <option value="en">{t('settings.language.en')}</option>
                <option value="zh">{t('settings.language.zh')}</option>
              </select>
            </Field>
          </div>
          <div className="sm:col-span-2">
            <Field label={t('admin.prompts.field.name')}>
              <input
                value={draft.name}
                onChange={(e) => setDraft((prev) => ({ ...prev, name: e.target.value }))}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                disabled={busy || readOnly}
              />
            </Field>
          </div>
          <div className="sm:col-span-2">
            <Field label={t('admin.prompts.field.description')}>
              <input
                value={draft.description ?? ''}
                onChange={(e) => setDraft((prev) => ({ ...prev, description: e.target.value }))}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                disabled={busy || readOnly}
              />
            </Field>
          </div>
          <div className="sm:col-span-2">
            <Field label={t('admin.prompts.field.content')}>
              <textarea
                value={draft.content}
                onChange={(e) => setDraft((prev) => ({ ...prev, content: e.target.value }))}
                className="h-64 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm font-mono"
                disabled={busy || readOnly}
              />
            </Field>
          </div>
        </div>

        {status ? (
          <p className={`mt-4 text-sm ${status.tone === 'error' ? 'text-rose-600' : 'text-slate-600'}`}>{status.message}</p>
        ) : null}

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            type="button"
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
            onClick={() => void save()}
            disabled={busy || readOnly}
          >
            {t('common.save')}
          </button>
          {selected ? (
            <button
              type="button"
              className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:border-slate-400 disabled:opacity-50"
              onClick={() => void activate(selected.prompt_id)}
              disabled={busy || readOnly}
            >
              {t('common.active')}
            </button>
          ) : null}
          {selected ? (
            <button
              type="button"
              className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-2 text-sm font-semibold text-rose-700 hover:border-rose-300 disabled:opacity-50"
              onClick={() => void remove(selected.prompt_id)}
              disabled={busy || readOnly}
            >
              {t('common.delete')}
            </button>
          ) : null}
        </div>
      </section>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block text-sm text-slate-700">
      <span className="text-xs uppercase tracking-wide text-slate-500">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  )
}
