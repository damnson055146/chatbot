import { useEffect, useMemo, useState } from 'react'
import { DEFAULT_USER_PREFERENCES, exportConversationHistory, type UserPreferences } from '../../services/userPreferences'

const AVATAR_COLOR_PRESETS = ['#0f172a', '#2563eb', '#0f766e', '#f97316', '#9333ea', '#ea580c']

interface UserSettingsDrawerProps {
  isOpen: boolean
  onClose: () => void
  onSave: (next: UserPreferences) => void
  onReset: () => void
  preferences: UserPreferences
  hasCustomizations: boolean
}

export function UserSettingsDrawer({
  isOpen,
  onClose,
  onSave,
  onReset,
  preferences,
  hasCustomizations,
}: UserSettingsDrawerProps) {
  const [formState, setFormState] = useState<UserPreferences>(preferences)
  const retentionOptions = useMemo(() => [30, 60, 90], [])
  const isDirty = useMemo(() => JSON.stringify(formState) !== JSON.stringify(preferences), [formState, preferences])

  useEffect(() => {
    setFormState(preferences)
  }, [preferences])

  const handleSubmit: React.FormEventHandler<HTMLFormElement> = (event) => {
    event.preventDefault()
    onSave(sanitizePreferences(formState))
  }

  const handleExport = () => {
    const payload = exportConversationHistory()
    if (typeof window === 'undefined') return
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `rag-conversations-${new Date().toISOString().split('T')[0]}.json`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className={`fixed inset-0 z-50 transition ${isOpen ? 'pointer-events-auto' : 'pointer-events-none'}`}>
      <div className={`absolute inset-0 bg-slate-900/40 transition-opacity ${isOpen ? 'opacity-100' : 'opacity-0'}`} onClick={onClose} />
      <aside
        className={`absolute right-0 top-0 h-full w-full max-w-md transform bg-white shadow-2xl transition-transform duration-200 ${
          isOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <header className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <div>
            <p className="text-base font-semibold text-slate-900">User settings</p>
            <p className="text-sm text-slate-500">Control defaults and export your conversation history.</p>
            {hasCustomizations ? <p className="text-xs font-medium text-amber-600">Custom defaults active</p> : null}
          </div>
          <button type="button" className="text-sm font-medium text-brand-primary" onClick={onClose}>
            Close
          </button>
        </header>
        <form onSubmit={handleSubmit} className="flex h-[calc(100%-64px)] flex-col">
          <div className="flex-1 space-y-6 overflow-y-auto px-6 py-6">
            <section>
              <h3 className="text-sm font-semibold text-slate-900">Profile</h3>
              <div className="mt-4 space-y-4">
                <label className="block text-sm text-slate-600">
                  <span className="text-xs uppercase tracking-wide text-slate-500">Display name</span>
                  <input
                    type="text"
                    value={formState.displayName}
                    onChange={(event) => setFormState((prev) => ({ ...prev, displayName: event.target.value }))}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-primary focus:outline-none focus:ring-2 focus:ring-brand-primary/40"
                  />
                </label>
                <label className="block text-sm text-slate-600">
                  <span className="text-xs uppercase tracking-wide text-slate-500">Email (optional)</span>
                  <input
                    type="email"
                    value={formState.email ?? ''}
                    onChange={(event) => setFormState((prev) => ({ ...prev, email: event.target.value }))}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-primary focus:outline-none focus:ring-2 focus:ring-brand-primary/40"
                  />
                </label>
                <div className="text-sm text-slate-600">
                  <span className="text-xs uppercase tracking-wide text-slate-500">Avatar accent</span>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {AVATAR_COLOR_PRESETS.map((color) => {
                      const isSelected = formState.avatarColor === color
                      return (
                        <button
                          type="button"
                          key={color}
                          aria-label={`Use avatar color ${color}`}
                          aria-pressed={isSelected}
                          className={`flex h-10 w-10 items-center justify-center rounded-full border-2 transition ${
                            isSelected ? 'border-slate-900' : 'border-transparent hover:border-slate-300'
                          }`}
                          style={{ backgroundColor: color }}
                          onClick={() => setFormState((prev) => ({ ...prev, avatarColor: color }))}
                        >
                          {isSelected ? (
                            <svg viewBox="0 0 20 20" className="h-5 w-5 text-white" fill="none" stroke="currentColor" strokeWidth="2.2">
                              <path d="m5 10 3 3 7-7" strokeLinecap="round" strokeLinejoin="round" />
                            </svg>
                          ) : null}
                        </button>
                      )
                    })}
                    <label className="flex items-center gap-2 rounded-full border border-dashed border-slate-300 px-3 py-1 text-xs font-medium text-slate-600">
                      Custom
                      <input
                        type="color"
                        value={formState.avatarColor}
                        onChange={(event) => setFormState((prev) => ({ ...prev, avatarColor: event.target.value }))}
                        className="h-7 w-12 cursor-pointer border-0 bg-transparent p-0"
                        aria-label="Pick a custom avatar color"
                      />
                    </label>
                  </div>
                </div>
              </div>
            </section>

            <section>
              <h3 className="text-sm font-semibold text-slate-900">Defaults</h3>
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <label className="text-sm text-slate-600">
                  <span className="text-xs uppercase tracking-wide text-slate-500">Preferred language</span>
                  <select
                    value={formState.preferredLanguage}
                    onChange={(event) =>
                      setFormState((prev) => ({ ...prev, preferredLanguage: event.target.value as UserPreferences['preferredLanguage'] }))
                    }
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-primary focus:outline-none focus:ring-2 focus:ring-brand-primary/40"
                  >
                    <option value="auto">Auto detect</option>
                    <option value="en">English</option>
                    <option value="zh">Chinese</option>
                  </select>
                </label>
                <label className="text-sm text-slate-600">
                  <span className="text-xs uppercase tracking-wide text-slate-500">Explain like new</span>
                  <select
                    value={formState.explainLikeNewDefault ? 'yes' : 'no'}
                    onChange={(event) => setFormState((prev) => ({ ...prev, explainLikeNewDefault: event.target.value === 'yes' }))}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-primary focus:outline-none focus:ring-2 focus:ring-brand-primary/40"
                  >
                    <option value="no">Off by default</option>
                    <option value="yes">On by default</option>
                  </select>
                </label>
                <label className="text-sm text-slate-600">
                  <span className="text-xs uppercase tracking-wide text-slate-500">Top K</span>
                  <input
                    type="number"
                    min={1}
                    max={20}
                    value={formState.defaultTopK}
                    onChange={(event) =>
                      setFormState((prev) => ({ ...prev, defaultTopK: Number(event.target.value) || prev.defaultTopK }))
                    }
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-primary focus:outline-none focus:ring-2 focus:ring-brand-primary/40"
                  />
                </label>
                <label className="text-sm text-slate-600">
                  <span className="text-xs uppercase tracking-wide text-slate-500">Citations</span>
                  <input
                    type="number"
                    min={1}
                    max={10}
                    value={formState.defaultKCite}
                    onChange={(event) =>
                      setFormState((prev) => ({ ...prev, defaultKCite: Number(event.target.value) || prev.defaultKCite }))
                    }
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-primary focus:outline-none focus:ring-2 focus:ring-brand-primary/40"
                  />
                </label>
              </div>
            </section>

            <section>
              <h3 className="text-sm font-semibold text-slate-900">Data controls</h3>
              <div className="mt-4 space-y-4">
                <label className="text-sm text-slate-600">
                  <span className="text-xs uppercase tracking-wide text-slate-500">Retention window</span>
                  <select
                    value={formState.retentionDays}
                    onChange={(event) => setFormState((prev) => ({ ...prev, retentionDays: Number(event.target.value) as 30 | 60 | 90 }))}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-primary focus:outline-none focus:ring-2 focus:ring-brand-primary/40"
                  >
                    {retentionOptions.map((days) => (
                      <option key={days} value={days}>
                        {days} days
                      </option>
                    ))}
                  </select>
                </label>
                <label className="text-sm text-slate-600">
                  <span className="text-xs uppercase tracking-wide text-slate-500">Theme</span>
                  <select
                    value={formState.theme}
                    onChange={(event) => setFormState((prev) => ({ ...prev, theme: event.target.value as UserPreferences['theme'] }))}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-primary focus:outline-none focus:ring-2 focus:ring-brand-primary/40"
                  >
                    <option value="light">Default</option>
                    <option value="high-contrast">High contrast</option>
                  </select>
                </label>
                <button
                  type="button"
                  onClick={handleExport}
                  className="inline-flex items-center justify-center rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:border-brand-primary/70 hover:text-brand-primary"
                >
                  Export conversations (JSON)
                </button>
                <p className="text-xs text-slate-500">
                  Conversations are exported from your browser storage. Server-side exports will be added when the backend endpoint is available.
                </p>
              </div>
            </section>
          </div>
          <footer className="flex items-center justify-between border-t border-slate-200 px-6 py-4">
            <button
              type="button"
              className="text-sm font-medium text-slate-500 hover:text-brand-primary"
              onClick={() => {
                onReset()
                setFormState({ ...DEFAULT_USER_PREFERENCES })
              }}
            >
              Reset to defaults
            </button>
            <div className="flex gap-3">
              <button
                type="button"
                className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-600 hover:border-brand-primary/70 hover:text-brand-primary"
                onClick={onClose}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="rounded-lg bg-brand-primary px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-brand-primary/90 disabled:opacity-50"
                disabled={!isDirty}
              >
                Save changes
              </button>
            </div>
          </footer>
        </form>
      </aside>
    </div>
  )
}

const clampNumber = (value: number, min: number, max: number, fallback: number) => {
  if (Number.isNaN(value)) return fallback
  return Math.min(Math.max(value, min), max)
}

const sanitizePreferences = (prefs: UserPreferences): UserPreferences => ({
  displayName: prefs.displayName.trim() || DEFAULT_USER_PREFERENCES.displayName,
  email: prefs.email?.trim() || undefined,
  avatarColor: prefs.avatarColor || DEFAULT_USER_PREFERENCES.avatarColor,
  preferredLanguage: prefs.preferredLanguage,
  explainLikeNewDefault: Boolean(prefs.explainLikeNewDefault),
  defaultTopK: clampNumber(prefs.defaultTopK, 1, 20, DEFAULT_USER_PREFERENCES.defaultTopK),
  defaultKCite: clampNumber(prefs.defaultKCite, 1, 10, DEFAULT_USER_PREFERENCES.defaultKCite),
  retentionDays: ([30, 60, 90].includes(prefs.retentionDays) ? prefs.retentionDays : DEFAULT_USER_PREFERENCES.retentionDays) as 30 | 60 | 90,
  theme: prefs.theme === 'high-contrast' ? 'high-contrast' : 'light',
})
