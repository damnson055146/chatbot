import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  deleteAdminSource,
  fetchAdminSources,
  ingestUpload,
  uploadAttachment,
  upsertAdminSource,
  verifyAdminSource,
  type AdminSourcePayload,
} from '../../services/apiClient'

const SUPPORTED_UPLOAD_ACCEPT = [
  'application/pdf',
  'text/plain',
  'text/markdown',
  'image/png',
  'image/jpeg',
  'image/webp',
  'audio/mpeg',
  'audio/mp4',
  'audio/wav',
  'audio/webm',
  'audio/ogg',
  'audio/aac',
  'audio/x-m4a',
  '.txt',
  '.md',
].join(',')

const MAX_CONCURRENT_INGEST = 3

type UploadStatus = 'queued' | 'uploading' | 'ingesting' | 'ready' | 'error'

type UploadItem = {
  id: string
  filename: string
  sizeBytes: number
  status: UploadStatus
  uploadId?: string
  domain: string
  freshness: string
  tags: string
  error?: string
}

type SourceDraft = {
  doc_id: string
  source_name: string
  language: string
  domain: string
  freshness: string
  url: string
  tags: string
  description: string
}

const normalizeTags = (raw: string) =>
  raw
    .split(',')
    .map((tag) => tag.trim())
    .filter(Boolean)

const formatBytes = (bytes: number) => {
  if (!Number.isFinite(bytes)) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let value = bytes
  let idx = 0
  while (value >= 1024 && idx < units.length - 1) {
    value /= 1024
    idx += 1
  }
  const rounded = value >= 10 ? Math.round(value) : Math.round(value * 10) / 10
  return `${rounded} ${units[idx]}`
}

