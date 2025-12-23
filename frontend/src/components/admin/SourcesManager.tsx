import { useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  deleteAdminSource,
  fetchAdminSources,
  upsertAdminSource,
  type AdminSourcePayload,
  type AdminSourceUpsertRequestPayload,
} from '../../services/apiClient'

const normalizeTags = (raw: string) =>
  raw
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean)

const formatTags = (tags: string[] | undefined) => (tags && tags.length > 0 ? tags.join(', ') : '')

const nowIsoDate = () => new Date().toISOString().slice(0, 10)

export function SourcesManager() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null)
  const [status, setStatus] = useState<{ tone: 'info' | 'error'; message: string } | null>(null)
  const [busy, setBusy] = useState(false)

  const sourcesQuery = useQuery<AdminSourcePayload[], Error>({
    queryKey: ['admin-sources'],
    queryFn: fetchAdminSources,
    staleTime: 1000 * 15,
  })

  const sources = sourcesQuery.data ?? []
  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase()
    if (!term) return sources
    return sources.filter((s) => {
      const hay = `${s.doc_id} ${s.source_name} ${s.language} ${s.domain ?? ''} ${s.url ?? ''} ${(s.tags ?? []).join(' ')}`
      return hay.toLowerCase().includes(term)
    })
  }, [sources, search])

  const selected = useMemo(
    () => (selectedDocId ? sources.find((s) => s.doc_id === selectedDocId) ?? null : null),
    [sources, selectedDocId],
  )

  const [draft, setDraft] = useState<AdminSourceUpsertRequestPayload>({
    doc_id: '',
    source_name: '',
    language: 'en',
    domain: '',
    freshness: nowIsoDate(),
    url: '',
    tags: [],
    description: '',
  })
  const [draftTags, setDraftTags] = useState('')

  const loadDraftFromSelected = (source: AdminSourcePayload | null) => {
    if (!source) {
      setDraft({
        doc_id: '',
        source_name: '',
        language: 'en',
        domain: '',
        freshness: nowIsoDate(),
        url: '',
        tags: [],
        description: '',
      })
      setDraftTags('')
      return
    }
    setDraft({
      doc_id: source.doc_id,
      source_name: source.source_name,
      language: source.language,
      domain: source.domain ?? '',
      freshness: source.freshness ?? '',
      url: source.url ?? '',
      tags: source.tags ?? [],
      description: source.description ?? '',
    })
    setDraftTags(formatTags(source.tags))
  }

  const handleSelect = (docId: string) => {
    setSelectedDocId(docId)
    const source = sources.find((s) => s.doc_id === docId) ?? null
    loadDraftFromSelected(source)
    setStatus(null)
  }

  const handleNew = () => {
    setSelectedDocId(null)
    loadDraftFromSelected(null)
    setStatus(null)
  }

  const save = async () => {
    if (!draft.doc_id.trim() || !draft.source_name.trim() || !draft.language.trim()) {
      setStatus({ tone: 'error', message: 'doc_id, source_name, and language are required.' })
      return
    }
    setBusy(true)
    setStatus(null)
    try {
      const payload: AdminSourceUpsertRequestPayload = {
        ...draft,
        doc_id: draft.doc_id.trim(),
        source_name: draft.source_name.trim(),
        language: draft.language.trim(),
        domain: draft.domain?.trim() || null,
        freshness: draft.freshness?.trim() || null,
        url: draft.url?.trim() || null,
        tags: normalizeTags(draftTags),
        description: draft.description?.trim() || null,
      }
      const result = await upsertAdminSource(payload)
      await queryClient.invalidateQueries({ queryKey: ['admin-sources'] })
      await queryClient.invalidateQueries({ queryKey: ['admin-config'] })
      setSelectedDocId(result.source.doc_id)
      setStatus({ tone: 'info', message: `Saved ${result.source.doc_id}` })
    } catch (e) {
      setStatus({ tone: 'error', message: e instanceof Error ? e.message : 'Unable to save source.' })
    } finally {
      setBusy(false)
    }
  }

  const remove = async (docId: string) => {
    const ok = typeof window === 'undefined' ? true : window.confirm(`Delete source "${docId}"?`)
    if (!ok) return
    setBusy(true)
    setStatus(null)
    try {
      await deleteAdminSource(docId)
      await queryClient.invalidateQueries({ queryKey: ['admin-sources'] })
      await queryClient.invalidateQueries({ queryKey: ['admin-config'] })
      if (selectedDocId === docId) {
        handleNew()
      }
      setStatus({ tone: 'info', message: `Deleted ${docId}` })
    } catch (e) {
      setStatus({ tone: 'error', message: e instanceof Error ? e.message : 'Unable to delete source.' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mt-4 grid gap-6 lg:grid-cols-2">
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-900">Sources</h3>
            <p className="mt-1 text-xs text-slate-500">Backed by /v1/admin/sources</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="rounded-full border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:border-slate-400"
              onClick={() => void sourcesQuery.refetch()}
              disabled={sourcesQuery.isLoading}
            >
              Refresh
            </button>
            <button
              type="button"
              className="rounded-full border border-slate-900 bg-slate-900 px-4 py-2 text-xs font-semibold text-white hover:bg-slate-800"
              onClick={handleNew}
            >
              + New
            </button>
          </div>
        </div>

        <div className="mt-4">
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by doc_id, name, language, domain, url, tags…"
            className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-slate-200"
          />
        </div>

        {sourcesQuery.isLoading ? <p className="mt-4 text-sm text-slate-500">Loading…</p> : null}
        {sourcesQuery.error ? <p className="mt-4 text-sm text-rose-600">{sourcesQuery.error.message}</p> : null}

        <div className="mt-4 overflow-auto">
          <table className="min-w-[720px] w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-slate-400">
              <tr>
                <th className="py-2">doc_id</th>
                <th className="py-2">source_name</th>
                <th className="py-2">lang</th>
                <th className="py-2">domain</th>
                <th className="py-2">freshness</th>
                <th className="py-2">updated</th>
                <th className="py-2">actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.map((s) => {
                const active = s.doc_id === selectedDocId
                return (
                  <tr key={s.doc_id} className={active ? 'bg-slate-50' : ''}>
                    <td className="py-2 font-medium text-slate-900">
                      <button type="button" className="underline" onClick={() => handleSelect(s.doc_id)}>
                        {s.doc_id}
                      </button>
                    </td>
                    <td className="py-2 text-slate-700">{s.source_name}</td>
                    <td className="py-2 text-slate-700">{s.language}</td>
                    <td className="py-2 text-slate-700">{s.domain ?? '-'}</td>
                    <td className="py-2 text-slate-700">{s.freshness ?? '-'}</td>
                    <td className="py-2 text-slate-500">
                      {s.last_updated_at ? new Date(s.last_updated_at).toLocaleString() : '-'}
                    </td>
                    <td className="py-2">
                      <button
                        type="button"
                        className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-1 text-xs font-semibold text-rose-700 hover:border-rose-300"
                        onClick={() => void remove(s.doc_id)}
                        disabled={busy}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                )
              })}
              {filtered.length === 0 && !sourcesQuery.isLoading ? (
                <tr>
                  <td colSpan={7} className="py-6 text-center text-sm text-slate-500">
                    No sources found.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-900">{selected ? `Edit: ${selected.doc_id}` : 'Create source'}</h3>
            <p className="mt-1 text-xs text-slate-500">Creates or updates the document metadata used by retrieval/citations.</p>
          </div>
          <button
            type="button"
            className="rounded-full border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:border-slate-400"
            onClick={() => loadDraftFromSelected(selected)}
            disabled={busy}
          >
            Revert
          </button>
        </div>

        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <Field label="doc_id *">
            <input
              value={draft.doc_id}
              onChange={(e) => setDraft((prev) => ({ ...prev, doc_id: e.target.value }))}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              placeholder="visa_requirements"
              disabled={busy}
            />
          </Field>
          <Field label="language *">
            <select
              value={draft.language}
              onChange={(e) => setDraft((prev) => ({ ...prev, language: e.target.value }))}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              disabled={busy}
            >
              <option value="en">en</option>
              <option value="zh">zh</option>
              <option value="auto">auto</option>
            </select>
          </Field>
          <Field label="source_name *">
            <input
              value={draft.source_name}
              onChange={(e) => setDraft((prev) => ({ ...prev, source_name: e.target.value }))}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              placeholder="visa_requirements"
              disabled={busy}
            />
          </Field>
          <Field label="domain">
            <input
              value={draft.domain ?? ''}
              onChange={(e) => setDraft((prev) => ({ ...prev, domain: e.target.value }))}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              placeholder="visa / admissions / fees / scholarship"
              disabled={busy}
            />
          </Field>
          <Field label="freshness">
            <input
              value={draft.freshness ?? ''}
              onChange={(e) => setDraft((prev) => ({ ...prev, freshness: e.target.value }))}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              placeholder="2025-01-01"
              disabled={busy}
            />
          </Field>
          <Field label="url">
            <input
              value={draft.url ?? ''}
              onChange={(e) => setDraft((prev) => ({ ...prev, url: e.target.value }))}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              placeholder="https://example.edu/visa"
              disabled={busy}
            />
          </Field>
          <Field label="tags (comma separated)">
            <input
              value={draftTags}
              onChange={(e) => setDraftTags(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              placeholder="policy, official"
              disabled={busy}
            />
          </Field>
          <div className="sm:col-span-2">
            <Field label="description">
              <textarea
                value={draft.description ?? ''}
                onChange={(e) => setDraft((prev) => ({ ...prev, description: e.target.value }))}
                className="h-28 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                placeholder="Short description shown in admin lists."
                disabled={busy}
              />
            </Field>
          </div>
        </div>

        {status ? (
          <p className={`mt-4 text-sm ${status.tone === 'error' ? 'text-rose-600' : 'text-slate-600'}`}>{status.message}</p>
        ) : null}

        <div className="mt-4 flex items-center gap-3">
          <button
            type="button"
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
            onClick={() => void save()}
            disabled={busy}
          >
            Save
          </button>
          {selected ? (
            <button
              type="button"
              className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-2 text-sm font-semibold text-rose-700 hover:border-rose-300 disabled:opacity-50"
              onClick={() => void remove(selected.doc_id)}
              disabled={busy}
            >
              Delete
            </button>
          ) : null}
        </div>
      </section>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block text-sm text-slate-700">
      <span className="text-xs uppercase tracking-wide text-slate-500">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  )
}



