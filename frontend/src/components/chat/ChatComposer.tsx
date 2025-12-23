import { useCallback, useEffect, useRef } from 'react'

interface ChatComposerProps {
  value: string
  placeholder?: string
  disabled?: boolean
  uploadDisabled?: boolean
  onChange: (value: string) => void
  onSubmit: () => void
  onUploadClick?: () => void
  containerClassName?: string
}

export function ChatComposer({
  value,
  placeholder = 'Message the Study Abroad assistant…',
  disabled,
  uploadDisabled,
  onChange,
  onSubmit,
  onUploadClick,
  containerClassName,
}: ChatComposerProps) {
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
    if (disabled) return
    onSubmit()
  }

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      if (!disabled) {
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
            aria-label="Upload files"
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
            aria-label="Message composer"
            placeholder={placeholder}
            className="flex-1 resize-none bg-transparent text-base leading-relaxed text-slate-900 placeholder:text-slate-400 focus:outline-none"
            value={value}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={handleKeyDown}
            style={{ maxHeight: 136 }}
          />
          <button
            type="submit"
            aria-label="Send message"
            className="h-10 w-10 rounded-full bg-slate-900 text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={disabled}
          >
            <svg viewBox="0 0 20 20" className="mx-auto h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="m3 10 14-7-4 7 4 7z" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>
        <p className="mt-2 text-center text-xs text-slate-400">Enter to send · Shift+Enter for new line</p>
      </div>
    </form>
  )
}

export default ChatComposer
