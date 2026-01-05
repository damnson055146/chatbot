import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { fetchMetricsHistory, fetchMetricsSnapshot } from '../../services/apiClient'
import { MetricsDashboard } from './MetricsDashboard'

const DEFAULT_HISTORY_LIMIT = 30

export function AdminMetricsPanel() {
  const { t } = useTranslation()
  const metricsQuery = useQuery({
    queryKey: ['metrics'],
    queryFn: fetchMetricsSnapshot,
    staleTime: 1000 * 15,
  })
  const historyQuery = useQuery({
    queryKey: ['metrics-history', DEFAULT_HISTORY_LIMIT],
    queryFn: () => fetchMetricsHistory(DEFAULT_HISTORY_LIMIT),
    staleTime: 1000 * 60,
  })

  if (metricsQuery.isLoading) {
    return <p className="mt-6 text-sm text-slate-500">{t('common.loading')}</p>
  }

  if (metricsQuery.error) {
    return (
      <p className="mt-6 text-sm text-rose-600">
        {(metricsQuery.error as Error).message}
      </p>
    )
  }

  return (
    <div className="mt-6">
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-900">{t('admin.metrics.title')}</h3>
          </div>
          <button
            type="button"
            className="rounded-full border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:border-slate-400"
            onClick={() => {
              void metricsQuery.refetch()
              void historyQuery.refetch()
            }}
            disabled={metricsQuery.isLoading}
          >
            {t('common.refresh')}
          </button>
        </div>
        <MetricsDashboard
          data={metricsQuery.data ?? {}}
          history={historyQuery.data ?? []}
          historyLoading={historyQuery.isLoading}
        />
        {historyQuery.error ? (
          <p className="mt-4 text-sm text-rose-600">{(historyQuery.error as Error).message}</p>
        ) : null}
      </div>
    </div>
  )
}

export default AdminMetricsPanel
