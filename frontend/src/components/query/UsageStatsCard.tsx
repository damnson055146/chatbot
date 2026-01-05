import type { ServiceStatusResponsePayload } from '../../services/apiClient'
import { useTranslation } from 'react-i18next'

interface UsageStatsCardProps {
  data?: ServiceStatusResponsePayload
  isLoading: boolean
  error?: Error | null
}

const STATUS_COLORS: Record<string, string> = {
  green: 'bg-emerald-100 text-emerald-700',
  amber: 'bg-amber-100 text-amber-700',
  red: 'bg-rose-100 text-rose-700',
}

export function UsageStatsCard({ data, isLoading, error }: UsageStatsCardProps) {
  const { t } = useTranslation()
  if (isLoading) {
    return (
      <section className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-500" aria-busy="true">
        {t('query.usage.loading')}
      </section>
    )
  }

  if (error) {
    return (
      <section className="rounded-xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-700">
        {t('query.usage.error', { endpoint: '/v1/status', message: error.message })}
      </section>
    )
  }

  if (!data || data.categories.length === 0) {
    return (
      <section className="rounded-xl border border-dashed border-slate-300 bg-white p-6 text-sm text-slate-500">
        {t('query.usage.empty')}
      </section>
    )
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <header className="flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold text-slate-900">{t('query.usage.title')}</p>
          <p className="text-xs text-slate-500">
            {t('query.usage.snapshot_at', { time: new Date(data.generated_at).toLocaleTimeString() })}
          </p>
        </div>
      </header>
      <div className="mt-4 space-y-4 text-sm text-slate-700">
        {data.categories.map((category) => (
          <div key={category.name}>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{category.name}</p>
            <ul className="mt-2 space-y-2">
              {category.metrics.map((metric) => (
                <li key={metric.name} className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2">
                  <div>
                    <p className="text-sm font-medium text-slate-900">{formatMetricName(metric.name)}</p>
                    <p className="text-xs text-slate-500">
                      {metric.value !== undefined ? formatMetricValue(t, metric) : t('query.usage.metric.na')}
                    </p>
                  </div>
                  <span className={`rounded-full px-3 py-1 text-xs font-semibold ${STATUS_COLORS[metric.status] ?? 'bg-slate-100 text-slate-600'}`}>
                    {metric.status}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  )
}

const formatMetricName = (name: string) =>
  name
    .split('_')
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(' ')

const formatMetricValue = (
  t: (key: string, options?: Record<string, unknown>) => string,
  metric: ServiceStatusResponsePayload['categories'][number]['metrics'][number],
) => {
  if (metric.name.startsWith('latency')) {
    return t('query.usage.metric.latency_value', {
      value: Math.round(metric.value ?? 0),
      target: Math.round(metric.target ?? 0),
    })
  }
  if (metric.name.includes('rate')) {
    const percentage = Math.round((metric.value ?? 0) * 100)
    const target = Math.round((metric.target ?? 0) * 100)
    return t('query.usage.metric.rate_value', { value: percentage, target })
  }
  return metric.value?.toString() ?? t('query.usage.metric.na')
}
