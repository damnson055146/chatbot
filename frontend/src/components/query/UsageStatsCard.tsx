import type { ServiceStatusResponsePayload } from '../../services/apiClient'

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
  if (isLoading) {
    return (
      <section className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-500" aria-busy="true">
        Loading service status…
      </section>
    )
  }

  if (error) {
    return (
      <section className="rounded-xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-700">
        Unable to load `/v1/status`: {error.message}
      </section>
    )
  }

  if (!data || data.categories.length === 0) {
    return (
      <section className="rounded-xl border border-dashed border-slate-300 bg-white p-6 text-sm text-slate-500">
        Service status will appear once the backend reports metrics.
      </section>
    )
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <header className="flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold text-slate-900">Usage & health</p>
          <p className="text-xs text-slate-500">Snapshot generated at {new Date(data.generated_at).toLocaleTimeString()}</p>
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
                      {metric.value !== undefined ? formatMetricValue(metric) : 'n/a'}
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

const formatMetricValue = (metric: ServiceStatusResponsePayload['categories'][number]['metrics'][number]) => {
  if (metric.name.startsWith('latency')) {
    return `${Math.round(metric.value ?? 0)} ms p95 (target ${Math.round(metric.target ?? 0)} ms)`
  }
  if (metric.name.includes('rate')) {
    const percentage = Math.round((metric.value ?? 0) * 100)
    const target = Math.round((metric.target ?? 0) * 100)
    return `${percentage}% (keep ≤ ${target}% )`
  }
  return metric.value?.toString() ?? 'n/a'
}
