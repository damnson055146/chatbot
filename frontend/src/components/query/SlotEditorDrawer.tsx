import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { SlotDefinitionPayload } from '../../services/apiClient'

interface SlotEditorDrawerProps {
  isOpen: boolean
  onClose: () => void
  onSave: (payload: { slots: Record<string, unknown>; reset_slots: string[] }) => Promise<void>
  sessionId?: string
  slotDefinitions: SlotDefinitionPayload[]
  slots: Record<string, unknown>
  slotErrors: Record<string, string>
}

type SlotFormState = Record<string, string>

const normalizeValue = (value: unknown) => {
  if (value === null || value === undefined) return ''
  return String(value)
}

const slotLabel = (name: string) => {
  if (name === 'target_country') return 'target country/university'
  return name
}

const isEmailSlot = (name: string) => name.toLowerCase().includes('email')
const isValidEmail = (value: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)

const buildInitialState = (
  slotDefinitions: SlotDefinitionPayload[],
  slots: Record<string, unknown>,
  extras: string[],
): SlotFormState => {
  const next: SlotFormState = {}
  for (const slot of slotDefinitions) {
    next[slot.name] = normalizeValue(slots[slot.name])
  }
  for (const name of extras) {
    next[name] = normalizeValue(slots[name])
  }
  return next
}

