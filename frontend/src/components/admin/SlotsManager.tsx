import { useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { fetchAdminConfig, updateAdminSlots, type AdminSlotConfigPayload } from '../../services/apiClient'

const normalizeName = (value: string) => value.trim().toLowerCase().replace(/\s+/g, '_')

const emptySlot = (): AdminSlotConfigPayload => ({
  name: '',
  description: '',
  prompt: '',
  prompt_zh: '',
  required: false,
  value_type: 'string',
  choices: null,
  min_value: null,
  max_value: null,
})

export function SlotsManager({ readOnly = false }: { readOnly?: boolean }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<{ tone: 'info' | 'error'; message: string } | null>(null)
  const [busy, setBusy] = useState(false)

  const configQuery = useQuery({
    queryKey: ['admin-config'],
    queryFn: fetchAdminConfig,
    staleTime: 1000 * 15,
  })

  const [draft, setDraft] = useState<AdminSlotConfigPayload[]>([])

  useEffect(() => {
    if (!configQuery.data) return
    setDraft((configQuery.data.slots ?? []).map((s) => ({ ...s })))
  }, [configQuery.data])

  const issues = useMemo(() => {
    const errors: string[] = []
    const seen = new Set<string>()
    for (const slot of draft) {
      const name = normalizeName(slot.name)
      if (!name) {
        errors.push(t('admin.slots.error.name_required'))
        continue
      }
      if (seen.has(name)) {
        errors.push(t('admin.slots.error.duplicate_name', { name }))
      }
      seen.add(name)
      if (slot.value_type === 'choice') {
        const choices = Array.isArray(slot.choices) ? slot.choices.filter(Boolean) : []
        if (choices.length === 0) {
          errors.push(t('admin.slots.error.choice_no_choices', { name }))
        }
      }
    }
    return errors
  }, [draft, t])

  const addSlot = () => {
    if (readOnly) return
    setDraft((prev) => [...prev, emptySlot()])
  }

  const removeSlot = (index: number) => {
    if (readOnly) return
    setDraft((prev) => prev.filter((_, idx) => idx !== index))
  }

  const save = async () => {
    if (readOnly) return
    setStatus(null)
    if (issues.length > 0) {
      setStatus({ tone: 'error', message: issues[0] })
      return
    }
    setBusy(true)
    try {
      const payloadSlots = draft.map((s) => ({
        ...s,
        name: normalizeName(s.name),
        description: s.description ?? '',
        prompt: s.prompt?.trim() || null,
        prompt_zh: s.prompt_zh?.trim() || null,
        value_type: s.value_type,
        choices:
          s.value_type === 'choice'
            ? (Array.isArray(s.choices) ? s.choices.map((c) => String(c).trim()).filter(Boolean) : [])
            : null,
        min_value: s.value_type === 'number' ? (s.min_value ?? null) : null,
        max_value: s.value_type === 'number' ? (s.max_value ?? null) : null,
      }))

      await updateAdminSlots({ slots: payloadSlots })
      await queryClient.invalidateQueries({ queryKey: ['admin-config'] })
      await queryClient.invalidateQueries({ queryKey: ['sessions'] })
      setStatus({ tone: 'info', message: t('admin.slots.status.updated') })
    } catch (e) {
      setStatus({ tone: 'error', message: e instanceof Error ? e.message : t('admin.slots.error.update') })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mt-6">
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-900">{t('admin.slots.title')}</h3>
            <p className="mt-1 text-xs text-slate-500">{t('admin.slots.subtitle')}</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="rounded-full border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:border-slate-400"
              onClick={() => void configQuery.refetch()}
              disabled={configQuery.isLoading}
            >
              {t('common.refresh')}
            </button>
            <button
              type="button"
              className="rounded-full border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:border-slate-400"
              onClick={addSlot}
              disabled={busy || readOnly}
            >
              {t('admin.slots.add_slot')}
            </button>
            <button
              type="button"
              className="rounded-full bg-slate-900 px-4 py-2 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
              onClick={() => void save()}
              disabled={busy || readOnly}
            >
              {t('common.save')}
            </button>
          </div>
        </div>

        {configQuery.isLoading ? <p className="mt-4 text-sm text-slate-500">{t('common.loading')}</p> : null}
        {configQuery.error ? <p className="mt-4 text-sm text-rose-600">{String(configQuery.error)}</p> : null}

        {issues.length > 0 ? (
          <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            <p className="font-semibold">{t('admin.slots.validation')}</p>
            <ul className="mt-2 list-disc pl-5">
              {issues.slice(0, 5).map((msg) => (
                <li key={msg}>{msg}</li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="mt-6 space-y-4">
          {draft.map((slot, idx) => (
            <div key={`${slot.name}-${idx}`} className="rounded-2xl border border-slate-200 bg-white p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-xs font-semibold uppercase tracking-[0.35em] text-slate-400">
                    {t('admin.slots.slot_number', { num: idx + 1 })}
                  </p>
                  <p className="mt-1 text-sm font-semibold text-slate-900">{slot.name || t('admin.slots.unnamed')}</p>
                </div>
                <button
                  type="button"
                  className="rounded-full border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700 hover:border-rose-300"
                  onClick={() => removeSlot(idx)}
                  disabled={busy || readOnly}
                >
                  {t('admin.slots.remove')}
                </button>
              </div>

              <div className="mt-4 grid gap-4 lg:grid-cols-2">
                <Field label={t('admin.slots.field.name')}>
                  <input
                    value={slot.name}
                    onChange={(e) => updateSlot(idx, { name: e.target.value })}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                    disabled={busy || readOnly}
                  />
                </Field>
                <Field label={t('admin.slots.field.value_type')}>
                  <select
                    value={slot.value_type}
                    onChange={(e) => updateSlot(idx, { value_type: e.target.value })}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                    disabled={busy || readOnly}
                  >
                    <option value="string">{t('admin.slots.value_type.string')}</option>
                    <option value="number">{t('admin.slots.value_type.number')}</option>
                    <option value="choice">{t('admin.slots.value_type.choice')}</option>
                  </select>
                </Field>

                <div className="lg:col-span-2">
                  <Field label={t('admin.slots.field.description')}>
                    <input
                      value={slot.description ?? ''}
                      onChange={(e) => updateSlot(idx, { description: e.target.value })}
                      className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                      disabled={busy || readOnly}
                    />
                  </Field>
                </div>

                <Field label={t('admin.slots.field.prompt_en')}>
                  <input
                    value={(slot.prompt as string) ?? ''}
                    onChange={(e) => updateSlot(idx, { prompt: e.target.value })}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                    disabled={busy || readOnly}
                  />
                </Field>
                <Field label={t('admin.slots.field.prompt_zh')}>
                  <input
                    value={(slot.prompt_zh as string) ?? ''}
                    onChange={(e) => updateSlot(idx, { prompt_zh: e.target.value })}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                    disabled={busy || readOnly}
                  />
                </Field>

                <div className="flex items-center gap-3 lg:col-span-2">
                  <label className="inline-flex items-center gap-2 text-sm text-slate-700">
                    <input
                      type="checkbox"
                      checked={Boolean(slot.required)}
                      onChange={(e) => updateSlot(idx, { required: e.target.checked })}
                      disabled={busy || readOnly}
                    />
                    {t('admin.slots.required')}
                  </label>
                </div>

                {slot.value_type === 'choice' ? (
                  <div className="lg:col-span-2">
                    <Field label={t('admin.slots.field.choices')}>
                      <input
                        value={Array.isArray(slot.choices) ? slot.choices.join(', ') : ''}
                        onChange={(e) =>
                          updateSlot(idx, {
                            choices: e.target.value
                              .split(',')
                              .map((c) => c.trim())
                              .filter(Boolean),
                          })
                        }
                        className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                        disabled={busy || readOnly}
                      />
                    </Field>
                  </div>
                ) : null}

                {slot.value_type === 'number' ? (
                  <>
                    <Field label={t('admin.slots.field.min_value')}>
                      <input
                        type="number"
                        value={slot.min_value ?? ''}
                        onChange={(e) => updateSlot(idx, { min_value: e.target.value === '' ? null : Number(e.target.value) })}
                        className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                        disabled={busy || readOnly}
                      />
                    </Field>
                    <Field label={t('admin.slots.field.max_value')}>
                      <input
                        type="number"
                        value={slot.max_value ?? ''}
                        onChange={(e) => updateSlot(idx, { max_value: e.target.value === '' ? null : Number(e.target.value) })}
                        className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                        disabled={busy || readOnly}
                      />
                    </Field>
                  </>
                ) : null}
              </div>
            </div>
          ))}
          {draft.length === 0 && !configQuery.isLoading ? (
            <div className="rounded-2xl border border-dashed border-slate-200 bg-white px-4 py-10 text-center text-sm text-slate-500">
              No slots configured.
            </div>
          ) : null}
        </div>

        {status ? (
          <p className={`mt-4 text-sm ${status.tone === 'error' ? 'text-rose-600' : 'text-slate-600'}`}>{status.message}</p>
        ) : null}
      </section>
    </div>
  )

  function updateSlot(index: number, patch: Partial<AdminSlotConfigPayload>) {
    setDraft((prev) => prev.map((s, i) => (i === index ? { ...s, ...patch } : s)))
  }
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block text-sm text-slate-700">
      <span className="text-xs uppercase tracking-wide text-slate-500">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  )
}

