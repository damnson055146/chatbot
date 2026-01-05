import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { i18next } from '../../utils/i18n'
import { useUserPreferences } from '../../hooks/useUserPreferences'
import { type SupportedLanguage } from '../../services/userPreferences'

const LANGUAGE_OPTIONS: Array<{ value: SupportedLanguage; labelKey: string }> = [
  { value: 'auto', labelKey: 'settings.language.auto' },
  { value: 'en', labelKey: 'settings.language.en' },
  { value: 'zh', labelKey: 'settings.language.zh' },
]

const resolveUiLanguage = (language: SupportedLanguage): 'en' | 'zh' => {
  if (language === 'auto') {
    const browser = (typeof navigator !== 'undefined' ? navigator.language : 'en').slice(0, 2).toLowerCase()
    return browser === 'zh' ? 'zh' : 'en'
  }
  return language === 'zh' ? 'zh' : 'en'
}

export function LanguageSwitcher() {
  const { t } = useTranslation()
  const { preferences, updatePreferences } = useUserPreferences()
  const [open, setOpen] = useState(false)
  const wrapperRef = useRef<HTMLDivElement | null>(null)

  const selected = (preferences.preferredLanguage ?? 'auto') as SupportedLanguage
  const selectedLabel = useMemo(() => {
    const option = LANGUAGE_OPTIONS.find((item) => item.value === selected)
    return option ? t(option.labelKey) : t('settings.language.auto')
  }, [selected, t])

  const handleSelect = (next: SupportedLanguage) => {
    setOpen(false)
    if (next === selected) return
    updatePreferences({ preferredLanguage: next })
    void i18next.changeLanguage(resolveUiLanguage(next))
  }

  useEffect(() => {
    if (!open) return
    const handleClick = (event: MouseEvent | TouchEvent) => {
      if (!wrapperRef.current) return
      if (wrapperRef.current.contains(event.target as Node)) return
      setOpen(false)
    }
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false)
      }
    }
    window.addEventListener('mousedown', handleClick)
    window.addEventListener('touchstart', handleClick)
    window.addEventListener('keydown', handleKey)
    return () => {
      window.removeEventListener('mousedown', handleClick)
      window.removeEventListener('touchstart', handleClick)
      window.removeEventListener('keydown', handleKey)
    }
  }, [open])

  return (
    <div ref={wrapperRef} className="relative">
      <button
        type="button"
        className="flex items-center gap-2 rounded-full border border-slate-200 bg-white/90 px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm backdrop-blur transition hover:border-slate-300 focus:outline-none focus:ring-2 focus:ring-slate-200"
        onClick={() => setOpen((prev) => !prev)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={t('settings.preferred_language')}
      >
        <svg
          aria-hidden="true"
          className="h-4 w-4 text-slate-500"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <circle cx="12" cy="12" r="9" />
          <path d="M3 12h18" />
          <path d="M12 3c2.5 2.6 4 5.5 4 9s-1.5 6.4-4 9c-2.5-2.6-4-5.5-4-9s1.5-6.4 4-9z" />
        </svg>
        <span className="max-w-[110px] truncate">{selectedLabel}</span>
        <svg
          aria-hidden="true"
          className={`h-3.5 w-3.5 text-slate-400 transition ${open ? 'rotate-180' : ''}`}
          viewBox="0 0 20 20"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="m6 8 4 4 4-4" />
        </svg>
      </button>

      {open ? (
        <div
          role="listbox"
          aria-label={t('settings.preferred_language')}
          className="absolute right-0 z-50 mt-2 w-44 rounded-2xl border border-slate-200 bg-white p-1 shadow-lg"
        >
          {LANGUAGE_OPTIONS.map((option) => {
            const isActive = option.value === selected
            return (
              <button
                key={option.value}
                type="button"
                role="option"
                aria-selected={isActive}
                className={`flex w-full items-center justify-between rounded-xl px-3 py-2 text-xs font-semibold transition ${
                  isActive ? 'bg-slate-100 text-slate-900' : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                }`}
                onClick={() => handleSelect(option.value)}
              >
                <span className="truncate">{t(option.labelKey)}</span>
                {isActive ? (
                  <svg
                    aria-hidden="true"
                    className="h-4 w-4 text-slate-500"
                    viewBox="0 0 20 20"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="m4 10 4 4 8-8" />
                  </svg>
                ) : null}
              </button>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}
