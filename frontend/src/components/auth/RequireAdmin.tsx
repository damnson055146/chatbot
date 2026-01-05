import { useQuery } from '@tanstack/react-query'
import { Navigate, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { authMe, clearAccessToken, getAccessToken, isAdminRole } from '../../services/apiClient'

export function RequireAdmin({ children }: { children: React.ReactNode }) {
  const { t } = useTranslation()
  const location = useLocation()
  const token = getAccessToken()

  const { data, isLoading, isError } = useQuery({
    queryKey: ['authMe'],
    queryFn: authMe,
    enabled: Boolean(token),
    retry: false,
  })

  if (!token) {
    const next = encodeURIComponent(`${location.pathname}${location.search}`)
    return <Navigate to={`/login?next=${next}`} replace />
  }

  if (isLoading) {
    return <div className="flex items-center justify-center py-16 text-sm text-slate-500">{t('auth.checking_permissions')}</div>
  }

  if (isError) {
    clearAccessToken()
    const next = encodeURIComponent(`${location.pathname}${location.search}`)
    return <Navigate to={`/login?next=${next}`} replace />
  }

  if (!isAdminRole(data?.role)) {
    return (
      <div className="mx-auto flex w-full max-w-xl flex-col px-6 py-14">
        <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
          <h1 className="text-xl font-semibold text-slate-900">{t('auth.no_permission')}</h1>
          <p className="mt-2 text-sm text-slate-500">{t('auth.restricted_admin')}</p>
          <div className="mt-6 flex flex-wrap gap-3">
            <a className="btn btn-primary" href={`/login?next=${encodeURIComponent(`${location.pathname}${location.search}`)}`}>
              {t('auth.sign_in_admin')}
            </a>
            <a className="btn btn-ghost" href="/">
              {t('common.back_to_chat')}
            </a>
          </div>
        </div>
      </div>
    )
  }

  return <>{children}</>
}

