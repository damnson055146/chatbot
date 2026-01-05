import { useMemo, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { resolveApiUrl } from '../../utils/url'

export interface HighlightSpanPayload {
  start: number
  end: number
}

export interface ChunkDetailPayload {
  chunk_id: string
  doc_id: string
  text: string
  last_verified_at?: string | null
  highlights?: HighlightSpanPayload[]
  metadata?: Record<string, unknown>
}

export interface AttachmentPreviewPayload {
  upload_id: string
  filename: string
  mime_type: string
  size_bytes: number
  preview_url?: string | null
  download_url?: string | null
  text_excerpt?: string | null
  expires_at?: string | null
}

function renderHighlightedText(text: string, highlights: HighlightSpanPayload[]) {
  if (!highlights.length) return text
  const sorted = [...highlights].sort((a, b) => a.start - b.start)
  const nodes: ReactNode[] = []
  let cursor = 0
  for (const span of sorted) {
    const start = Math.max(0, Math.min(text.length, span.start))
    const end = Math.max(0, Math.min(text.length, span.end))
    if (end <= start) continue
    if (start > cursor) nodes.push(text.slice(cursor, start))
    nodes.push(
      <mark key={`${start}-${end}`} className="rounded bg-amber-100 px-1 py-0.5 text-slate-900">
        {text.slice(start, end)}
      </mark>,
    )
    cursor = end
  }
  if (cursor < text.length) nodes.push(text.slice(cursor))
  return nodes
}

interface ContextRailProps {
  isOpen: boolean
  title?: string
  isLoading?: boolean
  error?: string | null
  chunk?: ChunkDetailPayload | null
  attachment?: AttachmentPreviewPayload | null
  citationScore?: number | null
  onClose: () => void
}

export function ContextRail({
  isOpen,
  title = 'Context',
  isLoading,
  error,
  chunk,
  attachment,
  citationScore,
  onClose,
}: ContextRailProps) {
  const { t } = useTranslation()
  const highlightSpans = useMemo(() => chunk?.highlights ?? [], [chunk])
  const previewUrl = resolveApiUrl(attachment?.preview_url)
  const downloadUrl = resolveApiUrl(attachment?.download_url)
  const attachmentOpenUrl = previewUrl || downloadUrl || null
  const formattedScore = Number.isFinite(citationScore ?? NaN) ? (citationScore as number).toFixed(2) : null
  return (
    <aside
      className={`fixed inset-y-0 right-0 z-40 w-full max-w-md border-l border-slate-200 bg-white shadow-2xl ${
        isOpen ? 'block xl:static xl:z-auto xl:w-[380px] xl:max-w-none xl:shadow-none' : 'hidden'
      }`}
    >
      <div className="flex h-full flex-col">
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-4">
          <div>
            <p className="text-[11px] uppercase tracking-[0.4em] text-slate-400">{t('chat.context_rail')}</p>
            <h2 className="mt-1 text-sm font-semibold text-slate-900">{title}</h2>
          </div>
          <button
            type="button"
            className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-700 hover:border-slate-400"
            onClick={onClose}
            aria-label={t('chat.close')}
          >
            {t('chat.close')}
          </button>
        </div>

        <div className="flex-1 overflow-y-auto overscroll-contain px-5 py-4">
          {isLoading ? (
            <p className="text-sm text-slate-500">{t('chat.loading_passage')}</p>
          ) : error ? (
            <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p>
          ) : attachment ? (
            <div className="space-y-4">
              <div className="rounded-3xl border border-slate-200 bg-slate-50 px-4 py-3">
                <p className="text-xs font-semibold uppercase tracking-[0.35em] text-slate-400">{t('chat.attachments')}</p>
                <p className="mt-2 text-sm font-semibold text-slate-800">{attachment.filename}</p>
                <p className="mt-1 text-xs text-slate-500">
                  {Math.round(attachment.size_bytes / 1024)} KB · {attachment.mime_type}
                </p>
                {attachmentOpenUrl ? (
                  <a
                    className="mt-2 inline-flex text-[11px] font-medium text-slate-900 underline"
                    href={attachmentOpenUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {t('chat.attachment.view')}
                  </a>
                ) : null}
              </div>
              <div className="rounded-3xl border border-slate-200 bg-white px-4 py-4">
                <p className="text-xs font-semibold uppercase tracking-[0.35em] text-slate-400">{t('chat.attachment.preview')}</p>
                {previewUrl && attachment.mime_type.startsWith('image/') ? (
                  <img
                    src={previewUrl}
                    alt={attachment.filename}
                    className="mt-3 w-full rounded-2xl border border-slate-200"
                  />
                ) : previewUrl && attachment.mime_type === 'application/pdf' ? (
                  <iframe
                    title={attachment.filename}
                    src={previewUrl}
                    className="mt-3 h-80 w-full rounded-2xl border border-slate-200"
                  />
                ) : attachment.text_excerpt ? (
                  <p className="mt-3 whitespace-pre-line text-sm leading-6 text-slate-800">{attachment.text_excerpt}</p>
                ) : (
                  <p className="mt-3 text-sm text-slate-500">{t('chat.attachment.preview_unavailable')}</p>
                )}
              </div>
            </div>
          ) : chunk ? (
            <div className="space-y-4">
              <div className="rounded-3xl border border-slate-200 bg-slate-50 px-4 py-3">
                <p className="text-xs font-semibold uppercase tracking-[0.35em] text-slate-400">{t('chat.context.chunk')}</p>
                <p className="mt-2 text-sm font-semibold text-slate-800">
                  {chunk.doc_id} · {chunk.chunk_id}
                </p>
                {formattedScore ? (
                  <p className="mt-1 text-xs text-slate-500">{t('chat.rerank_score')}: {formattedScore}</p>
                ) : null}
                {chunk.last_verified_at ? (
                  <p className="mt-1 text-xs text-slate-500">
                    {t('chat.last_verified', { date: new Date(chunk.last_verified_at).toLocaleDateString() })}
                  </p>
                ) : null}
              </div>
              <div className="rounded-3xl border border-slate-200 bg-white px-4 py-4">
                <p className="text-xs font-semibold uppercase tracking-[0.35em] text-slate-400">{t('chat.passage')}</p>
                <p className="mt-3 whitespace-pre-line text-sm leading-6 text-slate-800">
                  {renderHighlightedText(chunk.text, highlightSpans)}
                </p>
              </div>
            </div>
          ) : (
            <p className="text-sm text-slate-500">{t('chat.select_citation')}</p>
          )}
        </div>
      </div>
    </aside>
  )
}

export default ContextRail
