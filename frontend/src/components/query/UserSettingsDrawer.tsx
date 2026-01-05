import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  authLogout,
  authMe,
  changePassword,
  clearAccessToken,
  getAccessToken,
  updateResetQuestion,
} from '../../services/apiClient'
import { DEFAULT_USER_PREFERENCES, exportConversationHistory, type UserPreferences } from '../../services/userPreferences'

const AVATAR_COLOR_PRESETS = ['#0f172a', '#2563eb', '#0f766e', '#f97316', '#9333ea', '#ea580c']

interface UserSettingsDrawerProps {
  isOpen: boolean
  onClose: () => void
  onSave: (next: UserPreferences) => void | Promise<void>
  onReset: () => void
  preferences: UserPreferences
  hasCustomizations: boolean
}

const resolveErrorMessage = (error: unknown, fallback: string) => {
  if (typeof error === 'object' && error && 'response' in error) {
    const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
    if (typeof detail === 'string' && detail.trim()) {
      return detail
    }
  }
  if (error instanceof Error && error.message) {
    return error.message
  }
  return fallback
}

export function UserSettingsDrawer({
  isOpen,
  onClose,
  onSave,
  onReset,
  preferences,
  hasCustomizations,
}: UserSettingsDrawerProps) {
  const { t } = useTranslation()
  const [formState, setFormState] = useState<UserPreferences>(preferences)
  const [token, setToken] = useState<string | null>(() => getAccessToken())
  const [logoutError, setLogoutError] = useState<string | null>(null)
  const [exportError, setExportError] = useState<string | null>(null)
  const [isExporting, setIsExporting] = useState(false)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [changePasswordError, setChangePasswordError] = useState<string | null>(null)
  const [changePasswordStatus, setChangePasswordStatus] = useState<string | null>(null)
  const [isChangingPassword, setIsChangingPassword] = useState(false)
  const [resetQuestion, setResetQuestion] = useState('')
  const [resetAnswer, setResetAnswer] = useState('')
  const [resetUpdateError, setResetUpdateError] = useState<string | null>(null)
  const [resetUpdateStatus, setResetUpdateStatus] = useState<string | null>(null)
  const [isUpdatingReset, setIsUpdatingReset] = useState(false)
  const retentionOptions = useMemo(() => [30, 60, 90], [])
  const isDirty = useMemo(() => JSON.stringify(formState) !== JSON.stringify(preferences), [formState, preferences])

  useEffect(() => {
    if (!isOpen) return
    setToken(getAccessToken())
    setLogoutError(null)
    setExportError(null)
    setChangePasswordError(null)
    setChangePasswordStatus(null)
    setResetUpdateError(null)
    setResetUpdateStatus(null)
  }, [isOpen])

  useEffect(() => {
    setFormState(preferences)
  }, [preferences])

  const authQuery = useQuery({
    queryKey: ['authMe'],
    queryFn: authMe,
    enabled: Boolean(token) && isOpen,
    retry: false,
    staleTime: 1000 * 60,
  })

  const roleLabel = useMemo(() => {
    if (authQuery.isLoading) return t('auth.checking_permissions')
    const role = authQuery.data?.role
    if (!role) return t('settings.role.unknown')
    return t(`settings.role.${role}`)
  }, [authQuery.data?.role, authQuery.isLoading, t])
  const canAdjustRetrieval = authQuery.data?.role === 'admin'

  const handleSubmit: React.FormEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault()
    await onSave(sanitizePreferences(formState))
  }

  const handleExport = async () => {
    setExportError(null)
    setIsExporting(true)
    try {
      const payload = await exportConversationHistory()
      if (typeof window === 'undefined') return
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `rag-conversations-${new Date().toISOString().split('T')[0]}.json`
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setExportError(err instanceof Error ? err.message : t('settings.export_failed'))
    } finally {
      setIsExporting(false)
    }
  }

  const handleLogout = async () => {
    setLogoutError(null)
    try {
      if (token) {
        await authLogout()
      }
    } catch (err) {
      setLogoutError(err instanceof Error ? err.message : t('settings.sign_out_failed'))
    } finally {
      clearAccessToken()
      setToken(null)
      onClose()
    }
  }

  const handleChangePassword = async () => {
    setChangePasswordError(null)
    setChangePasswordStatus(null)
    const current = currentPassword.trim()
    const nextPassword = newPassword.trim()
    if (!current) {
      setChangePasswordError(t('auth.current_password_required'))
      return
    }
    if (!nextPassword) {
      setChangePasswordError(t('auth.new_password_required'))
      return
    }
    setIsChangingPassword(true)
    try {
      await changePassword({ current_password: current, new_password: nextPassword })
      setChangePasswordStatus(t('auth.change_password_success'))
      setCurrentPassword('')
      setNewPassword('')
    } catch (err) {
      setChangePasswordError(resolveErrorMessage(err, t('auth.change_password_failed')))
    } finally {
      setIsChangingPassword(false)
    }
  }

  const handleUpdateResetQuestion = async () => {
    setResetUpdateError(null)
    setResetUpdateStatus(null)
    const question = resetQuestion.trim()
    const answer = resetAnswer.trim()
    if (!question) {
      setResetUpdateError(t('auth.reset_question_required'))
      return
    }
    if (!answer) {
      setResetUpdateError(t('auth.reset_answer_required'))
      return
    }
    setIsUpdatingReset(true)
    try {
      await updateResetQuestion({ reset_question: question, reset_answer: answer })
      setResetUpdateStatus(t('auth.reset_question_updated'))
      setResetAnswer('')
    } catch (err) {
      setResetUpdateError(resolveErrorMessage(err, t('auth.reset_question_update_failed')))
    } finally {
      setIsUpdatingReset(false)
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
            <p className="text-base font-semibold text-slate-900">{t('settings.title')}</p>
            <p className="text-sm text-slate-500">{t('settings.subtitle')}</p>
            {hasCustomizations ? <p className="text-xs font-medium text-amber-600">{t('settings.custom_defaults_active')}</p> : null}
          </div>
          <button type="button" className="text-sm font-medium text-brand-primary" onClick={onClose}>
            {t('common.close')}
          </button>
        </header>
        <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col">
          <div className="flex-1 space-y-6 overflow-y-auto px-6 py-6">
            <section>
              <h3 className="text-sm font-semibold text-slate-900">{t('settings.profile')}</h3>
              <div className="mt-4 space-y-4">
                <label className="block text-sm text-slate-600">
                  <span className="text-xs uppercase tracking-wide text-slate-500">{t('settings.display_name')}</span>
                  <input
                    type="text"
                    value={formState.displayName}
                    onChange={(event) => setFormState((prev) => ({ ...prev, displayName: event.target.value }))}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-primary focus:outline-none focus:ring-2 focus:ring-brand-primary/40"
                  />
                </label>
                <label className="block text-sm text-slate-600">
                  <span className="text-xs uppercase tracking-wide text-slate-500">{t('settings.email_optional')}</span>
                  <input
                    type="email"
                    value={formState.email ?? ''}
                    onChange={(event) => setFormState((prev) => ({ ...prev, email: event.target.value }))}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-primary focus:outline-none focus:ring-2 focus:ring-brand-primary/40"
                  />
                </label>
                <div className="text-sm text-slate-600">
                  <span className="text-xs uppercase tracking-wide text-slate-500">{t('settings.avatar_accent')}</span>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {AVATAR_COLOR_PRESETS.map((color) => {
                      const isSelected = formState.avatarColor === color
                      return (
                        <button
                          type="button"
                          key={color}
                          aria-label={t('settings.avatar_use_color', { color })}
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
                      {t('settings.avatar_custom')}
                      <input
                        type="color"
                        value={formState.avatarColor}
                        onChange={(event) => setFormState((prev) => ({ ...prev, avatarColor: event.target.value }))}
                        className="h-7 w-12 cursor-pointer border-0 bg-transparent p-0"
                        aria-label={t('settings.avatar_pick_color')}
                      />
                    </label>
                  </div>
                </div>
              </div>
            </section>

            <section>
              <h3 className="text-sm font-semibold text-slate-900">{t('settings.defaults')}</h3>
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <label className="text-sm text-slate-600">
                  <span className="text-xs uppercase tracking-wide text-slate-500">{t('settings.preferred_language')}</span>
                  <select
                    value={formState.preferredLanguage}
                    onChange={(event) =>
                      setFormState((prev) => ({ ...prev, preferredLanguage: event.target.value as UserPreferences['preferredLanguage'] }))
                    }
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-primary focus:outline-none focus:ring-2 focus:ring-brand-primary/40"
                  >
                    <option value="auto">{t('settings.language.auto')}</option>
                    <option value="en">{t('settings.language.en')}</option>
                    <option value="zh">{t('settings.language.zh')}</option>
                  </select>
                </label>
                <label className="text-sm text-slate-600">
                  <span className="text-xs uppercase tracking-wide text-slate-500">{t('settings.explain_like_new')}</span>
                  <select
                    value={formState.explainLikeNewDefault ? 'yes' : 'no'}
                    onChange={(event) => setFormState((prev) => ({ ...prev, explainLikeNewDefault: event.target.value === 'yes' }))}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-primary focus:outline-none focus:ring-2 focus:ring-brand-primary/40"
                  >
                    <option value="no">{t('settings.explain.off')}</option>
                    <option value="yes">{t('settings.explain.on')}</option>
                  </select>
                </label>
                {canAdjustRetrieval ? (
                  <label className="text-sm text-slate-600">
                    <span className="text-xs uppercase tracking-wide text-slate-500">{t('settings.top_k')}</span>
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
                ) : null}
                {canAdjustRetrieval ? (
                  <label className="text-sm text-slate-600">
                    <span className="text-xs uppercase tracking-wide text-slate-500">{t('settings.citations')}</span>
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
                ) : null}
              </div>
            </section>

            <section>
              <h3 className="text-sm font-semibold text-slate-900">{t('settings.data_controls')}</h3>
              <div className="mt-4 space-y-4">
                <label className="text-sm text-slate-600">
                  <span className="text-xs uppercase tracking-wide text-slate-500">{t('settings.retention_window')}</span>
                  <select
                    value={formState.retentionDays}
                    onChange={(event) => setFormState((prev) => ({ ...prev, retentionDays: Number(event.target.value) as 30 | 60 | 90 }))}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-primary focus:outline-none focus:ring-2 focus:ring-brand-primary/40"
                  >
                    {retentionOptions.map((days) => (
                      <option key={days} value={days}>
                        {t('settings.retention_days', { count: days })}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="text-sm text-slate-600">
                  <span className="text-xs uppercase tracking-wide text-slate-500">{t('settings.theme')}</span>
                  <select
                    value={formState.theme}
                    onChange={(event) => setFormState((prev) => ({ ...prev, theme: event.target.value as UserPreferences['theme'] }))}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-primary focus:outline-none focus:ring-2 focus:ring-brand-primary/40"
                  >
                    <option value="light">{t('settings.theme.light')}</option>
                    <option value="high-contrast">{t('settings.theme.high_contrast')}</option>
                  </select>
                </label>
                <button
                  type="button"
                  onClick={() => void handleExport()}
                  className="inline-flex items-center justify-center rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:border-brand-primary/70 hover:text-brand-primary"
                  disabled={isExporting}
                >
                  {t('settings.export_conversations')}
                </button>
                <p className="text-xs text-slate-500">{t('settings.export_help')}</p>
                {exportError ? <p className="text-xs text-rose-600">{exportError}</p> : null}
              </div>
            </section>

            {token ? (
              <section>
                <h3 className="text-sm font-semibold text-slate-900">{t('settings.account')}</h3>
                <div className="mt-4 space-y-3">
                  <div className="text-sm text-slate-600">
                    <span className="text-xs uppercase tracking-wide text-slate-500">{t('settings.role')}</span>
                    <p className="mt-1 text-sm font-semibold text-slate-900">{roleLabel}</p>
                  </div>
                  <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
                    <p className="text-sm font-semibold text-slate-900">{t('auth.change_password_title')}</p>
                    <div className="mt-3 space-y-3">
                      <div>
                        <label className="text-xs font-semibold uppercase tracking-wide text-slate-500" htmlFor="current-password">
                          {t('auth.current_password_label')}
                        </label>
                        <input
                          id="current-password"
                          type="password"
                          className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-slate-300 focus:ring-2 focus:ring-slate-100"
                          value={currentPassword}
                          onChange={(event) => setCurrentPassword(event.target.value)}
                          placeholder={t('auth.current_password_placeholder')}
                        />
                      </div>
                      <div>
                        <label className="text-xs font-semibold uppercase tracking-wide text-slate-500" htmlFor="new-password">
                          {t('auth.new_password_label')}
                        </label>
                        <input
                          id="new-password"
                          type="password"
                          className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-slate-300 focus:ring-2 focus:ring-slate-100"
                          value={newPassword}
                          onChange={(event) => setNewPassword(event.target.value)}
                          placeholder={t('auth.password_placeholder')}
                        />
                      </div>
                      <button
                        type="button"
                        className="btn btn-primary w-full"
                        onClick={() => void handleChangePassword()}
                        disabled={isChangingPassword}
                      >
                        {t('auth.change_password')}
                      </button>
                      {changePasswordError ? (
                        <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{changePasswordError}</p>
                      ) : null}
                      {changePasswordStatus ? (
                        <p className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{changePasswordStatus}</p>
                      ) : null}
                    </div>
                  </div>
                  <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
                    <p className="text-sm font-semibold text-slate-900">{t('auth.reset_question_title')}</p>
                    <p className="mt-1 text-xs text-slate-500">{t('auth.reset_question_help')}</p>
                    <div className="mt-3 space-y-3">
                      <div>
                        <label className="text-xs font-semibold uppercase tracking-wide text-slate-500" htmlFor="reset-question">
                          {t('auth.reset_question_label')}
                        </label>
                        <input
                          id="reset-question"
                          type="text"
                          className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-slate-300 focus:ring-2 focus:ring-slate-100"
                          value={resetQuestion}
                          onChange={(event) => setResetQuestion(event.target.value)}
                          placeholder={t('auth.reset_question_placeholder')}
                        />
                      </div>
                      <div>
                        <label className="text-xs font-semibold uppercase tracking-wide text-slate-500" htmlFor="reset-answer">
                          {t('auth.reset_answer_label')}
                        </label>
                        <input
                          id="reset-answer"
                          type="text"
                          className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-slate-300 focus:ring-2 focus:ring-slate-100"
                          value={resetAnswer}
                          onChange={(event) => setResetAnswer(event.target.value)}
                          placeholder={t('auth.reset_answer_placeholder')}
                        />
                      </div>
                      <button
                        type="button"
                        className="btn btn-secondary w-full"
                        onClick={() => void handleUpdateResetQuestion()}
                        disabled={isUpdatingReset}
                      >
                        {t('auth.reset_question_update')}
                      </button>
                      {resetUpdateError ? (
                        <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{resetUpdateError}</p>
                      ) : null}
                      {resetUpdateStatus ? (
                        <p className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{resetUpdateStatus}</p>
                      ) : null}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleLogout()}
                    className="inline-flex items-center justify-center rounded-lg border border-rose-200 px-4 py-2 text-sm font-medium text-rose-700 hover:border-rose-300"
                  >
                    {t('settings.sign_out')}
                  </button>
                  {logoutError ? <p className="text-xs text-rose-600">{logoutError}</p> : null}
                </div>
              </section>
            ) : null}
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
              {t('settings.reset_to_defaults')}
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
                disabled={!isDirty}
              >
                {t('settings.save_changes')}
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
  preferredLanguage: (['auto', 'en', 'zh'] as const).includes(prefs.preferredLanguage as 'auto' | 'en' | 'zh')
    ? prefs.preferredLanguage
    : DEFAULT_USER_PREFERENCES.preferredLanguage,
  explainLikeNewDefault: Boolean(prefs.explainLikeNewDefault),
  defaultTopK: clampNumber(prefs.defaultTopK, 1, 20, DEFAULT_USER_PREFERENCES.defaultTopK),
  defaultKCite: clampNumber(prefs.defaultKCite, 1, 10, DEFAULT_USER_PREFERENCES.defaultKCite),
  retentionDays: ([30, 60, 90].includes(prefs.retentionDays) ? prefs.retentionDays : DEFAULT_USER_PREFERENCES.retentionDays) as 30 | 60 | 90,
  theme: prefs.theme === 'high-contrast' ? 'high-contrast' : 'light',
})
