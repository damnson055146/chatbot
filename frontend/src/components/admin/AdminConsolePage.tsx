import { useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  fetchAdminAudit,
  fetchAdminConfig,
  fetchMetricsSnapshot,
  updateAdminRetrieval,
  type AdminConfigPayload,
  type MetricsSnapshotPayload,
} from '../../services/apiClient'
import { useServiceStatus } from '../../hooks/useServiceStatus'
import { MetricsDashboard } from './MetricsDashboard'
import { SourcesManager } from './SourcesManager'

type TabKey = 'status' | 'metrics' | 'sources' | 'config' | 'audit'

const prettyJson = (value: unknown) => {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

export function AdminConsolePage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const params = useParams()
  const [tab, setTab] = useState<TabKey>('status')

  useEffect(() => {
    const raw = (params.section ?? 'status').toString().toLowerCase()
    const next: TabKey = (['status', 'metrics', 'sources', 'config', 'audit'].includes(raw) ? raw : 'status') as TabKey
    setTab(next)
  }, [params.section])

  const statusQuery = useServiceStatus()
  const metricsQuery = useQuery<MetricsSnapshotPayload, Error>({
    queryKey: ['metrics'],
    queryFn: fetchMetricsSnapshot,
    staleTime: 1000 * 15,
  })
  const configQuery = useQuery<AdminConfigPayload, Error>({
    queryKey: ['admin-config'],
    queryFn: fetchAdminConfig,
    staleTime: 1000 * 30,
  })
  const auditQuery = useQuery({
    queryKey: ['admin-audit', 100],
    queryFn: () => fetchAdminAudit(100),
    staleTime: 1000 * 10,
  })

  const retrievalDefaults = useMemo(() => {
    const retrieval = configQuery.data?.retrieval
    return {
      alpha: retrieval?.alpha ?? 0.5,
      top_k: retrieval?.top_k ?? 8,
      k_cite: retrieval?.k_cite ?? 2,
    }
  }, [configQuery.data])

  const [retrievalDraft, setRetrievalDraft] = useState(retrievalDefaults)

  // Keep draft in sync when config loads
  useEffect(() => {
    setRetrievalDraft(retrievalDefaults)
  }, [retrievalDefaults])

  const updateRetrieval = async () => {
    await updateAdminRetrieval(retrievalDraft)
    await queryClient.invalidateQueries({ queryKey: ['admin-config'] })
    await queryClient.invalidateQueries({ queryKey: ['metrics'] })
  }

  const goToTab = (next: TabKey) => {
    setTab(next)
    navigate(`/admin/${next}`)
  }

  return (
    <div className="min-h-screen bg-[#F7F7F8] text-slate-900">
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-4">
          <div>
            <p className="text-[11px] uppercase tracking-[0.4em] text-slate-400">Admin console</p>
            <h1 className="text-xl font-semibold text-slate-900">System & governance</h1>
          </div>
          <Link
            to="/"
            className="rounded-full border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:border-slate-400"
          >
            Back to chat
          </Link>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl px-6 py-6">
        <div className="flex flex-wrap gap-2">
          <TabButton active={tab === 'status'} onClick={() => goToTab('status')}>
            Status
          </TabButton>
          <TabButton active={tab === 'metrics'} onClick={() => goToTab('metrics')}>
            Metrics
          </TabButton>
          <TabButton active={tab === 'sources'} onClick={() => goToTab('sources')}>
            Sources
          </TabButton>
          <TabButton active={tab === 'config'} onClick={() => goToTab('config')}>
            Admin config
          </TabButton>
          <TabButton active={tab === 'audit'} onClick={() => goToTab('audit')}>
            Audit log
          </TabButton>
        </div>

        {tab === 'status' ? (
          <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-sm font-semibold text-slate-900">/v1/status</h2>
            {statusQuery.isLoading ? (
              <p className="mt-3 text-sm text-slate-500">Loading…</p>
            ) : statusQuery.error ? (
              <p className="mt-3 text-sm text-rose-600">{statusQuery.error.message}</p>
            ) : (
              <pre className="mt-4 overflow-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-50">
                {prettyJson(statusQuery.data)}
              </pre>
            )}
          </section>
        ) : null}

        {tab === 'metrics' ? (
          <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-sm font-semibold text-slate-900">/v1/metrics</h2>
              <button
                type="button"
                className="rounded-full border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:border-slate-400"
                onClick={() => void metricsQuery.refetch()}
              >
                Refresh
              </button>
            </div>
            {metricsQuery.isLoading ? (
              <p className="mt-3 text-sm text-slate-500">Loading…</p>
            ) : metricsQuery.error ? (
              <p className="mt-3 text-sm text-rose-600">{metricsQuery.error.message}</p>
            ) : (
              <MetricsDashboard data={metricsQuery.data as MetricsSnapshotPayload} />
            )}
          </section>
        ) : null}

        {tab === 'sources' ? (
          <section className="mt-6">
            <SourcesManager />
          </section>
        ) : null}

        {tab === 'config' ? (
          <section className="mt-6 grid gap-6 lg:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-sm font-semibold text-slate-900">Retrieval settings</h2>
              <p className="mt-1 text-xs text-slate-500">Updates /v1/admin/retrieval</p>
              <div className="mt-4 grid gap-4 sm:grid-cols-3">
                <label className="text-sm text-slate-700">
                  <span className="text-xs uppercase tracking-wide text-slate-500">alpha</span>
                  <input
                    type="number"
                    step="0.05"
                    min={0}
                    max={1}
                    value={retrievalDraft.alpha}
                    onChange={(e) => setRetrievalDraft((prev) => ({ ...prev, alpha: Number(e.target.value) }))}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-200"
                  />
                </label>
                <label className="text-sm text-slate-700">
                  <span className="text-xs uppercase tracking-wide text-slate-500">top_k</span>
                  <input
                    type="number"
                    min={1}
                    max={50}
                    value={retrievalDraft.top_k}
                    onChange={(e) => setRetrievalDraft((prev) => ({ ...prev, top_k: Number(e.target.value) }))}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-200"
                  />
                </label>
                <label className="text-sm text-slate-700">
                  <span className="text-xs uppercase tracking-wide text-slate-500">k_cite</span>
                  <input
                    type="number"
                    min={1}
                    max={10}
                    value={retrievalDraft.k_cite}
                    onChange={(e) => setRetrievalDraft((prev) => ({ ...prev, k_cite: Number(e.target.value) }))}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-200"
                  />
                </label>
              </div>
              <div className="mt-4 flex items-center gap-3">
                <button
                  type="button"
                  className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
                  onClick={() => void updateRetrieval()}
                  disabled={configQuery.isLoading}
                >
                  Save
                </button>
                <button
                  type="button"
                  className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:border-slate-400"
                  onClick={() => setRetrievalDraft(retrievalDefaults)}
                >
                  Reset
                </button>
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-sm font-semibold text-slate-900">/v1/admin/config</h2>
              {configQuery.isLoading ? (
                <p className="mt-3 text-sm text-slate-500">Loading…</p>
              ) : configQuery.error ? (
                <p className="mt-3 text-sm text-rose-600">{configQuery.error.message}</p>
              ) : (
                <pre className="mt-4 overflow-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-50">
                  {prettyJson(configQuery.data)}
                </pre>
              )}
            </div>
          </section>
        ) : null}

        {tab === 'audit' ? (
          <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-sm font-semibold text-slate-900">/v1/admin/audit</h2>
              <button
                type="button"
                className="rounded-full border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:border-slate-400"
                onClick={() => void auditQuery.refetch()}
              >
                Refresh
              </button>
            </div>
            {auditQuery.isLoading ? (
              <p className="mt-3 text-sm text-slate-500">Loading…</p>
            ) : auditQuery.error ? (
              <p className="mt-3 text-sm text-rose-600">{String(auditQuery.error)}</p>
            ) : (
              <pre className="mt-4 overflow-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-50">
                {prettyJson(auditQuery.data)}
              </pre>
            )}
          </section>
        ) : null}
      </main>
    </div>
  )
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      className={`rounded-full border px-4 py-2 text-xs font-semibold ${
        active ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-300 bg-white text-slate-700 hover:border-slate-400'
      }`}
      onClick={onClick}
    >
      {children}
    </button>
  )
}


