export function TypingIndicator() {
  return (
    <div className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-3 py-2 text-xs text-slate-500 shadow-sm">
      <span className="typing-dot" />
      <span className="typing-dot" style={{ animationDelay: '120ms' }} />
      <span className="typing-dot" style={{ animationDelay: '240ms' }} />
    </div>
  )
}
