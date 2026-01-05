import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { MetricsHistoryEntryPayload, MetricsSnapshotPayload } from '../../services/apiClient'

type Dict = Record<string, unknown>

const asDict = (value: unknown): Dict | null => (value && typeof value === 'object' ? (value as Dict) : null)
const asNumber = (value: unknown): number | null => (typeof value === 'number' && Number.isFinite(value) ? value : null)
const asString = (value: unknown): string | null => (typeof value === 'string' ? value : null)

const formatMs = (t: (key: string) => string, value: number | null) => {
  if (value === null) return t('common.na')
  return `${Math.round(value)} ${t('common.ms')}`
}

const formatRate = (t: (key: string) => string, value: number | null) => {
  if (value === null) return t('common.na')
  return `${Math.round(value * 100)}%`
}

const formatTimestamp = (value: string | null) => {
  if (!value) return '--'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString()
}

const statusColor = (status: string | null) => {
  switch ((status ?? '').toLowerCase()) {
    case 'green':
      return 'bg-emerald-100 text-emerald-700 border-emerald-200'
    case 'amber':
      return 'bg-amber-100 text-amber-700 border-amber-200'
    case 'red':
      return 'bg-rose-100 text-rose-700 border-rose-200'
    default:
      return 'bg-slate-100 text-slate-600 border-slate-200'
  }
}

function extractEndpointStats(snapshot: Dict) {
  const rows: Array<{
    name: string
    count: number | null
    p50: number | null
    p95: number | null
    avg: number | null
  }> = []
  for (const [key, value] of Object.entries(snapshot)) {
    if (!key.startsWith('/')) continue
    const block = asDict(value)
    if (!block) continue
    rows.push({
      name: key,
      count: asNumber(block.count),
      avg: asNumber(block.avg_latency_ms),
      p50: asNumber(block.p50_latency_ms),
      p95: asNumber(block.p95_latency_ms),
    })
  }
  rows.sort((a, b) => (b.count ?? 0) - (a.count ?? 0))
  return rows
}

function extractPhaseStats(snapshot: Dict) {
  const phases = asDict(snapshot.phases) ?? {}
  const rows: Array<{ name: string; count: number | null; p50: number | null; p95: number | null; avg: number | null }> = []
  for (const [name, value] of Object.entries(phases)) {
    const block = asDict(value)
    if (!block) continue
    rows.push({
      name,
      count: asNumber(block.count),
      avg: asNumber(block.avg_latency_ms),
      p50: asNumber(block.p50_latency_ms),
      p95: asNumber(block.p95_latency_ms),
    })
  }
  const order = ['retrieval', 'rerank', 'generation', 'end_to_end']
  rows.sort((a, b) => order.indexOf(a.name) - order.indexOf(b.name))
  return rows
}

function extractDiagnostics(snapshot: Dict) {
  const d = asDict(snapshot.diagnostics) ?? {}
  return {
    emptyRetrievals: asNumber(d.empty_retrievals),
    rerankFallbacks: asNumber(d.rerank_fallbacks),
    lowConfidenceAnswers: asNumber(d.low_confidence_answers),
    citationAvg: asNumber(d.citation_coverage_avg),
    citationP50: asNumber(d.citation_coverage_p50),
    citationP95: asNumber(d.citation_coverage_p95),
    activeSessions: asNumber(asDict(d.sessions)?.active),
    retrievalRecallAvg: asNumber(d.retrieval_recall_avg),
    retrievalMrrAvg: asNumber(d.retrieval_mrr_avg),
    retrievalEvalK: asNumber(d.retrieval_eval_k),
  }
}

function extractStatus(snapshot: Dict) {
  const status = asDict(snapshot.status) ?? {}
  const latency = asDict(status.latency) ?? {}
  const quality = asDict(status.quality) ?? {}
  return { latency, quality }
}

function extractCounters(snapshot: Dict) {
  const counters = asDict(snapshot.counters) ?? {}
  const rows = Object.entries(counters)
    .map(([name, value]) => ({ name, value: asNumber(value) }))
    .filter((row) => row.value !== null)
    .sort((a, b) => (b.value ?? 0) - (a.value ?? 0))
  return rows
}

function extractTrendRows(entries: MetricsHistoryEntryPayload[]) {
  return entries.map((entry, index) => {
    const snapshot = asDict(entry.snapshot) ?? {}
    const endpointStats = extractEndpointStats(snapshot)
    const phaseStats = extractPhaseStats(snapshot)
    const diagnostics = extractDiagnostics(snapshot)
    const queryEndpoint = endpointStats.find((row) => row.name === '/v1/query')
    const queryCount = queryEndpoint?.count ?? null
    const e2eP95 = phaseStats.find((row) => row.name === 'end_to_end')?.p95 ?? null
    const lowConfRate = getRate(diagnostics.lowConfidenceAnswers, queryCount)
    const emptyRate = getRate(diagnostics.emptyRetrievals, queryCount)
    return {
      key: `${entry.timestamp}-${index}`,
      timestamp: entry.timestamp,
      queryCount,
      e2eP95,
      lowConfRate,
      emptyRate,
    }
  })
}

