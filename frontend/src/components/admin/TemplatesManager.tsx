import { useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  deleteAdminTemplate,
  fetchAdminTemplates,
  upsertAdminTemplate,
  type AdminTemplatePayload,
  type AdminTemplateUpsertRequestPayload,
} from '../../services/apiClient'

const emptyDraft = (): AdminTemplateUpsertRequestPayload => ({
  template_id: '',
  name: '',
  language: 'en',
  category: '',
  description: '',
  content: '',
})

export function TemplatesManager({ readOnly = false }: { readOnly?: boolean }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [draft, setDraft] = useState<AdminTemplateUpsertRequestPayload>(emptyDraft)
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState<{ tone: 'info' | 'error'; message: string } | null>(null)

  const templatesQuery = useQuery<AdminTemplatePayload[], Error>({
    queryKey: ['admin-templates'],
    queryFn: fetchAdminTemplates,
    staleTime: 1000 * 15,
  })

  const templates = templatesQuery.data ?? []
  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase()
    if (!term) return templates
    return templates.filter((t) =>
      `${t.template_id} ${t.name} ${t.language} ${t.category ?? ''} ${t.description ?? ''}`.toLowerCase().includes(term),
    )
  }, [templates, search])

  const selected = useMemo(
    () => (selectedId ? templates.find((t) => t.template_id === selectedId) ?? null : null),
    [templates, selectedId],
  )

  const loadDraft = (template: AdminTemplatePayload | null) => {
    if (!template) {
      setDraft(emptyDraft())
      return
    }
    setDraft({
      template_id: template.template_id,
      name: template.name,
      language: template.language,
      category: template.category ?? '',
      description: template.description ?? '',
      content: template.content,
    })
  }

  const onSelect = (id: string) => {
    setSelectedId(id)
    loadDraft(templates.find((t) => t.template_id === id) ?? null)
    setStatus(null)
  }

  const onNew = () => {
    setSelectedId(null)
    loadDraft(null)
    setStatus(null)
  }

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['admin-templates'] })
  }

  const save = async () => {
    if (readOnly) return
    if (!draft.template_id.trim() || !draft.name.trim() || !draft.language.trim() || !draft.content.trim()) {
      setStatus({ tone: 'error', message: t('admin.templates.error.required') })
      return
    }
    setBusy(true)
    setStatus(null)
    try {
      const payload: AdminTemplateUpsertRequestPayload = {
        template_id: draft.template_id.trim(),
        name: draft.name.trim(),
        language: draft.language.trim(),
        category: draft.category?.trim() || null,
        description: draft.description?.trim() || null,
        content: draft.content,
      }
      const res = await upsertAdminTemplate(payload)
      await refresh()
      setSelectedId(res.template.template_id)
      setStatus({ tone: 'info', message: t('admin.templates.status.saved', { id: res.template.template_id }) })
    } catch (e) {
      setStatus({ tone: 'error', message: e instanceof Error ? e.message : t('admin.templates.error.save') })
    } finally {
      setBusy(false)
    }
  }

  const remove = async (templateId: string) => {
    if (readOnly) return
    const ok = typeof window === 'undefined' ? true : window.confirm(t('admin.templates.delete_confirm', { id: templateId }))
    if (!ok) return
    setBusy(true)
    setStatus(null)
    try {
      await deleteAdminTemplate(templateId)
      await refresh()
      if (selectedId === templateId) onNew()
      setStatus({ tone: 'info', message: t('admin.templates.status.deleted', { id: templateId }) })
    } catch (e) {
      setStatus({ tone: 'error', message: e instanceof Error ? e.message : t('admin.templates.error.delete') })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mt-6 grid gap-6 lg:grid-cols-2">
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-900">{t('admin.templates.title')}</h3>
            <p className="mt-1 text-xs text-slate-500">{t('admin.templates.subtitle')}</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="rounded-full border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:border-slate-400"
              onClick={() => void templatesQuery.refetch()}
              disabled={templatesQuery.isLoading}
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
            placeholder={t('admin.templates.search_placeholder')}
            className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-slate-200"
          />
        </div>

        {templatesQuery.isLoading ? <p className="mt-4 text-sm text-slate-500">{t('common.loading')}</p> : null}
        {templatesQuery.error ? <p className="mt-4 text-sm text-rose-600">{templatesQuery.error.message}</p> : null}

        <ul className="mt-4 space-y-2">
          {filtered.map((t) => {
            const active = t.template_id === selectedId
            return (
              <li key={t.template_id}>
                <button
                  type="button"
                  className={`flex w-full items-start justify-between rounded-xl border px-4 py-3 text-left ${
                    active ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-white text-slate-900 hover:border-slate-300'
                  }`}
                  onClick={() => onSelect(t.template_id)}
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold">{t.name}</p>
                    <p className={`mt-1 text-xs ${active ? 'text-white/70' : 'text-slate-500'}`}>
                      {t.template_id} · {t.language}
                      {t.category ? ` · ${t.category}` : ''}
                    </p>
                  </div>
                  <span className={`text-xs ${active ? 'text-white/70' : 'text-slate-400'}`}>›</span>
                </button>
              </li>
            )
          })}
          {filtered.length === 0 && !templatesQuery.isLoading ? (
            <li className="rounded-xl border border-dashed border-slate-200 bg-white px-4 py-6 text-center text-sm text-slate-500">
              {t('admin.templates.none')}
            </li>
          ) : null}
        </ul>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-900">
              {selected ? t('admin.templates.edit_title', { id: selected.template_id }) : t('admin.templates.create_title')}
            </h3>
            <p className="mt-1 text-xs text-slate-500">{t('admin.templates.hint')}</p>
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
          <Field label={t('admin.templates.field.template_id')}>
            <input
              value={draft.template_id}
              onChange={(e) => setDraft((prev) => ({ ...prev, template_id: e.target.value }))}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              disabled={busy || readOnly}
            />
          </Field>
          <Field label={t('admin.templates.field.language')}>
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
          <div className="sm:col-span-2">
            <Field label={t('admin.templates.field.name')}>
              <input
                value={draft.name}
                onChange={(e) => setDraft((prev) => ({ ...prev, name: e.target.value }))}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                disabled={busy || readOnly}
              />
            </Field>
          </div>
          <Field label={t('admin.templates.field.category')}>
            <input
              value={draft.category ?? ''}
              onChange={(e) => setDraft((prev) => ({ ...prev, category: e.target.value }))}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              disabled={busy || readOnly}
            />
          </Field>
          <Field label={t('admin.templates.field.description')}>
            <input
              value={draft.description ?? ''}
              onChange={(e) => setDraft((prev) => ({ ...prev, description: e.target.value }))}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              disabled={busy || readOnly}
            />
          </Field>
          <div className="sm:col-span-2">
            <Field label={t('admin.templates.field.content')}>
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
              className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-2 text-sm font-semibold text-rose-700 hover:border-rose-300 disabled:opacity-50"
              onClick={() => void remove(selected.template_id)}
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