export function SourcesManager({ readOnly = false }: { readOnly?: boolean }) {
  const { t, i18n } = useTranslation()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<{ tone: 'info' | 'error'; message: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null)
  const defaultLanguage = (i18n.language ?? '').toLowerCase().startsWith('zh') ? 'zh' : 'en'
  const [draft, setDraft] = useState<SourceDraft>({
    doc_id: '',
    source_name: '',
    language: defaultLanguage,
    domain: '',
    freshness: '',
    url: '',
    tags: '',
    description: '',
  })
  const [uploads, setUploads] = useState<UploadItem[]>([])
  const [dragActive, setDragActive] = useState(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const inflightRef = useRef<Set<string>>(new Set())
  const uploadsRef = useRef<UploadItem[]>([])
  const pillButtonClass = [
    'rounded-full border border-slate-300 bg-white px-4 py-2',
    'text-xs font-semibold text-slate-700 hover:border-slate-400 disabled:opacity-50',
  ].join(' ')
  const dangerButtonClass = [
    'rounded-lg border border-rose-200 bg-rose-50 px-3 py-1',
    'text-xs font-semibold text-rose-700 hover:border-rose-300 disabled:opacity-50',
  ].join(' ')
  const compactButtonClass = [
    'rounded-lg border border-slate-300 bg-white px-3 py-1',
    'text-xs font-semibold text-slate-700 hover:border-slate-400 disabled:opacity-50',
  ].join(' ')
  const searchInputClass = [
    'w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm',
    'focus:outline-none focus:ring-2 focus:ring-slate-200',
  ].join(' ')

  const sourcesQuery = useQuery<AdminSourcePayload[], Error>({
    queryKey: ['admin-sources'],
    queryFn: fetchAdminSources,
    staleTime: 1000 * 15,
  })

  const sources = sourcesQuery.data ?? []
  const hasQueuedUploads = uploads.some((item) => item.status === 'queued' && item.uploadId)
  const isIngesting = uploads.some((item) => item.status === 'ingesting')
  const selectedSource = useMemo(
    () => (selectedDocId ? sources.find((source) => source.doc_id === selectedDocId) ?? null : null),
    [sources, selectedDocId],
  )
  const isEditing = Boolean(selectedDocId)
  const dropZoneClassName = [
    'mt-4 flex min-h-[160px] cursor-pointer flex-col items-center justify-center rounded-2xl',
    'border-2 border-dashed px-4 py-6 text-center transition',
    dragActive ? 'border-slate-500 bg-slate-50' : 'border-slate-200',
    readOnly ? 'cursor-not-allowed opacity-60' : '',
  ]
    .filter(Boolean)
    .join(' ')
  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase()
    if (!term) return sources
    return sources.filter((s) => {
      const hay = `${s.doc_id} ${s.source_name} ${s.language} ${s.domain ?? ''} ${s.url ?? ''} ${s.description ?? ''} ${(s.tags ?? []).join(' ')}`
      return hay.toLowerCase().includes(term)
    })
  }, [sources, search])

  const refreshSources = async () => {
    await queryClient.invalidateQueries({ queryKey: ['admin-sources'] })
    await queryClient.invalidateQueries({ queryKey: ['admin-config'] })
  }

  const toDraft = (source: AdminSourcePayload): SourceDraft => ({
    doc_id: source.doc_id,
    source_name: source.source_name,
    language: source.language,
    domain: source.domain ?? '',
    freshness: source.freshness ?? '',
    url: source.url ?? '',
    tags: (source.tags ?? []).join(', '),
    description: source.description ?? '',
  })

  const resetDraft = () => {
    setSelectedDocId(null)
    setDraft({
      doc_id: '',
      source_name: '',
      language: defaultLanguage,
      domain: '',
      freshness: '',
      url: '',
      tags: '',
      description: '',
    })
  }

  const updateUpload = useCallback((id: string, update: Partial<UploadItem>) => {
    setUploads((prev) => prev.map((item) => (item.id === id ? { ...item, ...update } : item)))
  }, [])

  const selectSource = (source: AdminSourcePayload) => {
    setSelectedDocId(source.doc_id)
    setDraft(toDraft(source))
    setStatus(null)
  }

  const startIngest = useCallback(
    async (itemId: string) => {
      const current = uploadsRef.current.find((item) => item.id === itemId)
      if (!current?.uploadId) return
      if (inflightRef.current.has(itemId)) return
      inflightRef.current.add(itemId)
      updateUpload(itemId, { status: 'ingesting', error: undefined })
      try {
        await ingestUpload({
          upload_id: current.uploadId,
          source_name: current.filename,
          domain: current.domain.trim() || undefined,
          freshness: current.freshness.trim() || undefined,
          tags: normalizeTags(current.tags),
        })
        updateUpload(itemId, { status: 'ready' })
        await refreshSources()
      } catch (error) {
        updateUpload(itemId, {
          status: 'error',
          error: error instanceof Error ? error.message : t('admin.sources.upload_error'),
        })
      } finally {
        inflightRef.current.delete(itemId)
      }
    },
    [refreshSources, t, updateUpload],
  )

  const runQueue = useCallback(() => {
    if (readOnly) return
    const inflightCount = inflightRef.current.size
    const available = MAX_CONCURRENT_INGEST - inflightCount
    if (available <= 0) return
    const queued = uploadsRef.current.filter(
      (item) => item.status === 'queued' && item.uploadId && !inflightRef.current.has(item.id),
    )
    queued.slice(0, available).forEach((item) => {
      void startIngest(item.id)
    })
  }, [readOnly, startIngest])

  useEffect(() => {
    uploadsRef.current = uploads
    runQueue()
  }, [uploads, runQueue])

  const handleFiles = async (files: FileList | File[]) => {
    if (readOnly) return
    const list = Array.from(files)
    if (!list.length) return
    setStatus(null)

    for (const file of list) {
      const id = `upload-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      const entry: UploadItem = {
        id,
        filename: file.name,
        sizeBytes: file.size,
        status: 'uploading',
        domain: '',
        freshness: '',
        tags: '',
      }
      setUploads((prev) => [...prev, entry])

      try {
        const uploaded = await uploadAttachment(file, undefined, 'rag')
        updateUpload(id, { status: 'queued', uploadId: uploaded.upload_id })
      } catch (error) {
        updateUpload(id, {
          status: 'error',
          error: error instanceof Error ? error.message : t('admin.sources.upload_error'),
        })
      }
    }
  }

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    setDragActive(false)
    if (readOnly) return
    if (event.dataTransfer.files && event.dataTransfer.files.length > 0) {
      void handleFiles(event.dataTransfer.files)
    }
  }

  const handleDragOver = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    if (!readOnly) setDragActive(true)
  }

  const handleDragLeave = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragActive(false)
  }

  const handlePickFiles = () => {
    if (readOnly) return
    fileInputRef.current?.click()
  }

  const handleRetry = (itemId: string) => {
    if (readOnly) return
    updateUpload(itemId, { status: 'queued', error: undefined })
  }

  const handleIngestAll = () => {
    if (readOnly) return
    runQueue()
  }

  const saveSource = async () => {
    if (readOnly) return
    if (!draft.doc_id.trim() || !draft.source_name.trim() || !draft.language.trim()) {
      setStatus({ tone: 'error', message: t('admin.sources.error.required') })
      return
    }
    setBusy(true)
    setStatus(null)
    try {
      const res = await upsertAdminSource({
        doc_id: draft.doc_id.trim(),
        source_name: draft.source_name.trim(),
        language: draft.language.trim(),
        domain: draft.domain.trim() || undefined,
        freshness: draft.freshness.trim() || undefined,
        url: draft.url.trim() || undefined,
        tags: normalizeTags(draft.tags),
        description: draft.description.trim() || undefined,
      })
      await refreshSources()
      setSelectedDocId(res.source.doc_id)
      setDraft(toDraft(res.source))
      setStatus({ tone: 'info', message: t('admin.sources.status.saved', { id: res.source.doc_id }) })
    } catch (error) {
      setStatus({ tone: 'error', message: error instanceof Error ? error.message : t('admin.sources.error.save') })
    } finally {
      setBusy(false)
    }
  }

  const verifySource = async () => {
    if (readOnly || !selectedDocId) return
    setBusy(true)
    setStatus(null)
    try {
      const res = await verifyAdminSource(selectedDocId)
      await refreshSources()
      setStatus({
        tone: 'info',
        message: t('admin.sources.status.verified', {
          id: res.doc_id,
          time: new Date(res.verified_at).toLocaleString(),
        }),
      })
    } catch (error) {
      setStatus({ tone: 'error', message: error instanceof Error ? error.message : t('admin.sources.error.verify') })
    } finally {
      setBusy(false)
    }
  }

  const remove = async (docId: string): Promise<boolean> => {
    if (readOnly) return
    const ok = typeof window === 'undefined' ? true : window.confirm(t('admin.sources.delete_confirm', { id: docId }))
    if (!ok) return false
    setBusy(true)
    setStatus(null)
    try {
      await deleteAdminSource(docId)
      await refreshSources()
      setStatus({ tone: 'info', message: t('admin.sources.status.deleted', { id: docId }) })
      return true
    } catch (e) {
      setStatus({ tone: 'error', message: e instanceof Error ? e.message : t('admin.sources.error.delete') })
      return false
    } finally {
      setBusy(false)
    }
  }

  const uploadStatusLabel = (item: UploadItem) => {
    switch (item.status) {
      case 'uploading':
        return t('admin.sources.upload.status.uploading')
      case 'ingesting':
        return t('admin.sources.upload.status.ingesting')
      case 'ready':
        return t('admin.sources.upload.status.ready')
      case 'error':
        return t('admin.sources.upload.status.error')
      default:
        return t('admin.sources.upload.status.queued')
    }
  }

  return (
    <div className="mt-4 grid gap-6 lg:grid-cols-2">
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-900">{t('admin.sources.title')}</h3>
            <p className="mt-1 text-xs text-slate-500">
              {t('admin.sources.subtitle', { endpoint: '/v1/admin/sources' })}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className={pillButtonClass}
              onClick={() => void sourcesQuery.refetch()}
              disabled={sourcesQuery.isLoading}
            >
              {t('common.refresh')}
            </button>
            <button
              type="button"
              className={pillButtonClass}
              onClick={resetDraft}
              disabled={readOnly}
            >
              {t('admin.sources.action.new')}
            </button>
          </div>
        </div>

        <div className="mt-4">
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('admin.sources.search_placeholder')}
            className={searchInputClass}
          />
        </div>

        {sourcesQuery.isLoading ? <p className="mt-4 text-sm text-slate-500">{t('common.loading')}</p> : null}
        {sourcesQuery.error ? (
          <p className="mt-4 text-sm text-rose-600">{sourcesQuery.error.message}</p>
        ) : null}

        <div className="mt-4 overflow-auto">
          <table className="min-w-[720px] w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-slate-400">
              <tr>
                <th className="py-2">{t('admin.sources.table.doc_id')}</th>
                <th className="py-2">{t('admin.sources.table.source_name')}</th>
                <th className="py-2">{t('admin.sources.table.lang')}</th>
                <th className="py-2">{t('admin.sources.table.domain')}</th>
                <th className="py-2">{t('admin.sources.table.freshness')}</th>
                <th className="py-2">{t('admin.sources.table.updated')}</th>
                <th className="sticky right-0 bg-white py-2 pl-3 text-right">{t('admin.sources.table.actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.map((s) => (
                <tr key={s.doc_id}>
                  <td className="py-2 font-medium text-slate-900">{s.doc_id}</td>
                  <td className="py-2 text-slate-700">{s.source_name}</td>
                  <td className="py-2 text-slate-700">{s.language}</td>
                  <td className="py-2 text-slate-700">{s.domain ?? '-'}</td>
                  <td className="py-2 text-slate-700">{s.freshness ?? '-'}</td>
                  <td className="py-2 text-slate-500">
                    {s.last_updated_at ? new Date(s.last_updated_at).toLocaleString() : '-'}
                  </td>
                  <td className="sticky right-0 bg-white py-2 pl-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        type="button"
                        className={compactButtonClass}
                        onClick={() => selectSource(s)}
                        disabled={readOnly}
                      >
                        {t('admin.sources.action.edit')}
                      </button>
                      <button
                        type="button"
                        className={dangerButtonClass}
                        onClick={() => void remove(s.doc_id)}
                        disabled={busy || readOnly}
                      >
                        {t('common.delete')}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && !sourcesQuery.isLoading ? (
                <tr>
                  <td colSpan={7} className="py-6 text-center text-sm text-slate-500">
                    {t('admin.sources.none')}
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        <div className="mt-6 border-t border-slate-200 pt-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.35em] text-slate-400">
                {isEditing ? t('admin.sources.edit_title') : t('admin.sources.create_title')}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                {selectedSource?.last_updated_at
                  ? t('admin.sources.last_updated', { time: new Date(selectedSource.last_updated_at).toLocaleString() })
                  : t('admin.sources.edit_hint')}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {selectedDocId ? (
                <button
                  type="button"
                  className={compactButtonClass}
                  onClick={verifySource}
                  disabled={busy || readOnly}
                >
                  {t('admin.sources.action.verify')}
                </button>
              ) : null}
              {selectedDocId ? (
                <button
                  type="button"
                  className={dangerButtonClass}
                  onClick={async () => {
                    if (!selectedDocId) return
                    const deleted = await remove(selectedDocId)
                    if (deleted) resetDraft()
                  }}
                  disabled={busy || readOnly}
                >
                  {t('admin.sources.action.delete_doc')}
                </button>
              ) : null}
              <button
                type="button"
                className={pillButtonClass}
                onClick={saveSource}
                disabled={busy || readOnly}
              >
                {t('common.save')}
              </button>
            </div>
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <Field label={t('admin.sources.field.doc_id')}>
              <input
                value={draft.doc_id}
                onChange={(event) => setDraft((prev) => ({ ...prev, doc_id: event.target.value }))}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                placeholder={t('admin.sources.field.doc_id_placeholder')}
                disabled={readOnly || isEditing}
              />
            </Field>
            <Field label={t('admin.sources.field.source_name')}>
              <input
                value={draft.source_name}
                onChange={(event) => setDraft((prev) => ({ ...prev, source_name: event.target.value }))}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                placeholder={t('admin.sources.field.source_name_placeholder')}
                disabled={readOnly}
              />
            </Field>
            <Field label={t('admin.sources.field.language')}>
              <input
                value={draft.language}
                onChange={(event) => setDraft((prev) => ({ ...prev, language: event.target.value }))}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                placeholder={t('admin.sources.field.language_placeholder')}
                disabled={readOnly}
              />
            </Field>
            <Field label={t('admin.sources.field.domain')}>
              <input
                value={draft.domain}
                onChange={(event) => setDraft((prev) => ({ ...prev, domain: event.target.value }))}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                placeholder={t('admin.sources.field.domain_placeholder')}
                disabled={readOnly}
              />
            </Field>
            <Field label={t('admin.sources.field.freshness')}>
              <input
                type="date"
                value={draft.freshness}
                onChange={(event) => setDraft((prev) => ({ ...prev, freshness: event.target.value }))}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                disabled={readOnly}
              />
            </Field>
            <Field label={t('admin.sources.field.url')}>
              <input
                value={draft.url}
                onChange={(event) => setDraft((prev) => ({ ...prev, url: event.target.value }))}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                placeholder={t('admin.sources.field.url_placeholder')}
                disabled={readOnly}
              />
            </Field>
            <Field label={t('admin.sources.field.tags')} className="sm:col-span-2">
              <input
                value={draft.tags}
                onChange={(event) => setDraft((prev) => ({ ...prev, tags: event.target.value }))}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                placeholder={t('admin.sources.field.tags_placeholder')}
                disabled={readOnly}
              />
            </Field>
            <Field label={t('admin.sources.field.description')} className="sm:col-span-2">
              <textarea
                value={draft.description}
                onChange={(event) => setDraft((prev) => ({ ...prev, description: event.target.value }))}
                className="min-h-[96px] w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                placeholder={t('admin.sources.field.description_placeholder')}
                disabled={readOnly}
              />
            </Field>
          </div>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-900">{t('admin.sources.upload_title')}</h3>
            <p className="mt-1 text-xs text-slate-500">{t('admin.sources.upload_subtitle')}</p>
          </div>
          <button
            type="button"
            className={pillButtonClass}
            onClick={handleIngestAll}
            disabled={readOnly || !hasQueuedUploads}
          >
            {t('admin.sources.upload_ingest_all')}
          </button>
        </div>

        <div
          role="button"
          tabIndex={readOnly ? -1 : 0}
          className={dropZoneClassName}
          onClick={handlePickFiles}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault()
              handlePickFiles()
            }
          }}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept={SUPPORTED_UPLOAD_ACCEPT}
            multiple
            className="hidden"
            onChange={(event) => {
              if (event.target.files) {
                void handleFiles(event.target.files)
                event.target.value = ''
              }
            }}
            disabled={readOnly}
          />
          <p className="text-sm font-semibold text-slate-700">
            {dragActive ? t('admin.sources.upload_drop') : t('admin.sources.upload_action')}
          </p>
          <p className="mt-2 text-xs text-slate-500">{t('admin.sources.upload_support')}</p>
        </div>

        {uploads.length > 0 ? (
          <div className="mt-4 space-y-3">
            {uploads.map((item) => (
              <div key={item.id} className="rounded-xl border border-slate-100 bg-slate-50 px-4 py-3 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate font-medium text-slate-800">{item.filename}</p>
                    <p className="mt-1 text-xs text-slate-500">{formatBytes(item.sizeBytes)}</p>
                  </div>
                  <span className="text-xs uppercase tracking-wide text-slate-500">{uploadStatusLabel(item)}</span>
                </div>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <Field label={t('admin.sources.upload_meta.domain')}>
                    <input
                      value={item.domain}
                      onChange={(event) => updateUpload(item.id, { domain: event.target.value })}
                      className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                      placeholder={t('admin.sources.upload_meta.domain_placeholder')}
                      disabled={readOnly || item.status === 'ingesting' || item.status === 'ready'}
                    />
                  </Field>
                  <Field label={t('admin.sources.upload_meta.freshness')}>
                    <input
                      type="date"
                      value={item.freshness}
                      onChange={(event) => updateUpload(item.id, { freshness: event.target.value })}
                      className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                      disabled={readOnly || item.status === 'ingesting' || item.status === 'ready'}
                    />
                  </Field>
                  <Field label={t('admin.sources.upload_meta.tags')} className="sm:col-span-2">
                    <input
                      value={item.tags}
                      onChange={(event) => updateUpload(item.id, { tags: event.target.value })}
                      className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                      placeholder={t('admin.sources.upload_meta.tags_placeholder')}
                      disabled={readOnly || item.status === 'ingesting' || item.status === 'ready'}
                    />
                  </Field>
                </div>
                <div className="mt-3 flex items-center gap-2">
                  {item.status === 'error' && item.uploadId ? (
                    <button
                      type="button"
                      className={compactButtonClass}
                      onClick={() => handleRetry(item.id)}
                      disabled={readOnly || isIngesting}
                    >
                      {t('admin.sources.upload_retry')}
                    </button>
                  ) : null}
                  {item.status === 'ready' ? (
                    <span className="text-xs font-semibold text-emerald-600">{t('admin.sources.upload_done')}</span>
                  ) : null}
                </div>
                {item.error ? <p className="mt-2 text-xs text-rose-600">{item.error}</p> : null}
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-4 text-xs text-slate-500">{t('admin.sources.upload_empty')}</p>
        )}

        {status ? (
          <p className={`mt-4 text-sm ${status.tone === 'error' ? 'text-rose-600' : 'text-slate-600'}`}>
            {status.message}
          </p>
        ) : null}
      </section>
    </div>
  )
}

function Field({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <label className={`block text-sm text-slate-700 ${className ?? ''}`}>
      <span className="text-xs uppercase tracking-wide text-slate-500">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  )
}

export default SourcesManager
