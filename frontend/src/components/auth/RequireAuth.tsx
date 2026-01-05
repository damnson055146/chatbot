import { useQuery } from '@tanstack/react-query'
import { Navigate, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { authMe, clearAccessToken, getAccessToken } from '../../services/apiClient'

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { t } = useTranslation()
  const location = useLocation()
  const token = getAccessToken()

  const { isLoading, isError } = useQuery({
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

  return <>{children}</>
}
