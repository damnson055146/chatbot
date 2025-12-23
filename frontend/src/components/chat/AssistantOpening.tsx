import { AssistantAvatar } from './AssistantAvatar'
import { ASSISTANT_PROFILE, getAssistantGreeting, getAssistantOpeningStatement } from '../../utils/assistantProfile'

interface AssistantOpeningProps {
  displayName?: string
  suggestions: string[]
  onSuggestionClick: (prompt: string) => void
}

export function AssistantOpening({ displayName, suggestions, onSuggestionClick }: AssistantOpeningProps) {
  const greeting = getAssistantGreeting()
  const openingStatement = getAssistantOpeningStatement()
  const friendlyName = displayName?.trim() || 'there'

  return (
    <section className="rounded-[32px] border border-slate-200 bg-white/90 px-6 py-6 shadow-sm backdrop-blur">
      <div className="flex flex-col gap-6 md:flex-row md:items-center">
        <div className="flex flex-1 items-start gap-4">
          <AssistantAvatar size={72} showHalo className="shrink-0" />
          <div>
            <p className="text-xs uppercase tracking-[0.4em] text-slate-400">{ASSISTANT_PROFILE.title}</p>
            <h2 className="mt-1 text-xl font-semibold text-slate-900">
              {greeting}, {friendlyName}. I'm {ASSISTANT_PROFILE.name}.
            </h2>
            <p className="mt-2 text-sm text-slate-600">{openingStatement}</p>
            <p className="mt-3 text-sm text-slate-600">{ASSISTANT_PROFILE.tagline}</p>
          </div>
        </div>
        <div className="rounded-3xl border border-dashed border-slate-200 bg-slate-50/80 px-5 py-4 text-sm text-slate-600 md:w-72">
          <p className="text-xs font-semibold uppercase tracking-[0.35em] text-slate-400">How I can help now</p>
          <ul className="mt-3 space-y-3">
            {ASSISTANT_PROFILE.highlights.map((highlight) => (
              <li key={highlight.title}>
                <button
                  type="button"
                  className="w-full rounded-2xl border border-transparent px-3 py-2 text-left transition hover:border-slate-200 hover:bg-white"
                  onClick={() => onSuggestionClick(highlight.prompt)}
                >
                  <p className="text-sm font-semibold text-slate-900">{highlight.title}</p>
                  <p className="text-xs text-slate-500">{highlight.description}</p>
                  <span className="mt-1 inline-flex text-[11px] font-semibold uppercase tracking-[0.3em] text-slate-600">
                    Use this prompt
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
      <div className="mt-5 flex flex-wrap gap-2">
        {suggestions.map((suggestion) => (
          <button
            type="button"
            key={suggestion}
            className="rounded-full border border-slate-200 bg-white/70 px-4 py-2 text-sm text-slate-600 transition hover:border-slate-400"
            onClick={() => onSuggestionClick(suggestion)}
          >
            {suggestion}
          </button>
        ))}
      </div>
    </section>
  )
}

export default AssistantOpening
