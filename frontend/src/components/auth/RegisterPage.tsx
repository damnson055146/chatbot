import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { authLogin, authRegister, setAccessToken } from '../../services/apiClient'
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

export function RegisterPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [resetQuestion, setResetQuestion] = useState('')
  const [resetAnswer, setResetAnswer] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const next = searchParams.get('next') ?? ''

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setIsSubmitting(true)
    setError(null)
    try {
      const trimmedUsername = username.trim()
      const trimmedPassword = password.trim()
      const trimmedConfirm = confirmPassword.trim()
      const trimmedQuestion = resetQuestion.trim()
      const trimmedAnswer = resetAnswer.trim()
      if (!trimmedUsername) {
        setError(t('auth.username_required'))
        return
      }
      if (!trimmedPassword) {
        setError(t('auth.password_required'))
        return
      }
      if (trimmedPassword !== trimmedConfirm) {
        setError(t('auth.password_mismatch'))
        return
      }
      if (!trimmedQuestion) {
        setError(t('auth.reset_question_required'))
        return
      }
      if (!trimmedAnswer) {
        setError(t('auth.reset_answer_required'))
        return
      }
      await authRegister(trimmedUsername, trimmedPassword, trimmedQuestion, trimmedAnswer)
      const result = await authLogin(trimmedUsername, trimmedPassword)
      setAccessToken(result.access_token)
      if (next) {
        navigate(next, { replace: true })
        return
      }
      navigate('/', { replace: true })
    } catch (err) {
      setError(resolveErrorMessage(err, t('auth.register_failed')))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="relative mx-auto flex w-full max-w-md flex-col px-6 py-14">
      <div className="absolute right-6 top-6">
        <LanguageSwitcher />
      </div>
      <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="text-xl font-semibold text-slate-900">{t('auth.sign_up')}</h1>
        <p className="mt-1 text-sm text-slate-500">{t('auth.sign_up_help')}</p>

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
              autoComplete="new-password"
              className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-slate-300 focus:ring-2 focus:ring-slate-100"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder={t('auth.password_placeholder')}
            />
          </div>
          <div>
            <label className="text-xs font-semibold uppercase tracking-wide text-slate-500" htmlFor="confirm-password">
              {t('auth.confirm_password_label')}
            </label>
            <input
              id="confirm-password"
              type="password"
              autoComplete="new-password"
              className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-slate-300 focus:ring-2 focus:ring-slate-100"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              placeholder={t('auth.password_placeholder')}
            />
          </div>
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

          {error ? <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p> : null}

          <button type="submit" className="btn btn-primary w-full" disabled={isSubmitting}>
            {isSubmitting ? t('auth.signing_up') : t('auth.sign_up')}
          </button>

          <button
            type="button"
            className="btn btn-secondary w-full"
            onClick={() => navigate(`/login${next ? `?next=${encodeURIComponent(next)}` : ''}`, { replace: true })}
          >
            {t('auth.back_to_sign_in')}
          </button>
        </form>
      </div>
    </div>
  )
}
