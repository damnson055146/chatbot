import { useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { LanguageSwitcher } from '../layout/LanguageSwitcher'
import {
  authMe,
  fetchAdminConfig,
  getAccessToken,
  updateAdminRetrieval,
  type AdminConfigPayload,
} from '../../services/apiClient'
import { PromptsManager } from './PromptsManager'
import { AssistantProfileManager } from './AssistantProfileManager'
import { AssistantOpeningManager } from './AssistantOpeningManager'
import { SourcesManager } from './SourcesManager'
import { JobsManager } from './JobsManager'
import { StatusDashboard } from './StatusDashboard'
import { AdminMetricsPanel } from './AdminMetricsPanel'
import { SlotsManager } from './SlotsManager'

type AdminSection = 'status' | 'metrics' | 'config' | 'slots' | 'sources' | 'jobs' | 'prompts' | 'opening' | 'profile'

const ADMIN_NAV: Array<{ key: AdminSection; labelKey: string; descKey: string }> = [
  { key: 'status', labelKey: 'admin.nav.status.label', descKey: 'admin.nav.status.desc' },
  { key: 'metrics', labelKey: 'admin.nav.metrics.label', descKey: 'admin.nav.metrics.desc' },
  { key: 'config', labelKey: 'admin.nav.config.label', descKey: 'admin.nav.config.desc' },
  { key: 'slots', labelKey: 'admin.nav.slots.label', descKey: 'admin.nav.slots.desc' },
  { key: 'sources', labelKey: 'admin.nav.sources.label', descKey: 'admin.nav.sources.desc' },
  { key: 'jobs', labelKey: 'admin.nav.jobs.label', descKey: 'admin.nav.jobs.desc' },
  { key: 'prompts', labelKey: 'admin.nav.prompts.label', descKey: 'admin.nav.prompts.desc' },
  { key: 'opening', labelKey: 'admin.nav.opening.label', descKey: 'admin.nav.opening.desc' },
  { key: 'profile', labelKey: 'admin.nav.profile.label', descKey: 'admin.nav.profile.desc' },
]

const prettyJson = (value: unknown) => {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

export function AdminConsolePage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const params = useParams()
  const [section, setSection] = useState<AdminSection>('config')
  const token = getAccessToken()

  const authQuery = useQuery({
    queryKey: ['authMe'],
    queryFn: authMe,
    enabled: Boolean(token),
    staleTime: 1000 * 60,
    retry: false,
  })
  const isReadOnly = authQuery.data?.role === 'admin_readonly'

  useEffect(() => {
    const raw = (params.section ?? 'config').toString().toLowerCase()
    const allowed = ADMIN_NAV.map((item) => item.key)
    const next: AdminSection = (allowed.includes(raw as AdminSection) ? raw : 'config') as AdminSection
    setSection(next)
  }, [params.section])

  const configQuery = useQuery<AdminConfigPayload, Error>({
    queryKey: ['admin-config'],
    queryFn: fetchAdminConfig,
    staleTime: 1000 * 30,
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
    if (isReadOnly) return
    await updateAdminRetrieval(retrievalDraft)
    await queryClient.invalidateQueries({ queryKey: ['admin-config'] })
    await queryClient.invalidateQueries({ queryKey: ['metrics'] })
  }

  const goToSection = (next: AdminSection) => {
    setSection(next)
    navigate(`/admin/${next}`)
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-4">
          <div>
            <p className="text-[11px] uppercase tracking-[0.4em] text-slate-400">{t('admin.title')}</p>
            <h1 className="text-xl font-semibold text-slate-900">{t('admin.subtitle')}</h1>
          </div>
          <div className="flex items-center gap-2">
            {isReadOnly ? (
              <span className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-700">
                {t('admin.readonly.badge')}
              </span>
            ) : null}
            <LanguageSwitcher />
            <Link
              to="/"
              className="rounded-full border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:border-slate-400"
            >
              {t('common.back_to_chat')}
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl px-6 py-6">
        <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
          <aside className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <p className="px-3 text-[11px] font-semibold uppercase tracking-[0.4em] text-slate-400">{t('admin.section.admin')}</p>
            <nav className="mt-3 space-y-1">
              {ADMIN_NAV.map((item) => (
                <AdminNavItem
                  key={item.key}
                  active={item.key === section}
                  label={t(item.labelKey)}
                  description={t(item.descKey)}
                  onClick={() => goToSection(item.key)}
                />
              ))}
            </nav>
          </aside>

          <section>
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <p className="text-[11px] font-semibold uppercase tracking-[0.4em] text-slate-400">
                {ADMIN_NAV.find((i) => i.key === section) ? t(ADMIN_NAV.find((i) => i.key === section)!.labelKey) : t('admin.section.admin')}
              </p>
              <h2 className="mt-2 text-lg font-semibold text-slate-900">
                {ADMIN_NAV.find((i) => i.key === section) ? t(ADMIN_NAV.find((i) => i.key === section)!.descKey) : ''}
              </h2>
            </div>

            {section === 'prompts' ? (
              <section className="mt-6">
                <PromptsManager readOnly={isReadOnly} />
              </section>
            ) : null}

            {section === 'opening' ? (
              <section className="mt-6">
                <AssistantOpeningManager readOnly={isReadOnly} />
              </section>
            ) : null}

            {section === 'profile' ? (
              <section className="mt-6">
                <AssistantProfileManager readOnly={isReadOnly} />
              </section>
            ) : null}

            {section === 'status' ? (
              <section className="mt-6">
                <StatusDashboard />
              </section>
            ) : null}

            {section === 'metrics' ? (
              <section className="mt-6">
                <AdminMetricsPanel />
              </section>
            ) : null}

            {section === 'sources' ? (
              <section className="mt-6">
                <SourcesManager readOnly={isReadOnly} />
              </section>
            ) : null}

            {section === 'slots' ? (
              <section className="mt-6">
                <SlotsManager readOnly={isReadOnly} />
              </section>
            ) : null}

            {section === 'jobs' ? (
              <section className="mt-6">
                <JobsManager readOnly={isReadOnly} />
              </section>
            ) : null}

            {section === 'config' ? (
              <section className="mt-6 grid gap-6 lg:grid-cols-2">
                <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                  <h3 className="text-sm font-semibold text-slate-900">{t('admin.config.retrieval_settings')}</h3>
                  <p className="mt-1 text-xs text-slate-500">{t('admin.config.updates_endpoint', { endpoint: '/v1/admin/retrieval' })}</p>
                  <div className="mt-4 grid gap-4 sm:grid-cols-3">
                    <label className="text-sm text-slate-700">
                      <span className="text-xs uppercase tracking-wide text-slate-500">{t('admin.config.alpha')}</span>
                      <input
                        type="number"
                        step="0.05"
                        min={0}
                        max={1}
                        value={retrievalDraft.alpha}
                        onChange={(e) => setRetrievalDraft((prev) => ({ ...prev, alpha: Number(e.target.value) }))}
                        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-200"
                        disabled={isReadOnly}
                      />
                    </label>
                    <label className="text-sm text-slate-700">
                      <span className="text-xs uppercase tracking-wide text-slate-500">{t('admin.config.top_k')}</span>
                      <input
                        type="number"
                        min={1}
                        max={50}
                        value={retrievalDraft.top_k}
                        onChange={(e) => setRetrievalDraft((prev) => ({ ...prev, top_k: Number(e.target.value) }))}
                        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-200"
                        disabled={isReadOnly}
                      />
                    </label>
                    <label className="text-sm text-slate-700">
                      <span className="text-xs uppercase tracking-wide text-slate-500">{t('admin.config.k_cite')}</span>
                      <input
                        type="number"
                        min={1}
                        max={10}
                        value={retrievalDraft.k_cite}
                        onChange={(e) => setRetrievalDraft((prev) => ({ ...prev, k_cite: Number(e.target.value) }))}
                        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-200"
                        disabled={isReadOnly}
                      />
                    </label>
                  </div>
                  <div className="mt-4 flex items-center gap-3">
                    <button
                      type="button"
                      className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
                      onClick={() => void updateRetrieval()}
                      disabled={configQuery.isLoading || isReadOnly}
                    >
                      {t('common.save')}
                    </button>
                    <button
                      type="button"
                      className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:border-slate-400"
                      onClick={() => setRetrievalDraft(retrievalDefaults)}
                      disabled={isReadOnly}
                    >
                      {t('admin.config.reset')}
                    </button>
                  </div>
                </div>

                <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                  <h3 className="text-sm font-semibold text-slate-900">{t('admin.config.endpoint_config')}</h3>
                  {configQuery.isLoading ? (
                    <p className="mt-3 text-sm text-slate-500">{t('common.loading')}</p>
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

          </section>
        </div>
      </main>
    </div>
  )
}

function AdminNavItem({
  active,
  label,
  description,
  onClick,
}: {
  active: boolean
  label: string
  description: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full rounded-xl px-3 py-2 text-left transition ${
        active ? 'bg-slate-900 text-white' : 'bg-transparent text-slate-700 hover:bg-slate-50'
      }`}
    >
      <p className="text-sm font-semibold">{label}</p>
      <p className={`mt-1 text-xs ${active ? 'text-white/70' : 'text-slate-500'}`}>{description}</p>
    </button>
  )
}
