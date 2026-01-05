import type { TFunction } from 'i18next'

export interface AssistantProfileHighlight {
  title: string
  description: string
  prompt: string
}

export interface AssistantProfileConfig {
  name: string
  title: string
  tagline: string
  avatar: {
    accent: string
    base: string
    ring: string
    face: string
    image_url?: string | null
  }
  highlights: AssistantProfileHighlight[]
}

export const ASSISTANT_AVATAR = {
  accent: '#2563eb',
  base: '#e0f2ff',
  ring: '#bfdbfe',
  face: '#0f172a',
  image_url: null,
} as const

export interface AssistantProfileOverrides {
  name?: string | null
  avatar?: Partial<AssistantProfileConfig['avatar']> | null
}

export const getAssistantProfile = (t: TFunction): AssistantProfileConfig => {
  return {
    name: String(t('assistant.name')),
    title: String(t('assistant.title')),
    tagline: String(t('assistant.tagline')),
    avatar: ASSISTANT_AVATAR,
    highlights: (t('assistant.highlights', { returnObjects: true }) ?? []) as AssistantProfileHighlight[],
  }
}

export const mergeAssistantProfile = (
  base: AssistantProfileConfig,
  overrides?: AssistantProfileOverrides | null,
): AssistantProfileConfig => {
  if (!overrides) return base
  const name = overrides.name?.trim()
  const avatarOverrides = overrides.avatar ?? {}
  const avatar = {
    ...base.avatar,
    ...Object.fromEntries(
      Object.entries(avatarOverrides).filter(([, value]) => typeof value === 'string' && value.trim().length > 0),
    ),
  }
  return {
    ...base,
    name: name && name.length > 0 ? name : base.name,
    avatar,
  }
}

export const getAssistantGreeting = (t: TFunction, referenceDate = new Date()): string => {
  const hour = referenceDate.getHours()
  if (hour >= 5 && hour < 11) return String(t('assistant.greeting.morning'))
  if (hour >= 11 && hour < 17) return String(t('assistant.greeting.afternoon'))
  if (hour >= 17 && hour < 22) return String(t('assistant.greeting.evening'))
  return String(t('assistant.greeting.default'))
}

export const getAssistantOpeningStatement = (t: TFunction, referenceDate = new Date()): string => {
  const statements = (t('assistant.opening_statements', { returnObjects: true }) ?? []) as string[]
  if (!statements.length) return ''
  const index = referenceDate.getDate() % statements.length
  return String(statements[index] ?? '')
}
