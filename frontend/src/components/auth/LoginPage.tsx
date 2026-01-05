import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { authLogin, fetchResetQuestion, isAdminRole, resetPassword, setAccessToken } from '../../services/apiClient'
import { LanguageSwitcher } from '../layout/LanguageSwitcher'

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

export function LoginPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showReset, setShowReset] = useState(false)
  const [resetUsername, setResetUsername] = useState('')
  const [resetQuestion, setResetQuestion] = useState<string | null>(null)
  const [resetAnswer, setResetAnswer] = useState('')
  const [resetNewPassword, setResetNewPassword] = useState('')
  const [resetError, setResetError] = useState<string | null>(null)
  const [resetStatus, setResetStatus] = useState<string | null>(null)
  const [isResetting, setIsResetting] = useState(false)

  const next = searchParams.get('next') ?? ''

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setIsSubmitting(true)
    setError(null)
    try {
      const trimmedUsername = username.trim()
      const trimmedPassword = password.trim()
      if (!trimmedUsername) {
        setError(t('auth.username_required'))
        return
      }
      if (!trimmedPassword) {
        setError(t('auth.password_required'))
        return
      }
      const result = await authLogin(trimmedUsername, trimmedPassword)
      setAccessToken(result.access_token)
      if (next) {
        navigate(next, { replace: true })
        return
      }
      navigate(isAdminRole(result.role) ? '/admin' : '/', { replace: true })
    } catch (err) {
      setError(resolveErrorMessage(err, t('auth.login_failed')))
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleFetchQuestion = async () => {
    setResetError(null)
    setResetStatus(null)
    const trimmed = resetUsername.trim()
    if (!trimmed) {
      setResetError(t('auth.username_required'))
      return
    }
    setIsResetting(true)
    try {
      const result = await fetchResetQuestion(trimmed)
      setResetQuestion(result.reset_question)
    } catch (err) {
      setResetError(resolveErrorMessage(err, t('auth.reset_question_failed')))
      setResetQuestion(null)
    } finally {
      setIsResetting(false)
    }
  }

  const handleResetPassword = async () => {
    setResetError(null)
    setResetStatus(null)
    const trimmed = resetUsername.trim()
    const answer = resetAnswer.trim()
    const nextPassword = resetNewPassword.trim()
    if (!trimmed) {
      setResetError(t('auth.username_required'))
      return
    }
    if (!answer) {
      setResetError(t('auth.reset_answer_required'))
      return
    }
    if (!nextPassword) {
      setResetError(t('auth.password_required'))
      return
    }
    setIsResetting(true)
    try {
      await resetPassword({ username: trimmed, reset_answer: answer, new_password: nextPassword })
      setResetStatus(t('auth.reset_password_success'))
      setResetAnswer('')
      setResetNewPassword('')
      setUsername(trimmed)
    } catch (err) {
      setResetError(resolveErrorMessage(err, t('auth.reset_password_failed')))
    } finally {
      setIsResetting(false)
    }
  }

  return (
    <div className="relative mx-auto flex w-full max-w-md flex-col px-6 py-14">
      <div className="absolute right-6 top-6">
        <LanguageSwitcher />
      </div>
      <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="text-xl font-semibold text-slate-900">{t('auth.sign_in')}</h1>
        <p className="mt-1 text-sm text-slate-500">{t('auth.password_optional_help')}</p>

        <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
          <div>
            <label className="text-xs font-semibold uppercase tracking-wide text-slate-500" htmlFor="username">
              {t('auth.username_label')}
            </label>
            <input
              id="username"
              type="text"
              autoComplete="username"
              className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-slate-300 focus:ring-2 focus:ring-slate-100"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder={t('auth.username_placeholder')}
            />
          </div>
          <div>
            <label className="text-xs font-semibold uppercase tracking-wide text-slate-500" htmlFor="password">
              {t('auth.password_label')}
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-slate-300 focus:ring-2 focus:ring-slate-100"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder={t('auth.password_placeholder')}
            />
          </div>

          {error ? <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p> : null}

          <button type="submit" className="btn btn-primary w-full" disabled={isSubmitting}>
            {isSubmitting ? t('auth.signing_in') : t('auth.continue')}
          </button>

          <button
            type="button"
            className="btn btn-secondary w-full"
            onClick={() => navigate(`/register${next ? `?next=${encodeURIComponent(next)}` : ''}`, { replace: true })}
          >
            {t('auth.sign_up')}
          </button>

          <button
            type="button"
            className="btn btn-ghost w-full"
            onClick={() => {
              setShowReset((prev) => !prev)
              setResetError(null)
              setResetStatus(null)
            }}
          >
            {t('auth.forgot_password')}
          </button>

        </form>
        {showReset ? (
          <div className="mt-6 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
            <p className="text-sm font-semibold text-slate-900">{t('auth.reset_password_title')}</p>
            <p className="mt-1 text-xs text-slate-500">{t('auth.reset_password_help')}</p>
            <div className="mt-4 space-y-3">
              <div>
                <label className="text-xs font-semibold uppercase tracking-wide text-slate-500" htmlFor="reset-username">
                  {t('auth.username_label')}
                </label>
                <input
                  id="reset-username"
                  type="text"
                  className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-slate-300 focus:ring-2 focus:ring-slate-100"
                  value={resetUsername}
                  onChange={(event) => setResetUsername(event.target.value)}
                  placeholder={t('auth.username_placeholder')}
                />
              </div>
              <button
                type="button"
                className="btn btn-secondary w-full"
                onClick={() => void handleFetchQuestion()}
                disabled={isResetting}
              >
                {t('auth.fetch_reset_question')}
              </button>
              {resetQuestion ? (
                <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700">
                  {resetQuestion}
                </div>
              ) : null}
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
              <div>
                <label className="text-xs font-semibold uppercase tracking-wide text-slate-500" htmlFor="reset-new-password">
                  {t('auth.new_password_label')}
                </label>
                <input
                  id="reset-new-password"
                  type="password"
                  className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-slate-300 focus:ring-2 focus:ring-slate-100"
                  value={resetNewPassword}
                  onChange={(event) => setResetNewPassword(event.target.value)}
                  placeholder={t('auth.password_placeholder')}
                />
              </div>
              <button type="button" className="btn btn-primary w-full" onClick={() => void handleResetPassword()} disabled={isResetting}>
                {t('auth.reset_password')}
              </button>
              {resetError ? (
                <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{resetError}</p>
              ) : null}
              {resetStatus ? (
                <p className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{resetStatus}</p>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
