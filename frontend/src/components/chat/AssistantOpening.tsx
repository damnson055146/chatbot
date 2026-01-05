import { AssistantAvatar } from './AssistantAvatar'
import { useTranslation } from 'react-i18next'
import { getAssistantGreeting, getAssistantOpeningStatement, type AssistantProfileConfig } from '../../utils/assistantProfile'

interface AssistantOpeningProps {
  assistant: AssistantProfileConfig
  displayName?: string
  suggestions: string[]
  onSuggestionClick: (prompt: string) => void
  openingStatement?: string | null
}

export function AssistantOpening({
  assistant,
  displayName,
  suggestions,
  onSuggestionClick,
  openingStatement,
}: AssistantOpeningProps) {
  const { t } = useTranslation()
  const greeting = getAssistantGreeting(t)
  const resolvedOpening = openingStatement?.trim() || getAssistantOpeningStatement(t)
  const friendlyName = displayName?.trim() || t('assistant.friendly_name_fallback')

  return (
    <section className="rounded-[32px] border border-slate-200 bg-white/90 px-6 py-6 shadow-sm backdrop-blur">
      <div className="flex flex-col gap-6 md:flex-row md:items-center">
        <div className="flex flex-1 items-start gap-4">
          <AssistantAvatar size={72} showHalo className="shrink-0" avatar={assistant.avatar} />
          <div>
            <p className="text-xs uppercase tracking-[0.4em] text-slate-400">{assistant.title}</p>
            <h2 className="mt-1 text-xl font-semibold text-slate-900">
              {t('assistant.intro_line', { greeting, name: friendlyName, assistantName: assistant.name })}
            </h2>
            {resolvedOpening ? <p className="mt-2 text-sm text-slate-600">{resolvedOpening}</p> : null}
            <p className="mt-3 text-sm text-slate-600">{assistant.tagline}</p>
          </div>
        </div>
        <div className="rounded-3xl border border-dashed border-slate-200 bg-slate-50/80 px-5 py-4 text-sm text-slate-600 md:w-72">
          <p className="text-xs font-semibold uppercase tracking-[0.35em] text-slate-400">{t('assistant.help_now')}</p>
          <ul className="mt-3 space-y-3">
            {assistant.highlights.map((highlight) => (
              <li key={highlight.title}>
                <button
                  type="button"
                  className="w-full rounded-2xl border border-transparent px-3 py-2 text-left transition hover:border-slate-200 hover:bg-white"
                  onClick={() => onSuggestionClick(highlight.prompt)}
                >
                  <p className="text-sm font-semibold text-slate-900">{highlight.title}</p>
                  <p className="text-xs text-slate-500">{highlight.description}</p>
                  <span className="mt-1 inline-flex text-[11px] font-semibold uppercase tracking-[0.3em] text-slate-600">
                    {t('assistant.use_prompt')}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
      {suggestions.length > 0 ? (
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
      ) : null}
    </section>
  )
}

export default AssistantOpening
