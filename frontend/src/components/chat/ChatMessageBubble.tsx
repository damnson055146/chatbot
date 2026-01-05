import { AssistantAvatar } from './AssistantAvatar'
import type { ChatMessageModel, MessageAttachment } from './types'
import { useTranslation } from 'react-i18next'
import type { AssistantProfileConfig } from '../../utils/assistantProfile'
import { resolveApiUrl } from '../../utils/url'

interface ChatMessageBubbleProps {
  message: ChatMessageModel
  onCopy?: (content: string) => void
  onRetry?: (message: ChatMessageModel) => void
  onCitationClick?: (citation: NonNullable<ChatMessageModel['citations']>[number], message: ChatMessageModel) => void
  onAttachmentPreview?: (attachment: MessageAttachment, message: ChatMessageModel) => void
  onEscalate?: (message: ChatMessageModel) => void
  showCitationSources?: boolean
  assistantName?: string
  assistantAvatar?: AssistantProfileConfig['avatar']
  userDisplayName?: string
  userAvatarColor?: string
}

const CopyIcon = () => (
  <svg className="h-4 w-4" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
    <path d="M7 5h7a2 2 0 0 1 2 2v7" strokeLinecap="round" strokeLinejoin="round" />
    <rect x="4" y="8" width="8" height="8" rx="2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

const RetryIcon = () => (
  <svg className="h-4 w-4" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
    <path d="M4 9a6 6 0 1 1 1.757 4.243" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M4 13.5v-4.5h4.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

const getInitial = (value: string | undefined, fallback: string) => {
  if (!value) return fallback
  const trimmed = value.trim()
  return trimmed ? trimmed[0]?.toUpperCase() ?? fallback : fallback
}

export function ChatMessageBubble({
  message,
  onCopy,
  onRetry,
  onCitationClick,
  onAttachmentPreview,
  onEscalate,
  showCitationSources = false,
  assistantName,
  assistantAvatar,
  userDisplayName,
  userAvatarColor = '#0f172a',
}: ChatMessageBubbleProps) {
  const { t } = useTranslation()
  const isAssistant = message.role === 'assistant'
  const roleLabel = isAssistant ? assistantName ?? t('assistant.name') : userDisplayName || t('chat.you')
  const fallbackInitial = t('chat.initial_fallback')
  const reviewSuggested = Boolean(message.diagnostics?.review_suggested)
  const reviewReason = message.diagnostics?.review_reason ?? undefined
  const showReviewAction = Boolean(onEscalate && isAssistant && (reviewSuggested || message.lowConfidence))
  const languageBadge = (() => {
    const raw = (message.language ?? '').toString().toLowerCase()
    if (raw === 'en') return 'EN'
    if (raw === 'zh') return 'ZH'
    return null
  })()
  return (
    <div className={`group flex gap-3 ${isAssistant ? 'justify-start' : 'justify-end'}`}>
      <div className="hidden h-11 w-11 flex-shrink-0 items-center justify-center rounded-full lg:flex" aria-hidden="true">
        {isAssistant ? (
          <AssistantAvatar size={44} avatar={assistantAvatar} />
        ) : (
          <div
            className="flex h-full w-full items-center justify-center rounded-full text-sm font-semibold text-white"
            style={{ backgroundColor: userAvatarColor }}
          >
            {getInitial(userDisplayName, fallbackInitial)}
          </div>
        )}
      </div>
      <div
        className={`chat-fade-in relative max-w-[760px] rounded-3xl border border-slate-200 bg-white px-5 py-4 text-sm leading-relaxed text-slate-900 shadow-sm transition ${
          isAssistant ? 'self-start' : 'self-end'
        }`}
      >
        <div className="flex items-center justify-between text-[11px] uppercase tracking-[0.4em] text-slate-400">
          <span>{roleLabel}</span>
          <span className="flex items-center gap-2">
            {languageBadge ? (
              <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-1 text-[10px] font-semibold tracking-[0.25em] text-slate-500">
                {languageBadge}
              </span>
            ) : null}
            <span>{new Date(message.createdAt).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}</span>
          </span>
        </div>
        <div className="mt-4 flex items-center justify-end gap-2 text-slate-400 opacity-0 pointer-events-none transition-opacity group-hover:opacity-100 group-hover:pointer-events-auto">
          <button
            type="button"
            aria-label={t('chat.actions.copy_aria')}
            className="rounded-full border border-transparent p-1 hover:border-slate-300 hover:text-slate-900"
            onClick={() => onCopy?.(message.content)}
          >
            <CopyIcon />
          </button>
          {isAssistant && onRetry ? (
            <button
              type="button"
              aria-label={t('chat.actions.retry_aria')}
              className="rounded-full border border-transparent p-1 hover:border-slate-300 hover:text-slate-900"
              onClick={() => onRetry(message)}
            >
              <RetryIcon />
            </button>
          ) : null}
          {showReviewAction ? (
            <button
              type="button"
              className="rounded-full border border-transparent px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.25em] text-slate-500 hover:border-slate-300 hover:text-slate-900"
              onClick={() => onEscalate?.(message)}
            >
              {t('chat.request_review')}
            </button>
          ) : null}
        </div>
        <p
          className="mt-2 whitespace-pre-line text-base leading-7 text-inherit"
          aria-live={isAssistant && message.streaming ? 'polite' : undefined}
          aria-busy={isAssistant && message.streaming ? true : undefined}
        >
          {message.content}
        </p>
        {message.lowConfidence ? (
          <p className="mt-3 rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] font-medium text-amber-800">
            {t('chat.low_confidence')}
          </p>
        ) : null}
        {reviewSuggested ? (
          <p className="mt-3 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-[11px] font-medium text-slate-700">
            {reviewReason === 'conflict'
              ? t('chat.review_reason.conflict')
              : reviewReason === 'discretionary'
                ? t('chat.review_reason.discretionary')
                : t('chat.review_suggested')}
          </p>
        ) : null}

        {message.citations && message.citations.length > 0 ? (
          <div className="mt-4 space-y-2 text-xs text-slate-600">
            <p className="font-semibold uppercase tracking-[0.4em] text-slate-400">{t('chat.citations')}</p>
            <div className="flex flex-wrap gap-2">
              {message.citations.map((citation) => {
                const score = Number.isFinite(citation.score) ? citation.score.toFixed(2) : null
                return (
                  <button
                    key={citation.chunk_id}
                    type="button"
                    className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-700 hover:border-slate-400"
                    onClick={() => onCitationClick?.(citation, message)}
                    aria-label={t('chat.open_citation_aria', { name: citation.source_name ?? citation.doc_id })}
                  >
                    <span className="max-w-[140px] truncate">{citation.source_name ?? citation.doc_id}</span>
                    {score ? <span className="text-[10px] font-semibold text-slate-500">{score}</span> : null}
                  </button>
                )
              })}
            </div>
            <ul className="mt-3 space-y-2">
              {message.citations.slice(0, 2).map((citation) => (
                <li key={`${citation.chunk_id}-preview`} className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2">
                  <div className="flex items-center justify-between text-[11px] uppercase tracking-[0.4em] text-slate-500">
                    <span>{citation.source_name ?? citation.doc_id}</span>
                    <span>{citation.score.toFixed(2)}</span>
                  </div>
                  <p className="mt-1 text-xs text-slate-600">{citation.snippet}</p>
                  {citation.last_verified_at ? (
                    <p className="mt-1 text-[11px] text-slate-500">
                      {t('chat.last_verified', { date: new Date(citation.last_verified_at).toLocaleDateString() })}
                    </p>
                  ) : null}
                  {showCitationSources && citation.url && (
                    <a
                      className="mt-2 inline-flex text-[11px] font-medium text-slate-900 underline"
                      href={resolveApiUrl(citation.url)}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {t('chat.attachment.view_source')}
                    </a>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {message.attachments && message.attachments.length > 0 ? (
          <div className="mt-3 space-y-2 text-xs text-slate-600">
            <p className="font-semibold uppercase tracking-[0.4em] text-slate-400">{t('chat.attachments')}</p>
            <ul className="space-y-2">
              {message.attachments.map((attachment) => {
                const downloadUrl = resolveApiUrl(attachment.downloadUrl)
                return (
                  <li
                    key={attachment.clientId}
                    className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white px-3 py-2"
                  >
                    <div>
                      <p className="font-medium text-slate-900">{attachment.filename}</p>
                      <p className="text-[11px] text-slate-500">
                        {Math.round(attachment.sizeBytes / 1024)} KB · {attachment.mimeType}
                      </p>
                    </div>
                    {downloadUrl || attachment.uploadId ? (
                      <div className="flex items-center gap-3 text-[11px] font-semibold text-slate-900">
                        {attachment.uploadId ? (
                          <button
                            type="button"
                            className="underline"
                            onClick={() => onAttachmentPreview?.(attachment, message)}
                          >
                            {t('chat.attachment.preview')}
                          </button>
                        ) : null}
                        {downloadUrl ? (
                          <a
                            className="underline"
                            href={downloadUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            {t('chat.attachment.view')}
                          </a>
                        ) : null}
                      </div>
                    ) : null}
                  </li>
                )
              })}
            </ul>
          </div>
        ) : null}

        {message.diagnostics ? (
          <div className="mt-3 flex flex-wrap gap-3 text-[11px] text-slate-500">
            {message.diagnostics.end_to_end_ms !== undefined ? (
              <span>{t('chat.diagnostics.end_to_end', { ms: Math.round(message.diagnostics.end_to_end_ms) })}</span>
            ) : null}
            {message.diagnostics.citation_coverage !== undefined ? (
              <span>{t('chat.diagnostics.citation_coverage', { pct: Math.round(message.diagnostics.citation_coverage * 100) })}</span>
            ) : null}
          </div>
        ) : null}

      </div>
    </div>
  )
}
