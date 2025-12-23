import { AssistantAvatar } from './AssistantAvatar'
import type { ChatMessageModel } from './types'

interface ChatMessageBubbleProps {
  message: ChatMessageModel
  onCopy?: (content: string) => void
  onRetry?: (message: ChatMessageModel) => void
  assistantName?: string
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

const getInitial = (value?: string) => {
  if (!value) return 'Y'
  const trimmed = value.trim()
  return trimmed ? trimmed[0]?.toUpperCase() ?? 'Y' : 'Y'
}

export function ChatMessageBubble({
  message,
  onCopy,
  onRetry,
  assistantName = 'Assistant',
  userDisplayName,
  userAvatarColor = '#0f172a',
}: ChatMessageBubbleProps) {
  const isAssistant = message.role === 'assistant'
  const roleLabel = isAssistant ? assistantName : userDisplayName || 'You'
  return (
    <div className={`group flex gap-3 ${isAssistant ? 'justify-start' : 'justify-end'}`}>
      <div className="hidden h-9 w-9 flex-shrink-0 items-center justify-center rounded-full lg:flex" aria-hidden="true">
        {isAssistant ? (
          <AssistantAvatar size={36} />
        ) : (
          <div
            className="flex h-full w-full items-center justify-center rounded-full text-xs font-semibold text-white"
            style={{ backgroundColor: userAvatarColor }}
          >
            {getInitial(userDisplayName)}
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
          <span>{new Date(message.createdAt).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}</span>
        </div>
        <p className="mt-3 whitespace-pre-line text-base leading-7 text-inherit">{message.content}</p>
        {message.lowConfidence ? (
          <p className="mt-3 rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] font-medium text-amber-800">
            Low confidence · consider verifying with additional details.
          </p>
        ) : null}

        {message.citations && message.citations.length > 0 ? (
          <div className="mt-4 space-y-2 text-xs text-slate-600">
            <p className="font-semibold uppercase tracking-[0.4em] text-slate-400">Citations</p>
            <ul className="space-y-2">
              {message.citations.map((citation) => (
                <li key={citation.chunk_id} className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2">
                  <div className="flex items-center justify-between text-[11px] uppercase tracking-[0.4em] text-slate-500">
                    <span>{citation.source_name ?? citation.doc_id}</span>
                    <span>{citation.score.toFixed(2)}</span>
                  </div>
                  <p className="mt-1 text-xs text-slate-600">{citation.snippet}</p>
                  {citation.url && (
                    <a
                      className="mt-2 inline-flex text-[11px] font-medium text-slate-900 underline"
                      href={citation.url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      View source
                    </a>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {message.attachments && message.attachments.length > 0 ? (
          <div className="mt-3 space-y-2 text-xs text-slate-600">
            <p className="font-semibold uppercase tracking-[0.4em] text-slate-400">Attachments</p>
            <ul className="space-y-2">
              {message.attachments.map((attachment) => (
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
                  {attachment.downloadUrl ? (
                    <a
                      className="text-[11px] font-semibold text-slate-900 underline"
                      href={attachment.downloadUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      View
                    </a>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {message.diagnostics ? (
          <div className="mt-3 flex flex-wrap gap-3 text-[11px] text-slate-500">
            {message.diagnostics.end_to_end_ms !== undefined ? (
              <span>End-to-end {Math.round(message.diagnostics.end_to_end_ms)} ms</span>
            ) : null}
            {message.diagnostics.citation_coverage !== undefined ? (
              <span>Citation coverage {Math.round(message.diagnostics.citation_coverage * 100)}%</span>
            ) : null}
          </div>
        ) : null}

        <div className="absolute right-4 top-4 hidden gap-2 text-slate-400 group-hover:flex">
          <button
            type="button"
            aria-label="Copy message"
            className="rounded-full border border-transparent p-1 hover:border-slate-300 hover:text-slate-900"
            onClick={() => onCopy?.(message.content)}
          >
            <CopyIcon />
          </button>
          {isAssistant && onRetry ? (
            <button
              type="button"
              aria-label="Retry message"
              className="rounded-full border border-transparent p-1 hover:border-slate-300 hover:text-slate-900"
              onClick={() => onRetry(message)}
            >
              <RetryIcon />
            </button>
          ) : null}
        </div>
      </div>
    </div>
  )
}
