import { useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { fetchAdminJobs, ingestUpload, rebuildIndex, type AdminJobEntryPayload } from '../../services/apiClient'

const formatMs = (value?: number | null) => {
  if (!value && value !== 0) return '—'
  if (value < 1000) return `${Math.round(value)}ms`
  return `${(value / 1000).toFixed(1)}s`
}

const formatIso = (iso?: string | null) => {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString()
}

export function JobsManager({ readOnly = false }: { readOnly?: boolean }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [limit, setLimit] = useState(50)
  const [status, setStatus] = useState<{ tone: 'info' | 'error'; message: string } | null>(null)
  const [busy, setBusy] = useState(false)

  const [uploadId, setUploadId] = useState('')
  const [docId, setDocId] = useState('')
  const [sourceName, setSourceName] = useState('')
  const [language, setLanguage] = useState('auto')

  const jobsQuery = useQuery({
    queryKey: ['admin-jobs', limit],
    queryFn: () => fetchAdminJobs(limit),
    staleTime: 1000 * 10,
  })

  const jobs = useMemo(() => jobsQuery.data?.jobs ?? [], [jobsQuery.data])

  const triggerRebuild = async () => {
    if (readOnly) return
    const ok = typeof window === 'undefined' ? true : window.confirm(t('admin.jobs.confirm_rebuild'))
    if (!ok) return
    setBusy(true)
    setStatus(null)
    try {
      const result = await rebuildIndex()
      setStatus({
        tone: 'info',
        message: t('admin.jobs.status.index_rebuilt', { documents: result.document_count, chunks: result.chunk_count }),
      })
      await queryClient.invalidateQueries({ queryKey: ['admin-jobs'] })
    } catch (err: any) {
      setStatus({ tone: 'error', message: err?.message ?? t('admin.jobs.error.index_rebuild_failed') })
    } finally {
      setBusy(false)
    }
  }

  const triggerIngest = async () => {
    if (readOnly) return
    const trimmed = uploadId.trim()
    if (!trimmed) {
      setStatus({ tone: 'error', message: t('admin.jobs.upload_id_required') })
      return
    }
    const ok = typeof window === 'undefined' ? true : window.confirm(t('admin.jobs.confirm_ingest', { uploadId: trimmed }))
    if (!ok) return
    setBusy(true)
    setStatus(null)
    try {
      const result = await ingestUpload({
        upload_id: trimmed,
        doc_id: docId.trim() || undefined,
        source_name: sourceName.trim() || undefined,
        language: language.trim() || 'auto',
      })
      setStatus({
        tone: 'info',
        message: t('admin.jobs.status.ingested', { doc_id: result.doc_id, chunks: result.chunk_count }),
      })
      await queryClient.invalidateQueries({ queryKey: ['admin-jobs'] })
      await queryClient.invalidateQueries({ queryKey: ['admin-sources'] })
      await queryClient.invalidateQueries({ queryKey: ['metrics'] })
    } catch (err: any) {
      setStatus({ tone: 'error', message: err?.message ?? t('admin.jobs.error.ingest_failed') })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-900">{t('admin.jobs.title')}</h3>
            <p className="mt-1 text-xs text-slate-500">{t('admin.jobs.subtitle')}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-xs text-slate-500">
              {t('admin.jobs.limit')}{' '}
              <input
                type="number"
                min={10}
                max={200}
                value={limit}
                onChange={(e) => setLimit(Number(e.target.value))}
                className="ml-2 w-20 rounded-lg border border-slate-300 px-2 py-1 text-xs text-slate-900"
              />
            </label>
            <button type="button" className="btn btn-ghost" onClick={() => void jobsQuery.refetch()}>
              {t('common.refresh')}
            </button>
            <button type="button" className="btn btn-primary" disabled={busy || readOnly} onClick={() => void triggerRebuild()}>
              {t('admin.jobs.rebuild_index')}
            </button>
          </div>
        </div>

        {status ? (
          <div
            className={`mt-4 rounded-2xl border px-4 py-3 text-sm ${
              status.tone === 'error' ? 'border-rose-200 bg-rose-50 text-rose-700' : 'border-slate-200 bg-slate-50 text-slate-700'
            }`}
          >
            {status.message}
          </div>
        ) : null}

        <div className="mt-6 rounded-2xl border border-slate-200 bg-white p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t('admin.jobs.ingest_upload')}</p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="text-sm text-slate-700">
              <span className="text-xs uppercase tracking-wide text-slate-500">{t('admin.jobs.field.upload_id')}</span>
              <input
                value={uploadId}
                onChange={(e) => setUploadId(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-200"
                placeholder={t('admin.jobs.upload_id_placeholder')}
                disabled={readOnly}
              />
            </label>
            <label className="text-sm text-slate-700">
              <span className="text-xs uppercase tracking-wide text-slate-500">{t('admin.jobs.field.language')}</span>
              <input
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-200"
                placeholder={t('admin.jobs.language_placeholder')}
                disabled={readOnly}
              />
            </label>
            <label className="text-sm text-slate-700">
              <span className="text-xs uppercase tracking-wide text-slate-500">{t('admin.jobs.doc_id_optional')}</span>
              <input
                value={docId}
                onChange={(e) => setDocId(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-200"
                placeholder={t('admin.jobs.doc_id_placeholder')}
                disabled={readOnly}
              />
            </label>
            <label className="text-sm text-slate-700">
              <span className="text-xs uppercase tracking-wide text-slate-500">{t('admin.jobs.source_name_optional')}</span>
              <input
                value={sourceName}
                onChange={(e) => setSourceName(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-200"
                placeholder={t('admin.jobs.source_name_placeholder')}
                disabled={readOnly}
              />
            </label>
          </div>
          <div className="mt-4">
            <button type="button" className="btn btn-primary" disabled={busy || readOnly} onClick={() => void triggerIngest()}>
              {t('admin.jobs.ingest_now')}
            </button>
            <p className="mt-2 text-xs text-slate-500">{t('admin.jobs.ingest_hint')}</p>
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold text-slate-900">{t('admin.jobs.history')}</h3>
          <span className="text-xs text-slate-500">{t('admin.jobs.entries', { count: jobs.length })}</span>
        </div>

        {jobsQuery.isLoading ? (
          <p className="mt-4 text-sm text-slate-500">{t('common.loading')}</p>
        ) : jobsQuery.error ? (
          <p className="mt-4 text-sm text-rose-600">{(jobsQuery.error as Error).message}</p>
        ) : jobs.length === 0 ? (
          <p className="mt-4 text-sm text-slate-500">{t('admin.jobs.no_jobs')}</p>
        ) : (
          <div className="mt-4 overflow-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="py-2 pr-4">{t('admin.jobs.table.type')}</th>
                  <th className="py-2 pr-4">{t('admin.jobs.table.status')}</th>
                  <th className="py-2 pr-4">{t('admin.jobs.table.started')}</th>
                  <th className="py-2 pr-4">{t('admin.jobs.table.duration')}</th>
                  <th className="py-2 pr-4">{t('admin.jobs.table.job_id')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {jobs.map((job: AdminJobEntryPayload) => (
                  <tr key={job.job_id} className="align-top">
                    <td className="py-3 pr-4 font-semibold text-slate-900">{job.job_type}</td>
                    <td className="py-3 pr-4 text-slate-700">{job.status}</td>
                    <td className="py-3 pr-4 text-slate-700">{formatIso(job.started_at)}</td>
                    <td className="py-3 pr-4 text-slate-700">{formatMs(job.duration_ms)}</td>
                    <td className="py-3 pr-4 font-mono text-xs text-slate-500">{job.job_id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
