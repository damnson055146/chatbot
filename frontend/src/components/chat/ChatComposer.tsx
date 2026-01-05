import { useCallback, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'

interface ChatComposerProps {
  value: string
  placeholder?: string
  disabled?: boolean
  isStreaming?: boolean
  uploadDisabled?: boolean
  onChange: (value: string) => void
  onSubmit: () => void
  onUploadClick?: () => void
  onStop?: () => void
  containerClassName?: string
}

export function ChatComposer({
  value,
  placeholder,
  disabled,
  isStreaming,
  uploadDisabled,
  onChange,
  onSubmit,
  onUploadClick,
  onStop,
  containerClassName,
}: ChatComposerProps) {
  const { t } = useTranslation()
  const resolvedPlaceholder = placeholder ?? t('query.placeholder')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const resizeTextarea = useCallback(() => {
    const textarea = textareaRef.current
    if (!textarea) return
    textarea.style.height = 'auto'
    const maxHeight = 136
    textarea.style.height = `${Math.min(textarea.scrollHeight, maxHeight)}px`
  }, [])

  useEffect(() => {
    resizeTextarea()
  }, [value, resizeTextarea])

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (disabled || isStreaming) return
    onSubmit()
  }

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      event.preventDefault()
      if (!disabled && !isStreaming) onSubmit()
      return
    }
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      if (!disabled && !isStreaming) {
        onSubmit()
      }
    }
  }

  return (
    <form onSubmit={handleSubmit} className="sticky bottom-0 z-20 border-t border-slate-200 bg-[#F7F7F8]">
      <div className={containerClassName ?? 'mx-auto w-full max-w-3xl px-4 py-4'}>
        <div className="flex items-end gap-3 rounded-[28px] border border-slate-200 bg-white px-4 py-3 shadow-sm focus-within:border-slate-400">
          <button
            type="button"
            aria-label={t('chat.composer.upload_aria')}
            className="h-10 w-10 rounded-full text-slate-500 transition hover:bg-slate-100"
            onClick={onUploadClick}
            disabled={uploadDisabled}
          >
            <svg viewBox="0 0 24 24" className="mx-auto h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.6">
              <path
                d="M17 13v6a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-6"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <path
                d="M12 17V3m0 0-4 4m4-4 4 4"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
          <textarea
            ref={textareaRef}
            rows={1}
            maxLength={2000}
            aria-label={t('chat.composer.aria')}
            placeholder={resolvedPlaceholder}
            className="flex-1 resize-none bg-transparent text-base leading-relaxed text-slate-900 placeholder:text-slate-400 focus:outline-none"
            value={value}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={handleKeyDown}
            style={{ maxHeight: 136 }}
          />
          {isStreaming ? (
            <button
              type="button"
              aria-label={t('chat.stop_generating')}
              className="h-10 w-10 rounded-full border border-slate-300 text-slate-700 transition hover:border-slate-400"
              onClick={onStop}
            >
              <span className="mx-auto block h-3 w-3 rounded-sm bg-slate-700" />
            </button>
          ) : (
            <button
              type="submit"
              aria-label={t('chat.composer.send_aria')}
              className="h-10 w-10 rounded-full bg-slate-900 text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={disabled}
            >
              <svg viewBox="0 0 20 20" className="mx-auto h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="m3 10 14-7-4 7 4 7z" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          )}
        </div>
        <p className="mt-2 text-center text-xs text-slate-400">{t('chat.composer.shortcuts')}</p>
      </div>
    </form>
  )
}

export default ChatComposer