export function MetricsDashboard({
  data,
  history = [],
  historyLoading = false,
}: {
  data: MetricsSnapshotPayload
  history?: MetricsHistoryEntryPayload[]
  historyLoading?: boolean
}) {
  const { t } = useTranslation()
  const snapshot = useMemo(() => asDict(data) ?? {}, [data])
  const endpointStats = useMemo(() => extractEndpointStats(snapshot), [snapshot])
  const phaseStats = useMemo(() => extractPhaseStats(snapshot), [snapshot])
  const diagnostics = useMemo(() => extractDiagnostics(snapshot), [snapshot])
  const status = useMemo(() => extractStatus(snapshot), [snapshot])
  const counters = useMemo(() => extractCounters(snapshot), [snapshot])
  const trendRows = useMemo(() => extractTrendRows(history), [history])
  const maxE2e = Math.max(...trendRows.map((row) => row.e2eP95 ?? 0), 0)
  const maxLowConf = Math.max(...trendRows.map((row) => row.lowConfRate ?? 0), 0)
  const maxEmpty = Math.max(...trendRows.map((row) => row.emptyRate ?? 0), 0)
  const evalKLabel = diagnostics.retrievalEvalK ? Math.round(diagnostics.retrievalEvalK) : 'k'

  const queryEndpoint = endpointStats.find((row) => row.name === '/v1/query')
  const queryCount = queryEndpoint?.count ?? null
  const [showRaw, setShowRaw] = useState(false)

  return (
    <div className="mt-4 space-y-6">
      <section className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          label={t('admin.metrics.card.active_sessions')}
          value={diagnostics.activeSessions !== null ? String(diagnostics.activeSessions) : t('common.na')}
          hint="diagnostics.sessions.active"
        />
        <MetricCard
          label={t('admin.metrics.card.query_count')}
          value={queryCount !== null ? String(queryCount) : t('common.na')}
          hint="endpoint count window"
        />
        <MetricCard
          label={t('admin.metrics.card.e2e_p95')}
          value={formatMs(t, phaseStats.find((p) => p.name === 'end_to_end')?.p95 ?? null)}
          hint="phases.end_to_end.p95_latency_ms"
        />
        <MetricCard
          label={t('admin.metrics.card.low_conf_rate')}
          value={formatRate(t, getRate(diagnostics.lowConfidenceAnswers, queryCount))}
          hint="low_confidence_answers / query_count"
        />
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-900">{t('admin.metrics.phase_latency')}</h3>
          <p className="mt-1 text-xs text-slate-500">{t('admin.metrics.phase_latency_hint')}</p>
          <table className="mt-4 w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-slate-400">
              <tr>
                <th className="py-2">{t('admin.metrics.table.phase')}</th>
                <th className="py-2">{t('admin.metrics.table.count')}</th>
                <th className="py-2">{t('admin.metrics.table.p50')}</th>
                <th className="py-2">{t('admin.metrics.table.p95')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {phaseStats.map((row) => (
                <tr key={row.name}>
                  <td className="py-2 font-medium text-slate-900">{row.name}</td>
                  <td className="py-2 text-slate-600">{row.count ?? t('common.na')}</td>
                  <td className="py-2 text-slate-600">{formatMs(t, row.p50)}</td>
                  <td className="py-2 text-slate-600">{formatMs(t, row.p95)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-900">{t('admin.metrics.quality')}</h3>
          <p className="mt-1 text-xs text-slate-500">{t('admin.metrics.quality_hint')}</p>
          <div className="mt-4 grid gap-3">
            <QualityRow
              label={t('admin.metrics.quality.empty_retrieval_rate')}
              value={formatRate(t, getRate(diagnostics.emptyRetrievals, queryCount))}
              status={asString(asDict(status.quality.empty_retrieval_rate)?.status)}
            />
            <QualityRow
              label={t('admin.metrics.quality.low_conf_rate')}
              value={formatRate(t, getRate(diagnostics.lowConfidenceAnswers, queryCount))}
              status={asString(asDict(status.quality.low_confidence_rate)?.status)}
            />
            <QualityRow
              label={t('admin.metrics.quality.citation_p95')}
              value={diagnostics.citationP95 !== null ? `${Math.round(diagnostics.citationP95 * 100)}%` : t('common.na')}
              status={null}
            />
            <QualityRow
              label={t('admin.metrics.quality.recall_at_k', { k: evalKLabel })}
              value={formatRate(t, diagnostics.retrievalRecallAvg)}
              status={null}
            />
            <QualityRow
              label={t('admin.metrics.quality.mrr', { k: evalKLabel })}
              value={formatRate(t, diagnostics.retrievalMrrAvg)}
              status={null}
            />
          </div>
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-900">{t('admin.metrics.endpoints')}</h3>
          <p className="mt-1 text-xs text-slate-500">{t('admin.metrics.endpoints_hint')}</p>
          <div className="mt-4 overflow-auto">
            <table className="min-w-[560px] w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="py-2">{t('admin.metrics.table.endpoint')}</th>
                  <th className="py-2">{t('admin.metrics.table.count')}</th>
                  <th className="py-2">{t('admin.metrics.table.p95')}</th>
                  <th className="py-2">{t('admin.metrics.table.avg')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {endpointStats.map((row) => (
                  <tr key={row.name}>
                    <td className="py-2 font-medium text-slate-900">{row.name}</td>
                    <td className="py-2 text-slate-600">{row.count ?? t('common.na')}</td>
                    <td className="py-2 text-slate-600">{formatMs(t, row.p95)}</td>
                    <td className="py-2 text-slate-600">{formatMs(t, row.avg)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-900">{t('admin.metrics.counters_top')}</h3>
          <p className="mt-1 text-xs text-slate-500">{t('admin.metrics.counters_hint')}</p>
          {counters.length === 0 ? (
            <p className="mt-4 text-sm text-slate-500">{t('admin.metrics.no_counters')}</p>
          ) : (
            <ul className="mt-4 space-y-2">
              {counters.slice(0, 20).map((row) => (
                <li key={row.name} className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
                  <span className="font-medium text-slate-900">{row.name}</span>
                  <span className="text-slate-600">{Math.round(row.value ?? 0)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-900">{t('admin.metrics.trends.title')}</h3>
            <p className="mt-1 text-xs text-slate-500">{t('admin.metrics.trends.subtitle')}</p>
          </div>
          <span className="text-xs text-slate-400">/v1/metrics/history</span>
        </div>
        {historyLoading ? (
          <p className="mt-4 text-sm text-slate-500">{t('common.loading')}</p>
        ) : trendRows.length === 0 ? (
          <p className="mt-4 text-sm text-slate-500">{t('admin.metrics.trends.empty')}</p>
        ) : (
          <div className="mt-4 overflow-auto">
            <table className="min-w-[680px] w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="py-2">{t('admin.metrics.trends.table.time')}</th>
                  <th className="py-2">{t('admin.metrics.trends.table.query_count')}</th>
                  <th className="py-2">{t('admin.metrics.trends.table.e2e_p95')}</th>
                  <th className="py-2">{t('admin.metrics.trends.table.low_conf')}</th>
                  <th className="py-2">{t('admin.metrics.trends.table.empty_retrieval')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {trendRows.map((row) => (
                  <tr key={row.key}>
                    <td className="py-2 text-slate-600">{formatTimestamp(row.timestamp)}</td>
                    <td className="py-2 text-slate-600">{row.queryCount ?? t('common.na')}</td>
                    <td className="py-2 text-slate-600">
                      <div className="space-y-1">
                        <span>{formatMs(t, row.e2eP95)}</span>
                        <TrendBar value={row.e2eP95} max={maxE2e} tone="bg-slate-900" />
                      </div>
                    </td>
                    <td className="py-2 text-slate-600">
                      <div className="space-y-1">
                        <span>{formatRate(t, row.lowConfRate)}</span>
                        <TrendBar value={row.lowConfRate ?? null} max={maxLowConf} tone="bg-amber-500" />
                      </div>
                    </td>
                    <td className="py-2 text-slate-600">
                      <div className="space-y-1">
                        <span>{formatRate(t, row.emptyRate)}</span>
                        <TrendBar value={row.emptyRate ?? null} max={maxEmpty} tone="bg-rose-500" />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold text-slate-900">{t('admin.metrics.raw_json')}</h3>
          <button
            type="button"
            className="rounded-full border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:border-slate-400"
            onClick={() => setShowRaw((prev) => !prev)}
          >
            {showRaw ? t('common.hide') : t('common.show')}
          </button>
        </div>
        {showRaw ? (
          <pre className="mt-4 overflow-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-50">{JSON.stringify(snapshot, null, 2)}</pre>
        ) : null}
      </section>
    </div>
  )
}

function getRate(numerator: number | null, denominator: number | null | undefined) {
  if (numerator === null || denominator === null || denominator === undefined || denominator <= 0) return null
  return numerator / denominator
}

function MetricCard({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <p className="text-[11px] font-semibold uppercase tracking-[0.4em] text-slate-400">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-slate-900">{value}</p>
      {hint ? <p className="mt-2 text-xs text-slate-500">{hint}</p> : null}
    </div>
  )
}

function QualityRow({ label, value, status }: { label: string; value: string; status: string | null }) {
  const { t } = useTranslation()
  return (
    <div className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white px-4 py-3">
      <div>
        <p className="text-sm font-semibold text-slate-900">{label}</p>
        <p className="mt-1 text-xs text-slate-500">{value}</p>
      </div>
      <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${statusColor(status)}`}>{status ?? t('common.na')}</span>
    </div>
  )
}

function TrendBar({ value, max, tone }: { value: number | null; max: number; tone: string }) {
  if (value === null || max <= 0) {
    return <div className="h-1 w-full rounded-full bg-slate-100" />
  }
  const width = Math.max(4, Math.round((value / max) * 100))
  return (
    <div className="h-1 w-full rounded-full bg-slate-100">
      <div className={`h-1 rounded-full ${tone}`} style={{ width: `${width}%` }} />
    </div>
  )
}
