import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { fetchServiceStatus } from '../../services/apiClient'
import { UsageStatsCard } from '../query/UsageStatsCard'

export function StatusDashboard() {
  const { t } = useTranslation()
  const statusQuery = useQuery({
    queryKey: ['status'],
    queryFn: fetchServiceStatus,
    staleTime: 1000 * 15,
  })

  return (
    <div className="mt-6">
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-900">{t('admin.status.title')}</h3>
          </div>
          <button
            type="button"
            className="rounded-full border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:border-slate-400"
            onClick={() => void statusQuery.refetch()}
            disabled={statusQuery.isLoading}
          >
            {t('common.refresh')}
          </button>
        </div>
        <div className="mt-4">
          <UsageStatsCard
            data={statusQuery.data}
            isLoading={statusQuery.isLoading}
            error={statusQuery.error as Error | null | undefined}
          />
        </div>
      </div>
    </div>
  )
}

export default StatusDashboard