export function SlotEditorDrawer({
  isOpen,
  onClose,
  onSave,
  sessionId,
  slotDefinitions,
  slots,
  slotErrors,
}: SlotEditorDrawerProps) {
  const { t } = useTranslation()
  const [formState, setFormState] = useState<SlotFormState>({})
  const [baseline, setBaseline] = useState<SlotFormState>({})
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState<{ tone: 'info' | 'error'; message: string } | null>(null)

  const definitionNames = useMemo(() => new Set(slotDefinitions.map((slot) => slot.name)), [slotDefinitions])
  const extraSlotNames = useMemo(() => Object.keys(slots).filter((name) => !definitionNames.has(name)).sort(), [slots, definitionNames])
  const localErrors = useMemo(() => {
    const next: Record<string, string> = {}
    for (const slot of slotDefinitions) {
      const raw = formState[slot.name] ?? ''
      const value = raw.trim()
      const baselineValue = (baseline[slot.name] ?? '').trim()
      if (!value) continue
      if (value === baselineValue) continue
      const valueType = slot.value_type || 'string'
      if (isEmailSlot(slot.name) && !isValidEmail(value)) {
        next[slot.name] = t('query.slots_validation_email')
        continue
      }
      if (valueType === 'number') {
        const parsed = Number(value)
        if (Number.isNaN(parsed)) {
          next[slot.name] = t('query.slots_validation_number')
          continue
        }
        if (slot.min_value !== undefined && slot.min_value !== null && parsed < slot.min_value) {
          next[slot.name] = t('query.slots_validation_min', { min: slot.min_value })
          continue
        }
        if (slot.max_value !== undefined && slot.max_value !== null && parsed > slot.max_value) {
          next[slot.name] = t('query.slots_validation_max', { max: slot.max_value })
          continue
        }
      }
      if (valueType === 'choice' && Array.isArray(slot.choices) && slot.choices.length > 0) {
        if (!slot.choices.includes(value)) {
          next[slot.name] = t('query.slots_validation_choice')
        }
      }
    }
    return next
  }, [baseline, formState, slotDefinitions, t])
  const hasLocalErrors = Object.keys(localErrors).length > 0

  useEffect(() => {
    if (!isOpen) return
    const next = buildInitialState(slotDefinitions, slots, extraSlotNames)
    setBaseline(next)
    setFormState(next)
    setStatus(null)
  }, [isOpen, slotDefinitions, slots, extraSlotNames])

  const isDirty = useMemo(() => JSON.stringify(formState) !== JSON.stringify(baseline), [formState, baseline])

  const handleResetAll = () => {
    const cleared: SlotFormState = {}
    for (const key of Object.keys(formState)) {
      cleared[key] = ''
    }
    setFormState(cleared)
  }

  const handleSubmit: React.FormEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault()
    if (!sessionId) {
      setStatus({ tone: 'error', message: t('query.slots_drawer_no_session') })
      return
    }
    if (hasLocalErrors) {
      setStatus({ tone: 'error', message: t('query.slots_validation_failed') })
      return
    }
    const updates: Record<string, unknown> = {}
    const resetSlots: string[] = []
    for (const [name, value] of Object.entries(formState)) {
      const trimmed = value.trim()
      const before = baseline[name] ?? ''
      if (!trimmed) {
        if (before.trim()) {
          resetSlots.push(name)
        }
        continue
      }
      if (trimmed !== before.trim()) {
        updates[name] = trimmed
      }
    }
    if (Object.keys(updates).length === 0 && resetSlots.length === 0) {
      onClose()
      return
    }
    setBusy(true)
    setStatus(null)
    try {
      await onSave({ slots: updates, reset_slots: resetSlots })
      setStatus({ tone: 'info', message: t('query.slots_updated') })
      onClose()
    } catch (error) {
      setStatus({
        tone: 'error',
        message: error instanceof Error ? error.message : t('query.slots_update_failed'),
      })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={`fixed inset-0 z-50 transition ${isOpen ? 'pointer-events-auto' : 'pointer-events-none'}`}>
      <div className={`absolute inset-0 bg-slate-900/40 transition-opacity ${isOpen ? 'opacity-100' : 'opacity-0'}`} onClick={onClose} />
      <aside
        className={`absolute right-0 top-0 flex h-full w-full max-w-md flex-col transform bg-white shadow-2xl transition-transform duration-200 ${
          isOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <header className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <div>
            <p className="text-base font-semibold text-slate-900">{t('query.slots_drawer_title')}</p>
            <p className="text-sm text-slate-500">{t('query.slots_drawer_subtitle')}</p>
            {sessionId ? <p className="mt-1 text-xs text-slate-400">Session {sessionId.slice(0, 12)}</p> : null}
          </div>
          <button type="button" className="text-sm font-medium text-brand-primary" onClick={onClose}>
            {t('common.close')}
          </button>
        </header>
        <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col">
          <div className="flex-1 space-y-6 overflow-y-auto px-6 py-6">
            {status ? (
              <div
                className={`rounded-2xl border px-4 py-3 text-sm ${
                  status.tone === 'error' ? 'border-rose-200 bg-rose-50 text-rose-700' : 'border-slate-200 bg-slate-50 text-slate-700'
                }`}
              >
                {status.message}
              </div>
            ) : null}
            {!sessionId ? (
              <div className="rounded-2xl border border-dashed border-slate-200 bg-white px-4 py-10 text-center text-sm text-slate-500">
                {t('query.slots_drawer_no_session')}
              </div>
            ) : null}

            {slotDefinitions.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-slate-200 bg-white px-4 py-10 text-center text-sm text-slate-500">
                {t('query.slots_empty')}
              </div>
            ) : (
              <section>
                <h3 className="text-xs font-semibold uppercase tracking-[0.35em] text-slate-400">{t('query.slots_section_defined')}</h3>
                <div className="mt-4 space-y-4">
                  {slotDefinitions.map((slot) => {
                    const valueType = slot.value_type || 'string'
                    const value = formState[slot.name] ?? ''
                    const error = localErrors[slot.name] ?? slotErrors?.[slot.name]
                    const inputType =
                      valueType === 'number' ? 'number' : isEmailSlot(slot.name) ? 'email' : 'text'
                    return (
                      <div key={slot.name} className="rounded-2xl border border-slate-200 bg-white p-4">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="text-sm font-semibold text-slate-900">{slotLabel(slot.name)}</p>
                            <p className="mt-1 text-xs text-slate-500">{slot.description || slot.prompt || ''}</p>
                            {slot.required ? <span className="mt-2 inline-block rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-700">{t('query.slots_required')}</span> : null}
                          </div>
                          <button
                            type="button"
                            className="shrink-0 rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600 hover:border-slate-300"
                            onClick={() => setFormState((prev) => ({ ...prev, [slot.name]: '' }))}
                            disabled={busy}
                          >
                            {t('query.slots_clear')}
                          </button>
                        </div>
                        <div className="mt-3">
                          {valueType === 'choice' && Array.isArray(slot.choices) && slot.choices.length > 0 ? (
                            <select
                              value={value}
                              onChange={(event) => setFormState((prev) => ({ ...prev, [slot.name]: event.target.value }))}
                              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-200"
                              disabled={busy}
                            >
                              <option value="">{t('query.slots_empty_option')}</option>
                              {slot.choices.map((choice) => (
                                <option key={choice} value={choice}>
                                  {choice}
                                </option>
                              ))}
                            </select>
                          ) : (
                            <input
                              type={inputType}
                              value={value}
                              min={valueType === 'number' ? slot.min_value ?? undefined : undefined}
                              max={valueType === 'number' ? slot.max_value ?? undefined : undefined}
                              onChange={(event) => setFormState((prev) => ({ ...prev, [slot.name]: event.target.value }))}
                              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-200"
                              disabled={busy}
                            />
                          )}
                          {error ? <p className="mt-2 text-xs text-rose-600">{error}</p> : null}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </section>
            )}

            {extraSlotNames.length > 0 ? (
              <section>
                <h3 className="text-xs font-semibold uppercase tracking-[0.35em] text-slate-400">{t('query.slots_section_other')}</h3>
                <div className="mt-4 space-y-4">
                  {extraSlotNames.map((name) => (
                    <div key={name} className="rounded-2xl border border-slate-200 bg-white p-4">
                      <div className="flex items-start justify-between gap-3">
                        <p className="text-sm font-semibold text-slate-900">{slotLabel(name)}</p>
                        <button
                          type="button"
                          className="shrink-0 rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600 hover:border-slate-300"
                          onClick={() => setFormState((prev) => ({ ...prev, [name]: '' }))}
                          disabled={busy}
                        >
                          {t('query.slots_clear')}
                        </button>
                      </div>
                      <div className="mt-3">
                        <input
                          type="text"
                          value={formState[name] ?? ''}
                          onChange={(event) => setFormState((prev) => ({ ...prev, [name]: event.target.value }))}
                          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-200"
                          disabled={busy}
                        />
                        {slotErrors?.[name] ? <p className="mt-2 text-xs text-rose-600">{slotErrors[name]}</p> : null}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            ) : null}
          </div>
          <footer className="flex items-center justify-between border-t border-slate-200 px-6 py-4">
            <button
              type="button"
              className="text-sm font-medium text-slate-500 hover:text-brand-primary"
              onClick={handleResetAll}
              disabled={busy || !sessionId}
            >
              {t('query.slots_reset_all')}
            </button>
            <div className="flex gap-3">
              <button
                type="button"
                className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-600 hover:border-brand-primary/70 hover:text-brand-primary"
                onClick={onClose}
              >
                {t('common.cancel')}
              </button>
              <button
                type="submit"
                className="rounded-lg bg-brand-primary px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-brand-primary/90 disabled:opacity-50"
                disabled={!isDirty || busy || !sessionId || hasLocalErrors}
              >
                {t('common.save')}
              </button>
            </div>
          </footer>
        </form>
      </aside>
    </div>
  )
}
